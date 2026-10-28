"""Public media endpoints for recipe photos and imported images.

Images are intentionally served without JWT so a plain ``<img>`` tag can load
them.  Only image extensions inside the configured roots are exposed; Markdown
files and other corpus files are never reachable through this router.
"""

from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import FileResponse
from PIL import Image, ImageOps

from app.config import settings

router = APIRouter()

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}
_MAX_THUMB_WIDTH = 1600
_THUMB_CACHE = _PROJECT_ROOT / "data" / "media_cache"
_IMPORT_ROOT = _PROJECT_ROOT / "data" / "imports" / "recipes"
_OVERRIDE_ROOT = _PROJECT_ROOT / "data" / "recipe_images"


def _corpus_root() -> Path:
    configured = Path(settings.rag.paths.base_data_path)
    return configured if configured.is_absolute() else _PROJECT_ROOT / configured


def _resolve(root: Path, relative: str) -> Path:
    root = root.resolve()
    relative = unquote(relative or "").lstrip("/")
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root):
        raise HTTPException(status_code=404, detail="图片不存在")
    if ".git" in candidate.parts:
        raise HTTPException(status_code=404, detail="图片不存在")
    if not candidate.is_file() or candidate.suffix.lower() not in _ALLOWED_SUFFIXES:
        raise HTTPException(status_code=404, detail="图片不存在")
    return candidate


def _thumbnail(candidate: Path, width: int) -> Optional[Path]:
    """Return a cached thumbnail, or ``None`` when the original is already small enough."""
    cache_dir = _THUMB_CACHE / "thumbs"
    cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        mtime = candidate.stat().st_mtime_ns
    except OSError:
        raise HTTPException(status_code=404, detail="图片不存在") from None
    key = hashlib.sha1(
        f"{candidate}|{mtime}|{width}".encode("utf-8", "ignore")
    ).hexdigest()
    cached = cache_dir / f"{key}.jpg"
    if cached.exists():
        return cached

    with Image.open(candidate) as image:
        image = ImageOps.exif_transpose(image)
        if image.width <= width and image.height <= width * 2:
            # Re-encoding an already small image only wastes CPU and bytes.
            return None
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        image.thumbnail((width, width * 2), Image.LANCZOS)
        temp = cached.with_name(f"{cached.stem}.{uuid.uuid4().hex}.tmp")
        try:
            image.save(temp, "JPEG", quality=82, optimize=True)
            temp.replace(cached)
        finally:
            if temp.exists():
                temp.unlink(missing_ok=True)
    return cached


def _serve(root: Path, relative: str, width: int) -> FileResponse:
    candidate = _resolve(root, relative)
    if width and candidate.suffix.lower() != ".gif":
        try:
            thumb = _thumbnail(candidate, width)
            if thumb is not None:
                return FileResponse(
                    thumb,
                    media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=604800"},
                )
        except HTTPException:
            raise
        except Exception:
            # Corrupt/unsupported image: fall back to the original file.
            pass

    media_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
    return FileResponse(
        candidate,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/media/recipes/{image_path:path}")
def recipe_image(
    image_path: str,
    w: int = Query(0, ge=0, le=_MAX_THUMB_WIDTH, description="缩略图宽度，0 为原图"),
) -> FileResponse:
    return _serve(_corpus_root(), image_path, w)


@router.get("/media/imports/recipes/{image_path:path}")
def imported_recipe_image(
    image_path: str,
    w: int = Query(0, ge=0, le=_MAX_THUMB_WIDTH, description="缩略图宽度，0 为原图"),
) -> FileResponse:
    return _serve(_IMPORT_ROOT, image_path, w)


@router.get("/media/recipe-images/{image_path:path}")
def fetched_recipe_image(
    image_path: str,
    w: int = Query(0, ge=0, le=_MAX_THUMB_WIDTH, description="缩略图宽度，0 为原图"),
) -> FileResponse:
    """Images fetched from public sources for corpus recipes that lack photos."""
    return _serve(_OVERRIDE_ROOT, image_path, w)


# ---------------------------------------------------------------------------
# Uploaded images (chat attachments / generated pictures) served from MinIO
# ---------------------------------------------------------------------------
_UPLOAD_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def _fetch_upload_object(object_name: str) -> bytes:
    """Read one object out of the private bucket (sync, called in a thread)."""
    from minio import Minio

    config = settings.image_storage
    client = Minio(
        config.minio_endpoint,
        access_key=config.minio_access_key,
        secret_key=config.minio_secret_key,
        secure=config.minio_secure,
    )
    response = None
    try:
        response = client.get_object(config.minio_bucket, object_name)
        return response.read()
    finally:
        if response is not None:
            response.close()
            response.release_conn()


@router.get("/media/uploads/{object_name}")
async def uploaded_image(object_name: str) -> Response:
    """Serve a chat/generated image stored in MinIO.

    The bucket stays private; this route is the only public surface. Object names
    are flat (``YYYYMMDD_<uuid>.jpg``) and validated against a suffix whitelist.
    """
    config = settings.image_storage
    if (config.provider or "minio").strip().lower() != "minio":
        raise HTTPException(status_code=404, detail="图片不存在")

    if not object_name or "/" in object_name or "\\" in object_name or ".." in object_name:
        raise HTTPException(status_code=404, detail="图片不存在")

    suffix = Path(object_name).suffix.lower()
    content_type = _UPLOAD_CONTENT_TYPES.get(suffix)
    if content_type is None:
        raise HTTPException(status_code=404, detail="图片不存在")

    try:
        data = await asyncio.to_thread(_fetch_upload_object, object_name)
    except Exception:
        raise HTTPException(status_code=404, detail="图片不存在") from None

    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
