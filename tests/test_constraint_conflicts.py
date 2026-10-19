"""SU-16 冲突检测测试（离线）。"""

from app.reasoning.constraints.conflicts import (
    build_clarification_question,
    detect_conflicts,
)
from app.reasoning.constraints.parser import parse_constraints


def test_vegan_with_egg_conflicts():
    profile = parse_constraints(text="我是纯素", ingredients=["鸡蛋"])
    conflicts = detect_conflicts(profile)
    assert any("纯素" in item and "鸡蛋" in item for item in conflicts)


def test_vegetarian_with_pork_conflicts():
    profile = parse_constraints(text="我是素食", ingredients=["五花肉"])
    conflicts = detect_conflicts(profile)
    assert any("素食" in item and "五花肉" in item for item in conflicts)


def test_gluten_free_with_flour_conflicts():
    profile = parse_constraints(text="无麸质", ingredients=["面粉"])
    conflicts = detect_conflicts(profile)
    assert any("无麸质" in item and "面粉" in item for item in conflicts)


def test_allergen_with_explicit_include_conflicts():
    profile = parse_constraints(
        diet_constraints=["花生过敏"], ingredients=["花生"]
    )
    conflicts = detect_conflicts(profile)
    assert any("花生" in item for item in conflicts)


def test_include_and_exclude_same_ingredient_conflicts():
    profile = parse_constraints(text="想吃鸡蛋但不吃鸡蛋")
    conflicts = detect_conflicts(profile)
    assert any("同时被要求包含和排除" in item for item in conflicts)


def test_conflict_builds_clarification_question():
    profile = parse_constraints(text="我是纯素", ingredients=["鸡蛋"])
    conflicts = detect_conflicts(profile)
    question = build_clarification_question(conflicts)
    assert question
    assert "请确认" in question


def test_no_conflict_for_compatible_profile():
    profile = parse_constraints(text="我是纯素", ingredients=["豆腐"])
    assert detect_conflicts(profile) == []
    assert build_clarification_question([]) is None
