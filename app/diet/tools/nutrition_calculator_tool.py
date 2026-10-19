"""Agent tool for deterministic nutrition estimation."""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.agent.tools.base import BaseTool
from app.agent.types import ToolResult
from app.diet.nutrition.service import estimate_nutrition

logger = logging.getLogger(__name__)


class NutritionCalculatorTool(BaseTool):
    name = "nutrition_calculator"
    description = """按食材和用量估算热量、蛋白质、脂肪和碳水。
命中本地营养表时返回高/中置信度；未知食物返回 low，不会伪造精确值。"""

    parameters = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "food_name": {"type": "string"},
                        "quantity": {"type": "number"},
                        "unit": {"type": "string"},
                        "weight_g": {"type": "number"},
                    },
                    "required": ["food_name"],
                },
                "description": "食物项列表",
            }
        },
        "required": ["items"],
    }

    async def execute(
        self,
        items: Optional[list[dict[str, Any]]] = None,
        user_id: Optional[str] = None,
        **kwargs,
    ) -> ToolResult:
        if not items:
            return ToolResult(success=False, error="items 参数不能为空")
        try:
            return ToolResult(success=True, data=estimate_nutrition(items))
        except Exception as exc:
            logger.exception("nutrition_calculator failed: %s", exc)
            return ToolResult(success=False, error=f"营养计算失败: {exc}")


__all__ = ["NutritionCalculatorTool"]
