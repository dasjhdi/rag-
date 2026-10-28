"""把底层模型/网络异常翻译成用户能看懂的话。

后台日志仍然记录原始异常（含 request id），但前端不展示供应商原文——
否则用户会看到 `Error code: 403 - {'error': {'message': 'Access to model
denied...` 这类无法自助处理的长串。
"""

from __future__ import annotations


def friendly_llm_error(exc: BaseException | str) -> str:
    """把异常映射成一句可操作的提示。"""
    text = str(exc or "")
    lowered = text.lower()

    if "accessdenied" in lowered or "access to model denied" in lowered or "403" in text:
        return "模型服务拒绝访问（403）：当前 API Key 无权使用配置的模型，请联系管理员检查 LLM 配置。"
    if "401" in text or "invalid api key" in lowered or "unauthorized" in lowered:
        return "模型服务鉴权失败（401）：请检查 API Key 是否正确或已过期。"
    if "429" in text or "rate limit" in lowered or "too many requests" in lowered:
        return "模型服务限流（429）：请求过于频繁，请稍后重试。"
    if "timeout" in lowered or "timed out" in lowered:
        return "模型服务响应超时，请稍后重试。"
    if "connection" in lowered or "connect" in lowered or "network" in lowered:
        return "无法连接模型服务，请检查网络后重试。"
    return "回答生成失败，请稍后再试。"
