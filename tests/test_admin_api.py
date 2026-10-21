"""后台管理接口测试（离线）。

覆盖无数据库也能验证的部分：
- 路由注册与前缀（含 v1.1–v1.3 新增的会话、审计、写操作）
- 匿名请求被拒绝（401）
- 能力矩阵与 require_capability 的越权拦截
- 用户序列化中的计数合并与默认值
- 成本估算（含模型单价覆盖与兜底）
- 后台限流滑动窗口

需要数据库的端到端行为（管理员 200 / 普通用户 403 / 写操作生效）
由真实请求验证，见交付说明。
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.admin import (
    ASSIGNABLE_ROLES,
    CAPABILITIES,
    _serialize_user,
    get_current_user,
    require_admin,
    require_capability,
    router,
)
from app.database.models import ADMIN_ROLES, UserModel
from app.security.admin_rate_limit import SlidingWindowLimiter
from app.services import pricing


def _fake_request(user_id=None, username=None):
    return SimpleNamespace(state=SimpleNamespace(user_id=user_id, username=username))


def _user(role: str = "user", is_active: bool = True) -> UserModel:
    user = UserModel(username=f"u_{role}", password_hash="x")
    user.id = uuid4()
    user.role = role
    user.is_active = is_active
    return user


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------
def test_router_paths_registered():
    paths = {route.path for route in router.routes}
    assert router.prefix == "/admin"
    for expected in (
        "/admin/whoami",
        "/admin/overview",
        "/admin/users",
        "/admin/usage",
        "/admin/audit",
        "/admin/sessions",
        "/admin/sessions/{session_id}",
        "/admin/users/{user_id}/status",
        "/admin/users/{user_id}/role",
        "/admin/users/{user_id}/reset-password",
    ):
        assert expected in paths, f"缺少路由 {expected}"


# ---------------------------------------------------------------------------
# 身份与权限
# ---------------------------------------------------------------------------
async def test_get_current_user_rejects_anonymous():
    with pytest.raises(HTTPException) as exc:
        await get_current_user(_fake_request())
    assert exc.value.status_code == 401


async def test_require_admin_rejects_plain_user():
    with pytest.raises(HTTPException) as exc:
        await require_admin(_user("user"))
    assert exc.value.status_code == 403


async def test_require_admin_accepts_every_admin_role():
    for role in ADMIN_ROLES:
        user = await require_admin(_user(role))
        assert user.role == role


def test_capability_matrix_is_consistent():
    # 每个后台角色都必须能读
    for role in ADMIN_ROLES:
        assert "read" in CAPABILITIES[role], f"{role} 缺少 read 权限"
    # 普通用户不在矩阵里
    assert "user" not in CAPABILITIES
    # 只有超管能动角色和看审计
    for role in ADMIN_ROLES - {"super_admin"}:
        assert "user_role" not in CAPABILITIES[role]
        assert "audit" not in CAPABILITIES[role]
    # ops 管账号但不管角色
    assert "user_status" in CAPABILITIES["ops"]
    assert "user_role" not in CAPABILITIES["ops"]
    # support 只能看会话，不能改账号
    assert "sessions" in CAPABILITIES["support"]
    assert "user_status" not in CAPABILITIES["support"]


async def test_viewer_cannot_manage_users():
    dep = require_capability("user_status")
    with pytest.raises(HTTPException) as exc:
        await dep(_user("viewer"))
    assert exc.value.status_code == 403


async def test_super_admin_can_manage_roles():
    dep = require_capability("user_role")
    user = await dep(_user("super_admin"))
    assert user.role == "super_admin"


def test_assignable_roles_cover_user_and_admins():
    assert "user" in ASSIGNABLE_ROLES
    for role in ADMIN_ROLES:
        assert role in ASSIGNABLE_ROLES


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------
def test_user_model_is_admin_property():
    user = _user("user")
    assert user.is_admin is False
    user.role = "ops"
    assert user.is_admin is True


def test_serialize_user_merges_counts():
    user = _user("support")
    user.created_at = None
    user.last_login_at = None
    user.occupation = "student"

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

    assert payload["role"] == "support"
    assert payload["is_active"] is True
    assert payload["counts"]["conversations"] == 3
    assert payload["counts"]["tokens"] == 12345


def test_serialize_user_without_counts_defaults_to_zero():
    user = _user("user", is_active=False)
    user.created_at = None
    user.last_login_at = None
    user.occupation = "teacher"

    payload = _serialize_user(user, {})

    assert payload["is_active"] is False
    assert payload["occupation"] == "teacher"
    assert all(value == 0 for value in payload["counts"].values())


# ---------------------------------------------------------------------------
# 成本估算
# ---------------------------------------------------------------------------
def test_pricing_default_fallback():
    pricing.reset_cache()
    cost = pricing.estimate_cost("完全不存在的模型", 1000, 1000)
    default = pricing.price_for(None)
    assert cost == round(default["input"] + default["output"], 4)


def test_pricing_uses_model_override():
    pricing.reset_cache()
    model = "deepseek-ai/DeepSeek-V3.2"
    price = pricing.price_for(model)
    cost = pricing.estimate_cost(model, 10_000, 2_000)
    expected = round(10_000 / 1000 * price["input"] + 2_000 / 1000 * price["output"], 4)
    assert cost == expected
    assert cost > 0


def test_pricing_handles_none_tokens():
    pricing.reset_cache()
    assert pricing.estimate_cost("any", None, None) == 0.0


def test_pricing_currency_is_configured():
    pricing.reset_cache()
    assert pricing.currency() in {"CNY", "USD"}


# ---------------------------------------------------------------------------
# 后台限流
# ---------------------------------------------------------------------------
def test_rate_limiter_blocks_after_limit():
    limiter = SlidingWindowLimiter(limit=3, window_seconds=60)
    assert limiter.allow("alice") is True
    assert limiter.allow("alice") is True
    assert limiter.allow("alice") is True
    assert limiter.allow("alice") is False
    # 其他账号不受影响
    assert limiter.allow("bob") is True


def test_rate_limiter_reset():
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60)
    assert limiter.allow("carol") is True
    assert limiter.allow("carol") is False
    limiter.reset()
    assert limiter.allow("carol") is True
