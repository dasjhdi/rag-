"""双因子（TOTP）业务逻辑：绑定、确认、关闭、校验与恢复码消费。

约定：
- secret 一律经 ``secret_box`` 加密后落库；
- 恢复码只存 SHA-256 哈希，明文只在确认绑定那一次返回；
- 动态码校验带时间片防重放（``totp_last_counter``）。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select

from app.config import settings
from app.database.models import UserModel
from app.database.session import get_session_context
from app.security import totp
from app.security.secret_box import decrypt_secret, encrypt_secret
from app.security.token_version import token_version_service

logger = logging.getLogger(__name__)


class TotpError(ValueError):
    """业务侧可直接展示的错误。"""


async def _load_user(session, user_id: str) -> Optional[UserModel]:
    try:
        return (
            await session.execute(select(UserModel).where(UserModel.id == user_id))
        ).scalar_one_or_none()
    except Exception:
        return None


def is_required_for(user: UserModel) -> bool:
    """该校验的账号是否被策略强制要求绑定。"""
    return bool(
        settings.TOTP_ENABLED
        and settings.TOTP_REQUIRED_FOR_SUPER_ADMIN
        and getattr(user, "role", "") == "super_admin"
        and not getattr(user, "totp_enabled", False)
    )


async def get_status(user: UserModel) -> dict:
    return {
        "enabled": bool(getattr(user, "totp_enabled", False)),
        "required": is_required_for(user),
        "policy_enabled": bool(settings.TOTP_ENABLED),
        "confirmed_at": (
            user.totp_confirmed_at.isoformat() if getattr(user, "totp_confirmed_at", None) else None
        ),
        "recovery_codes_left": totp.count_unused_recovery_codes(
            getattr(user, "totp_recovery_codes", None)
        ),
        "issuer": settings.TOTP_ISSUER,
    }


async def start_setup(user_id: str, username: str) -> dict:
    """生成新的共享密钥并暂存（尚未启用，需 confirm 才生效）。"""
    async with get_session_context() as session:
        user = await _load_user(session, user_id)
        if user is None:
            raise TotpError("账号不存在")
        if user.totp_enabled:
            raise TotpError("双因子已启用，如需更换请先关闭")

        secret = totp.generate_secret()
        user.totp_secret = encrypt_secret(secret)
        user.totp_enabled = False
        user.totp_confirmed_at = None
        user.totp_last_counter = 0
        await session.flush()

    return {
        "secret": secret,
        "otpauth_uri": totp.provisioning_uri(secret, username, settings.TOTP_ISSUER),
        "issuer": settings.TOTP_ISSUER,
        "digits": totp.DIGITS,
        "period": totp.PERIOD,
    }


async def confirm_setup(user_id: str, code: str) -> list[str]:
    """确认绑定：校验一次动态码，成功后启用并返回明文恢复码（仅此一次）。"""
    async with get_session_context() as session:
        user = await _load_user(session, user_id)
        if user is None:
            raise TotpError("账号不存在")
        if user.totp_enabled:
            raise TotpError("双因子已启用")
        if not user.totp_secret:
            raise TotpError("请先生成密钥")

        secret = decrypt_secret(user.totp_secret)
        ok, counter = totp.verify_code(secret, code)
        if not ok:
            raise TotpError("验证码不正确，请确认手机时间与服务器一致")

        recovery_codes = totp.generate_recovery_codes()
        user.totp_enabled = True
        user.totp_confirmed_at = datetime.utcnow()
        user.totp_last_counter = counter
        user.totp_recovery_codes = totp.build_recovery_payload(recovery_codes)
        await session.flush()

    # 绑定第二因素后作废旧会话：必须重新用「密码 + 动态码」登录。
    # 走统一服务而不是直接改列，避免 Redis 里的版本缓存与数据库不一致。
    await token_version_service.bump(user_id)

    logger.info("TOTP enabled for user %s", user_id)
    return recovery_codes


async def disable(user_id: str, password: str, code: str, verify_password) -> None:
    """关闭双因子：必须同时提供密码与当前动态码（或恢复码）。"""
    async with get_session_context() as session:
        user = await _load_user(session, user_id)
        if user is None:
            raise TotpError("账号不存在")
        if not user.totp_enabled:
            raise TotpError("双因子尚未启用")
        if not verify_password(password, user.password_hash):
            raise TotpError("登录密码不正确")
        if not await _consume_in_session(session, user, code):
            raise TotpError("验证码不正确")

        # 清空绑定信息：恢复码一并作废，重新绑定会生成新的
        user.totp_enabled = False
        user.totp_secret = None
        user.totp_confirmed_at = None
        user.totp_last_counter = 0
        user.totp_recovery_codes = None
        await session.flush()

    await token_version_service.bump(user_id)
    logger.warning("TOTP disabled for user %s", user_id)


async def _consume_in_session(session, user: UserModel, code: str) -> bool:
    secret = decrypt_secret(user.totp_secret or "")
    if secret:
        ok, counter = totp.verify_code(
            secret, code, last_counter=int(user.totp_last_counter or 0)
        )
        if ok:
            user.totp_last_counter = counter
            return True

    matched, updated = totp.consume_recovery_code(user.totp_recovery_codes, code)
    if matched:
        user.totp_recovery_codes = updated
        return True
    return False


async def consume(user_id: str, code: str) -> tuple[bool, str]:
    """登录时校验第二因素，返回 ``(是否通过, 方式)``。"""
    async with get_session_context() as session:
        user = await _load_user(session, user_id)
        if user is None or not user.totp_enabled:
            return False, ""

        secret = decrypt_secret(user.totp_secret or "")
        if secret:
            ok, counter = totp.verify_code(
                secret, code, last_counter=int(user.totp_last_counter or 0)
            )
            if ok:
                user.totp_last_counter = counter
                await session.flush()
                return True, "totp"

        matched, updated = totp.consume_recovery_code(user.totp_recovery_codes, code)
        if matched:
            user.totp_recovery_codes = updated
            await session.flush()
            logger.warning("Recovery code used for user %s", user_id)
            return True, "recovery"

        return False, ""


async def admin_reset(username: str) -> bool:
    """运维兜底：清空指定账号的双因子绑定（供 scripts/reset_totp.py 调用）。"""
    async with get_session_context() as session:
        user = (
            await session.execute(select(UserModel).where(UserModel.username == username))
        ).scalar_one_or_none()
        if user is None:
            return False
        user.totp_secret = None
        user.totp_enabled = False
        user.totp_confirmed_at = None
        user.totp_last_counter = 0
        user.totp_recovery_codes = None
        await session.flush()

    await token_version_service.bump(user.id)
    return True
