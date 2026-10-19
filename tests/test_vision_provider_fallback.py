"""Vision Provider 模型回退测试（离线）。

真实故障：视觉配置只使用 model_names[0]，当该模型额度耗尽（403
AccessDenied.Unpurchased）时整条图片识别链路直接失败。VisionProvider
现在按 model_names 顺序尝试，主模型不可用时自动切到备用模型。
"""

import pytest

from app.vision.provider import ImageInput, VisionProvider


class _Resp:
    def __init__(self, content: str):
        self.content = content


class _FakeInvoker:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def ainvoke(self, messages, **kwargs):
        self.calls.append(kwargs.get("model"))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return _Resp(item)


class _Profile:
    def __init__(self, models):
        self.model_names = list(models)
        self.api_key = "test-key"


class _Provider:
    def __init__(self, models):
        self._profile = _Profile(models)

    def get_profile(self, _llm_type=None):
        return self._profile


def _make_provider(models, invoker) -> VisionProvider:
    provider = VisionProvider.__new__(VisionProvider)
    provider._provider = _Provider(models)
    provider._invoker = invoker
    provider._callbacks = []
    return provider


_IMG = ImageInput.from_base64("Zm9v", "image/jpeg")


async def test_falls_back_to_next_model_on_failure():
    invoker = _FakeInvoker([RuntimeError("403 AccessDenied"), '{"ok": true}'])
    provider = _make_provider(["primary", "backup"], invoker)

    result = await provider.analyze(text="hi", images=[_IMG])

    assert result == '{"ok": true}'
    assert invoker.calls == ["primary", "backup"]


async def test_primary_model_is_used_when_it_succeeds():
    invoker = _FakeInvoker(['{"ok": true}'])
    provider = _make_provider(["primary", "backup"], invoker)

    result = await provider.analyze(text="hi", images=[_IMG])

    assert result == '{"ok": true}'
    assert invoker.calls == ["primary"]


async def test_raises_after_every_model_fails():
    invoker = _FakeInvoker([RuntimeError("a"), RuntimeError("b")])
    provider = _make_provider(["primary", "backup"], invoker)

    with pytest.raises(RuntimeError, match="b"):
        await provider.analyze(text="hi", images=[_IMG])

    assert invoker.calls == ["primary", "backup"]


async def test_requires_at_least_one_image():
    invoker = _FakeInvoker([])
    provider = _make_provider(["primary"], invoker)

    with pytest.raises(ValueError):
        await provider.analyze(text="hi", images=[])
