"""Agent tool for searching structured recipes."""

from __future__ import annotations

import logging
from typing import Optional

from app.agent.tools.base import BaseTool
from app.agent.types import ToolResult
from app.diet.recipes.service import recipe_service

logger = logging.getLogger(__name__)


class RecipeSearchTool(BaseTool):
    name = "recipe_search"
    description = """搜索结构化菜谱。支持关键词、分类、饮食标签、过敏原排除和最长耗时。
返回菜谱的食材、步骤、营养和标签，不依赖网络。"""

    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
            "category": {"type": "string", "description": "菜系或分类"},
            "diet_tag": {
                "type": "string",
                "description": "饮食标签，如 vegetarian、vegan、gluten_free",
            },
            "exclude_allergens": {
                "type": "array",
                "items": {"type": "string"},
                "description": "需要排除的过敏原或食材",
            },
            "max_minutes": {"type": "number", "description": "最长烹饪时间（分钟）"},
            "limit": {"type": "integer", "description": "返回数量，默认 10"},
        },
        "required": [],
    }

    async def execute(
        self,
        user_id: Optional[str] = None,
        query: Optional[str] = None,
        category: Optional[str] = None,
        diet_tag: Optional[str] = None,
        exclude_allergens: Optional[list[str]] = None,
        max_minutes: Optional[float] = None,
        limit: int = 10,
        **kwargs,
    ) -> ToolResult:
        if not user_id:
            return ToolResult(success=False, error="user_id 参数是必需的")
        try:
            items = await recipe_service.search(
                user_id,
                query=query,
                category=category,
                diet_tag=diet_tag,
                exclude_allergens=exclude_allergens,
                max_minutes=max_minutes,
                limit=limit,
            )
            return ToolResult(
                success=True,
                data={"items": items, "count": len(items)},
            )
        except Exception as exc:
            logger.exception("recipe_search failed: %s", exc)
            return ToolResult(success=False, error=f"菜谱搜索失败: {exc}")


__all__ = ["RecipeSearchTool"]
