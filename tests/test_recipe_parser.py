"""Recipe parsing, scaling and unit conversion tests (offline)."""

from app.diet.recipes.parser import (
    ParsedIngredient,
    ParsedRecipe,
    parse_recipe_document,
    scale_recipe,
)

SAMPLE = """# 番茄炒蛋

2人份

## 必备原料和工具
- 鸡蛋 2 个
- 番茄 300g
- 盐 适量
- 食用油 1 汤匙

## 操作
1. 鸡蛋打散，番茄切块。
2. 热锅加油，炒鸡蛋 2 分钟。
3. 加入番茄翻炒 3 分钟，加盐出锅。
"""


def test_parse_standard_markdown_recipe():
    recipe = parse_recipe_document(
        "recipe-1",
        "番茄炒蛋",
        SAMPLE,
        category="家常菜",
        difficulty="easy",
        source="test",
    )
    assert recipe.servings == 2.0
    assert recipe.title == "番茄炒蛋"
    assert len(recipe.ingredients) == 4
    egg = next(item for item in recipe.ingredients if item.name == "鸡蛋")
    assert egg.quantity == 2.0
    assert egg.unit == "个"
    assert egg.scalable is True
    salt = next(item for item in recipe.ingredients if item.name == "盐")
    assert salt.quantity is None
    assert salt.scalable is False
    assert len(recipe.steps) == 3
    assert recipe.steps[1].timer_seconds == 120
    assert recipe.steps[2].timer_seconds == 180
    assert recipe.total_minutes == 5.0
    assert "egg" in recipe.allergens


def test_parse_without_ingredient_section_falls_back_with_warning():
    content = "鸡胸肉 200g，加入盐和黑胡椒，煎 8 分钟。"
    recipe = parse_recipe_document("recipe-2", "煎鸡胸", content)
    assert recipe.ingredients
    assert recipe.warnings
    assert any("原料" in warning for warning in recipe.warnings)


def test_parse_empty_content_does_not_raise():
    recipe = parse_recipe_document("recipe-3", "", "")
    assert recipe.title == "未命名菜谱"
    assert recipe.ingredients == []
    assert recipe.steps == []
    assert recipe.warnings


def test_scale_recipe_doubles_scalable_quantities_only():
    recipe = parse_recipe_document("recipe-4", "番茄炒蛋", SAMPLE)
    scaled = scale_recipe(recipe, 4)
    assert scaled.servings == 4
    egg = next(item for item in scaled.ingredients if item.name == "鸡蛋")
    tomato = next(item for item in scaled.ingredients if item.name == "番茄")
    salt = next(item for item in scaled.ingredients if item.name == "盐")
    assert egg.quantity == 4.0
    assert tomato.quantity == 600.0
    assert salt.quantity is None
    assert scaled.nutrition["totals"]["calories"] == round(
        recipe.nutrition["totals"]["calories"] * 2, 2
    )


def test_imperial_conversion_in_to_dict():
    recipe = ParsedRecipe(
        recipe_id="recipe-5",
        title="测试菜",
        servings=1,
        ingredients=[
            ParsedIngredient(
                name="鸡胸肉",
                raw_name="鸡胸肉",
                quantity=100,
                unit="g",
                scalable=True,
            ),
            ParsedIngredient(
                name="牛奶",
                raw_name="牛奶",
                quantity=240,
                unit="ml",
                scalable=True,
            ),
        ],
    )
    payload = recipe.to_dict(servings=1, unit_system="imperial")
    chicken = payload["ingredients"][0]
    milk = payload["ingredients"][1]
    assert chicken["unit"] == "oz"
    assert chicken["quantity"] == 3.53
    assert milk["unit"] == "cup"
    assert milk["quantity"] == 1.0


def test_recipe_payload_contains_steps_and_nutrition_metadata():
    recipe = parse_recipe_document("recipe-6", "番茄炒蛋", SAMPLE)
    payload = recipe.to_dict(servings=4)
    assert payload["servings"] == 4
    assert payload["base_servings"] == 2
    assert payload["nutrition"]["source"] == "local_food_table"
    assert payload["steps"][0]["index"] == 1
    assert payload["unit_system"] == "metric"


MID_QUANTITY_SAMPLE = """# 蒜香啤酒鸭

2人份

## 必备原料和工具
- 大蒜 4 颗 ,拍散备用
- 蒜苗 2 根 切段备用
- 小米辣 3 颗，切两段即可(不吃辣的可以不用)
- 鸭肉 1000g
- 盐 适量

## 操作
1. 炒香配料。
"""


def test_parse_mid_quantity_with_prep_notes():
    """HowToCook 常见写法：数量夹在名称与做法说明之间。"""
    recipe = parse_recipe_document(
        "recipe-7",
        "蒜香啤酒鸭",
        MID_QUANTITY_SAMPLE,
        source="test",
    )
    by_name = {item.name: item for item in recipe.ingredients}

    garlic = by_name["蒜"]
    assert garlic.quantity == 4.0
    assert garlic.unit == "颗"
    assert garlic.scalable
    # 做法说明不并入名称
    assert "拍散" not in garlic.name

    sprout = by_name["蒜苗"]
    assert sprout.quantity == 2.0
    assert sprout.scalable

    chili = by_name["辣椒"]
    assert chili.quantity == 3.0
    assert chili.scalable

    duck = by_name["鸭肉"]
    assert duck.quantity == 1000.0

    salt = by_name["盐"]
    assert salt.scalable is False
