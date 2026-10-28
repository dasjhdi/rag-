"""Idempotent schema upgrades for databases created before new columns existed."""

from __future__ import annotations

import logging
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


_COLUMN_MIGRATIONS: tuple[tuple[str, str, str], ...] = (
    # Admin console: access control + activity tracking on users
    ("users", "role", "VARCHAR(20) NOT NULL DEFAULT 'user'"),
    ("users", "is_active", "BOOLEAN NOT NULL DEFAULT TRUE"),
    ("users", "last_login_at", "TIMESTAMP"),
    ("users", "token_version", "INTEGER NOT NULL DEFAULT 0"),
    # 双因子：secret 加密落库，恢复码只存哈希
    ("users", "totp_secret", "TEXT"),
    ("users", "totp_enabled", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ("users", "totp_confirmed_at", "TIMESTAMP"),
    ("users", "totp_last_counter", "INTEGER NOT NULL DEFAULT 0"),
    ("users", "totp_recovery_codes", "JSON"),
    # 审计：失败也要留痕，并把前后值结构化
    ("admin_audit_logs", "success", "BOOLEAN NOT NULL DEFAULT TRUE"),
    ("admin_audit_logs", "error", "VARCHAR(300)"),
    ("admin_audit_logs", "before", "JSON"),
    ("admin_audit_logs", "after", "JSON"),
    ("admin_audit_logs", "request_id", "VARCHAR(64)"),
    ("admin_audit_logs", "user_agent", "VARCHAR(300)"),
    # 用量：区分成功/失败，用于错误率告警
    ("llm_usage_logs", "status", "VARCHAR(20) NOT NULL DEFAULT 'success'"),
    ("llm_usage_logs", "error_type", "VARCHAR(80)"),
    ("diet_plan_meals", "status", "VARCHAR(20) NOT NULL DEFAULT 'planned'"),
    ("diet_plan_meals", "locked", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ("diet_plan_meals", "generation_batch_id", "VARCHAR(64)"),
    ("diet_plan_meals", "servings", "DOUBLE PRECISION"),
    ("diet_log_items", "nutrition_source", "VARCHAR(50)"),
    ("diet_log_items", "nutrition_confidence", "VARCHAR(20)"),
    ("user_food_preferences", "allergies", "JSON"),
    ("user_food_preferences", "allergy_severity", "JSON"),
    ("user_food_preferences", "dietary_restrictions", "JSON"),
    ("user_food_preferences", "favorite_cuisines", "JSON"),
    ("user_food_preferences", "preferred_foods", "JSON"),
    ("user_food_preferences", "health_conditions", "JSON"),
    ("user_food_preferences", "calorie_goal", "INTEGER"),
    ("user_food_preferences", "protein_goal", "DOUBLE PRECISION"),
    ("user_food_preferences", "fat_goal", "DOUBLE PRECISION"),
    ("user_food_preferences", "carbs_goal", "DOUBLE PRECISION"),
    ("user_food_preferences", "fiber_goal", "DOUBLE PRECISION"),
    ("user_food_preferences", "sodium_goal", "DOUBLE PRECISION"),
    ("user_food_preferences", "meals_per_day", "INTEGER NOT NULL DEFAULT 3"),
    (
        "user_food_preferences",
        "cooking_skill",
        "VARCHAR(20) NOT NULL DEFAULT 'intermediate'",
    ),
    ("user_food_preferences", "max_cook_minutes", "INTEGER NOT NULL DEFAULT 60"),
    (
        "user_food_preferences",
        "budget_level",
        "VARCHAR(20) NOT NULL DEFAULT 'medium'",
    ),
    ("user_food_preferences", "household_size", "INTEGER NOT NULL DEFAULT 1"),
    (
        "user_food_preferences",
        "unit_system",
        "VARCHAR(20) NOT NULL DEFAULT 'metric'",
    ),
    (
        "user_food_preferences",
        "spice_level",
        "VARCHAR(20) NOT NULL DEFAULT 'medium'",
    ),
    ("user_food_preferences", "version", "INTEGER NOT NULL DEFAULT 1"),
)


# 数据迁移：只做「收敛权限」这类幂等操作，绝不放大权限。
#
# 角色模型从 5 种收敛为 3 种（user / admin / super_admin）。旧的
# viewer / support / ops 统一降为普通用户：它们在旧模型里权限各不相同，
# 若自动映射到新的 admin，会凭空获得「重置密码、启停账号」等更宽的能力，
# 属于权限放大。需要后台权限的账号请由超管在管理后台显式改为 admin。
_DATA_MIGRATIONS: tuple[str, ...] = (
    "UPDATE users SET role = 'user' "
    "WHERE role NOT IN ('user', 'admin', 'super_admin')",
)



# 新列上的索引：create_all 不会给已存在的表补索引，这里显式补齐。
_INDEX_MIGRATIONS: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS ix_admin_audit_success ON admin_audit_logs (success)",
    "CREATE INDEX IF NOT EXISTS ix_admin_audit_request_id ON admin_audit_logs (request_id)",
    "CREATE INDEX IF NOT EXISTS ix_llm_usage_status ON llm_usage_logs (status)",
    "CREATE INDEX IF NOT EXISTS ix_alert_events_kind_created ON alert_events (kind, created_at DESC)",
)

async def apply_schema_migrations(engine: AsyncEngine) -> None:
    """Add columns that ``create_all`` cannot add to existing tables."""
    if engine.dialect.name != "postgresql":
        return

    statements: Iterable[str] = (
        f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl}'
        for table, column, ddl in _COLUMN_MIGRATIONS
    )

    async with engine.begin() as connection:
        for statement in statements:
            try:
                await connection.execute(text(statement))
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Schema migration skipped (%s): %s", statement, exc)

        for statement in _INDEX_MIGRATIONS:
            try:
                await connection.execute(text(statement))
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Index migration skipped (%s): %s", statement, exc)

        for statement in _DATA_MIGRATIONS:
            try:
                result = await connection.execute(text(statement))
                if result.rowcount and result.rowcount > 0:
                    logger.info(
                        "Data migration applied (%s rows): %s",
                        result.rowcount,
                        statement,
                    )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Data migration skipped (%s): %s", statement, exc)
