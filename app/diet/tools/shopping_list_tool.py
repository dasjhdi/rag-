"""Agent tool for weekly shopping lists."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Optional

from app.agent.tools.base import BaseTool
from app.agent.types import ToolResult
from app.diet.pantry.service import pantry_service

logger = logging.getLogger(__name__)


def _default_week_start(target: Optional[date] = None) -> date:
    current = target or date.today()
    return current - timedelta(days=current.weekday())


class ShoppingListTool(BaseTool):
    name = "shopping_list"
    description = """生成或读取一周购物清单。generate 会按计划食材聚合并扣除库存；
get 读取已保存清单；update 勾选或调整数量。"""

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["generate", "get", "update"],
                "description": "操作类型",
            },
            "week_start_date": {
                "type": "string",
                "description": "周开始日期 YYYY-MM-DD，默认本周一",
            },
            "item_id": {"type": "string", "description": "购物清单项 ID"},
            "checked": {"type": "boolean", "description": "是否已购买"},
            "quantity": {"type": "number", "description": "调整后的数量"},
            "unit": {"type": "string", "description": "单位"},
        },
        "required": ["action"],
    }

    async def execute(
        self,
        action: Optional[str] = None,
        user_id: Optional[str] = None,
        week_start_date: Optional[str] = None,
        item_id: Optional[str] = None,
        checked: Optional[bool] = None,
        quantity: Optional[float] = None,
        unit: Optional[str] = None,
        **kwargs: Any,
    ) -> ToolResult:
        if not user_id:
            return ToolResult(success=False, error="user_id 参数是必需的")
        if not action:
            return ToolResult(success=False, error="action 参数是必需的")
        try:
            week_start = (
                date.fromisoformat(week_start_date)
                if week_start_date
                else _default_week_start()
            )
            if action == "generate":
                return ToolResult(
                    success=True,
                    data=await pantry_service.generate_shopping_list(
                        user_id, week_start
                    ),
                )
            if action == "get":
                items = await pantry_service.list_shopping(user_id, week_start)
                return ToolResult(
                    success=True,
                    data={"week_start_date": week_start.isoformat(), "items": items},
                )
            if action == "update":
                if not item_id:
                    return ToolResult(
                        success=False, error="update 操作需要 item_id 参数"
                    )
                item = await pantry_service.update_shopping_item(
                    user_id,
                    item_id,
                    checked=checked,
                    quantity=quantity,
                    unit=unit,
                )
                if not item:
                    return ToolResult(success=False, error="购物清单项不存在或无权访问")
                return ToolResult(success=True, data={"item": item})
            return ToolResult(success=False, error=f"未知操作: {action}")
        except ValueError as exc:
            return ToolResult(success=False, error=f"日期或参数格式错误: {exc}")
        except Exception as exc:
            logger.exception("shopping_list failed: %s", exc)
            return ToolResult(success=False, error=f"购物清单操作失败: {exc}")


__all__ = ["ShoppingListTool"]
