"""Agent tool registration and offline behavior tests."""

from app.agent import setup_agent_module
from app.agent.registry import AgentHub
from app.diet.tools import register_diet_tools
from app.diet.tools.kitchen_timer_tool import KitchenTimerTool
from app.diet.tools.nutrition_calculator_tool import NutritionCalculatorTool
from app.diet.tools.pantry_manager_tool import PantryManagerTool
from app.diet.tools.recipe_search_tool import RecipeSearchTool
from app.diet.tools.shopping_list_tool import ShoppingListTool
from app.diet.tools.unit_converter_tool import UnitConverterTool


def test_six_new_tools_are_registered():
    setup_agent_module()
    register_diet_tools()
    registered = set(AgentHub.list_tools())
    expected = {
        "recipe_search",
        "nutrition_calculator",
        "unit_converter",
        "pantry_manager",
        "shopping_list",
        "kitchen_timer",
    }
    assert expected.issubset(registered)
    for name in expected:
        tool = AgentHub.get_tool(name)
        assert tool is not None
        assert tool.to_openai_schema()["function"]["name"] == name


async def test_unit_converter_tool_returns_cup_in_milliliters():
    result = await UnitConverterTool().execute(quantity=1, unit="杯", food_name="牛奶")
    assert result.success is True
    assert result.data["milliliters"] == 240.0


async def test_nutrition_tool_unknown_food_is_low_confidence():
    result = await NutritionCalculatorTool().execute(
        items=[{"food_name": "神秘食物", "quantity": 1, "unit": "份"}]
    )
    assert result.success is True
    assert result.data["confidence"] == "low"


async def test_recipe_search_requires_user_id():
    result = await RecipeSearchTool().execute(query="番茄")
    assert result.success is False
    assert "user_id" in result.error


async def test_pantry_tool_reports_missing_required_parameters():
    result = await PantryManagerTool().execute(action="add", user_id="user-1")
    assert result.success is False
    assert "name" in result.error
    missing_action = await PantryManagerTool().execute(user_id="user-1")
    assert missing_action.success is False
    assert "action" in missing_action.error


async def test_shopping_tool_requires_user_id():
    result = await ShoppingListTool().execute(action="get")
    assert result.success is False
    assert "user_id" in result.error


async def test_kitchen_timer_extracts_seconds_from_text():
    result = await KitchenTimerTool().execute(text="小火煮 5 分钟")
    assert result.success is True
    assert result.data["timers"][0]["seconds"] == 300
