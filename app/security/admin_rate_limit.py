"""后台接口的独立限流。

后台是高风险面：泄露的 token 可以对全站数据做批量读取，因此不依赖全局限流
（``RATE_LIMIT_ENABLED`` 常被关掉），单独按"登录用户名"做滑动窗口。

实现约束：
* 进程内计数，适用于单实例部署；多 worker 时各自计数，只能作为粗保护。
* 超过阈值直接 429，不做排队。
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Deque, Dict, Optional

from fastapi import HTTPException, Request, status

# 默认：每个账号 60 秒内最多 120 次后台请求
DEFAULT_LIMIT = 120
DEFAULT_WINDOW_SECONDS = 60.0


class SlidingWindowLimiter:
    """Thread-safe sliding-window counter keyed by an arbitrary string."""

    def __init__(self, limit: int = DEFAULT_LIMIT, window_seconds: float = DEFAULT_WINDOW_SECONDS):
        self._limit = limit
        self._window = window_seconds
        self._hits: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self._window
        with self._lock:
            bucket = self._hits.setdefault(key, deque())
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self._limit:
                return False
            bucket.append(now)
            # 顺带清理长期不活跃的 key，避免字典无限增长
            if len(self._hits) > 10_000:
                for k in [k for k, v in self._hits.items() if not v or v[-1] < cutoff]:
                    self._hits.pop(k, None)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


admin_limiter = SlidingWindowLimiter()


async def admin_rate_limit(request: Request) -> None:
    """FastAPI dependency: 429 when the caller exceeds the admin quota."""
    username: Optional[str] = getattr(request.state, "username", None)
    if not username:
        username = request.client.host if request.client else "anonymous"
    if not admin_limiter.allow(username):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="后台请求过于频繁，请稍后再试",
            headers={"Retry-After": str(int(DEFAULT_WINDOW_SECONDS))},
        )
