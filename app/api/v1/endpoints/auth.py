"""
Authentication API endpoints: register and login.
Includes security features: account lockout, audit logging.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.services.auth_service import auth_service
from app.security.audit import audit_logger
from app.security.session_cookies import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    clear_session_cookies,
    set_session_cookies,
)
from app.security.token_version import token_version_service

router = APIRouter()
logger = logging.getLogger(__name__)


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=3, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=3, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    # 长有效期令牌，仅用于 POST /auth/refresh 换新的访问令牌
    refresh_token: Optional[str] = None
    # 访问令牌剩余有效期（秒），前端据此提前续期
    expires_in: Optional[int] = None


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=8)


def _issue_tokens(user, response: Response) -> TokenResponse:
    """统一签发访问令牌与刷新令牌，并写入 HttpOnly 会话 Cookie。

    响应体仍带回 access_token，供 curl / 脚本 / 既有集成使用；
    浏览器侧不再读取它，只依赖 Cookie。
    """
    access_token = auth_service.create_access_token(user)
    refresh_token = auth_service.create_refresh_token(user)
    set_session_cookies(response, access_token, refresh_token)
    return TokenResponse(
        access_token=access_token,
        username=user.username,
        refresh_token=refresh_token,
        expires_in=auth_service.expire_minutes * 60,
    )


@router.post("/auth/register", response_model=TokenResponse)
async def register(request: RegisterRequest, http_request: Request, response: Response):
    """Register a new user with hashed password."""
    try:
        user = await auth_service.register_user(request.username, request.password)
    except ValueError as exc:
        audit_logger.login_failure(
            username=request.username,
            request=http_request,
            reason="registration_failed_username_exists",
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error("Register error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Registration failed")

    audit_logger.login_success(
        username=user.username,
        user_id=str(user.id),
        request=http_request,
    )
    return _issue_tokens(user, response)


@router.post("/auth/login", response_model=TokenResponse)
async def login(request: LoginRequest, http_request: Request, response: Response):
    """Authenticate user and return JWT token with security protections."""
    # Check if account is locked
    is_locked, remaining_seconds = await auth_service.is_account_locked(request.username)
    if is_locked:
        audit_logger.login_failure(
            username=request.username,
            request=http_request,
            reason="account_locked",
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"账户已被锁定，请在 {remaining_seconds // 60 + 1} 分钟后重试",
            headers={"Retry-After": str(remaining_seconds)},
        )

    user = await auth_service.authenticate_user(request.username, request.password)
    if not user:
        # Record failed attempt
        attempts, is_now_locked = await auth_service.record_failed_attempt(request.username)

        audit_logger.login_failure(
            username=request.username,
            request=http_request,
            reason="invalid_credentials",
        )

        if is_now_locked:
            audit_logger.account_locked(
                username=request.username,
                request=http_request,
                failed_attempts=attempts,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"登录失败次数过多，账户已锁定 {auth_service.lockout_minutes} 分钟",
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )

    # Clear failed attempts on successful login
    await auth_service.clear_failed_attempts(request.username)

    # Record activity for the admin console (best effort, never blocks login)
    await auth_service.touch_last_login(user.username)

    audit_logger.login_success(
        username=user.username,
        user_id=str(user.id),
        request=http_request,
    )
    return _issue_tokens(user, response)


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh(
    http_request: Request,
    response: Response,
    request: Optional[RefreshRequest] = None,
):
    """用刷新令牌换取新的访问令牌。

    刷新令牌优先取请求体；浏览器场景下取 HttpOnly Cookie，
    因此前端 401 时只需 ``credentials: 'include'`` 重试即可。
    """
    raw_token = (request.refresh_token if request else None) or http_request.cookies.get(
        REFRESH_COOKIE
    )
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少刷新令牌，请重新登录",
        )

    identity = auth_service.decode_refresh_token(raw_token)
    if not identity or not identity.get("username"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="刷新令牌无效或已过期，请重新登录",
        )

    user = await auth_service.get_user_by_username(identity["username"])
    if not user or not getattr(user, "is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号不存在或已被禁用",
        )

    # 刷新令牌同样受版本约束：改密/登出后旧刷新令牌不能换出新访问令牌
    if int(getattr(user, "token_version", 0) or 0) != int(identity.get("tv") or 0):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="刷新令牌已失效，请重新登录",
        )

    return _issue_tokens(user, response)


@router.get("/auth/whoami")
async def whoami(http_request: Request):
    """返回当前会话的账号信息，供前端在刷新页面后恢复登录态。"""
    user_id = getattr(http_request.state, "user_id", None)
    username = getattr(http_request.state, "username", None)
    if not user_id or not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="需要登录")

    user = await auth_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号不存在")

    return {
        "username": user.username,
        "role": getattr(user, "role", "user"),
        "is_admin": bool(getattr(user, "is_admin", False)),
    }


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(http_request: Request, response: Response, revoke: bool = True):
    """主动登出：默认递增令牌版本（全端登出）并清除会话 Cookie。

    ``revoke=false`` 只清除当前浏览器的 Cookie，不递增版本，其他设备不受影响。
    用于「在后台登录页被拒绝」这类场景：一次失败的尝试不应该把用户从别处踢下线。
    """
    user_id = getattr(http_request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="需要登录")

    if revoke:
        await token_version_service.bump(user_id)
    clear_session_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response

