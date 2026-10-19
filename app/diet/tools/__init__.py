# app/diet/tools/__init__.py
"""
饮食模块 Agent 工具

提供饮食计划和记录的 CRUD 工具，用于 Agent 对话式操作。
"""

from app.diet.tools.diet_plan_tool import DietPlanTool
from app.diet.tools.diet_log_tool import DietLogTool
from app.diet.tools.diet_analysis_tool import DietAnalysisTool
from app.diet.tools.recipe_search_tool import RecipeSearchTool
from app.diet.tools.nutrition_calculator_tool import NutritionCalculatorTool
from app.diet.tools.unit_converter_tool import UnitConverterTool
from app.diet.tools.pantry_manager_tool import PantryManagerTool
from app.diet.tools.shopping_list_tool import ShoppingListTool
from app.diet.tools.kitchen_timer_tool import KitchenTimerTool
from app.agent.registry import AgentHub


def register_diet_tools():
    """注册所有饮食相关工具到 AgentHub。"""
    AgentHub.register_tool(DietPlanTool(), provider="local")
    AgentHub.register_tool(DietLogTool(), provider="local")
    AgentHub.register_tool(DietAnalysisTool(), provider="local")
    AgentHub.register_tool(RecipeSearchTool(), provider="local")
    AgentHub.register_tool(NutritionCalculatorTool(), provider="local")
    AgentHub.register_tool(UnitConverterTool(), provider="local")
    AgentHub.register_tool(PantryManagerTool(), provider="local")
    AgentHub.register_tool(ShoppingListTool(), provider="local")
    AgentHub.register_tool(KitchenTimerTool(), provider="local")


__all__ = [
    "DietPlanTool",
    "DietLogTool",
    "DietAnalysisTool",
    "RecipeSearchTool",
    "NutritionCalculatorTool",
    "UnitConverterTool",
    "PantryManagerTool",
    "ShoppingListTool",
    "KitchenTimerTool",
    "register_diet_tools",
]
