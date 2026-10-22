"""
Authentication API endpoints: register and login.
Includes security features: account lockout, audit logging.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.services.auth_service import auth_service
from app.security.audit import audit_logger

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


def _issue_tokens(user) -> TokenResponse:
    """统一签发访问令牌与刷新令牌。"""
    return TokenResponse(
        access_token=auth_service.create_access_token(user),
        username=user.username,
        refresh_token=auth_service.create_refresh_token(user),
        expires_in=auth_service.expire_minutes * 60,
    )


@router.post("/auth/register", response_model=TokenResponse)
async def register(request: RegisterRequest, http_request: Request):
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
    return _issue_tokens(user)


@router.post("/auth/login", response_model=TokenResponse)
async def login(request: LoginRequest, http_request: Request):
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
    return _issue_tokens(user)


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh(request: RefreshRequest):
    """用刷新令牌换取新的访问令牌。

    只接受 ``typ=refresh`` 的令牌；访问令牌不能在此使用（反之亦然，
    ``decode_token`` 也会拒绝刷新令牌冒充访问令牌）。
    """
    identity = auth_service.decode_refresh_token(request.refresh_token)
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

    return _issue_tokens(user)
