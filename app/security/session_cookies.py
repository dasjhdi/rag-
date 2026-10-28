"""HttpOnly session cookies for same-origin deployments.

浏览器不再持有可被脚本读取的令牌：访问令牌与刷新令牌都以 ``HttpOnly`` Cookie
下发，前端只需 ``credentials: 'include'``。Bearer 头仍然保留，供 CLI / 脚本 /
既有集成使用，两者由鉴权网关统一识别。
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import Response

from app.config import settings

logger = logging.getLogger(__name__)

ACCESS_COOKIE = "ch_access"
REFRESH_COOKIE = "ch_refresh"

# 只在这些路径下发送刷新 Cookie，缩小暴露面
REFRESH_PATH = "/api/v1/auth"


def _base_kwargs(max_age: int) -> dict:
    kwargs = {
        "max_age": max_age,
        "httponly": True,
        "secure": bool(settings.COOKIE_SECURE),
        # 同域部署下 Lax 即可：跨站 POST 不带 Cookie，天然抵御 CSRF
        "samesite": "lax",
        "path": "/",
    }
    if settings.COOKIE_DOMAIN:
        kwargs["domain"] = settings.COOKIE_DOMAIN
    return kwargs


def set_session_cookies(
    response: Response,
    access_token: str,
    refresh_token: Optional[str] = None,
) -> None:
    """Attach access (and optionally refresh) cookies to a response."""
    access_max_age = int(settings.ACCESS_TOKEN_EXPIRE_MINUTES) * 60
    response.set_cookie(
        ACCESS_COOKIE, access_token, **_base_kwargs(access_max_age)
    )

    if refresh_token:
        refresh_max_age = int(settings.REFRESH_TOKEN_EXPIRE_DAYS) * 86400
        kwargs = _base_kwargs(refresh_max_age)
        kwargs["path"] = REFRESH_PATH
        response.set_cookie(REFRESH_COOKIE, refresh_token, **kwargs)


def clear_session_cookies(response: Response) -> None:
    """Expire both cookies (logout)."""
    response.delete_cookie(
        ACCESS_COOKIE,
        path="/",
        domain=settings.COOKIE_DOMAIN or None,
    )
    response.delete_cookie(
        REFRESH_COOKIE,
        path=REFRESH_PATH,
        domain=settings.COOKIE_DOMAIN or None,
    )
