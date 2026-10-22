"""访问令牌 / 刷新令牌的边界测试（离线）。

重点验证两类令牌不能互相冒用：
- 访问令牌不能拿去 /auth/refresh
- 刷新令牌不能当访问令牌访问业务接口
以及旧版无 typ 字段的令牌仍按访问令牌处理（向后兼容）。
"""

from datetime import datetime, timedelta
from uuid import uuid4

from jose import jwt

from app.api.v1.endpoints.auth import router as auth_router
from app.config import settings
from app.database.models import UserModel
from app.services.auth_service import auth_service


def _user() -> UserModel:
    user = UserModel(username="refresh_demo", password_hash="x")
    user.id = uuid4()
    user.is_active = True
    return user


def test_refresh_route_registered():
    paths = {route.path for route in auth_router.routes}
    assert "/auth/refresh" in paths


def test_access_token_decodes_as_access():
    user = _user()
    token = auth_service.create_access_token(user)
    identity = auth_service.decode_token(token)
    assert identity is not None
    assert identity["username"] == user.username
    assert identity["user_id"] == str(user.id)


def test_refresh_token_decodes_as_refresh():
    user = _user()
    token = auth_service.create_refresh_token(user)
    identity = auth_service.decode_refresh_token(token)
    assert identity is not None
    assert identity["username"] == user.username


def test_access_token_rejected_by_refresh_decoder():
    """访问令牌不能用来换新令牌。"""
    token = auth_service.create_access_token(_user())
    assert auth_service.decode_refresh_token(token) is None


def test_refresh_token_rejected_by_access_decoder():
    """刷新令牌不能当访问令牌用（否则长有效期令牌可绕过短有效期）。"""
    token = auth_service.create_refresh_token(_user())
    assert auth_service.decode_token(token) is None


def test_legacy_token_without_typ_still_accepted_as_access():
    """升级前签发的令牌没有 typ 字段，应继续可用，避免所有人被踢下线。"""
    user = _user()
    legacy = jwt.encode(
        {
            "sub": user.username,
            "uid": str(user.id),
            "exp": datetime.utcnow() + timedelta(minutes=5),
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    identity = auth_service.decode_token(legacy)
    assert identity is not None
    assert identity["username"] == user.username


def test_expired_refresh_token_rejected():
    user = _user()
    expired = jwt.encode(
        {
            "sub": user.username,
            "uid": str(user.id),
            "exp": datetime.utcnow() - timedelta(minutes=1),
            "typ": "refresh",
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    assert auth_service.decode_refresh_token(expired) is None


def test_refresh_ttl_longer_than_access_ttl():
    assert auth_service.refresh_days * 24 * 60 > auth_service.expire_minutes
