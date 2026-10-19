"""Thumbnail helper tests for the media router (offline)."""

from pathlib import Path

import pytest
from PIL import Image

from app.api import media


@pytest.fixture()
def cache(tmp_path, monkeypatch):
    target = tmp_path / "cache"
    monkeypatch.setattr(media, "_THUMB_CACHE", target)
    return target


def _image(path: Path, size: tuple[int, int]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (200, 120, 60)).save(path, "JPEG")
    return path


def test_small_image_skips_reencode(tmp_path, cache):
    source = _image(tmp_path / "small.jpg", (500, 375))
    assert media._thumbnail(source, 640) is None


def test_large_image_is_downscaled(tmp_path, cache):
    source = _image(tmp_path / "large.jpg", (1600, 1200))
    thumb = media._thumbnail(source, 640)
    assert thumb is not None and thumb.exists()
    with Image.open(thumb) as image:
        assert image.width <= 640


def test_thumbnail_is_cached(tmp_path, cache):
    source = _image(tmp_path / "large.jpg", (1600, 1200))
    first = media._thumbnail(source, 640)
    second = media._thumbnail(source, 640)
    assert first == second and first.exists()
