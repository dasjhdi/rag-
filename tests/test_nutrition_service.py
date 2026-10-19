"""Nutrition table, unit conversion and traceability tests (offline)."""

from app.diet.nutrition.service import (
    convert_quantity,
    enrich_food_item,
    estimate_nutrition,
    lookup_food,
    nutrition_coverage,
    search_foods,
)


def test_chicken_breast_matches_local_table():
    food = lookup_food("鸡胸肉")
    assert food is not None
    assert food["per_100g"]["calories"] == 133
    result = estimate_nutrition([{"food_name": "鸡胸肉", "quantity": 100, "unit": "g"}])
    assert result["totals"]["calories"] == 133.0
    assert result["totals"]["protein"] == 19.4
    assert result["confidence"] == "high"


def test_two_eggs_convert_to_about_100g():
    result = convert_quantity(2, "个", "鸡蛋")
    assert result["grams"] == 100.0
    assert result["known_unit"] is True
    assert result["confidence"] in {"medium", "high"}


def test_one_cup_milk_has_240_milliliters():
    result = convert_quantity(1, "杯", "牛奶")
    assert result["milliliters"] == 240.0
    assert result["grams"] == 247.2
    assert result["known_unit"] is True


def test_unknown_food_returns_low_confidence():
    result = estimate_nutrition([{"food_name": "神秘料理", "quantity": 1, "unit": "份"}])
    assert result["confidence"] == "low"
    assert result["coverage"] == 0.0
    assert result["items"][0]["nutrition_confidence"] == "low"
    assert result["items"][0]["nutrition_reason"]


def test_unknown_unit_does_not_silently_become_grams():
    result = convert_quantity(1, "神秘单位", "鸡胸肉")
    assert result["grams"] is None
    assert result["known_unit"] is False
    assert result["confidence"] == "low"


def test_enrich_food_item_only_fills_missing_fields():
    item = {"food_name": "鸡胸肉", "weight_g": 100, "calories": 999}
    enriched = enrich_food_item(item)
    assert enriched["calories"] == 999
    assert enriched["protein"] == 19.4
    assert enriched["nutrition_source"] == "local_food_table"
    assert enriched["nutrition_confidence"] == "high"


def test_nutrition_coverage_counts_traceable_items():
    coverage = nutrition_coverage(
        [
            {"nutrition_source": "local_food_table"},
            {"nutrition_confidence": "medium"},
            {"nutrition_confidence": "low"},
        ]
    )
    assert coverage["known_items"] == 2
    assert coverage["total_items"] == 3
    assert coverage["coverage"] == 0.667
    assert coverage["confidence"] == "medium"


def test_search_foods_matches_alias():
    results = search_foods("鸡胸", limit=10)
    assert any(item["name"] == "鸡胸肉" for item in results)
