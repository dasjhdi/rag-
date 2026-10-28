# app/utils/image_storage.py
"""Image persistence for chat uploads and generated pictures.

Primary backend is self-hosted MinIO (``provider=minio``): images never leave the
deployment. The legacy imgbb uploader is kept behind ``provider=imgbb`` for older
deployments that still rely on it.

Both paths return the same shape so callers stay backend-agnostic::

    {"url": "/media/uploads/20261026_ab12.jpg",
     "display_url": "...", "thumb_url": "...", "delete_url": None}
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_MIME_EXT = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
_MAX_BYTES = 10 * 1024 * 1024


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
async def upload_image(
    image_data: str,
    mime_type: str = "image/jpeg",
) -> Optional[dict]:
    """Persist a base64 image and return its public URLs (``None`` on failure)."""
    config = settings.image_storage
    if not config.enabled:
        logger.info("Image storage is disabled, skipping upload")
        return None

    provider = (config.provider or "minio").strip().lower()
    if provider == "imgbb":
        return await _upload_imgbb(image_data, mime_type)
    return await _upload_minio(image_data, mime_type)


async def upload_to_imgbb(image_data: str, mime_type: str = "image/jpeg") -> Optional[dict]:
    """Deprecated alias kept for older call sites; use :func:`upload_image`."""
    return await upload_image(image_data, mime_type)


# ---------------------------------------------------------------------------
# MinIO backend
# ---------------------------------------------------------------------------
def _ext_for_mime(mime: str) -> str:
    """Extension for a MIME type; unknown types fall back to ``.jpg``."""
    return _MIME_EXT.get((mime or "").lower(), ".jpg")


def _decode(image_data: str) -> bytes:
    payload = image_data.strip()
    if payload.startswith("data:"):
        _, _, payload = payload.partition(",")
    return base64.b64decode(payload, validate=False)


async def _load_bytes(image_data: str) -> tuple[bytes, str]:
    """Accept base64, data-URI or http(s) URL and return ``(bytes, mime)``.

    The legacy imgbb API accepted URLs directly (``image=<url>``); generated
    images still come through that path, so URLs are downloaded first.
    """
    payload = (image_data or "").strip()
    if payload.startswith(("http://", "https://")):
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            response = await client.get(payload)
            response.raise_for_status()
            mime = (response.headers.get("content-type") or "").split(";")[0].strip()
            return response.content, mime or "image/jpeg"
    return _decode(payload), ""


def _make_thumbnail(data: bytes, max_px: int) -> Optional[bytes]:
    """Bounded JPEG thumbnail; ``None`` when the format is unsupported."""
    try:
        from PIL import Image, ImageOps

        with Image.open(io.BytesIO(data)) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            img.thumbnail((max_px, max_px))
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=82, optimize=True)
            return buffer.getvalue()
    except Exception as exc:
        logger.warning("Thumbnail generation failed: %s", exc)
        return None


def _minio_upload_sync(
    *,
    endpoint: str,
    access_key: str,
    secret_key: str,
    secure: bool,
    bucket: str,
    objects: list[tuple[str, bytes, str]],
) -> None:
    """Create the bucket if needed, then upload every object (run in a thread)."""
    from minio import Minio

    client = Minio(
        endpoint,
        access_key=access_key,
        secret_key=secret_key,
        secure=secure,
    )
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
        logger.info("Created MinIO bucket: %s", bucket)

    for name, data, content_type in objects:
        client.put_object(
            bucket,
            name,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )


async def _upload_minio(image_data: str, mime_type: str) -> Optional[dict]:
    config = settings.image_storage
    if not config.minio_access_key or not config.minio_secret_key:
        logger.warning(
            "MinIO credentials missing (MINIO_ACCESS_KEY / MINIO_SECRET_KEY), skipping upload"
        )
        return None

    try:
        data, detected_mime = await _load_bytes(image_data)
    except Exception as exc:
        logger.warning("Unable to read image payload: %s", exc)
        return None

    if not data:
        logger.warning("Empty image payload, skipping upload")
        return None
    if len(data) > _MAX_BYTES:
        logger.warning("Image too large (%s bytes), skipping upload", len(data))
        return None

    mime = (mime_type or detected_mime or "image/jpeg").lower()
    if not mime.startswith("image/"):
        mime = detected_mime or "image/jpeg"
    ext = _ext_for_mime(mime)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    name = f"{stamp}_{uuid.uuid4().hex}{ext}"

    thumb_name: Optional[str] = None
    thumb_bytes: Optional[bytes] = None
    if mime != "image/gif":
        thumb_bytes = _make_thumbnail(data, config.thumbnail_max_px)
        if thumb_bytes:
            thumb_name = f"{stamp}_{uuid.uuid4().hex}_t.jpg"

    objects: list[tuple[str, bytes, str]] = [(name, data, mime)]
    if thumb_name and thumb_bytes:
        objects.append((thumb_name, thumb_bytes, "image/jpeg"))

    try:
        await asyncio.to_thread(
            _minio_upload_sync,
            endpoint=config.minio_endpoint,
            access_key=config.minio_access_key,
            secret_key=config.minio_secret_key,
            secure=config.minio_secure,
            bucket=config.minio_bucket,
            objects=objects,
        )
    except Exception as exc:
        logger.error("MinIO upload failed: %s", exc)
        return None

    base = (config.public_base or "").rstrip("/")

    def url_for(object_name: str) -> str:
        path = f"/media/uploads/{object_name}"
        return f"{base}{path}" if base else path

    logger.info("Image stored in MinIO: %s", name)
    return {
        "url": url_for(name),
        "display_url": url_for(name),
        "thumb_url": url_for(thumb_name) if thumb_name else url_for(name),
        "delete_url": None,
        "provider": "minio",
    }


# ---------------------------------------------------------------------------
# Legacy imgbb backend
# ---------------------------------------------------------------------------
async def _upload_imgbb(image_data: str, mime_type: str = "image/jpeg") -> Optional[dict]:
    storage_config = settings.image_storage
    if not storage_config.api_key:
        logger.warning("imgbb API key is not configured, skipping upload")
        return None

    try:
        params = {
            "key": storage_config.api_key,
            "image": image_data,
        }
        if storage_config.expiration:
            params["expiration"] = str(storage_config.expiration)

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                storage_config.upload_url,
                data=params,
            )
            response.raise_for_status()
            result = response.json()

            if result.get("success"):
                return {
                    "url": result["data"]["url"],
                    "display_url": result["data"].get("display_url"),
                    "delete_url": result["data"].get("delete_url"),
                    "thumb_url": (result["data"].get("thumb") or {}).get("url"),
                    "provider": "imgbb",
                }

            logger.error("imgbb upload failed: %s", result)
            return None
    except Exception as exc:
        logger.exception("Failed to upload image to imgbb: %s", exc)
        return None
