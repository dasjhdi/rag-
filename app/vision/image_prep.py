"""送进视觉模型前的图片归一化。

为什么需要：
- 手机原图常见 3000–4000px、3–8MB，base64 后体积再涨 33%，视觉模型读这种
  请求容易超时（实测原图 90s 读超时，缩到 512px 后 2–4s 返回）。
- 模型侧真正需要的信息远小于原图：菜品识别、食材识别在 1024px 长边下已足够。

策略：
- 已经足够小（长边 <= max_edge 且体积 <= max_bytes）的图片**原样透传**，
  避免二次压缩损失画质；
- 否则按 EXIF 方向摆正 → 长边缩到 max_edge → 转 RGB（透明底铺白）→
  JPEG 渐进式编码，质量从 quality 逐级降到 60，仍超限则继续缩边；
- 任何异常都回退原图：预处理不能成为新的失败点。
"""

from __future__ import annotations

import base64
import binascii
import io
import logging
from dataclasses import dataclass
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Pillow 是已有依赖（缩略图/图片处理在用），这里只做纯内存操作
try:  # pragma: no cover - 环境缺 Pillow 时降级为原图透传
    from PIL import Image, ImageOps
except Exception:  # pragma: no cover
    Image = None  # type: ignore
    ImageOps = None  # type: ignore

_JPEG_MIME = "image/jpeg"
_FORMATS_KEEP_AS_IS = {"JPEG", "PNG", "WEBP", "GIF"}


@dataclass
class PreparedImage:
    """归一化结果，附带体积与尺寸，便于日志与度量。"""

    data: str
    mime_type: str
    original_bytes: int
    output_bytes: int
    original_size: Optional[Tuple[int, int]] = None
    output_size: Optional[Tuple[int, int]] = None
    resized: bool = False
    reason: str = "unchanged"

    @property
    def saved_ratio(self) -> float:
        if not self.original_bytes:
            return 0.0
        return 1 - self.output_bytes / self.original_bytes


def _strip_prefix(data: str) -> str:
    """兼容前端偶尔直接传 `data:image/png;base64,...` 的情况。"""
    if data.startswith("data:") and "," in data:
        return data.split(",", 1)[1]
    return data


def _decode(data: str) -> bytes:
    payload = _strip_prefix(data).strip()
    # base64 常见缺少 padding，补齐后再解
    padding = (-len(payload)) % 4
    if padding:
        payload += "=" * padding
    return base64.b64decode(payload, validate=False)


def _encode_jpeg(image: "Image.Image", quality: int) -> bytes:
    buffer = io.BytesIO()
    image.save(
        buffer,
        format="JPEG",
        quality=quality,
        optimize=True,
        progressive=True,
    )
    return buffer.getvalue()


def _to_rgb(image: "Image.Image") -> "Image.Image":
    """透明底铺白，避免 PNG 转 JPEG 后出现黑底。"""
    if image.mode in ("RGBA", "LA") or (
        image.mode == "P" and "transparency" in image.info
    ):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.split()[-1])
        return background
    return image.convert("RGB")


def prepare_image(
    data_b64: str,
    mime_type: str = _JPEG_MIME,
    *,
    max_edge: int = 1024,
    quality: int = 85,
    max_bytes: int = 2_000_000,
) -> PreparedImage:
    """按需压缩图片，返回可直接塞进 data URL 的 base64。

    输出统一是「不带 data: 前缀」的纯 base64，调用方无需关心入参形态。
    """
    payload = _strip_prefix(data_b64).strip()
    original_len = len(payload) * 3 // 4

    if Image is None:  # pragma: no cover
        return PreparedImage(payload, mime_type, original_len, original_len)

    try:
        raw = _decode(data_b64)
    except (binascii.Error, ValueError) as exc:
        logger.warning("Image decode failed, passing through: %s", exc)
        return PreparedImage(
            payload, mime_type, original_len, original_len, reason="decode_error"
        )

    try:
        with Image.open(io.BytesIO(raw)) as source:
            source.load()
            fmt = (source.format or "").upper()
            original_size = source.size

            # 已经足够小：不重新编码，避免无谓的画质损失
            if (
                max(source.size) <= max_edge
                and len(raw) <= max_bytes
                and fmt in _FORMATS_KEEP_AS_IS
            ):
                return PreparedImage(
                    payload,
                    mime_type,
                    len(raw),
                    len(raw),
                    original_size,
                    original_size,
                    resized=False,
                    reason="unchanged",
                )

            image = ImageOps.exif_transpose(source) if ImageOps else source
            if max(image.size) > max_edge:
                image = image.copy()
                image.thumbnail((max_edge, max_edge), Image.LANCZOS)
            rgb = _to_rgb(image)

            # 先降质量，仍超限再缩边，最多三轮
            current = rgb
            encoded = b""
            for round_index in range(3):
                q = quality
                while q >= 60:
                    encoded = _encode_jpeg(current, q)
                    if len(encoded) <= max_bytes:
                        break
                    q -= 10
                if len(encoded) <= max_bytes:
                    break
                next_edge = max(320, int(max(current.size) * 0.75))
                current = current.copy()
                current.thumbnail((next_edge, next_edge), Image.LANCZOS)

            return PreparedImage(
                data=base64.b64encode(encoded).decode("utf-8"),
                mime_type=_JPEG_MIME,
                original_bytes=len(raw),
                output_bytes=len(encoded),
                original_size=original_size,
                output_size=current.size,
                resized=True,
                reason="resized" if max(original_size) > max_edge else "reencoded",
            )
    except Exception as exc:  # 损坏文件、解压炸弹等一律透传
        logger.warning("Image normalize failed, passing through: %s", exc)
        return PreparedImage(
            payload, mime_type, original_len, original_len, reason="passthrough_error"
        )
