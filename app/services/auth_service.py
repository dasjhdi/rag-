"""
Authentication service for CookHero.

Provides user registration, password hashing, and JWT token generation.
Includes security features: account lockout after failed attempts.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

import bcrypt
from jose import jwt
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from redis.asyncio import Redis

from app.config import settings
from app.database.models import UserModel
from app.database.session import get_session_context

logger = logging.getLogger(__name__)


class AuthService:
    """Service for user authentication and registration with security features."""

    def __init__(self, secret_key: str | None = None):
        self.secret_key = secret_key or settings.JWT_SECRET_KEY
        self.algorithm = settings.JWT_ALGORITHM
        self.expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        self.refresh_days = settings.REFRESH_TOKEN_EXPIRE_DAYS
        self.max_failed_attempts = settings.LOGIN_MAX_FAILED_ATTEMPTS
        self.lockout_minutes = settings.LOGIN_LOCKOUT_MINUTES
        self._redis: Optional[Redis] = None

    def set_redis(self, redis_client: Redis) -> None:
        """Set Redis client for login attempt tracking."""
        self._redis = redis_client

    # ------------------------------------------------------------------
    # Login attempt tracking (account lockout protection)
    # ------------------------------------------------------------------
    async def _get_failed_attempts_key(self, username: str) -> str:
        """Generate Redis key for tracking failed login attempts."""
        return f"auth:failed_attempts:{username}"

    async def _get_lockout_key(self, username: str) -> str:
        """Generate Redis key for account lockout."""
        return f"auth:lockout:{username}"

    async def is_account_locked(self, username: str) -> Tuple[bool, int]:
        """
        Check if account is locked due to too many failed attempts.

        Returns:
            Tuple of (is_locked, remaining_seconds)
        """
        if not self._redis:
            return False, 0

        lockout_key = await self._get_lockout_key(username)
        ttl = await self._redis.ttl(lockout_key)

        if ttl > 0:
            return True, ttl

        return False, 0

    async def record_failed_attempt(self, username: str) -> Tuple[int, bool]:
        """
        Record a failed login attempt.

        Returns:
            Tuple of (current_attempts, is_now_locked)
        """
        if not self._redis:
            return 0, False

        failed_key = await self._get_failed_attempts_key(username)
        lockout_key = await self._get_lockout_key(username)

        # Increment failed attempts
        attempts = await self._redis.incr(failed_key)

        # Set expiry on the counter (reset after lockout period)
        await self._redis.expire(failed_key, self.lockout_minutes * 60)

        # Check if we need to lock the account
        if attempts >= self.max_failed_attempts:
            # Lock the account
            await self._redis.setex(
                lockout_key,
                self.lockout_minutes * 60,
                "locked"
            )
            logger.warning(f"Account locked: {username} after {attempts} failed attempts")
            return attempts, True

        return attempts, False

    async def clear_failed_attempts(self, username: str) -> None:
        """Clear failed login attempts after successful login."""
        if not self._redis:
            return

        failed_key = await self._get_failed_attempts_key(username)
        lockout_key = await self._get_lockout_key(username)

        await self._redis.delete(failed_key, lockout_key)

    # ------------------------------------------------------------------
    # User retrieval helpers
    # ------------------------------------------------------------------
    async def get_user_by_username(self, username: str) -> Optional[UserModel]:
        async with get_session_context() as session:
            stmt = select(UserModel).where(UserModel.username == username)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Registration & authentication
    # ------------------------------------------------------------------
    async def register_user(self, username: str, password: str) -> UserModel:
        existing = await self.get_user_by_username(username)
        if existing:
            raise ValueError("Username already exists")

        password_hash = self._hash_password(password)
        user = UserModel(username=username, password_hash=password_hash)

        async with get_session_context() as session:
            session.add(user)
            try:
                await session.flush()
            except IntegrityError as exc:
                logger.warning("Integrity error on user register: %s", exc)
                raise ValueError("Username already exists")

        logger.info("Created user %s", username)
        return user

    async def authenticate_user(self, username: str, password: str) -> Optional[UserModel]:
        user = await self.get_user_by_username(username)
        if not user:
            return None
        if not self._verify_password(password, user.password_hash):
            return None
        # Disabled accounts must not be able to log in, even with a valid password.
        if not getattr(user, "is_active", True):
            logger.warning("Rejected login for disabled user %s", username)
            return None
        return user

    async def touch_last_login(self, username: str) -> None:
        """Record a successful login timestamp (best effort, never blocks login)."""
        try:
            async with get_session_context() as session:
                stmt = (
                    update(UserModel)
                    .where(UserModel.username == username)
                    .values(last_login_at=datetime.utcnow())
                )
                await session.execute(stmt)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to update last_login_at for %s: %s", username, exc)

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------
    def create_access_token(self, user: UserModel) -> str:
        expire = datetime.now() + timedelta(minutes=self.expire_minutes)
        payload = {
            "sub": user.username,
            "uid": str(user.id),
            "exp": expire,
            "typ": "access",
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def create_refresh_token(self, user: UserModel) -> str:
        """Long-lived token used only by POST /auth/refresh."""
        expire = datetime.now() + timedelta(days=self.refresh_days)
        payload = {
            "sub": user.username,
            "uid": str(user.id),
            "exp": expire,
            "typ": "refresh",
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def decode_token(self, token: str) -> Optional[dict]:
        """Decode an ACCESS token. Refresh tokens are rejected here on purpose."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            # 旧版本令牌没有 typ 字段，按访问令牌处理以保持向后兼容
            if payload.get("typ", "access") != "access":
                logger.warning("Rejected non-access token at access endpoint")
                return None
            return {"username": payload.get("sub"), "user_id": payload.get("uid")}
        except Exception as exc:  # broad catch to avoid import of ExpiredSignatureError etc
            logger.warning("Failed to decode token: %s", exc)
            return None

    def decode_refresh_token(self, token: str) -> Optional[dict]:
        """Decode a REFRESH token. Access tokens are rejected here on purpose."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            if payload.get("typ") != "refresh":
                logger.warning("Rejected non-refresh token at /auth/refresh")
                return None
            return {"username": payload.get("sub"), "user_id": payload.get("uid")}
        except Exception as exc:
            logger.warning("Failed to decode refresh token: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Password helpers
    # ------------------------------------------------------------------
    def _hash_password(self, password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    def _verify_password(self, password: str, hashed: str) -> bool:
        try:
            return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
        except ValueError:
            return False


auth_service = AuthService()
