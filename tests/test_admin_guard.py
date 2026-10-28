"""后台护栏的单元测试：写操作限流、失败审计动作映射、双因子强制策略。"""

import time

from app.security.admin_rate_limit import SlidingWindowLimiter


def test_sliding_window_blocks_after_limit():
    limiter = SlidingWindowLimiter(limit=3, window_seconds=60)
    assert all(limiter.allow("admin") for _ in range(3))
    assert limiter.allow("admin") is False
    # 其他账号不受影响
    assert limiter.allow("other") is True


def test_sliding_window_expires():
    limiter = SlidingWindowLimiter(limit=1, window_seconds=0.2)
    assert limiter.allow("admin") is True
    assert limiter.allow("admin") is False
    time.sleep(0.25)
    assert limiter.allow("admin") is True


def test_admin_action_mapping():
    from app.main import _admin_action_of

    assert _admin_action_of("/api/v1/admin/users/{user_id}/status") == ("user.status", "user")
    assert _admin_action_of("/api/v1/admin/users/{user_id}/role") == ("user.role", "user")
    assert _admin_action_of("/api/v1/admin/users/{user_id}/reset-password") == (
        "user.reset_password",
        "user",
    )
    assert _admin_action_of("/api/v1/admin/users") == ("user.create", "user")
    assert _admin_action_of("/api/v1/admin/users/{user_id}") == ("user.delete", "user")
    assert _admin_action_of("/api/v1/admin/alerts/check") == ("alert.check", "alert")

