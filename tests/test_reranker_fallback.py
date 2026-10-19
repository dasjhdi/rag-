"""SU-3.3 重排兜底测试（离线）。"""

from langchain_core.documents import Document

from app.rag.rerankers.base import BaseReranker
from app.rag.rerankers.lexical_reranker import (
    FaultTolerantReranker,
    LexicalReranker,
)


def _docs() -> list[Document]:
    return [
        Document(page_content="清蒸鲈鱼：鲈鱼处理干净后上锅蒸八分钟。"),
        Document(page_content="红烧肉需要五花肉、冰糖和酱油，小火慢炖。"),
        Document(page_content="番茄炒蛋：先把鸡蛋炒散，再下番茄翻炒。"),
    ]


class StubReranker(BaseReranker):
    def __init__(self, *, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0

    async def rerank(self, query, documents):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return list(documents) if self.result is None else self.result


# ---------------------------------------------------------------------------
# LexicalReranker
# ---------------------------------------------------------------------------


async def test_lexical_reranker_puts_matching_doc_first():
    docs = _docs()
    reranker = LexicalReranker()

    result = await reranker.rerank("番茄炒蛋怎么做", docs)

    assert result[0].page_content.startswith("番茄炒蛋")
    assert result[0].metadata["rerank_score"] > 0
    assert all("rerank_score" in doc.metadata for doc in result)


async def test_lexical_reranker_is_descending():
    docs = _docs()
    result = await LexicalReranker().rerank("番茄炒蛋 红烧肉", docs)

    scores = [doc.metadata["rerank_score"] for doc in result]
    assert scores == sorted(scores, reverse=True)


async def test_lexical_reranker_keeps_all_documents():
    docs = _docs()
    result = await LexicalReranker().rerank("番茄炒蛋", docs)
    assert len(result) == len(docs)


async def test_lexical_reranker_empty_documents():
    assert await LexicalReranker().rerank("番茄炒蛋", []) == []


async def test_lexical_reranker_without_signal_keeps_order():
    docs = _docs()
    result = await LexicalReranker().rerank("完全无关的查询词", docs)

    assert [doc.page_content for doc in result] == [doc.page_content for doc in docs]
    assert all(doc.metadata["rerank_score"] == 0.0 for doc in result)


# ---------------------------------------------------------------------------
# FaultTolerantReranker
# ---------------------------------------------------------------------------


async def test_fallback_is_used_when_primary_raises():
    docs = _docs()
    primary = StubReranker(error=RuntimeError("api down"))
    fallback = LexicalReranker()
    wrapper = FaultTolerantReranker(primary, fallback)

    result = await wrapper.rerank("番茄炒蛋", docs)

    assert primary.calls == 1
    assert wrapper.fallback_used == 1
    assert result[0].page_content.startswith("番茄炒蛋")


async def test_fallback_is_used_when_primary_returns_empty():
    docs = _docs()
    primary = StubReranker(result=[])
    wrapper = FaultTolerantReranker(primary, LexicalReranker())

    result = await wrapper.rerank("番茄炒蛋", docs)

    assert primary.calls == 1
    assert wrapper.fallback_used == 1
    assert len(result) == len(docs)


async def test_fallback_not_used_when_primary_succeeds():
    docs = _docs()
    primary = StubReranker(result=docs[:1])
    fallback = StubReranker()
    wrapper = FaultTolerantReranker(primary, fallback)

    result = await wrapper.rerank("番茄炒蛋", docs)

    assert result == docs[:1]
    assert primary.calls == 1
    assert fallback.calls == 0
    assert wrapper.fallback_used == 0


async def test_empty_documents_skips_both_rerankers():
    primary = StubReranker()
    fallback = StubReranker()
    wrapper = FaultTolerantReranker(primary, fallback)

    assert await wrapper.rerank("番茄炒蛋", []) == []
    assert primary.calls == 0
    assert fallback.calls == 0


async def test_no_primary_goes_straight_to_fallback():
    docs = _docs()
    fallback = StubReranker()
    wrapper = FaultTolerantReranker(None, fallback)

    result = await wrapper.rerank("番茄炒蛋", docs)

    assert result == docs
    assert fallback.calls == 1
