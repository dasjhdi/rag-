"""SU-11 本地 Cross-Encoder 重排测试（离线，不下载模型）。"""

import sys
import threading

import pytest
from langchain_core.documents import Document

from app.rag.rerankers.base import BaseReranker
from app.rag.rerankers.cross_encoder_reranker import (
    LocalCrossEncoderReranker,
    build_sentence_transformer_scorer,
)


def _docs():
    return [
        Document(page_content="清蒸鲈鱼：上锅蒸八分钟。"),
        Document(page_content="番茄炒蛋：先炒鸡蛋再下番茄。"),
        Document(page_content="红烧肉：小火慢炖。"),
    ]


class _Fallback(BaseReranker):
    def __init__(self):
        self.calls = 0

    async def rerank(self, query, documents):
        self.calls += 1
        for doc in documents:
            doc.metadata["fallback_used"] = True
        return list(documents)


async def test_scores_are_sorted_descending_and_written():
    docs = _docs()
    reranker = LocalCrossEncoderReranker(lambda query, texts: [0.1, 0.9, 0.5])

    result = await reranker.rerank("番茄炒蛋", docs)

    assert [doc.page_content for doc in result] == [
        docs[1].page_content,
        docs[2].page_content,
        docs[0].page_content,
    ]
    assert [doc.metadata["rerank_score"] for doc in result] == [0.9, 0.5, 0.1]
    assert all(doc.metadata["rerank_backend"] == "cross_encoder" for doc in result)


async def test_equal_scores_keep_original_order():
    docs = _docs()
    reranker = LocalCrossEncoderReranker(lambda query, texts: [0.5, 0.5, 0.5])

    result = await reranker.rerank("任意查询", docs)

    assert [doc.page_content for doc in result] == [doc.page_content for doc in docs]


async def test_missing_scorer_uses_fallback():
    docs = _docs()
    fallback = _Fallback()
    reranker = LocalCrossEncoderReranker(None, fallback)

    result = await reranker.rerank("番茄炒蛋", docs)

    assert fallback.calls == 1
    assert result == docs
    assert all(doc.metadata["fallback_used"] for doc in result)


async def test_missing_scorer_without_fallback_keeps_order():
    docs = _docs()
    reranker = LocalCrossEncoderReranker(None)

    result = await reranker.rerank("番茄炒蛋", docs)

    assert [doc.page_content for doc in result] == [doc.page_content for doc in docs]
    assert all(doc.metadata["rerank_score"] == 0.0 for doc in result)
    assert all(doc.metadata["rerank_backend"] == "identity" for doc in result)


async def test_scorer_exception_uses_fallback():
    docs = _docs()
    fallback = _Fallback()

    def broken(query, texts):
        raise RuntimeError("model crashed")

    reranker = LocalCrossEncoderReranker(broken, fallback)

    result = await reranker.rerank("番茄炒蛋", docs)

    assert fallback.calls == 1
    assert result == docs


async def test_score_length_mismatch_uses_fallback():
    docs = _docs()
    fallback = _Fallback()
    reranker = LocalCrossEncoderReranker(lambda query, texts: [0.9], fallback)

    result = await reranker.rerank("番茄炒蛋", docs)

    assert fallback.calls == 1
    assert result == docs


async def test_fallback_failure_keeps_original_order():
    class BrokenFallback(BaseReranker):
        async def rerank(self, query, documents):
            raise RuntimeError("fallback crashed")

    docs = _docs()
    reranker = LocalCrossEncoderReranker(None, BrokenFallback())

    result = await reranker.rerank("番茄炒蛋", docs)

    assert [doc.page_content for doc in result] == [doc.page_content for doc in docs]
    assert all(doc.metadata["rerank_backend"] == "identity" for doc in result)


async def test_empty_documents_does_not_call_scorer():
    calls = []

    def scorer(query, texts):
        calls.append(texts)
        return []

    reranker = LocalCrossEncoderReranker(scorer)

    assert await reranker.rerank("番茄炒蛋", []) == []
    assert calls == []


async def test_sync_scorer_runs_in_worker_thread():
    main_thread = threading.get_ident()
    observed = {}

    def scorer(query, texts):
        observed["thread"] = threading.get_ident()
        return [1.0 for _ in texts]

    docs = _docs()
    await LocalCrossEncoderReranker(scorer).rerank("番茄炒蛋", docs)

    assert observed["thread"] != main_thread


def test_build_scorer_returns_none_without_model_name():
    assert build_sentence_transformer_scorer(None) is None
    assert build_sentence_transformer_scorer("") is None


def test_build_scorer_returns_none_when_dependency_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    assert build_sentence_transformer_scorer("any-model") is None


def test_config_defaults_disable_local_cross_encoder():
    from app.config.rag_config import RerankerConfig

    config = RerankerConfig()

    assert config.local_cross_encoder_enabled is False
    assert config.local_cross_encoder_model is None
