"""SU-1 结构化输出层测试（离线）。"""

import pytest
from pydantic import BaseModel, Field

from app.llm.structured import (
    StructuredOutputError,
    invoke_structured,
    reset_capability_cache,
    supports_native_json_schema,
)


class Dish(BaseModel):
    name: str
    calories: int = Field(ge=0)


class _Resp:
    def __init__(self, content):
        self.content = content


class FakeInvoker:
    """可编排的假 invoker：按调用序号返回预设结果或抛异常。"""

    # 类属性显式声明为 None，避免被 supports_native_json_schema 误判为声明值
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
        if callable(item):
            return item(kwargs)
        return _Resp(item)


@pytest.fixture(autouse=True)
def _clear_capability_cache():
    reset_capability_cache()
    yield
    reset_capability_cache()


async def test_uses_native_json_schema_by_default():
    invoker = FakeInvoker(['{"name": "番茄炒蛋", "calories": 180}'])

    result = await invoke_structured(invoker, [{"role": "user", "content": "hi"}], Dish)

    assert result == Dish(name="番茄炒蛋", calories=180)
    assert invoker.calls[0]["kwargs"]["response_format"]["type"] == "json_schema"
    assert (
        invoker.calls[0]["kwargs"]["response_format"]["json_schema"]["name"] == "Dish"
    )


async def test_declared_unsupported_uses_json_object():
    class DeclaredInvoker(FakeInvoker):
        supports_native_json_schema = False

    invoker = DeclaredInvoker(['{"name": "白米饭", "calories": 116}'])

    result = await invoke_structured(invoker, [{"role": "user", "content": "hi"}], Dish)

    assert result.calories == 116
    assert invoker.calls[0]["kwargs"]["response_format"] == {"type": "json_object"}


async def test_falls_back_when_provider_rejects_schema():
    unsupported = ValueError("unknown parameter: response_format")
    invoker = FakeInvoker([unsupported, '{"name": "红烧肉", "calories": 520}'])

    result = await invoke_structured(invoker, [{"role": "user", "content": "hi"}], Dish)

    assert result.name == "红烧肉"
    assert invoker.calls[0]["kwargs"]["response_format"]["type"] == "json_schema"
    assert invoker.calls[1]["kwargs"]["response_format"] == {"type": "json_object"}


async def test_unsupported_capability_is_cached_across_calls():
    unsupported = ValueError("response_format is not supported")
    invoker = FakeInvoker(
        [unsupported, '{"name": "A", "calories": 1}', '{"name": "B", "calories": 2}']
    )

    await invoke_structured(invoker, [{"role": "user", "content": "1"}], Dish)
    calls_after_first = len(invoker.calls)

    assert supports_native_json_schema(invoker) is False

    result = await invoke_structured(invoker, [{"role": "user", "content": "2"}], Dish)

    assert result.name == "B"
    assert len(invoker.calls) == calls_after_first + 1
    assert invoker.calls[-1]["kwargs"]["response_format"] == {"type": "json_object"}


async def test_repair_retry_on_invalid_json():
    invoker = FakeInvoker(
        ["这不是 JSON", '{"name": "番茄炒蛋", "calories": 180}']
    )

    result = await invoke_structured(invoker, [{"role": "user", "content": "hi"}], Dish)

    assert result.name == "番茄炒蛋"
    assert len(invoker.calls) == 2
    repair_messages = invoker.calls[1]["messages"]
    assert len(repair_messages) == 2
    assert "上一次输出无法通过校验" in repair_messages[-1]["content"]
    assert "json" in repair_messages[-1]["content"].lower()


async def test_schema_violation_triggers_retry():
    invoker = FakeInvoker(
        [
            '{"name": "x", "calories": -5}',
            '{"name": "x", "calories": 5}',
        ]
    )

    result = await invoke_structured(invoker, [{"role": "user", "content": "hi"}], Dish)

    assert result.calories == 5
    assert len(invoker.calls) == 2
    assert "validation_error" in invoker.calls[1]["messages"][-1]["content"]


async def test_custom_validator_triggers_retry():
    def _must_be_spicy(model: Dish) -> None:
        if "辣" not in model.name:
            raise ValueError("dish must be spicy")

    invoker = FakeInvoker(
        [
            '{"name": "清蒸鱼", "calories": 200}',
            '{"name": "辣子鸡", "calories": 300}',
        ]
    )

    result = await invoke_structured(
        invoker,
        [{"role": "user", "content": "hi"}],
        Dish,
        validator=_must_be_spicy,
    )

    assert result.name == "辣子鸡"
    assert len(invoker.calls) == 2


async def test_raises_structured_output_error_after_attempts():
    invoker = FakeInvoker(["无效输出"])

    with pytest.raises(StructuredOutputError) as excinfo:
        await invoke_structured(
            invoker, [{"role": "user", "content": "hi"}], Dish, max_attempts=2
        )

    error = excinfo.value
    assert error.attempts == 2
    assert len(invoker.calls) == 2
    assert error.errors
    assert error.last_response == "无效输出"
    assert "无效输出" in str(error)


async def test_parses_fenced_json_block():
    content = "```json\n{\"name\": \"宫保鸡丁\", \"calories\": 420}\n```"
    invoker = FakeInvoker([content])

    result = await invoke_structured(invoker, [{"role": "user", "content": "hi"}], Dish)

    assert result.name == "宫保鸡丁"


async def test_multimodal_content_parts_are_extracted():
    invoker = FakeInvoker(
        [[{"type": "text", "text": '{"name": "沙拉", "calories": 90}'}]]
    )

    result = await invoke_structured(invoker, [{"role": "user", "content": "hi"}], Dish)

    assert result.name == "沙拉"


async def test_invoke_error_is_retried_then_raises():
    invoker = FakeInvoker([RuntimeError("network down")])

    with pytest.raises(StructuredOutputError) as excinfo:
        await invoke_structured(
            invoker, [{"role": "user", "content": "hi"}], Dish, max_attempts=3
        )

    assert len(invoker.calls) == 3
    assert any("invoke_error" in e for e in excinfo.value.errors)
