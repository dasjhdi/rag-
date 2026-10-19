"""Pantry aggregation, inventory subtraction and cookable ranking tests."""

from datetime import date

from app.diet.pantry.service import (
    aggregate_plan_ingredients,
    apply_inventory,
    coverage_for_recipe,
    rank_cookable_recipes,
    select_expiring_items,
)
from app.diet.recipes.parser import ParsedIngredient, ParsedRecipe


def test_aggregate_same_ingredient_across_meals():
    meals = [
        {
            "dishes": [
                {
                    "recipe_id": "r1",
                    "ingredients": [
                        {"name": "鸡胸肉", "quantity": 200, "unit": "g"},
                        {"name": "番茄", "quantity": 2, "unit": "个"},
                    ],
                }
            ]
        },
        {
            "dishes": [
                {
                    "recipe_id": "r2",
                    "ingredients": [
                        {"name": "鸡胸肉", "quantity": 150, "unit": "g"},
                        {"name": "番茄", "quantity": 1, "unit": "个"},
                    ],
                }
            ]
        },
    ]
    items = aggregate_plan_ingredients(meals)
    chicken = next(item for item in items if item["name"] == "鸡胸肉")
    tomato = next(item for item in items if item["name"] == "番茄")
    assert chicken["quantity"] == 350.0
    assert chicken["unit"] == "g"
    assert chicken["recipe_ids"] == ["r1", "r2"]
    assert tomato["quantity"] == 3.0


def test_apply_inventory_subtracts_and_removes_satisfied_items():
    requirements = [
        {"name": "鸡胸肉", "normalized_name": "鸡胸肉", "quantity": 500, "unit": "g"},
        {"name": "番茄", "normalized_name": "番茄", "quantity": 2, "unit": "个"},
    ]
    pantry = [
        {"name": "鸡胸肉", "normalized_name": "鸡胸肉", "quantity": 200, "unit": "g"},
        {"name": "番茄", "normalized_name": "番茄", "quantity": 3, "unit": "个"},
    ]
    remaining = apply_inventory(requirements, pantry)
    assert len(remaining) == 1
    assert remaining[0]["name"] == "鸡胸肉"
    assert remaining[0]["quantity"] == 300.0


def test_apply_inventory_does_not_mix_units():
    requirements = [
        {"name": "牛奶", "normalized_name": "牛奶", "quantity": 1, "unit": "L"}
    ]
    pantry = [
        {"name": "牛奶", "normalized_name": "牛奶", "quantity": 500, "unit": "ml"}
    ]
    remaining = apply_inventory(requirements, pantry)
    assert remaining[0]["quantity"] == 1.0


def test_select_expiring_items_filters_and_sorts():
    items = [
        {"name": "酸奶", "expires_on": "2026-10-20"},
        {"name": "牛奶", "expires_on": "2026-10-18"},
        {"name": "鸡蛋", "expires_on": "2026-10-25"},
        {"name": "豆腐", "expires_on": None},
    ]
    selected = select_expiring_items(items, days=3, today=date(2026, 10, 17))
    assert [item["name"] for item in selected] == ["牛奶", "酸奶"]


def test_coverage_and_cookable_ranking():
    full = ParsedRecipe(
        recipe_id="full",
        title="全有菜",
        servings=1,
        ingredients=[
            ParsedIngredient(name="鸡蛋", raw_name="鸡蛋"),
            ParsedIngredient(name="番茄", raw_name="番茄"),
        ],
        total_minutes=10,
    )
    partial = ParsedRecipe(
        recipe_id="partial",
        title="缺一菜",
        servings=1,
        ingredients=[
            ParsedIngredient(name="鸡蛋", raw_name="鸡蛋"),
            ParsedIngredient(name="牛肉", raw_name="牛肉"),
        ],
        total_minutes=20,
    )
    coverage = coverage_for_recipe(full, {"鸡蛋", "番茄"})
    assert coverage["coverage"] == 1.0
    ranked = rank_cookable_recipes([partial, full], {"鸡蛋", "番茄"})
    assert [item["recipe_id"] for item in ranked] == ["full", "partial"]
    assert ranked[1]["missing"] == ["牛肉"]
