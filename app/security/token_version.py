"""Token versioning — invalidate every issued JWT for one account on demand.

Why this exists
---------------
The access token is a stateless JWT, so changing a password (or logging out)
cannot revoke tokens that were already handed out. Each user therefore carries a
monotonic ``token_version``; every token embeds the value it was minted with and
must still match the current one to be accepted.

Cost
----
Checking on every request means one lookup. To keep it off the hot path we cache
the current version in Redis (7-day TTL, refreshed on read). Cache misses and
Redis outages fall back to a single-column SELECT.
"""

from __future__ import annotations

import logging
from typing import Optional

from redis.asyncio import Redis
from sqlalchemy import select, update

from app.database.models import UserModel
from app.database.session import get_session_context

logger = logging.getLogger(__name__)

_KEY_TEMPLATE = "auth:token_version:{user_id}"
# Short TTL bounds the worst case where a failed cache write leaves a stale
# version behind: an old token could stay valid for at most this long.
_TTL_SECONDS = 300


def _key(user_id: str) -> str:
    return _KEY_TEMPLATE.format(user_id=user_id)


class TokenVersionService:
    """Read / bump the token version of a user."""

    def __init__(self) -> None:
        self._redis: Optional[Redis] = None

    def set_redis(self, redis_client: Redis) -> None:
        self._redis = redis_client

    async def get(self, user_id: Optional[str]) -> Optional[int]:
        """Current version for ``user_id``; ``None`` when the user is unknown."""
        if not user_id:
            return None

        if self._redis is not None:
            try:
                cached = await self._redis.get(_key(user_id))
                if cached is not None:
                    return int(cached)
            except Exception as exc:  # pragma: no cover - cache must never break auth
                logger.warning("Token version cache read failed: %s", exc)

        version = await self._load(user_id)
        if version is not None and self._redis is not None:
            await self._cache(user_id, version)
        return version

    async def matches(self, user_id: Optional[str], token_version: Optional[int]) -> bool:
        """True when the token was minted with the user's current version.

        Tokens issued before this mechanism existed have no ``tv`` claim and are
        treated as version 0, matching the column default.
        """
        current = await self.get(user_id)
        if current is None:
            return False
        return int(token_version or 0) == current

    async def bump(self, user_id: Optional[str]) -> Optional[int]:
        """Invalidate every existing token of the user; returns the new version."""
        if not user_id:
            return None

        try:
            async with get_session_context() as session:
                stmt = (
                    update(UserModel)
                    .where(UserModel.id == user_id)
                    .values(token_version=UserModel.token_version + 1)
                    .returning(UserModel.token_version)
                )
                result = await session.execute(stmt)
                version = result.scalar_one_or_none()
                await session.commit()
        except Exception as exc:
            logger.error("Failed to bump token version for %s: %s", user_id, exc)
            return None

        if version is not None:
            await self._cache(user_id, int(version))
        return int(version) if version is not None else None

    async def set_cached(self, user_id: Optional[str], version: Optional[int]) -> None:
        """Publish a known version without touching the database."""
        if not user_id or version is None:
            return
        await self._cache(user_id, int(version))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    async def _load(self, user_id: str) -> Optional[int]:
        try:
            async with get_session_context() as session:
                result = await session.execute(
                    select(UserModel.token_version).where(UserModel.id == user_id)
                )
                value = result.scalar_one_or_none()
        except Exception as exc:
            # Fail closed: an auth check that cannot be verified must deny.
            # A DB outage already breaks the rest of the API, so this adds no
            # new blast radius, and it prevents a temporary failure from
            # silently accepting a revoked token.
            logger.warning("Token version lookup failed for %s: %s", user_id, exc)
            return None
        return int(value) if value is not None else None

    async def _cache(self, user_id: str, version: int) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.set(_key(user_id), int(version), ex=_TTL_SECONDS)
        except Exception as exc:  # pragma: no cover
            logger.warning("Token version cache write failed: %s", exc)


token_version_service = TokenVersionService()
