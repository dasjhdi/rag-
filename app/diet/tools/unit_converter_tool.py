"""Agent tool for kitchen unit conversion."""

from __future__ import annotations

import logging
from typing import Optional

from app.agent.tools.base import BaseTool
from app.agent.types import ToolResult
from app.diet.nutrition.service import convert_quantity

logger = logging.getLogger(__name__)


class UnitConverterTool(BaseTool):
    name = "unit_converter"
    description = """把厨房用量换算为克；支持克、千克、盎司、磅、毫升、杯、勺、个、只、碗等。
未知单位会返回低置信度和原因，不会静默换算。"""

    parameters = {
        "type": "object",
        "properties": {
            "quantity": {"type": "number", "description": "数量"},
            "unit": {"type": "string", "description": "单位"},
            "food_name": {
                "type": "string",
                "description": "食物名称，用于个/只/碗等计件换算",
            },
        },
        "required": ["unit"],
    }

    async def execute(
        self,
        unit: Optional[str] = None,
        quantity: Optional[float] = None,
        food_name: str = "",
        user_id: Optional[str] = None,
        **kwargs,
    ) -> ToolResult:
        if not unit:
            return ToolResult(success=False, error="unit 参数是必需的")
        try:
            return ToolResult(
                success=True,
                data=convert_quantity(quantity, unit, food_name),
            )
        except Exception as exc:
            logger.exception("unit_converter failed: %s", exc)
            return ToolResult(success=False, error=f"单位换算失败: {exc}")


__all__ = ["UnitConverterTool"]
