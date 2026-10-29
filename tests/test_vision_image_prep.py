"""送模型前的图片归一化：体积、尺寸、透明底与异常回退。

测试只依赖 Pillow，构造内存图片，不读写磁盘、不调用模型。
"""

import base64
import io
import os

from PIL import Image

from app.vision.image_prep import prepare_image


def _jpeg_bytes(size, *, quality=95, color=None) -> bytes:
    image = Image.new("RGB", size, color or (120, 80, 60))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def _noise_jpeg(size, *, quality=95) -> bytes:
    """随机噪声几乎不可压缩，用来模拟手机原图的大体积。"""
    image = Image.frombytes("RGB", size, os.urandom(size[0] * size[1] * 3))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def _decode(data: str) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(data)))


class TestDownscale:
    def test_large_photo_is_downscaled(self):
        raw = _noise_jpeg((3024, 2016))
        result = prepare_image(_b64(raw), "image/jpeg", max_edge=1024, max_bytes=2_000_000)

        assert result.resized is True
        assert result.mime_type == "image/jpeg"
        assert max(result.output_size) <= 1024
        assert result.output_bytes <= 2_000_000
        assert result.output_bytes < result.original_bytes
        assert result.saved_ratio > 0.5
        assert max(_decode(result.data).size) <= 1024

    def test_hard_byte_cap_is_enforced(self):
        raw = _noise_jpeg((3024, 2016))
        result = prepare_image(_b64(raw), "image/jpeg", max_edge=1024, max_bytes=600_000)
        assert result.output_bytes <= 600_000

    def test_small_photo_is_not_recompressed(self):
        raw = _jpeg_bytes((400, 300), quality=80)
        encoded = _b64(raw)
        result = prepare_image(encoded, "image/jpeg")
        assert result.reason == "unchanged"
        assert result.resized is False
        assert result.data == encoded  # 原样透传，画质无损

    def test_exif_orientation_is_applied(self):
        image = Image.new("RGB", (1600, 1200), (200, 180, 160))
        exif = Image.Exif()
        exif[274] = 6  # 顺时针旋转 90°
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=90, exif=exif)

        result = prepare_image(_b64(buffer.getvalue()), "image/jpeg", max_edge=1024)
        width, height = _decode(result.data).size
        # 摆正后应是竖图
        assert height > width


class TestModes:
    def test_png_with_alpha_flattened_to_white(self):
        image = Image.new("RGBA", (1400, 1000), (0, 0, 0, 0))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")

        result = prepare_image(_b64(buffer.getvalue()), "image/png", max_edge=1024)
        assert result.mime_type == "image/jpeg"
        pixel = _decode(result.data).convert("RGB").getpixel((5, 5))
        assert min(pixel) > 240  # 透明区域铺白，而不是变黑

    def test_data_url_prefix_accepted(self):
        raw = _jpeg_bytes((500, 400))
        result = prepare_image(f"data:image/jpeg;base64,{_b64(raw)}")
        assert result.original_bytes > 0
        assert _decode(result.data).size == (500, 400)


class TestFallback:
    def test_corrupt_payload_passes_through(self):
        result = prepare_image("!!!not-an-image!!!", "image/jpeg")
        assert result.resized is False
        assert result.reason in ("decode_error", "passthrough_error")
        assert result.data == "!!!not-an-image!!!"

    def test_unsupported_format_passes_through(self):
        # GIF 静态图在支持列表内；这里造一个 Pillow 打不开的内容
        result = prepare_image(base64.b64encode(b"GIF89a").decode(), "image/gif")
        assert result.resized is False
        assert result.reason in ("passthrough_error", "decode_error")

    def test_ratio_without_original_bytes(self):
        assert prepare_image("").saved_ratio == 0.0
