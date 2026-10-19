"""Idempotent schema upgrades for databases created before new columns existed."""

from __future__ import annotations

import logging
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


_COLUMN_MIGRATIONS: tuple[tuple[str, str, str], ...] = (
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
