"""
检索查询分解（SU-3.1）

把复杂的用户需求拆解为多条互补、可独立检索的子查询，用于多路召回。

约束：

- 首项恒为原查询，保证召回不劣化
- 结果去重、限长
- LLM 失败时降级为单查询
"""

from __future__ import annotations

import logging
import re
from typing import Optional, Sequence

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field, field_validator

from app.config import settings, LLMType
from app.llm import LLMProvider, llm_context
from app.llm.structured import StructuredOutputError, invoke_structured

logger = logging.getLogger(__name__)

_WHITESPACE = re.compile(r"\s+")


class QueryPlanPayload(BaseModel):
    """查询分解结果。"""

    queries: list[str] = Field(default_factory=list)

    @field_validator("queries", mode="before")
    @classmethod
    def _coerce_queries(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, (list, tuple, set)):
            return [item for item in value if isinstance(item, str)]
        return []


QUERY_DECOMPOSITION_PROMPT = ChatPromptTemplate.from_template(
    """
你是 CookHero 的「检索查询分解器」。你的任务是把用户的复杂需求拆成最多 {max_queries} 条
**互补、可独立用于菜谱知识库语义检索**的中文查询。

【规则】
1. 每条查询聚焦一个方面：具体菜谱做法、食材处理、烹饪技巧、菜品推荐
2. 只保留用户**明确表达**的条件，禁止新增或推断口味、难度、时长等条件
3. 不要重复原查询本身
4. 若原查询已经足够简单、单条即可覆盖，返回空数组
5. 每条查询必须是完整自然语言句子，禁止关键词堆砌
6. 禁止输出解释、Markdown 或多余文本

{history}

用户当前查询：
{query}

【输出格式（强约束）】

{{"queries": ["子查询1", "子查询2"]}}
"""
)


def _normalize_key(text: str) -> str:
    """用于去重的归一化键：压缩空白 + 大小写折叠。"""
    return _WHITESPACE.sub(" ", text.strip()).casefold()


def merge_queries(
    original: str,
    generated: Sequence[str],
    max_queries: int,
) -> list[str]:
    """
    合并原查询与生成查询：首项为原查询，去重并限制数量。

    Args:
        original: 原查询（重写后的检索查询）。
        generated: LLM 生成的子查询。
        max_queries: 最大查询数（含原查询），小于 1 时按 1 处理。

    Returns:
        合并后的查询列表。
    """
    limit = max(1, int(max_queries))
    base = original.strip()
    if not base:
        return []

    merged = [base]
    seen = {_normalize_key(base)}

    for item in generated or []:
        if len(merged) >= limit:
            break
        if not isinstance(item, str):
            continue
        text = _WHITESPACE.sub(" ", item.strip())
        if not text:
            continue
        key = _normalize_key(text)
        if key in seen:
            continue
        seen.add(key)
        merged.append(text)

    return merged


class QueryPlanner:
    """基于 LLM 的检索查询分解器。"""

    MODULE_NAME = "rag_query_planner"

    def __init__(
        self,
        llm_type: LLMType | str = LLMType.FAST,
        provider: Optional[LLMProvider] = None,
        *,
        max_queries: int = 3,
        max_attempts: int = 2,
    ):
        self._llm_type = llm_type
        self._provider = provider or LLMProvider(settings.llm)
        self._llm = self._provider.create_invoker(llm_type, temperature=0.0)
        self.max_queries = max(1, int(max_queries))
        self.max_attempts = max(1, int(max_attempts))

    async def decompose(
        self,
        query: str,
        *,
        history_text: str = "",
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> list[str]:
        """
        把查询分解为多条子查询，并合并原查询。

        失败时降级为 ``[query]``。
        """
        base = (query or "").strip()
        if not base:
            return []

        history_block = (
            f"【对话历史上下文】\n{history_text.strip()}\n" if history_text.strip() else ""
        )

        try:
            template = QUERY_DECOMPOSITION_PROMPT.format_prompt(
                max_queries=self.max_queries - 1,
                history=history_block,
                query=base,
            )
            with llm_context(self.MODULE_NAME, user_id, conversation_id):
                payload = await invoke_structured(
                    self._llm,
                    list(template.messages),
                    QueryPlanPayload,
                    max_attempts=self.max_attempts,
                )
            return merge_queries(base, payload.queries, self.max_queries)
        except StructuredOutputError as exc:
            logger.warning(
                "Query decomposition failed after %d attempt(s): %s",
                exc.attempts,
                exc,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Query decomposition failed: %s", exc)

        return [base]


__all__ = ["QueryPlanner", "QueryPlanPayload", "merge_queries"]
