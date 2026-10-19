r"""结构化 JSON 提取回归测试（离线）。

真实故障：qwen 视觉模型返回的 JSON 末尾带有多余的 ``` 代码块围栏，
且 extracted_info 是嵌套对象。旧的实现先用非贪婪正则 `\{[\s\S]*?\}`
截取，遇到嵌套对象时会在第一个 `}` 处截断，导致整段解析失败、
图片识别结果被丢弃。
"""

import pytest

from app.utils.structured_json import extract_first_valid_json


def test_nested_object_with_trailing_fence():
    raw = (
        '\n{\n'
        '    "is_food_related": true,\n'
        '    "intent": "dish_identification",\n'
        '    "extracted_info": {\n'
        '        "dish_name": ["虾仁炒时蔬", "什锦炒虾仁"],\n'
        '        "ingredients": ["虾仁", "西兰花"]\n'
        '    },\n'
        '    "confidence": 0.95\n'
        '}\n```'
    )

    data = extract_first_valid_json(raw)

    assert data["intent"] == "dish_identification"
    assert data["extracted_info"]["ingredients"] == ["虾仁", "西兰花"]


def test_prose_before_and_after_json():
    raw = '好的，这是分析结果：\n{"a": {"b": 1}}\n希望有帮助！'
    assert extract_first_valid_json(raw) == {"a": {"b": 1}}


def test_fenced_json_block():
    raw = '```json\n{"a": {"b": [1, 2]}, "c": "d"}\n```'
    assert extract_first_valid_json(raw) == {"a": {"b": [1, 2]}, "c": "d"}


def test_braces_inside_string_values():
    raw = '{"text": "用 {大括号} 说话", "nested": {"x": 1}}'
    data = extract_first_valid_json(raw)
    assert data["text"] == "用 {大括号} 说话"
    assert data["nested"] == {"x": 1}


def test_escaped_quote_inside_string():
    raw = '{"text": "他说 \\"你好\\" 然后离开", "n": 2}'
    data = extract_first_valid_json(raw)
    assert data["text"] == '他说 "你好" 然后离开'


def test_trailing_comma_is_tolerated():
    raw = '{"a": 1, "b": [1, 2,],}'
    assert extract_first_valid_json(raw) == {"a": 1, "b": [1, 2]}


def test_first_object_wins():
    raw = '{"first": 1} and {"second": 2}'
    assert extract_first_valid_json(raw) == {"first": 1}


def test_raw_json_without_wrapping():
    assert extract_first_valid_json('{"a": 1}') == {"a": 1}


def test_empty_input_raises():
    with pytest.raises(ValueError):
        extract_first_valid_json("")


def test_non_json_input_raises():
    with pytest.raises(ValueError):
        extract_first_valid_json("这里没有任何 JSON 内容")
