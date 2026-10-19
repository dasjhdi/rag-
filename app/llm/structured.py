"""
结构化输出层（SU-1）

统一的 LLM 结构化输出入口，约束顺序为：

1. 原生 ``response_format={"type": "json_schema", ...}``（若提供方支持）
2. 携带校验错误信息的修复重试（带上一次原始输出与目标 JSON Schema）
3. 正则兜底解析（复用 ``extract_first_valid_json``）

设计原则：

- 失败必须显式：全部尝试失败后抛 ``StructuredOutputError``，调用方自行决定降级策略。
- 能力探测有缓存：一旦发现提供方不支持 json_schema，后续调用不再尝试。
- 保持向后兼容：不改变 ``extract_first_valid_json`` 的行为。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from app.utils.structured_json import extract_first_valid_json

logger = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=BaseModel)

# 判定为「提供方不支持 json_schema」的错误特征（大小写不敏感）
_UNSUPPORTED_SCHEMA_MARKERS = (
    "response_format",
    "json_schema",
    "json schema",
    "unknown parameter",
    "unrecognized",
    "unsupported",
    "not support",
    "invalid_request_error",
)

# 进程内能力缓存：key -> 是否支持原生 json_schema
_NATIVE_SCHEMA_SUPPORT: dict[str, bool] = {}


class StructuredOutputError(Exception):
    """结构化输出在全部尝试后仍然失败。"""

    def __init__(
        self,
        message: str,
        *,
        last_response: Optional[str] = None,
        errors: Optional[list[str]] = None,
        attempts: int = 0,
    ) -> None:
        super().__init__(message)
        self.last_response = last_response
        self.errors = list(errors or [])
        self.attempts = attempts

    def __str__(self) -> str:  # pragma: no cover - 展示用
        base = super().__str__()
        if self.last_response:
            snippet = self.last_response.strip().replace("\n", " ")[:200]
            return f"{base} | last_response={snippet!r}"
        return base


# =============================================================================
# 能力探测
# =============================================================================


def _invoker_cache_key(invoker: Any) -> str:
    """为 invoker 生成稳定的能力缓存键。"""
    explicit = getattr(invoker, "capability_key", None)
    if isinstance(explicit, str) and explicit:
        return explicit
    return f"{type(invoker).__module__}.{type(invoker).__qualname__}"


def supports_native_json_schema(invoker: Any) -> bool:
    """
    判断 invoker 是否支持原生 json_schema 响应格式。

    探测策略（乐观 + 学习失败）：

    1. 调用方显式声明：``invoker.supports_native_json_schema``（bool 或可调用对象）优先。
    2. 命中进程内缓存则直接返回。
    3. 否则乐观返回 True；一旦真实调用暴露「不支持」，由
       :func:`mark_native_schema_unsupported` 记录并缓存为 False。
    """
    declared = getattr(invoker, "supports_native_json_schema", None)
    if isinstance(declared, bool):
        return declared
    if callable(declared):  # pragma: no cover - 依赖调用方实现
        try:
            return bool(declared())
        except Exception as exc:  # noqa: BLE001 - 探测失败按不支持处理
            logger.warning("native schema probe failed: %s", exc)
            return False

    return _NATIVE_SCHEMA_SUPPORT.get(_invoker_cache_key(invoker), True)


def mark_native_schema_unsupported(invoker: Any) -> None:
    """记录「该 invoker 不支持原生 json_schema」，后续调用不再尝试。"""
    _NATIVE_SCHEMA_SUPPORT[_invoker_cache_key(invoker)] = False
    logger.info(
        "provider marked as not supporting native json_schema: %s",
        _invoker_cache_key(invoker),
    )


def reset_capability_cache() -> None:
    """清空能力探测缓存（仅用于测试）。"""
    _NATIVE_SCHEMA_SUPPORT.clear()


def _looks_like_unsupported_schema(exc: Exception) -> bool:
    """判断异常是否由「提供方不支持 json_schema」引起。"""
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(marker in text for marker in _UNSUPPORTED_SCHEMA_MARKERS)


# =============================================================================
# 请求 / 响应处理
# =============================================================================


def _build_response_format(schema: Type[BaseModel]) -> dict[str, Any]:
    """构造原生 json_schema 的 response_format 负载。"""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema.__name__[:64],
            "schema": schema.model_json_schema(),
        },
    }


def _extract_content(response: Any) -> str:
    """从 LLM 响应中提取文本内容，兼容多模态分段结构。"""
    if response is None:
        return ""
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text", "")))
        return "".join(parts)
    if isinstance(content, dict):
        return json.dumps(content, ensure_ascii=False)
    return str(content)


def _parse_payload(content: str, schema: Type[ModelT]) -> ModelT:
    """把文本内容解析为指定 Pydantic 模型。"""
    if not content or not content.strip():
        raise ValueError("empty response content")
    data = extract_first_valid_json(content)
    return schema.model_validate(data)


def _build_repair_message(schema: Type[BaseModel], error: str) -> dict[str, str]:
    """构造修复重试的追加消息。"""
    schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    return {
        "role": "user",
        "content": (
            "上一次输出无法通过校验：" + error + "\n"
            "请严格按下面的 JSON Schema 重新输出，只输出一个 JSON 对象，"
            "不要输出 Markdown 代码块、解释或任何多余文本：\n" + schema_json
        ),
    }


async def invoke_structured(
    invoker: Any,
    messages: list,
    schema: Type[ModelT],
    *,
    max_attempts: int = 2,
    validator: Optional[Callable[[ModelT], None]] = None,
    use_native_schema: bool = True,
    **kwargs: Any,
) -> ModelT:
    """
    调用 LLM 并返回经过 schema 校验的结构化结果。

    Args:
        invoker: 具备 ``ainvoke(messages, **kwargs)`` 的调用器（如 ``LLMInvoker``）。
        messages: 初始消息列表；修复重试会在此基础上追加消息。
        schema: 目标 Pydantic 模型。
        max_attempts: 解析/校验失败后的最大尝试次数（含首次）。
        validator: 额外的业务校验函数，抛异常即触发重试。
        use_native_schema: 是否允许尝试原生 json_schema。
        **kwargs: 透传给 ``invoker.ainvoke`` 的额外参数。

    Returns:
        校验通过的模型实例。

    Raises:
        StructuredOutputError: 全部尝试失败。
    """
    attempts = max(1, int(max_attempts))
    working_messages = list(messages)
    errors: list[str] = []
    last_response: Optional[str] = None
    attempt = 0
    allow_native = bool(use_native_schema)

    while attempt < attempts:
        attempt += 1
        call_kwargs = dict(kwargs)
        use_native = allow_native and supports_native_json_schema(invoker)
        if use_native:
            call_kwargs["response_format"] = _build_response_format(schema)
        else:
            call_kwargs["response_format"] = {"type": "json_object"}

        try:
            response = await invoker.ainvoke(working_messages, **call_kwargs)
        except Exception as exc:  # noqa: BLE001 - 需要区分「不支持」与其他错误
            if use_native and _looks_like_unsupported_schema(exc):
                mark_native_schema_unsupported(invoker)
                attempt -= 1  # 能力探测失败不计入尝试次数
                allow_native = False
                continue
            errors.append(f"invoke_error: {exc}")
            logger.warning("structured invoke failed (attempt %d): %s", attempt, exc)
            continue

        content = _extract_content(response)
        last_response = content

        try:
            parsed = _parse_payload(content, schema)
            if validator is not None:
                validator(parsed)
            return parsed
        except ValidationError as exc:
            message = f"validation_error: {exc.error_count()} issue(s)"
        except Exception as exc:  # noqa: BLE001 - 统一走重试
            message = f"{type(exc).__name__}: {exc}"

        errors.append(message)
        logger.warning(
            "structured parse failed (attempt %d/%d): %s", attempt, attempts, message
        )
        if attempt < attempts:
            working_messages = working_messages + [
                _build_repair_message(schema, message)
            ]

    raise StructuredOutputError(
        f"Failed to obtain valid {schema.__name__} after {attempts} attempt(s)",
        last_response=last_response,
        errors=errors,
        attempts=attempts,
    )


__all__ = [
    "StructuredOutputError",
    "invoke_structured",
    "supports_native_json_schema",
    "mark_native_schema_unsupported",
    "reset_capability_cache",
]
