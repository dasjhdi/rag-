"""本地 Cross-Encoder 重排（SU-11）。

设计要点：

- 业务代码只依赖 ``Scorer`` 可调用对象，不直接依赖 ``sentence_transformers``；
- 同步模型推理通过 ``asyncio.to_thread`` 执行，避免阻塞事件循环；
- scorer 缺失、抛异常或返回长度不匹配时，优先调用 fallback，最终回落到原序。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Optional, Sequence

from langchain_core.documents import Document

from app.rag.rerankers.base import BaseReranker

logger = logging.getLogger(__name__)

Scorer = Callable[[str, list[str]], Sequence[float]]


class LocalCrossEncoderReranker(BaseReranker):
    """使用本地 cross-encoder 分数对文档做稳定降序重排。"""

    def __init__(
        self,
        scorer: Optional[Scorer],
        fallback: Optional[BaseReranker] = None,
        *,
        score_key: str = "rerank_score",
    ):
        self.scorer = scorer
        self.fallback = fallback
        self.score_key = score_key

    async def rerank(self, query: str, documents: list[Document]) -> list[Document]:
        if not documents:
            return []

        if self.scorer is None:
            return await self._fallback_or_identity(query, documents)

        try:
            raw_scores = await asyncio.to_thread(
                self.scorer, query, [doc.page_content for doc in documents]
            )
            scores = [float(score) for score in raw_scores]
            if len(scores) != len(documents):
                raise ValueError(
                    f"scorer returned {len(scores)} scores for {len(documents)} documents"
                )
        except Exception as exc:  # noqa: BLE001 - 降级不应中断主链路
            logger.warning("cross-encoder scoring failed, using fallback: %s", exc)
            return await self._fallback_or_identity(query, documents)

        ranked = sorted(zip(documents, scores), key=lambda item: -item[1])
        for doc, score in ranked:
            doc.metadata[self.score_key] = float(score)
            doc.metadata["rerank_backend"] = "cross_encoder"

        logger.info("cross-encoder rerank: %d docs", len(ranked))
        return [doc for doc, _ in ranked]

    async def _fallback_or_identity(
        self, query: str, documents: list[Document]
    ) -> list[Document]:
        if self.fallback is not None:
            try:
                return await self.fallback.rerank(query, documents)
            except Exception as exc:  # noqa: BLE001 - 最终兜底必须稳定
                logger.warning("cross-encoder fallback failed, keeping order: %s", exc)

        for doc in documents:
            doc.metadata[self.score_key] = 0.0
            doc.metadata["rerank_backend"] = "identity"
        return list(documents)


def build_sentence_transformer_scorer(
    model_name: Optional[str],
) -> Optional[Scorer]:
    """延迟加载 ``sentence_transformers.CrossEncoder``。

    依赖未安装或模型加载失败时返回 ``None``，由调用方回落到本地词法重排，
    不影响服务启动。
    """

    if not model_name:
        return None

    try:
        from sentence_transformers import CrossEncoder  # type: ignore
    except Exception as exc:  # noqa: BLE001 - 可选依赖
        logger.warning(
            "sentence_transformers is unavailable, cross-encoder disabled: %s", exc
        )
        return None

    try:
        model = CrossEncoder(model_name)
    except Exception as exc:  # noqa: BLE001 - 模型不可用不应阻断启动
        logger.warning(
            "failed to load cross-encoder model '%s': %s", model_name, exc
        )
        return None

    def scorer(query: str, documents: list[str]) -> list[float]:
        pairs = [(query, document) for document in documents]
        predictions = model.predict(pairs)
        return [float(score) for score in predictions]

    return scorer


__all__ = ["LocalCrossEncoderReranker", "build_sentence_transformer_scorer", "Scorer"]
