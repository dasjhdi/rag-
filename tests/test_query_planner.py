"""SU-3.1 查询分解测试（离线）。"""

import json

import pytest

from app.rag.pipeline.query_planner import QueryPlanner, merge_queries


class _Resp:
    def __init__(self, content):
        self.content = content


class FakeInvoker:
    supports_native_json_schema = None

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def ainvoke(self, messages, **kwargs):
        self.calls.append({"messages": list(messages), "kwargs": dict(kwargs)})
        index = len(self.calls) - 1
        item = self.responses[index] if index < len(self.responses) else self.responses[-1]
        if isinstance(item, Exception):
            raise item
        return _Resp(item)


def _planner(responses, max_queries=3) -> QueryPlanner:
    planner = QueryPlanner.__new__(QueryPlanner)
    planner._llm_type = "fast"
    planner._provider = None
    planner._llm = FakeInvoker(responses)
    planner.max_queries = max_queries
    planner.max_attempts = 2
    return planner


# ---------------------------------------------------------------------------
# merge_queries（纯函数）
# ---------------------------------------------------------------------------


def test_merge_keeps_original_first():
    merged = merge_queries("番茄炒蛋怎么做", ["需要哪些食材"], 3)
    assert merged == ["番茄炒蛋怎么做", "需要哪些食材"]


def test_merge_deduplicates_case_and_whitespace():
    merged = merge_queries(
        "Tomato Egg",
        ["tomato   egg", "Tomato Egg", "  ", "需要哪些食材"],
        3,
    )
    assert merged == ["Tomato Egg", "需要哪些食材"]


def test_merge_respects_max_queries():
    merged = merge_queries("q", ["a", "b", "c", "d"], 2)
    assert merged == ["q", "a"]


def test_merge_max_queries_below_one_is_clamped():
    merged = merge_queries("q", ["a", "b"], 0)
    assert merged == ["q"]


def test_merge_empty_original_returns_empty():
    assert merge_queries("   ", ["a"], 3) == []


def test_merge_skips_non_string_items():
    merged = merge_queries("q", ["a", None, 3, {"x": 1}, "b"], 4)
    assert merged == ["q", "a", "b"]


def test_merge_normalizes_internal_whitespace():
    merged = merge_queries("q", ["低脂   高蛋白   晚餐"], 3)
    assert merged == ["q", "低脂 高蛋白 晚餐"]


# ---------------------------------------------------------------------------
# decompose（LLM 路径）
# ---------------------------------------------------------------------------


async def test_decompose_merges_generated_queries():
    content = json.dumps({"queries": ["番茄炒蛋需要哪些食材"]}, ensure_ascii=False)
    planner = _planner([content])

    result = await planner.decompose("推荐番茄炒蛋并告诉我怎么做")

    assert result == ["推荐番茄炒蛋并告诉我怎么做", "番茄炒蛋需要哪些食材"]
    assert len(planner._llm.calls) == 1


async def test_decompose_drops_duplicate_of_original():
    content = json.dumps(
        {"queries": ["推荐番茄炒蛋并告诉我怎么做", "需要哪些食材"]},
        ensure_ascii=False,
    )
    planner = _planner([content])

    result = await planner.decompose("推荐番茄炒蛋并告诉我怎么做")

    assert result == ["推荐番茄炒蛋并告诉我怎么做", "需要哪些食材"]


async def test_decompose_empty_queries_returns_original_only():
    planner = _planner([json.dumps({"queries": []})])
    result = await planner.decompose("红烧肉怎么做")
    assert result == ["红烧肉怎么做"]


async def test_decompose_failure_returns_original_only():
    planner = _planner([RuntimeError("network down")])
    result = await planner.decompose("红烧肉怎么做")
    assert result == ["红烧肉怎么做"]


async def test_decompose_unparseable_returns_original_only():
    planner = _planner(["不是 JSON"])
    result = await planner.decompose("红烧肉怎么做")
    assert result == ["红烧肉怎么做"]


async def test_decompose_empty_query_short_circuits():
    planner = _planner(["{}"])
    result = await planner.decompose("   ")
    assert result == []
    assert planner._llm.calls == []


async def test_decompose_limits_generated_queries():
    content = json.dumps({"queries": ["a", "b", "c", "d"]})
    planner = _planner([content], max_queries=2)

    result = await planner.decompose("q")

    assert result == ["q", "a"]


async def test_decompose_includes_history_in_prompt():
    content = json.dumps({"queries": []})
    planner = _planner([content])

    await planner.decompose("这个怎么做", history_text="用户上一轮问了红烧肉")

    prompt_text = planner._llm.calls[0]["messages"][0].content
    assert "红烧肉" in prompt_text


async def test_decompose_tolerates_single_string_payload():
    content = json.dumps({"queries": "番茄炒蛋需要哪些食材"}, ensure_ascii=False)
    planner = _planner([content])

    result = await planner.decompose("番茄炒蛋")

    assert result == ["番茄炒蛋", "番茄炒蛋需要哪些食材"]
