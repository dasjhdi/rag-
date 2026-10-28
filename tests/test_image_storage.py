"""Image storage helpers: payload decoding and object naming rules (no network)."""

import base64

from app.utils.image_storage import _decode, _ext_for_mime


def test_decode_accepts_plain_base64():
    raw = b"cookhero"
    assert _decode(base64.b64encode(raw).decode()) == raw


def test_decode_strips_data_uri_prefix():
    raw = b"\x89PNG\r\n"
    encoded = base64.b64encode(raw).decode()
    assert _decode(f"data:image/png;base64,{encoded}") == raw


def test_mime_to_extension_whitelist():
    assert _ext_for_mime("image/png") == ".png"
    assert _ext_for_mime("image/jpeg") == ".jpg"
    # 未知类型回退为 jpg，避免出现不可预知的扩展名
    assert _ext_for_mime("application/octet-stream") == ".jpg"
