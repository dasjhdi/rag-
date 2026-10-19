"""SU-10 语义观测指标测试（离线）。"""

import json
import sys
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from langchain_core.documents import Document

from app.api.v1.endpoints.semantic_metrics import get_semantic_metrics_summary
from app.conversation.intent import IntentDetector
from app.observability import semantic_metrics
from app.observability.semantic_metrics import SemanticMetricsCollector


def _load_rag_service_class():
    """Load rag_service.py directly to avoid app.services package side effects."""

    module_name = "_rag_service_under_test"
    if module_name not in sys.modules:
        path = Path("app/services/rag_service.py")
        source = path.read_text(encoding="utf-8").replace(
            "\nrag_service_instance = RAGService()",
            "\nrag_service_instance = None",
        )
        module = types.ModuleType(module_name)
        module.__file__ = str(path)
        sys.modules[module_name] = module
        exec(compile(source, str(path), "exec"), module.__dict__)
    return sys.modules[module_name].RAGService


class _Resp:
    def __init__(self, content):
        self.content = content


class _FakeInvoker:
    supports_native_json_schema = None

    async def ainvoke(self, messages, **kwargs):
        return _Resp(
            json.dumps(
                {
                    "intents": ["recipe_search"],
                    "need_rag": True,
                    "confidence": 0.91,
                    "reason": "测试",
                    "slots": {},
                },
                ensure_ascii=False,
            )
        )


class _FakeReranker:
    def __init__(self, *, fallback_used=0):
        self.fallback_used = fallback_used
        self.calls = 0

    async def rerank(self, query, documents):
        self.calls += 1
        return list(documents)


def test_intent_counters_and_rates():
    collector = SemanticMetricsCollector()
    collector.record_intent(intent="recipe_search", confidence=0.9, needs_clarification=False)
    collector.record_intent(intent="recipe_search", confidence=0.8, needs_clarification=False)
    collector.record_intent(intent="general_chat", confidence=0.3, needs_clarification=True)
    collector.record_intent(intent="cooking_tips", confidence=0.7, needs_clarification=False)

    snapshot = collector.snapshot()["intent"]

    assert snapshot["total"] == 4
    assert snapshot["low_confidence"] == 1
    assert snapshot["clarification_signals"] == 1
    assert snapshot["low_confidence_rate"] == 0.25
    assert snapshot["clarification_signal_rate"] == 0.25


def test_retrieval_counters_and_rates():
    collector = SemanticMetricsCollector()
    collector.record_retrieval(source="milvus", doc_count=2, cache_hit=False)
    collector.record_retrieval(source="milvus", doc_count=0, cache_hit=False)

    snapshot = collector.snapshot()["retrieval"]

    assert snapshot["total"] == 2
    assert snapshot["hit"] == 1
    assert snapshot["empty"] == 1
    assert snapshot["hit_rate"] == 0.5
    assert snapshot["empty_rate"] == 0.5


def test_cache_hit_rate():
    collector = SemanticMetricsCollector()
    collector.record_retrieval(source="milvus", doc_count=1, cache_hit=True)
    collector.record_retrieval(source="milvus", doc_count=1, cache_hit=False)

    snapshot = collector.snapshot()["retrieval"]

    assert snapshot["cache_hits"] == 1
    assert snapshot["cache_misses"] == 1
    assert snapshot["cache_hit_rate"] == 0.5


def test_cache_checked_false_does_not_change_cache_denominator():
    collector = SemanticMetricsCollector()
    collector.record_retrieval(
        source="milvus", doc_count=1, cache_hit=False, cache_checked=False
    )

    snapshot = collector.snapshot()["retrieval"]

    assert snapshot["cache_hits"] == 0
    assert snapshot["cache_misses"] == 0
    assert snapshot["cache_hit_rate"] == 0.0


def test_rerank_fallback_rate():
    collector = SemanticMetricsCollector()
    collector.record_rerank(fallback_used=True)
    collector.record_rerank(fallback_used=False)

    snapshot = collector.snapshot()["rerank"]

    assert snapshot["total"] == 2
    assert snapshot["fallbacks"] == 1
    assert snapshot["fallback_rate"] == 0.5


def test_empty_snapshot_has_zero_rates():
    snapshot = SemanticMetricsCollector().snapshot()

    assert snapshot["intent"]["low_confidence_rate"] == 0.0
    assert snapshot["intent"]["clarification_signal_rate"] == 0.0
    assert snapshot["retrieval"]["hit_rate"] == 0.0
    assert snapshot["retrieval"]["empty_rate"] == 0.0
    assert snapshot["retrieval"]["cache_hit_rate"] == 0.0
    assert snapshot["rerank"]["fallback_rate"] == 0.0


def test_by_intent_and_by_source_counts():
    collector = SemanticMetricsCollector()
    collector.record_intent(intent="recipe_search", confidence=0.9, needs_clarification=False)
    collector.record_intent(intent="recipe_search", confidence=0.9, needs_clarification=False)
    collector.record_intent(intent="general_chat", confidence=0.9, needs_clarification=False)
    collector.record_retrieval(source="recipes", doc_count=1, cache_hit=False)
    collector.record_retrieval(source="personal", doc_count=0, cache_hit=False)

    snapshot = collector.snapshot()

    assert snapshot["intent"]["by_intent"] == {
        "recipe_search": 2,
        "general_chat": 1,
    }
    assert snapshot["retrieval"]["by_source"]["recipes"] == {
        "total": 1,
        "hit": 1,
        "empty": 0,
    }
    assert snapshot["retrieval"]["by_source"]["personal"] == {
        "total": 1,
        "hit": 0,
        "empty": 1,
    }


def test_reset_clears_all_counters():
    collector = SemanticMetricsCollector()
    collector.record_intent(intent="recipe_search", confidence=0.9, needs_clarification=False)
    collector.record_retrieval(source="milvus", doc_count=1, cache_hit=True)
    collector.record_rerank(fallback_used=True)

    collector.reset()
    snapshot = collector.snapshot()

    assert snapshot["intent"]["total"] == 0
    assert snapshot["intent"]["by_intent"] == {}
    assert snapshot["retrieval"]["total"] == 0
    assert snapshot["retrieval"]["by_source"] == {}
    assert snapshot["rerank"]["total"] == 0


def test_concurrent_recording_does_not_lose_counts():
    collector = SemanticMetricsCollector()

    def worker():
        for _ in range(100):
            collector.record_intent(
                intent="recipe_search", confidence=0.9, needs_clarification=False
            )
            collector.record_retrieval(source="milvus", doc_count=1, cache_hit=False)
            collector.record_rerank(fallback_used=False)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: worker(), range(8)))

    snapshot = collector.snapshot()

    assert snapshot["intent"]["total"] == 800
    assert snapshot["intent"]["by_intent"]["recipe_search"] == 800
    assert snapshot["retrieval"]["total"] == 800
    assert snapshot["rerank"]["total"] == 800


async def test_intent_detector_records_metrics():
    semantic_metrics.reset()
    detector = IntentDetector.__new__(IntentDetector)
    detector._llm_type = "fast"
    detector._provider = None
    detector._llm = _FakeInvoker()
    detector.max_attempts = 1
    detector.use_native_schema = False

    result = await detector.detect()
    snapshot = semantic_metrics.snapshot()

    assert result.intent.value == "recipe_search"
    assert snapshot["intent"]["total"] == 1
    assert snapshot["intent"]["by_intent"]["recipe_search"] == 1
    semantic_metrics.reset()


async def test_rerank_fallback_is_recorded():
    semantic_metrics.reset()
    RAGService = _load_rag_service_class()
    service = RAGService.__new__(RAGService)
    service.reranker = _FakeReranker(fallback_used=0)
    service.config = SimpleNamespace(reranker=SimpleNamespace(enabled=True))

    async def rerank_with_fallback(query, documents):
        service.reranker.fallback_used += 1
        return list(documents)

    service.reranker.rerank = rerank_with_fallback

    docs = [Document(page_content="番茄炒蛋")]
    result = await service._rerank_if_needed("番茄炒蛋", docs)
    snapshot = semantic_metrics.snapshot()

    assert result == docs
    assert snapshot["rerank"]["total"] == 1
    assert snapshot["rerank"]["fallbacks"] == 1
    semantic_metrics.reset()


async def test_api_summary_returns_snapshot():
    semantic_metrics.reset()
    semantic_metrics.record_intent(
        intent="recipe_search", confidence=0.9, needs_clarification=False
    )

    payload = await get_semantic_metrics_summary()

    assert payload["intent"]["total"] == 1
    assert "retrieval" in payload
    assert "rerank" in payload
    semantic_metrics.reset()
