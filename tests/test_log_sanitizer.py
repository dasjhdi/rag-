"""日志脱敏过滤器：带参数的日志不能因脱敏而抛异常。"""

import logging

from app.security.sanitizer import SensitiveDataFilter


def _record(msg, *args, **kwargs):
    # LogRecord 需要「单元素元组包住 mapping」才会正确解包
    record_args = (kwargs,) if kwargs else (args or None)
    return logging.LogRecord(
        name="test",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=record_args,
        exc_info=None,
    )


def test_filter_renders_args_without_type_error():
    """模板含敏感键（token）时脱敏会改写模板；必须先渲染再脱敏，否则抛 TypeError。"""
    flt = SensitiveDataFilter()
    record = _record("Failed to decode refresh token: %s", "Signature has expired.")

    assert flt.filter(record) is True
    # 关键：不抛 TypeError，且消息仍可被格式化
    message = record.getMessage()
    assert isinstance(message, str) and message.startswith("Failed to decode")


def test_filter_masks_sensitive_values():
    flt = SensitiveDataFilter()
    record = _record("login with password=%s", "hunter2")

    flt.filter(record)
    assert "hunter2" not in record.getMessage()


def test_filter_handles_dict_args():
    flt = SensitiveDataFilter()
    record = _record("payload token=%(token)s", token="abc123")

    assert flt.filter(record) is True
    assert "abc123" not in record.getMessage()


def test_filter_survives_broken_template():
    """模板与参数不匹配时也不能抛异常。"""
    flt = SensitiveDataFilter()
    record = _record("no placeholder here", "extra")

    assert flt.filter(record) is True
    assert record.getMessage()
