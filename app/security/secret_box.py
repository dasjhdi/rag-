"""TOTP 共享密钥的静态加密。

后台双因子的 secret 等价于「第二因素」，不能像普通配置那样明文落库。
这里用 AES-GCM（pycryptodome）加密，密钥由 ``JWT_SECRET_KEY`` 派生：
换 JWT 密钥等价于让所有已绑定的验证器失效，需要重新绑定——这是可接受的
安全取舍，也比新增一份独立密钥更不容易漏配。
"""

from __future__ import annotations

import base64
import hashlib

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes

from app.config import settings

_PREFIX = "v1:"
_NONCE_BYTES = 12


def _key() -> bytes:
    seed = (settings.JWT_SECRET_KEY or "cookhero-dev-only").encode("utf-8")
    return hashlib.sha256(seed).digest()


def encrypt_secret(plaintext: str) -> str:
    """加密 TOTP secret，返回带版本前缀的 base64 串。"""
    if not plaintext:
        return ""
    nonce = get_random_bytes(_NONCE_BYTES)
    cipher = AES.new(_key(), AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext.encode("utf-8"))
    payload = nonce + tag + ciphertext
    return _PREFIX + base64.b64encode(payload).decode("ascii")


def decrypt_secret(value: str) -> str:
    """解密；不带前缀的历史数据按明文返回，保证平滑升级。"""
    if not value:
        return ""
    if not value.startswith(_PREFIX):
        return value

    try:
        payload = base64.b64decode(value[len(_PREFIX) :])
        nonce = payload[:_NONCE_BYTES]
        tag = payload[_NONCE_BYTES : _NONCE_BYTES + 16]
        ciphertext = payload[_NONCE_BYTES + 16 :]
        cipher = AES.new(_key(), AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext, tag).decode("utf-8")
    except Exception:  # 密钥轮换或数据损坏
        return ""
