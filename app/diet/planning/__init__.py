"""Deterministic weekly meal planning."""

from app.diet.planning.generator import (
    MEAL_CALORIE_SHARES,
    generate_week_plan,
    replace_single_meal,
)

__all__ = ["MEAL_CALORIE_SHARES", "generate_week_plan", "replace_single_meal"]
