"""
重排兜底（SU-3.3）

- ``LexicalReranker``：基于本地 BM25 的轻量重排，不依赖外部服务
- ``FaultTolerantReranker``：主重排器异常或返回空时自动切换到兜底实现

动机：原 ``SiliconFlowReranker`` 在 API 异常时直接返回原始顺序，
等于放弃排序，相关结果可能被淹没。本模块保证失败时仍有一次相关性排序。
"""

from __future__ import annotations

import logging
from typing import List, Optional

from langchain_core.documents import Document

from app.rag.pipeline.text_tokenizer import bm25_scores
from app.rag.rerankers.base import BaseReranker

logger = logging.getLogger(__name__)


class LexicalReranker(BaseReranker):
    """基于 BM25 的本地词法重排器。"""

    def __init__(self, *, score_key: str = "rerank_score"):
        self.score_key = score_key

    async def rerank(self, query: str, documents: List[Document]) -> List[Document]:
        if not documents:
            return []

        scores = bm25_scores(query, [doc.page_content for doc in documents])

        # 无词法信号时保持原顺序，但仍写入分数以保持下游行为一致
        if not scores or not any(score > 0 for score in scores):
            for doc in documents:
                doc.metadata[self.score_key] = 0.0
            return list(documents)

        # 稳定排序：同分文档保持原有相对顺序
        ranked = sorted(zip(documents, scores), key=lambda item: -item[1])
        for doc, score in ranked:
            doc.metadata[self.score_key] = float(score)

        logger.info(
            "lexical rerank: %d docs, top_score=%.4f", len(ranked), ranked[0][1]
        )
        return [doc for doc, _ in ranked]


class FaultTolerantReranker(BaseReranker):
    """带兜底的重排器装饰器。"""

    def __init__(
        self,
        primary: Optional[BaseReranker],
        fallback: BaseReranker,
    ):
        self.primary = primary
        self.fallback = fallback
        # 可观测性：兜底被触发的次数
        self.fallback_used = 0

    async def rerank(self, query: str, documents: List[Document]) -> List[Document]:
        if not documents:
            return []

        if self.primary is not None:
            try:
                result = await self.primary.rerank(query, documents)
            except Exception as exc:  # noqa: BLE001 - 兜底不应中断主链路
                logger.warning("primary reranker failed, using fallback: %s", exc)
            else:
                if result:
                    return result
                logger.warning("primary reranker returned no documents, using fallback")

        self.fallback_used += 1
        return await self.fallback.rerank(query, documents)


__all__ = ["LexicalReranker", "FaultTolerantReranker"]
