"""Recipe importer parsing and SSRF guard tests (offline)."""

import pytest

from app.diet.recipes.importer import (
    RecipeImportError,
    _parse_json_payload,
    _payload_to_recipe,
    _validate_public_url,
    extract_dom_recipe,
    extract_json_ld_recipe,
    extract_recipe_from_html,
    parse_iso_duration,
)

JSON_LD_HTML = """
<html><head>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Recipe",
  "name": "番茄炒蛋",
  "description": "经典家常菜",
  "image": ["/img/tomato.jpg", {"@type": "ImageObject", "url": "/img/tomato-2.jpg"}],
  "recipeYield": "3人份",
  "totalTime": "PT20M",
  "recipeCategory": "家常菜",
  "recipeIngredient": ["番茄 2 个", "鸡蛋 3 个", "盐 适量"],
  "recipeInstructions": [
    {"@type": "HowToStep", "text": "鸡蛋打散"},
    {"@type": "HowToStep", "text": "热锅炒蛋，盛出"},
    {"@type": "HowToStep", "text": "炒番茄后回锅，加盐"}
  ]
}
</script>
</head><body></body></html>
"""

DOM_HTML = """
<html><head>
<meta property="og:title" content="土豆炖牛肉">
<meta property="og:description" content="暖胃的一锅炖">
<meta property="og:image" content="https://example.com/beef.jpg">
</head><body><article>
<h1>土豆炖牛肉</h1>
<p>3人份，约 60 分钟</p>
<div class="ingredients"><ul>
<li>牛肉 500g</li><li>土豆 2 个</li><li>胡萝卜 1 根</li>
</ul></div>
<div class="steps"><ol>
<li>牛肉焯水</li><li>炒香后加水炖 40 分钟</li><li>加入土豆再炖 15 分钟</li>
</ol></div>
</article></body></html>
"""


def test_json_ld_recipe_is_extracted():
    recipe = extract_json_ld_recipe(JSON_LD_HTML, "https://example.com/recipe/1")

    assert recipe is not None
    assert recipe.title == "番茄炒蛋"
    assert recipe.servings == 3
    assert recipe.total_minutes == 20
    assert recipe.category == "家常菜"
    assert len(recipe.ingredients) == 3
    assert len(recipe.steps) == 3
    assert recipe.image_urls == [
        "https://example.com/img/tomato.jpg",
        "https://example.com/img/tomato-2.jpg",
    ]


def test_dom_fallback_is_used_without_json_ld():
    recipe = extract_dom_recipe(DOM_HTML, "https://example.com/beef")

    assert recipe is not None
    assert recipe.title == "土豆炖牛肉"
    assert recipe.servings == 3
    assert recipe.total_minutes == 60
    assert len(recipe.ingredients) == 3
    assert len(recipe.steps) == 3
    assert recipe.image_urls == ["https://example.com/beef.jpg"]


def test_recipe_without_content_raises_friendly_error():
    with pytest.raises(RecipeImportError, match="识别"):
        extract_recipe_from_html("<html><body><h1>空页面</h1></body></html>", "https://e.com")


def test_iso_duration_variants():
    assert parse_iso_duration("PT30M") == 30
    assert parse_iso_duration("PT1H20M") == 80
    assert parse_iso_duration("P1DT2H") == 1560
    assert parse_iso_duration("") is None


async def test_private_and_local_urls_are_rejected():
    for url in (
        "http://127.0.0.1/recipe",
        "http://localhost/recipe",
        "http://169.254.169.254/latest/meta-data",
        "file:///etc/passwd",
    ):
        with pytest.raises(RecipeImportError):
            await _validate_public_url(url)


def test_vision_json_payload_accepts_code_fences():
    payload = _parse_json_payload(
        '```json\n{"title": "菜", "ingredients": ["盐"], "steps": ["炒"]}\n```'
    )
    assert payload["title"] == "菜"


def test_payload_to_recipe_validates_required_fields():
    recipe = _payload_to_recipe(
        {
            "title": "清炒时蔬",
            "servings": "2",
            "ingredients": ["青菜 300g", "盐 适量"],
            "steps": ["洗净", "大火快炒"],
        }
    )
    assert recipe.title == "清炒时蔬"
    assert recipe.servings == 2
    assert len(recipe.steps) == 2

    with pytest.raises(RecipeImportError):
        _payload_to_recipe({"title": "只有标题"})
