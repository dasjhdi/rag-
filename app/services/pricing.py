"""成本估算：把 ``llm_usage_logs`` 里的 token 换算成金额。

单价写在 ``config.yml`` 的 ``pricing`` 段（单位：元 / 千 token），
未列出的模型使用 ``default`` 兜底。这里只做估算与趋势参考，不是账单依据。

设计约束：
* 配置文件只读一次并缓存，避免每次请求都读盘；
* 任何异常（文件缺失、字段类型不对）都退化为内置默认值，绝不阻断接口；
* 不写死任何供应商的真实价格——默认值只是量级参考，可按需覆盖。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_FALLBACK: dict[str, Any] = {
    "currency": "CNY",
    "default": {"input": 0.002, "output": 0.006},
    "models": {},
}

_cache: dict[str, Any] | None = None


def _load_pricing() -> dict[str, Any]:
    """Read the ``pricing`` block from config.yml (cached)."""
    global _cache
    if _cache is not None:
        return _cache

    try:
        path = Path("config.yml")
        if not path.exists():
            _cache = _FALLBACK
            return _cache
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        block = data.get("pricing") or {}
        _cache = {
            "currency": block.get("currency") or _FALLBACK["currency"],
            "default": {**_FALLBACK["default"], **(block.get("default") or {})},
            "models": block.get("models") or {},
        }
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to load pricing config, using fallback: %s", exc)
        _cache = _FALLBACK
    return _cache


def reset_cache() -> None:
    """Drop the cached pricing (used by tests)."""
    global _cache
    _cache = None


def currency() -> str:
    return _load_pricing()["currency"]


def price_for(model_name: str | None) -> dict[str, float]:
    """Return {'input': x, 'output': y} in CNY per 1K tokens."""
    pricing = _load_pricing()
    models = pricing["models"]
    if model_name and model_name in models:
        entry = models[model_name] or {}
        return {
            "input": float(entry.get("input", pricing["default"]["input"])),
            "output": float(entry.get("output", pricing["default"]["output"])),
        }
    return {
        "input": float(pricing["default"]["input"]),
        "output": float(pricing["default"]["output"]),
    }


def estimate_cost(
    model_name: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
) -> float:
    """Estimated cost in CNY, rounded to 4 decimals."""
    price = price_for(model_name)
    in_tokens = int(input_tokens or 0)
    out_tokens = int(output_tokens or 0)
    cost = in_tokens / 1000 * price["input"] + out_tokens / 1000 * price["output"]
    return round(cost, 4)
