"""P0 后台管理接口测试（离线）。

覆盖可在无数据库环境下验证的部分：
- 路由注册与前缀
- 匿名请求被拒绝（401）
- 用户序列化中的计数合并与默认值
- 管理员角色集合与 UserModel.is_admin 判定

需要数据库的端到端行为（管理员 200 / 普通用户 403 / 分页与搜索）
由 scripts 外的真实请求验证，见交付说明。
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.admin import _serialize_user, require_admin, router
from app.database.models import ADMIN_ROLES, UserModel


def _fake_request(user_id=None, username=None):
    return SimpleNamespace(state=SimpleNamespace(user_id=user_id, username=username))


def test_router_paths_registered():
    paths = {route.path for route in router.routes}
    assert router.prefix == "/admin"
    assert "/admin/overview" in paths
    assert "/admin/users" in paths
    assert "/admin/usage" in paths


async def test_require_admin_rejects_anonymous():
    with pytest.raises(HTTPException) as exc:
        await require_admin(_fake_request())
    assert exc.value.status_code == 401


def test_admin_roles_are_admin():
    assert "super_admin" in ADMIN_ROLES
    assert "ops" in ADMIN_ROLES
    assert "support" in ADMIN_ROLES
    assert "viewer" in ADMIN_ROLES
    assert "user" not in ADMIN_ROLES


def test_user_model_is_admin_property():
    user = UserModel(username="u1", password_hash="x")
    user.role = "user"
    assert user.is_admin is False
    user.role = "ops"
    assert user.is_admin is True


def test_serialize_user_merges_counts():
    user = UserModel(username="demo", password_hash="x")
    user.id = __import__("uuid").uuid4()
    user.role = "support"
    user.is_active = True
    user.created_at = None
    user.last_login_at = None
    user.occupation = None

    counts = {
        str(user.id): {
            "conversations": 3,
            "agent_sessions": 2,
            "diet_log_items": 11,
            "pantry_items": 5,
            "llm_calls": 42,
            "tokens": 12345,
        }
    }
    payload = _serialize_user(user, counts)

    assert payload["username"] == "demo"
    assert payload["role"] == "support"
    assert payload["is_active"] is True
    assert payload["counts"]["conversations"] == 3
    assert payload["counts"]["tokens"] == 12345


def test_serialize_user_without_counts_defaults_to_zero():
    user = UserModel(username="empty", password_hash="x")
    user.id = __import__("uuid").uuid4()
    user.role = "user"
    user.is_active = False
    user.created_at = None
    user.last_login_at = None
    user.occupation = "student"

    payload = _serialize_user(user, {})

    assert payload["is_active"] is False
    assert payload["occupation"] == "student"
    assert all(value == 0 for value in payload["counts"].values())
