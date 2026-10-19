"""SU-13 约束解析测试（离线）。"""

from app.reasoning.constraints.models import (
    ConstraintKind,
    ConstraintSeverity,
)
from app.reasoning.constraints.parser import parse_constraints


def _find(profile, kind, value=None):
    return [
        item
        for item in profile.constraints
        if item.kind is kind and (value is None or item.value == value)
    ]


def test_peanut_allergy_from_slot_is_hard():
    profile = parse_constraints(diet_constraints=["花生过敏"])
    items = _find(profile, ConstraintKind.ALLERGEN, "peanut")
    assert len(items) == 1
    assert items[0].severity is ConstraintSeverity.HARD
    assert items[0].source == "slot"


def test_milk_allergy_from_text():
    profile = parse_constraints(text="我对牛奶过敏")
    items = _find(profile, ConstraintKind.ALLERGEN, "milk")
    assert len(items) == 1
    assert items[0].severity is ConstraintSeverity.HARD
    assert items[0].source == "text"


def test_vegan_implies_vegetarian():
    profile = parse_constraints(text="我是纯素")
    assert _find(profile, ConstraintKind.DIET, "vegan")
    assert _find(profile, ConstraintKind.DIET, "vegetarian")


def test_gluten_free_is_hard_and_nutrition_is_soft():
    profile = parse_constraints(text="无麸质，低脂，高蛋白")
    assert _find(profile, ConstraintKind.DIET, "gluten_free")
    low_fat = _find(profile, ConstraintKind.NUTRITION, "low_fat")
    high_protein = _find(profile, ConstraintKind.NUTRITION, "high_protein")
    assert low_fat and low_fat[0].severity is ConstraintSeverity.SOFT
    assert high_protein and high_protein[0].severity is ConstraintSeverity.SOFT


def test_explicit_pork_exclusion():
    profile = parse_constraints(text="不吃猪肉")
    items = _find(profile, ConstraintKind.EXCLUDE_INGREDIENT, "猪肉")
    assert len(items) == 1
    assert items[0].severity is ConstraintSeverity.HARD


def test_duplicate_constraints_are_deduplicated_and_slot_wins():
    profile = parse_constraints(
        text="花生过敏",
        diet_constraints=["花生过敏", "花生过敏"],
    )
    items = _find(profile, ConstraintKind.ALLERGEN, "peanut")
    assert len(items) == 1
    assert items[0].source == "slot"


def test_explicit_cilantro_exclusion():
    profile = parse_constraints(text="不要放香菜")
    assert _find(profile, ConstraintKind.EXCLUDE_INGREDIENT, "香菜")


def test_unknown_constraint_is_not_dropped():
    profile = parse_constraints(text="不要放某某神秘酱")
    assert "某某神秘酱" in profile.unknown_terms


def test_ingredient_slot_is_soft_include():
    profile = parse_constraints(ingredients=["鸡蛋"])
    items = _find(profile, ConstraintKind.INCLUDE_INGREDIENT, "鸡蛋")
    assert len(items) == 1
    assert items[0].severity is ConstraintSeverity.SOFT
    assert items[0].source == "slot"


def test_taste_slot_is_soft():
    profile = parse_constraints(tastes=["微辣"])
    items = _find(profile, ConstraintKind.TASTE, "mild")
    assert items and items[0].severity is ConstraintSeverity.SOFT
