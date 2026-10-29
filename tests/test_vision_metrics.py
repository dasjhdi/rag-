"""视觉链路指标：耗时、超时、重试与体积压缩。

指标是进程内计数器，测试前后都要 reset，避免相互污染。
"""

import base64
import io

import pytest
from PIL import Image

from app.observability import semantic_metrics
from app.vision.provider import ImageInput, VisionProvider


@pytest.fixture(autouse=True)
def _clean_metrics():
    semantic_metrics.reset()
    yield
    semantic_metrics.reset()


def _tiny_image() -> ImageInput:
    buffer = io.BytesIO()
    Image.new("RGB", (120, 90), (180, 120, 80)).save(buffer, format="JPEG", quality=80)
    return ImageInput.from_base64(base64.b64encode(buffer.getvalue()).decode(), "image/jpeg")


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


class TestCollector:
    def test_success_and_failure_are_aggregated(self):
        semantic_metrics.record_vision(
            success=True, duration_ms=100, model="m1", input_bytes=1000, output_bytes=200
        )
        semantic_metrics.record_vision(
            success=True, duration_ms=300, model="m1", input_bytes=1000, output_bytes=200
        )
        semantic_metrics.record_vision(
            success=False, duration_ms=5000, model="m2", timeout=True
        )

        vision = semantic_metrics.snapshot()["vision"]
        assert vision["total"] == 3
        assert vision["success"] == 2
        assert vision["failed"] == 1
        assert vision["timeouts"] == 1
        assert vision["success_rate"] == pytest.approx(0.6667, abs=1e-4)
        assert vision["timeout_rate"] == pytest.approx(0.3333, abs=1e-4)
        assert vision["latency_ms"]["max"] == 5000
        assert vision["latency_ms"]["p50"] == 300
        assert vision["latency_ms"]["samples"] == 3
        assert vision["payload"]["input_bytes"] == 2000
        assert vision["payload"]["output_bytes"] == 400
        assert vision["payload"]["saved_ratio"] == pytest.approx(0.8)
        assert vision["by_model"]["m1"] == {"total": 2, "success": 2, "failed": 0}
        assert vision["by_model"]["m2"]["failed"] == 1

    def test_empty_snapshot_is_zero(self):
        vision = semantic_metrics.snapshot()["vision"]
        assert vision["total"] == 0
        assert vision["success_rate"] == 0.0
        assert vision["latency_ms"]["p95"] == 0
        assert vision["payload"]["saved_ratio"] == 0.0


class TestProviderInstrumentation:
    async def test_success_is_recorded(self):
        provider = _make_provider(["primary", "backup"], _FakeInvoker(['{"ok": true}']))

        result = await provider.analyze(text="hi", images=[_tiny_image()])

        assert result == '{"ok": true}'
        vision = semantic_metrics.snapshot()["vision"]
        assert vision["total"] == 1
        assert vision["success"] == 1
        assert vision["timeouts"] == 0
        assert vision["latency_ms"]["samples"] == 1
        assert vision["by_model"]["primary"]["success"] == 1

    async def test_failure_is_recorded(self):
        provider = _make_provider(
            ["primary", "backup"],
            _FakeInvoker([RuntimeError("401 unauthorized"), RuntimeError("boom")]),
        )

        with pytest.raises(RuntimeError):
            await provider.analyze(text="hi", images=[_tiny_image()])

        vision = semantic_metrics.snapshot()["vision"]
        assert vision["total"] == 1
        assert vision["failed"] == 1
        assert vision["success"] == 0

    async def test_timeout_retry_is_recorded(self):
        provider = _make_provider(
            ["primary"], _FakeInvoker([TimeoutError("timed out"), '{"ok": true}'])
        )

        result = await provider.analyze(text="hi", images=[_tiny_image()])

        assert result == '{"ok": true}'
        vision = semantic_metrics.snapshot()["vision"]
        assert vision["success"] == 1
        assert vision["timeouts"] == 1
        assert vision["retries_smaller"] == 1
        assert vision["retry_rate"] == 1.0
