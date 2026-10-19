"""索引清单一致性检查 runner（SU-12）。

用法：

    python -m scripts.check_index_manifest \
      --manifest data/index/recipes_manifest.json \
      --collection cook_hero_recipes \
      --embedding-model BAAI/bge-small-zh-v1.5 \
      --corpus-version howtocook-v1 \
      --dimension 512
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

from app.rag.vector_stores.index_manifest import check_manifest, load_manifest


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="CookHero 索引清单一致性检查")
    parser.add_argument("--manifest", required=True, help="索引清单 JSON 路径")
    parser.add_argument("--collection", required=True, help="期望的 Milvus 集合名")
    parser.add_argument("--embedding-model", required=True, help="期望的 embedding 模型")
    parser.add_argument("--corpus-version", required=True, help="期望的语料版本")
    parser.add_argument("--dimension", required=True, type=int, help="期望的向量维度")
    args = parser.parse_args(argv)

    path = Path(args.manifest)
    manifest = load_manifest(path)
    issues = check_manifest(
        manifest,
        collection=args.collection,
        embedding_model=args.embedding_model,
        corpus_version=args.corpus_version,
        dimension=args.dimension,
    )

    result = {
        "manifest": str(path),
        "ok": not issues,
        "issues": issues,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
