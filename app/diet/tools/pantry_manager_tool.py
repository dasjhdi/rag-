"""Agent tool for pantry inventory management."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

from app.agent.tools.base import BaseTool
from app.agent.types import ToolResult
from app.diet.pantry.service import pantry_service

logger = logging.getLogger(__name__)


class PantryManagerTool(BaseTool):
    name = "pantry_manager"
    description = """管理用户食材库存：list 查询、add 添加、update 更新、delete 删除、expiring 查询临期。
所有数据保存在本地数据库，不依赖网络。"""

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "add", "update", "delete", "expiring"],
                "description": "操作类型",
            },
            "item_id": {"type": "string", "description": "库存项 ID"},
            "name": {"type": "string", "description": "食材名称"},
            "quantity": {"type": "number", "description": "数量"},
            "unit": {"type": "string", "description": "单位"},
            "category": {"type": "string", "description": "分类"},
            "expires_on": {"type": "string", "description": "到期日 YYYY-MM-DD"},
            "location": {"type": "string", "description": "存放位置"},
            "notes": {"type": "string", "description": "备注"},
            "days": {"type": "integer", "description": "临期天数，默认 3"},
        },
        "required": ["action"],
    }

    async def execute(
        self,
        action: Optional[str] = None,
        user_id: Optional[str] = None,
        item_id: Optional[str] = None,
        name: Optional[str] = None,
        quantity: Optional[float] = None,
        unit: Optional[str] = None,
        category: Optional[str] = None,
        expires_on: Optional[str] = None,
        location: Optional[str] = None,
        notes: Optional[str] = None,
        days: int = 3,
        **kwargs: Any,
    ) -> ToolResult:
        if not user_id:
            return ToolResult(success=False, error="user_id 参数是必需的")
        if not action:
            return ToolResult(success=False, error="action 参数是必需的")

        try:
            if action == "list":
                items = await pantry_service.list_items(user_id)
                return ToolResult(success=True, data={"items": items})
            if action == "add":
                if not name:
                    return ToolResult(success=False, error="add 操作需要 name 参数")
                parsed_expiry = date.fromisoformat(expires_on) if expires_on else None
                item = await pantry_service.add_item(
                    user_id,
                    name=name,
                    quantity=quantity if quantity is not None else 0,
                    unit=unit or "g",
                    category=category,
                    expires_on=parsed_expiry,
                    location=location,
                    notes=notes,
                )
                return ToolResult(success=True, data={"item": item})
            if action == "update":
                if not item_id:
                    return ToolResult(
                        success=False, error="update 操作需要 item_id 参数"
                    )
                parsed_expiry = date.fromisoformat(expires_on) if expires_on else None
                item = await pantry_service.update_item(
                    user_id,
                    item_id,
                    name=name,
                    quantity=quantity,
                    unit=unit,
                    category=category,
                    expires_on=parsed_expiry,
                    location=location,
                    notes=notes,
                )
                if not item:
                    return ToolResult(success=False, error="库存项不存在或无权访问")
                return ToolResult(success=True, data={"item": item})
            if action == "delete":
                if not item_id:
                    return ToolResult(
                        success=False, error="delete 操作需要 item_id 参数"
                    )
                deleted = await pantry_service.delete_item(user_id, item_id)
                if not deleted:
                    return ToolResult(success=False, error="库存项不存在或无权访问")
                return ToolResult(success=True, data={"deleted": True})
            if action == "expiring":
                items = await pantry_service.expiring(user_id, days)
                return ToolResult(success=True, data={"items": items, "days": days})
            return ToolResult(success=False, error=f"未知操作: {action}")
        except ValueError as exc:
            return ToolResult(success=False, error=f"参数格式错误: {exc}")
        except Exception as exc:
            logger.exception("pantry_manager failed: %s", exc)
            return ToolResult(success=False, error=f"库存操作失败: {exc}")


__all__ = ["PantryManagerTool"]
