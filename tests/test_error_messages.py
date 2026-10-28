"""模型异常的用户可读文案。

前端不应展示供应商原始报文（例如 403 的 JSON），否则用户看到一串无法
自助处理的内容；原始异常仍写在后端日志里。
"""

from app.utils.error_messages import friendly_llm_error

RAW_403 = (
    "Error code: 403 - {'error': {'message': 'Access to model denied. Please make "
    "sure you are eligible for using the model.', 'type': 'AccessDenied.Unpurchased'}}"
)


class TestFriendlyError:
    def test_model_denied_is_actionable(self):
        message = friendly_llm_error(Exception(RAW_403))
        assert "403" in message
        assert "API Key" in message
        # 不能把供应商原文透给用户
        assert "Access to model denied" not in message
        assert "{" not in message

    def test_unauthorized(self):
        assert "401" in friendly_llm_error("401 Unauthorized: invalid api key")

    def test_rate_limited(self):
        assert "429" in friendly_llm_error("Error code: 429 - rate limit reached")

    def test_timeout(self):
        assert "超时" in friendly_llm_error("Request timed out after 30s")

    def test_connection(self):
        assert "网络" in friendly_llm_error("Connection error: getaddrinfo failed")

    def test_unknown_falls_back(self):
        message = friendly_llm_error("something odd happened")
        assert message == "回答生成失败，请稍后再试。"
        assert "odd" not in message

    def test_accepts_plain_string_and_none(self):
        assert friendly_llm_error("") == "回答生成失败，请稍后再试。"
