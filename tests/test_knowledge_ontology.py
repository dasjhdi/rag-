"""SU-5 食材与过敏原本体测试（离线）。"""

from app.knowledge.ontology import (
    allergens_for,
    canonicalize_ingredients,
    diet_tags_for,
    explain_allergens,
    normalize_ingredient,
)


def test_alias_normalization_maps_to_one_canonical_name():
    assert normalize_ingredient("土豆") == "土豆"
    assert normalize_ingredient("洋芋") == "土豆"
    assert normalize_ingredient("马铃薯") == "土豆"
    assert normalize_ingredient("  Potato  ") == "土豆"


def test_unknown_ingredient_is_returned_cleaned():
    assert normalize_ingredient("  神秘食材  ") == "神秘食材"
    assert normalize_ingredient("") == ""


def test_canonicalize_deduplicates_and_preserves_order():
    result = canonicalize_ingredients(
        ["番茄", "西红柿", " 番茄 ", "鸡蛋", "", "鸡蛋"]
    )
    assert result == ["番茄", "鸡蛋"]


def test_empty_input_returns_empty_results():
    assert canonicalize_ingredients([]) == []
    assert allergens_for([]) == set()
    assert diet_tags_for([]) == set()
    assert explain_allergens([]) == {}


def test_allergens_cover_direct_and_alias_hits():
    assert allergens_for(["花生"]) == {"peanut"}
    assert allergens_for(["花生酱"]) == {"peanut"}
    assert allergens_for(["花生米"]) == {"peanut"}
    assert allergens_for("花生") == {"peanut"}


def test_allergens_union_multiple_ingredients():
    assert allergens_for(["鸡蛋", "牛奶", "花生"]) == {
        "egg",
        "milk",
        "peanut",
    }


def test_compound_allergens_for_soy_sauce():
    assert allergens_for(["酱油"]) == {"soy", "wheat"}
    assert allergens_for(["生抽"]) == {"soy", "wheat"}


def test_explain_allergens_lists_contributors():
    explanation = explain_allergens(["花生酱", "花生", "牛奶"])
    assert explanation["peanut"] == ["花生", "花生酱"]
    assert explanation["milk"] == ["牛奶"]


def test_vegetarian_and_vegan_tags_are_derived_from_all_ingredients():
    tags = diet_tags_for(["豆腐", "番茄", "土豆"])
    assert {"vegetarian", "vegan", "gluten_free"} <= tags


def test_egg_is_vegetarian_but_not_vegan():
    tags = diet_tags_for(["鸡蛋", "番茄"])
    assert "vegetarian" in tags
    assert "vegan" not in tags
    assert "gluten_free" in tags


def test_meat_excludes_vegetarian_and_vegan():
    tags = diet_tags_for(["五花肉", "番茄"])
    assert "vegetarian" not in tags
    assert "vegan" not in tags


def test_wheat_excludes_gluten_free():
    tags = diet_tags_for(["面粉", "番茄"])
    assert "vegetarian" in tags
    assert "vegan" in tags
    assert "gluten_free" not in tags


def test_unknown_ingredient_does_not_raise_and_returns_empty_tags():
    assert allergens_for(["龙涎香"]) == set()
    assert diet_tags_for(["龙涎香"]) == set()
    assert diet_tags_for("龙涎香") == set()


def test_unknown_ingredient_is_ignored_in_diet_intersection():
    tags = diet_tags_for(["豆腐", "龙涎香"])
    assert {"vegetarian", "vegan", "gluten_free"} <= tags


def test_case_and_whitespace_are_ignored_for_aliases():
    assert allergens_for(["  PEANUT  "]) == {"peanut"}
