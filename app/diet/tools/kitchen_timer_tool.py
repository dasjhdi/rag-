"""Agent tool for deriving kitchen timers without background jobs."""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from app.agent.tools.base import BaseTool
from app.agent.types import ToolResult

logger = logging.getLogger(__name__)

_TIMER = re.compile(
    r"(?P<count>\d+(?:\.\d+)?)\s*(?P<unit>小时|分钟|分|秒钟|秒|hours?|minutes?|mins?|seconds?|secs?)",
    re.IGNORECASE,
)


def _seconds_from_text(text: str) -> Optional[int]:
    match = _TIMER.search(text or "")
    if not match:
        return None
    amount = float(match.group("count"))
    unit = match.group("unit").lower()
    if unit.startswith("小时") or unit.startswith("hour"):
        return int(amount * 3600)
    if unit.startswith("秒") or unit.startswith("second") or unit.startswith("sec"):
        return int(amount)
    return int(amount * 60)


class KitchenTimerTool(BaseTool):
    name = "kitchen_timer"
    description = """从步骤文本或分钟数生成厨房计时建议。
只返回计时秒数和标签，不创建后台任务，前端可据此启动本地倒计时。"""

    parameters = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "包含时间的步骤文本"},
            "minutes": {"type": "number", "description": "直接指定分钟数"},
            "seconds": {"type": "number", "description": "直接指定秒数"},
            "label": {"type": "string", "description": "计时器标签"},
            "steps": {
                "type": "array",
                "items": {"type": "string"},
                "description": "多个步骤文本",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        text: Optional[str] = None,
        minutes: Optional[float] = None,
        seconds: Optional[float] = None,
        label: Optional[str] = None,
        steps: Optional[list[str]] = None,
        user_id: Optional[str] = None,
        **kwargs: Any,
    ) -> ToolResult:
        timers: list[dict[str, Any]] = []
        if seconds is not None:
            timers.append(
                {
                    "label": label or "计时",
                    "seconds": max(1, int(seconds)),
                    "source": "explicit",
                }
            )
        elif minutes is not None:
            timers.append(
                {
                    "label": label or "计时",
                    "seconds": max(1, int(float(minutes) * 60)),
                    "source": "explicit",
                }
            )
        if text:
            value = _seconds_from_text(text)
            if value:
                timers.append(
                    {"label": label or text[:40], "seconds": value, "source": "text"}
                )
        for index, step in enumerate(steps or [], start=1):
            value = _seconds_from_text(step)
            if value:
                timers.append(
                    {
                        "label": f"步骤 {index}",
                        "seconds": value,
                        "source": "steps",
                        "text": step,
                    }
                )
        if not timers:
            return ToolResult(
                success=False,
                error="没有识别到时间，请提供 minutes/seconds 或包含“5 分钟”的文本",
            )
        return ToolResult(success=True, data={"timers": timers})


__all__ = ["KitchenTimerTool"]
