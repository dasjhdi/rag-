from typing import Any, AsyncGenerator, Dict, List, Optional

from langchain_core.messages import BaseMessage

from app.config import settings, LLMType
from app.llm import LLMProvider, llm_context


class LLMOrchestrator:
    """Handles LLM invocation and streaming responses."""

    MODULE_NAME = "main_response"

    def __init__(
        self,
        llm_type: LLMType | str = LLMType.NORMAL,
        provider: LLMProvider | None = None,
    ):
        self._llm_type = llm_type
        self._provider = provider or LLMProvider(settings.llm)
        # Use tracked invoker for usage statistics
        self._llm = self._provider.create_invoker(llm_type, streaming=True)
        # 按输出上限缓存 invoker：每种预算只建一次，避免每轮请求重建客户端
        self._budgeted: Dict[int, Any] = {}

    def _invoker_for(self, max_tokens: Optional[int]) -> Any:
        """取对应输出上限的 invoker；未指定时用配置里的默认值。"""
        if not max_tokens:
            return self._llm
        invoker = self._budgeted.get(max_tokens)
        if invoker is None:
            invoker = self._provider.create_invoker(
                self._llm_type, streaming=True, max_tokens=max_tokens
            )
            self._budgeted[max_tokens] = invoker
        return invoker

    async def stream(
        self,
        messages: List[BaseMessage],
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """流式生成回答。

        ``max_tokens`` 用于按意图收窄输出长度：短问答不必占用和菜谱同样的预算，
        既省钱也减少模型「凑字数」式的冗长。
        """
        invoker = self._invoker_for(max_tokens)

        # Use llm_context for usage tracking
        with llm_context(self.MODULE_NAME, user_id, conversation_id):
            async for chunk in invoker.astream(messages):
                if chunk.content:
                    yield str(chunk.content)
