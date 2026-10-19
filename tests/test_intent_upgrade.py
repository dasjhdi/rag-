"""SU-2 意图理解升级测试（离线）。"""

import json

import pytest

from app.conversation.intent import (
    IntentDetector,
    IntentPayload,
    QueryIntent,
    QuerySlots,
    SlotsPayload,
)


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


def _detector(responses) -> IntentDetector:
    detector = IntentDetector.__new__(IntentDetector)
    detector._llm_type = "fast"
    detector._provider = None
    detector._llm = FakeInvoker(responses)
    detector.max_attempts = 2
    detector.use_native_schema = True
    return detector


def _payload(**kwargs) -> str:
    return json.dumps(kwargs, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 新格式解析
# ---------------------------------------------------------------------------


async def test_parses_multi_intent_and_slots():
    content = _payload(
        intents=["recommendation", "recipe_search"],
        need_rag=True,
        confidence=0.88,
        reason="用户想要推荐并需要做法",
        slots={
            "ingredients": ["鸡蛋", "番茄"],
            "dish_names": ["番茄炒蛋"],
            "tastes": ["清淡"],
            "meal_type": "dinner",
            "time_budget_minutes": 20,
            "diet_constraints": ["减脂"],
            "servings": 2,
        },
    )
    result = await _detector([content]).detect()

    assert result.need_rag is True
    assert result.intent is QueryIntent.RECOMMENDATION
    assert result.intents == [
        QueryIntent.RECOMMENDATION,
        QueryIntent.RECIPE_SEARCH,
    ]
    assert result.confidence == pytest.approx(0.88)
    assert result.needs_clarification is False
    assert result.slots.ingredients == ["鸡蛋", "番茄"]
    assert result.slots.dish_names == ["番茄炒蛋"]
    assert result.slots.meal_type == "dinner"
    assert result.slots.time_budget_minutes == 20
    assert result.slots.diet_constraints == ["减脂"]
    assert result.slots.servings == 2


async def test_result_to_dict_is_serializable():
    content = _payload(
        intents=["cooking_tips"],
        confidence=0.7,
        reason="技巧问题",
        slots={"ingredients": ["牛肉"]},
    )
    result = await _detector([content]).detect()
    data = result.to_dict()

    assert data["intents"] == ["cooking_tips"]
    assert data["slots"]["ingredients"] == ["牛肉"]
    json.dumps(data, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 兼容性
# ---------------------------------------------------------------------------


async def test_legacy_single_intent_payload_still_works():
    content = _payload(
        need_rag=True, intent="recipe_search", reason="用户在问做法"
    )
    result = await _detector([content]).detect()

    assert result.need_rag is True
    assert result.intent is QueryIntent.RECIPE_SEARCH
    assert result.intents == [QueryIntent.RECIPE_SEARCH]
    assert result.confidence == IntentDetector.DEFAULT_CONFIDENCE
    assert result.needs_clarification is False
    assert result.slots == QuerySlots()


async def test_need_rag_is_derived_from_intents_not_llm_flag():
    content = _payload(
        intents=["general_chat"],
        need_rag=True,
        confidence=0.9,
        reason="闲聊",
    )
    result = await _detector([content]).detect()

    assert result.need_rag is False
    assert result.intent is QueryIntent.GENERAL_CHAT


async def test_unknown_intent_falls_back_to_general_chat():
    content = _payload(intents=["unknown_intent"], confidence=0.9, reason="?")
    result = await _detector([content]).detect()

    assert result.intents == [QueryIntent.GENERAL_CHAT]
    assert result.need_rag is False


async def test_invalid_intents_are_dropped_and_deduplicated():
    content = _payload(
        intents=["recipe_search", "RECIPE_SEARCH", "bogus", "recommendation"],
        confidence=0.8,
        reason="多标签",
    )
    result = await _detector([content]).detect()

    assert result.intents == [
        QueryIntent.RECIPE_SEARCH,
        QueryIntent.RECOMMENDATION,
    ]


# ---------------------------------------------------------------------------
# 置信度与澄清
# ---------------------------------------------------------------------------


async def test_low_confidence_requests_clarification():
    content = _payload(
        intents=["recommendation"], confidence=0.3, reason="需求模糊"
    )
    result = await _detector([content]).detect()

    assert result.confidence == pytest.approx(0.3)
    assert result.needs_clarification is True


async def test_confidence_is_clamped():
    content = _payload(intents=["recipe_search"], confidence=1.8, reason="很确定")
    result = await _detector([content]).detect()
    assert result.confidence == 1.0

    content = _payload(intents=["recipe_search"], confidence=-3, reason="负数")
    result = await _detector([content]).detect()
    assert result.confidence == 0.0


# ---------------------------------------------------------------------------
# 槽位清洗
# ---------------------------------------------------------------------------


async def test_slots_are_cleaned():
    content = _payload(
        intents=["recipe_search"],
        confidence=0.9,
        reason="清洗测试",
        slots={
            "ingredients": "鸡蛋、番茄，鸡蛋",
            "dish_names": ["  红烧肉  ", "", None],
            "tastes": ["清淡", "清淡", " 咸鲜 "],
            "meal_type": "下午茶",
            "time_budget_minutes": "30分钟",
            "diet_constraints": ["控糖", "控糖"],
            "servings": -2,
        },
    )
    result = await _detector([content]).detect()
    slots = result.slots

    assert slots.ingredients == ["鸡蛋", "番茄"]
    assert slots.dish_names == ["红烧肉"]
    assert slots.tastes == ["清淡", "咸鲜"]
    assert slots.meal_type is None
    assert slots.time_budget_minutes is None
    assert slots.diet_constraints == ["控糖"]
    assert slots.servings is None


async def test_chinese_meal_type_is_normalized():
    content = _payload(
        intents=["recommendation"],
        confidence=0.9,
        reason="早餐",
        slots={"meal_type": "早饭"},
    )
    result = await _detector([content]).detect()
    assert result.slots.meal_type == "breakfast"


async def test_numeric_string_minutes_are_parsed():
    content = _payload(
        intents=["recipe_search"],
        confidence=0.9,
        reason="时间",
        slots={"time_budget_minutes": "25", "servings": "3"},
    )
    result = await _detector([content]).detect()
    assert result.slots.time_budget_minutes == 25
    assert result.slots.servings == 3


def test_slots_payload_accepts_single_string():
    payload = SlotsPayload(ingredients="鸡蛋、番茄", dish_names=None)
    slots = QuerySlots.from_payload(payload)

    assert slots.ingredients == ["鸡蛋", "番茄"]
    assert slots.dish_names == []


def test_intent_payload_reason_tolerates_non_string():
    payload = IntentPayload(intents=["recipe_search"], reason=None)
    assert payload.reason == ""


# ---------------------------------------------------------------------------
# 失败降级
# ---------------------------------------------------------------------------


async def test_invoke_failure_returns_safe_default():
    result = await _detector([RuntimeError("network down")]).detect()

    assert result.need_rag is False
    assert result.intent is QueryIntent.GENERAL_CHAT
    assert result.intents == [QueryIntent.GENERAL_CHAT]
    assert result.confidence == 0.0
    assert result.slots == QuerySlots()
    assert result.needs_clarification is False


async def test_unparseable_output_returns_safe_default():
    result = await _detector(["完全不是 JSON 的文本"]).detect()

    assert result.need_rag is False
    assert result.intent is QueryIntent.GENERAL_CHAT
    assert result.raw == {}


async def test_repair_retry_recovers_from_bad_first_response():
    good = _payload(
        intents=["recipe_search"], confidence=0.9, reason="修复后成功"
    )
    detector = _detector(["垃圾输出", good])
    result = await detector.detect()

    assert result.intent is QueryIntent.RECIPE_SEARCH
    assert len(detector._llm.calls) == 2


async def test_native_schema_is_requested_by_default():
    good = _payload(intents=["recipe_search"], confidence=0.9, reason="ok")
    detector = _detector([good])
    await detector.detect()

    response_format = detector._llm.calls[0]["kwargs"]["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == "IntentPayload"
