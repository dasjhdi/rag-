"""Rate limiter middleware: counter isolation between endpoint scopes."""

import pytest
from starlette.requests import Request

from app.security.middleware.rate_limiter import RateLimitConfig, RateLimiter


class FakeRedis:
    """Minimal async Redis stub supporting INCR + EXPIRE."""

    def __init__(self) -> None:
        self.store: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    async def expire(self, key: str, ttl: int) -> bool:
        return True


def make_request(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST" if path.endswith(("login", "register")) else "GET",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 51000),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch):
    """Pin the sliding window so a test run cannot straddle a minute boundary."""
    monkeypatch.setattr(
        "app.security.middleware.rate_limiter.time.time", lambda: 1_700_000_000.0
    )
    return 1_700_000_000.0


@pytest.fixture
def limiter() -> RateLimiter:
    return RateLimiter(
        redis_client=FakeRedis(),
        config=RateLimitConfig(
            global_per_minute=100,
            login_per_minute=5,
            conversation_per_minute=30,
            window_seconds=60,
            enabled=True,
        ),
    )


@pytest.mark.asyncio
async def test_general_traffic_does_not_consume_login_budget(limiter):
    """A page load firing many list requests must not block a login attempt."""
    for _ in range(20):
        assert await limiter.check_rate_limit(make_request("/api/v1/agent/tools")) is None

    assert await limiter.check_rate_limit(make_request("/api/v1/auth/login")) is None


@pytest.mark.asyncio
async def test_login_scope_blocks_after_limit(limiter):
    for _ in range(5):
        assert await limiter.check_rate_limit(make_request("/api/v1/auth/login")) is None

    response = await limiter.check_rate_limit(make_request("/api/v1/auth/login"))

    assert response is not None
    assert response.status_code == 429
    assert response.headers["X-RateLimit-Limit"] == "5"


@pytest.mark.asyncio
async def test_scopes_use_distinct_keys(limiter):
    await limiter.check_rate_limit(make_request("/api/v1/agent/tools"))
    await limiter.check_rate_limit(make_request("/api/v1/auth/login"))
    await limiter.check_rate_limit(make_request("/api/v1/conversation"))

    keys = set(limiter.redis.store)
    assert any(":global:" in key for key in keys)
    assert any(":login:" in key for key in keys)
    assert any(":conversation:" in key for key in keys)
    assert len(keys) == 3


@pytest.mark.asyncio
async def test_conversation_limit_is_independent(limiter):
    for _ in range(30):
        assert (
            await limiter.check_rate_limit(make_request("/api/v1/conversation"))
            is None
        )

    response = await limiter.check_rate_limit(make_request("/api/v1/conversation"))
    assert response is not None
    assert response.headers["X-RateLimit-Limit"] == "30"

    # The login budget is untouched by conversation traffic.
    assert await limiter.check_rate_limit(make_request("/api/v1/auth/login")) is None
