"""TOTP (RFC 6238) 与恢复码的最小实现。

只依赖标准库：后台双因子不需要引入额外第三方包，也便于离线部署。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from typing import Iterable, Optional
from urllib.parse import quote, urlencode

DIGITS = 6
PERIOD = 30
SECRET_BYTES = 20  # 160 bit，RFC 4226 推荐长度
RECOVERY_CODE_COUNT = 10


def generate_secret(num_bytes: int = SECRET_BYTES) -> str:
    """生成 base32 编码的共享密钥（不带 padding，便于手工输入）。"""
    raw = secrets.token_bytes(num_bytes)
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def _decode_secret(secret: str) -> bytes:
    normalized = (secret or "").strip().replace(" ", "").upper()
    padding = "=" * (-len(normalized) % 8)
    return base64.b32decode(normalized + padding, casefold=True)


def time_counter(at: Optional[float] = None) -> int:
    """当前时间片编号（默认 30 秒一片）。"""
    return int((time.time() if at is None else at) // PERIOD)


def hotp(secret: str, counter: int, digits: int = DIGITS) -> str:
    """按 RFC 4226 计算一次性密码。"""
    digest = hmac.new(_decode_secret(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(truncated % (10**digits)).zfill(digits)


def verify_code(
    secret: str,
    code: str,
    *,
    at: Optional[float] = None,
    window: int = 1,
    last_counter: int = 0,
) -> tuple[bool, int]:
    """校验动态码，返回 ``(是否通过, 命中的时间片)``。

    - ``window=1`` 允许前后各 30 秒的时钟漂移；
    - ``last_counter`` 用于防重放：同一个码不能在同一时间片内用第二次。
    """
    cleaned = (code or "").strip().replace(" ", "")
    if not cleaned.isdigit() or len(cleaned) != DIGITS:
        return False, 0

    current = time_counter(at)
    matched = 0
    for offset in range(-window, window + 1):
        counter = current + offset
        if counter <= 0:
            continue
        if hmac.compare_digest(hotp(secret, counter), cleaned):
            matched = counter
            break

    if not matched:
        return False, 0
    if last_counter and matched <= last_counter:
        # 已用过的时间片，视为重放
        return False, 0
    return True, matched


def provisioning_uri(secret: str, account_name: str, issuer: str = "CookHero") -> str:
    """生成 otpauth:// 链接，可用任意验证器 App 扫码或手工录入。"""
    label = quote(f"{issuer}:{account_name}", safe="")
    params = urlencode(
        {
            "secret": secret,
            "issuer": issuer,
            "algorithm": "SHA1",
            "digits": DIGITS,
            "period": PERIOD,
        }
    )
    return f"otpauth://totp/{label}?{params}"


# ---------------------------------------------------------------------------
# 恢复码
# ---------------------------------------------------------------------------
def generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    """生成形如 ``a1b2c-3d4e5`` 的一次性恢复码。"""
    codes: list[str] = []
    for _ in range(count):
        raw = secrets.token_hex(5)  # 10 位十六进制 = 40 bit
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes


def normalize_recovery_code(code: str) -> str:
    return (code or "").strip().lower().replace("-", "").replace(" ", "")


def hash_recovery_code(code: str) -> str:
    return hashlib.sha256(normalize_recovery_code(code).encode("utf-8")).hexdigest()


def build_recovery_payload(codes: Iterable[str]) -> list[dict]:
    """把明文恢复码转成可落库的结构（只存哈希）。"""
    return [{"hash": hash_recovery_code(code), "used_at": None} for code in codes]


def consume_recovery_code(stored: Optional[list], code: str) -> tuple[bool, list]:
    """校验并消费一个恢复码，返回 ``(是否通过, 新的存储结构)``。"""
    if not stored or not code:
        return False, stored or []

    target = hash_recovery_code(code)
    updated: list[dict] = []
    matched = False
    for item in stored:
        entry = dict(item) if isinstance(item, dict) else {"hash": str(item), "used_at": None}
        if not matched and entry.get("used_at") is None and hmac.compare_digest(
            str(entry.get("hash", "")), target
        ):
            entry["used_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            matched = True
        updated.append(entry)
    return matched, updated


def count_unused_recovery_codes(stored: Optional[list]) -> int:
    if not stored:
        return 0
    return sum(
        1
        for item in stored
        if isinstance(item, dict) and item.get("used_at") is None
    )
