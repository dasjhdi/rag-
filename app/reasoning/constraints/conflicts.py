"""约束冲突检测与澄清问题生成（SU-16）。"""

from __future__ import annotations

from typing import Optional, Sequence

from app.knowledge.ontology import allergens_for, normalize_ingredient
from app.reasoning.constraints.models import (
    ConstraintKind,
    ConstraintProfile,
)
from app.reasoning.constraints.parser import ALLERGEN_LABELS


def detect_conflicts(profile: ConstraintProfile) -> list[str]:
    """识别约束之间的直接矛盾，返回中文可读冲突列表。"""
    if profile is None or profile.is_empty:
        return []

    diets = {
        item.value
        for item in profile.constraints
        if item.kind is ConstraintKind.DIET
    }
    allergens = {
        item.value
        for item in profile.constraints
        if item.kind is ConstraintKind.ALLERGEN
    }
    includes = [
        normalize_ingredient(item.value)
        for item in profile.constraints
        if item.kind is ConstraintKind.INCLUDE_INGREDIENT
    ]
    excludes = [
        normalize_ingredient(item.value)
        for item in profile.constraints
        if item.kind is ConstraintKind.EXCLUDE_INGREDIENT
    ]

    conflicts: list[str] = []
    seen: set[str] = set()

    def add(message: str) -> None:
        if message not in seen:
            seen.add(message)
            conflicts.append(message)

    for ingredient in includes:
        from app.reasoning.constraints.evaluator import diet_offenders

        if "vegan" in diets and diet_offenders("vegan", [ingredient]):
            add(f"纯素饮食与食材「{ingredient}」冲突")

        if "vegetarian" in diets and diet_offenders("vegetarian", [ingredient]):
            add(f"素食饮食与食材「{ingredient}」冲突")

        if "gluten_free" in diets and diet_offenders("gluten_free", [ingredient]):
            add(f"无麸质饮食与食材「{ingredient}」冲突")

        for allergen in sorted(allergens):
            if allergen in allergens_for([ingredient]):
                label = ALLERGEN_LABELS.get(allergen, allergen)
                add(f"过敏原「{label}」与食材「{ingredient}」冲突")

        for excluded in excludes:
            if _ingredient_matches(excluded, ingredient):
                add(f"食材「{ingredient}」同时被要求包含和排除")

    return conflicts


def _ingredient_matches(excluded: str, ingredient: str) -> bool:
    left = normalize_ingredient(excluded)
    right = normalize_ingredient(ingredient)
    if not left or not right:
        return False
    if left == right:
        return True
    from app.reasoning.constraints.evaluator import ingredient_matches

    return ingredient_matches(left, [right])


def build_clarification_question(
    conflicts: Sequence[str],
) -> Optional[str]:
    """把冲突列表转成一句可直接展示给用户的中文问题。"""
    items = [item.strip() for item in conflicts or () if item and item.strip()]
    if not items:
        return None
    preview = "；".join(items[:3])
    if len(items) > 3:
        preview += f"；另有 {len(items) - 3} 项冲突"
    return f"检测到饮食约束冲突：{preview}。请确认您希望优先保留哪一项约束？"


__all__ = ["detect_conflicts", "build_clarification_question"]
