"""Token versioning: password change / logout must invalidate old JWTs."""

import uuid

from app.database.models import UserModel
from app.security.token_version import TokenVersionService
from app.services.auth_service import AuthService


def _service_with_version(version):
    service = TokenVersionService()

    async def fake_get(_user_id):
        return version

    service.get = fake_get  # type: ignore[method-assign]
    return service


async def test_matches_accepts_current_version():
    service = _service_with_version(3)
    assert await service.matches("user-1", 3) is True


async def test_matches_rejects_stale_version():
    service = _service_with_version(3)
    assert await service.matches("user-1", 2) is False


async def test_missing_claim_is_treated_as_version_zero():
    """旧版本签发的令牌没有 tv 字段，应与列默认值 0 对齐。"""
    service = _service_with_version(0)
    assert await service.matches("legacy-user", None) is True


async def test_unknown_user_is_rejected():
    service = _service_with_version(None)
    assert await service.matches("ghost", 0) is False


def test_access_token_carries_token_version():
    user = UserModel(username="alice", password_hash="hash")
    user.id = uuid.uuid4()
    user.token_version = 7

    auth = AuthService(secret_key="unit-test-secret")
    identity = auth.decode_token(auth.create_access_token(user))

    assert identity is not None
    assert identity["username"] == "alice"
    assert identity["user_id"] == str(user.id)
    assert identity["tv"] == 7


def test_refresh_token_carries_token_version():
    user = UserModel(username="bob", password_hash="hash")
    user.id = uuid.uuid4()
    user.token_version = 2

    auth = AuthService(secret_key="unit-test-secret")
    identity = auth.decode_refresh_token(auth.create_refresh_token(user))

    assert identity is not None
    assert identity["tv"] == 2
