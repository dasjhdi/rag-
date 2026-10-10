# scripts/ingest_recipes.py
"""
HowToCook ingestion entry point for CookHero.

Loads the HowToCook markdown corpus, stores the parsed parent documents in
PostgreSQL and indexes the generated chunks into the Milvus "recipes"
collection.

This is the counterpart to scripts/sync_data.py: sync_data.py only clones or
pulls the upstream markdown corpus into data/HowToCook, while this script
performs the actual database and vector store ingestion.

The script is safe to re-run: existing global ("recipes") rows are replaced in
both PostgreSQL and Milvus before the new data is written.

Usage (must be run from the repository root):
    python -m scripts.ingest_recipes                 # ingest the local corpus
    python -m scripts.ingest_recipes --sync          # clone/pull corpus first
    python -m scripts.ingest_recipes --rebuild       # drop + recreate Milvus collection
    python -m scripts.ingest_recipes --dry-run       # parse only, write nothing
    python -m scripts.ingest_recipes --limit 20      # ingest a sample (smoke test)

Tip:
    Set HF_HUB_OFFLINE=1 once the embedding model is cached, otherwise the
    HuggingFace client attempts a network lookup before using the local cache.
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("scripts.ingest_recipes")


def _ensure_repo_root() -> Path:
    """
    config.yml and the data/ paths are resolved relative to the current working
    directory, so make sure the script always runs from the repository root.
    """
    root = Path(__file__).resolve().parents[1]
    if Path.cwd() != root:
        logger.info("Switching working directory to repository root: %s", root)
        os.chdir(root)
    return root


_ensure_repo_root()

# The imports below must happen after the working directory is fixed, because
# app.config reads config.yml at import time.
from app.config import settings  # noqa: E402
from app.database.document_repository import (  # noqa: E402
    DocumentRepository,
    document_repository,
)
from app.database.session import close_db, init_db  # noqa: E402
from app.rag.embeddings.embedding_factory import get_embedding_model  # noqa: E402
from app.rag.vector_stores.vector_store_factory import get_vector_store  # noqa: E402
from scripts.howtocook_loader import HowToCookLoader  # noqa: E402
from scripts.sync_data import sync_repo  # noqa: E402

# Chunk metadata uses this sentinel for public/global documents (see
# HowToCookLoader.ParsedDocument.to_metadata).
GLOBAL_USER_SENTINEL = "GLOBAL"

# data_source value used by the loader for every HowToCook document.
RECIPES_DATA_SOURCE = "recipes"


def _resolve_corpus_paths() -> tuple[Path, Path]:
    """Resolve the dishes and tips directories from config.yml."""
    base = Path(settings.rag.paths.base_data_path)
    howtocook = settings.rag.data_source.howtocook
    return base / howtocook.path_suffix, base / howtocook.tips_path_suffix


def _split_headers() -> list[tuple[str, str]]:
    """Markdown headers to split on, taken from config.yml."""
    return [tuple(pair) for pair in settings.rag.data_source.howtocook.headers_to_split_on]


async def _clear_retrieval_cache() -> None:
    """
    Drop cached retrieval results so freshly ingested content is visible.

    The RAG pipeline caches retrieval results in Redis (L1, exact match) and in a
    Milvus collection (L2, semantic match). Both are invalidated here.
    """
    try:
        from app.services.rag_service import rag_service_instance
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Could not import RAG service to clear caches: %s", exc)
        return

    cache_manager = rag_service_instance.cache_manager
    if not cache_manager:
        logger.info("Caching disabled, nothing to invalidate.")
        return

    keyword_cache = getattr(cache_manager, "keyword_cache", None)
    if keyword_cache is not None:
        try:
            cleared = await keyword_cache.clear("rag:retrieval:*")
            logger.info("Cleared Redis L1 retrieval cache: %s", cleared)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to clear Redis L1 cache: %s", exc)

    vector_cache = getattr(cache_manager, "vector_cache", None)
    if vector_cache is not None:
        try:
            cleared = await vector_cache.clear()
            logger.info("Cleared Milvus L2 retrieval cache: %s", cleared)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to clear Milvus L2 cache: %s", exc)


async def _write_parent_documents(documents: list, batch_size: int) -> int:
    """Insert the parsed parent documents into PostgreSQL. Returns the count."""
    removed = await document_repository.delete_by_data_source(RECIPES_DATA_SOURCE)
    if removed:
        logger.info("Removed %d previously ingested HowToCook documents", removed)

    payloads = [doc.to_dict() for doc in documents]
    written = 0
    for start in range(0, len(payloads), batch_size):
        batch = payloads[start : start + batch_size]
        await document_repository.create_batch(batch)
        written += len(batch)
        logger.info("PostgreSQL: stored %d/%d documents", written, len(payloads))
    return written


async def _index_chunks(chunks: list, *, rebuild: bool, batch_size: int) -> int:
    """Index chunks into the Milvus recipes collection. Returns the count."""
    collection_name = settings.rag.vector_store.collection_names["recipes"]
    embeddings = get_embedding_model(settings.rag)

    # The collection is always created without documents. This matters: when
    # documents that carry an ``id`` are handed to ``from_documents``, the ids are
    # forwarded to Milvus and the collection is created with a VARCHAR primary key
    # instead of an auto-generated INT64 one, after which every ``add_documents``
    # call (which never sends ids) fails with "Insert missed an field `pk`".
    # Passing no documents makes the factory use its placeholder-document path,
    # which produces the auto-id schema the rest of the app expects.
    vector_store = get_vector_store(
        milvus_config=settings.database.milvus,
        collection_name=collection_name,
        embeddings=embeddings,
        chunks=[],
        force_rebuild=rebuild,
    )

    if rebuild:
        logger.info(
            "Milvus: collection '%s' recreated, indexing all chunks", collection_name
        )
    else:
        # Replace any previously ingested global content so re-runs stay idempotent.
        try:
            await asyncio.to_thread(
                vector_store.col.delete,  # type: ignore[union-attr]
                f'user_id == "{GLOBAL_USER_SENTINEL}"',
            )
            logger.info("Removed previously indexed global chunks from '%s'", collection_name)
        except Exception as exc:
            logger.warning("Could not delete existing global chunks: %s", exc)

    indexed = 0
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        await asyncio.to_thread(vector_store.add_documents, batch)
        indexed += len(batch)
        logger.info("Milvus: indexed %d/%d chunks", indexed, len(chunks))

    return indexed


async def _refresh_metadata_cache() -> None:
    """Reload the cached metadata options used for retrieval filters."""
    DocumentRepository._cache_initialized = False
    await DocumentRepository.init_all_metadata_cache()


async def ingest(
    *,
    sync: bool,
    rebuild: bool,
    dry_run: bool,
    batch_size: int,
    limit: int | None,
) -> None:
    if sync:
        logger.info("Syncing the HowToCook corpus...")
        sync_repo()

    dishes_path, tips_path = _resolve_corpus_paths()
    logger.info("Corpus dishes path: %s", dishes_path)
    logger.info("Corpus tips path:   %s", tips_path)

    if not dishes_path.exists():
        raise SystemExit(
            f"Corpus not found at '{dishes_path}'. Run 'python -m scripts.sync_data' "
            f"or pass --sync to clone it first."
        )

    loader = HowToCookLoader(
        data_path=str(dishes_path),
        tips_path=str(tips_path) if tips_path.exists() else None,
        headers_to_split_on=_split_headers(),
    )

    documents = loader.load_documents()
    if limit is not None:
        documents = documents[:limit]
        logger.info("Limiting ingestion to the first %d documents", len(documents))

    chunks = loader.create_chunks(documents)

    logger.info(
        "Parsed %d documents into %d chunks (%d index documents)",
        len(documents),
        len(chunks),
        sum(1 for doc in documents if doc.is_dish_index),
    )

    if dry_run:
        logger.info("--dry-run set: nothing was written to PostgreSQL or Milvus.")
        return

    await init_db()
    try:
        written = await _write_parent_documents(documents, batch_size)
        indexed = await _index_chunks(chunks, rebuild=rebuild, batch_size=batch_size)
        await _refresh_metadata_cache()
        await _clear_retrieval_cache()
        logger.info(
            "Ingestion complete: %d documents in PostgreSQL, %d chunks in Milvus.",
            written,
            indexed,
        )
    finally:
        await close_db()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest the HowToCook corpus into PostgreSQL and Milvus."
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="clone/pull the HowToCook corpus into data/HowToCook before ingesting",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="drop and recreate the Milvus recipes collection instead of updating it",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="parse the corpus and report counts without writing anything",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help="documents/chunks per batch (default: 64)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="only ingest the first N documents (useful for smoke tests)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.batch_size < 1:
        logger.error("--batch-size must be a positive integer")
        return 2
    try:
        asyncio.run(
            ingest(
                sync=args.sync,
                rebuild=args.rebuild,
                dry_run=args.dry_run,
                batch_size=args.batch_size,
                limit=args.limit,
            )
        )
    except SystemExit as exc:
        logger.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())