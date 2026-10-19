"""Recipe image extraction and Markdown image resolution.

HowToCook keeps photos next to each recipe (``./成品.jpg``) while imported
recipes use absolute ``/media/...`` or remote URLs.  This module turns both
shapes into URLs the browser can load, and picks a sensible cover image.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import quote, unquote

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}

# ![alt](src) / ![alt](<src with spaces>) / ![alt](src "title")
MARKDOWN_IMAGE_RE = re.compile(
    r"!\[(?P<alt>[^\]]*)\]\(\s*(?P<src><[^>]+>|[^\s)]+)(?:\s+[\"'][^\"']*[\"'])?\s*\)"
)

# Prefer dish photos over process shots when choosing a cover.
_COVER_KEYWORDS = (
    "成品",
    "封面",
    "主图",
    "预览",
    "完成",
    "成品图",
    "cover",
    "hero",
    "final",
    "result",
)


@dataclass(frozen=True)
class RecipeImage:
    """A resolved recipe image."""

    url: str
    alt: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"url": self.url, "alt": self.alt}


def _default_image_root() -> Path:
    """Resolve the corpus root lazily so the parser stays import-light."""
    try:
        from app.config import settings

        return Path(settings.rag.paths.base_data_path)
    except Exception:  # pragma: no cover - configuration is optional for parsing
        return Path("data/HowToCook")


def resolve_image_url(
    src: str,
    source: str = "",
    *,
    image_root: str | Path | None = None,
) -> Optional[str]:
    """Resolve one Markdown image source to a browser-safe URL.

    - absolute http(s) URLs are returned as-is
    - already-resolved ``/media/...`` URLs are returned as-is
    - local paths are resolved relative to the document and must stay inside
      the corpus root; anything outside is rejected (path traversal guard)
    """
    raw = html.unescape(unquote((src or "").strip().strip("<>")))
    if not raw or raw.startswith(("data:", "javascript:", "blob:")):
        return None

    if raw.startswith(("http://", "https://")):
        return raw
    if raw.startswith("/media/"):
        return raw
    if raw.startswith("//"):
        return f"https:{raw}"

    # Personal / imported documents have no local image directory.
    if not source or source.startswith(("personal::", "import::")):
        return None

    source_path = Path(source)
    if not source_path.suffix or not source_path.exists():
        return None

    root = Path(image_root) if image_root is not None else _default_image_root()
    try:
        root = root.resolve()
        candidate = (source_path.parent / raw).resolve()
    except OSError:
        return None

    if (
        not candidate.is_file()
        or not candidate.is_relative_to(root)
        or candidate.suffix.lower() not in IMAGE_SUFFIXES
    ):
        return None

    relative = candidate.relative_to(root).as_posix()
    return f"/media/recipes/{quote(relative, safe='/')}"


def extract_image_refs(content: str) -> list[tuple[str, str]]:
    """Return ``(src, alt)`` for every Markdown image in order."""
    if not content:
        return []
    return [
        (match.group("src"), (match.group("alt") or "").strip())
        for match in MARKDOWN_IMAGE_RE.finditer(content)
    ]


def collect_recipe_images(
    content: str,
    source: str = "",
    *,
    image_root: str | Path | None = None,
    limit: int = 8,
) -> tuple[list[RecipeImage], Optional[str]]:
    """Collect unique resolved images and choose a cover image.

    Cover preference: alt/filename signals such as 成品/封面/预览, otherwise
    the last image in the document (HowToCook usually puts the finished dish
    photo at the end).
    """
    images: list[RecipeImage] = []
    seen: set[str] = set()
    for src, alt in extract_image_refs(content):
        url = resolve_image_url(src, source, image_root=image_root)
        if not url or url in seen:
            continue
        seen.add(url)
        images.append(RecipeImage(url=url, alt=alt))

    if not images:
        override = override_image_for(source, image_root=image_root)
        if override:
            return [override], override.url
        return [], None

    def score(image: RecipeImage) -> int:
        haystack = f"{image.alt} {image.url}".casefold()
        return sum(10 for keyword in _COVER_KEYWORDS if keyword in haystack)

    # max() keeps the first maximum; use the index as a tiebreaker so later
    # images (often the plated dish) win when no keyword matches.
    best_index = 0
    best_score = -1
    for index, image in enumerate(images):
        value = score(image)
        if value >= best_score:
            best_score = value
            best_index = index

    return images[: max(1, limit)], images[best_index].url


def strip_markdown_images(text: str) -> str:
    """Remove image markup from a line while keeping the surrounding text."""
    if not text:
        return ""
    return MARKDOWN_IMAGE_RE.sub("", text)


def first_image_in_line(
    line: str,
    source: str = "",
    *,
    image_root: str | Path | None = None,
) -> Optional[str]:
    """Resolve the first image in a Markdown line, if any."""
    match = MARKDOWN_IMAGE_RE.search(line or "")
    if not match:
        return None
    return resolve_image_url(match.group("src"), source, image_root=image_root)


def iter_resolved_images(
    content: str,
    source: str = "",
    *,
    image_root: str | Path | None = None,
) -> Iterable[RecipeImage]:
    """Yield resolved images without de-duplicating (internal helper)."""
    for src, alt in extract_image_refs(content):
        url = resolve_image_url(src, source, image_root=image_root)
        if url:
            yield RecipeImage(url=url, alt=alt)


# ---------------------------------------------------------------------------
# Fetched-image overrides
# ---------------------------------------------------------------------------
# Some corpus recipes do not ship a photo.  ``scripts/fetch_recipe_images.py``
# stores fetched photos in ``data/recipe_images`` and records them in a
# manifest keyed by the recipe's path relative to the corpus root.  Keeping
# this outside the Markdown files makes the enrichment reversible and survives
# a corpus sync.


def _manifest_path(image_root: str | Path | None = None) -> Path:
    root = Path(image_root) if image_root is not None else _default_image_root()
    return root.parent / "recipe_images" / "manifest.json"


@lru_cache(maxsize=16)
def _load_manifest(path_str: str, mtime_ns: int) -> dict:
    try:
        payload = json.loads(Path(path_str).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def image_override_version(image_root: str | Path | None = None) -> str:
    """Return a cache-busting version for fetched-image overrides."""
    manifest_path = _manifest_path(image_root)
    try:
        return str(manifest_path.stat().st_mtime_ns)
    except OSError:
        return "0"


def override_image_for(
    source: str,
    *,
    image_root: str | Path | None = None,
) -> Optional[RecipeImage]:
    """Return the fetched cover image for a corpus recipe, if one exists."""
    if not source or source.startswith(("personal::", "import::")):
        return None
    source_path = Path(source)
    if not source_path.suffix:
        return None

    root = Path(image_root) if image_root is not None else _default_image_root()
    manifest_path = _manifest_path(image_root)
    if not manifest_path.is_file():
        return None

    try:
        relative = source_path.resolve().relative_to(root.resolve()).as_posix()
        mtime_ns = manifest_path.stat().st_mtime_ns
    except (OSError, ValueError):
        return None

    manifest = _load_manifest(str(manifest_path), mtime_ns)
    entry = (manifest.get("images") or {}).get(relative)
    if not isinstance(entry, dict):
        return None

    filename = str(entry.get("file") or "").strip()
    if (
        not filename
        or "/" in filename
        or "\\" in filename
        or filename.startswith(".")
        or not (manifest_path.parent / filename).is_file()
    ):
        return None

    return RecipeImage(
        url=f"/media/recipe-images/{quote(filename)}",
        alt=str(entry.get("title") or ""),
    )
