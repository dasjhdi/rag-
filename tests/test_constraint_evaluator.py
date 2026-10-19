"""SU-14 / SU-15 候选评估测试（离线）。"""

from langchain_core.documents import Document

from app.knowledge.ontology import extract_ingredients_from_document, find_ingredients
from app.reasoning.constraints.evaluator import (
    assess_document,
    build_evaluation,
    evaluate_documents,
)
from app.reasoning.constraints.parser import parse_constraints


def _doc(doc_id, title, content):
    return Document(
        page_content=content,
        metadata={"id": doc_id, "dish_name": title},
    )


def _recipe(*items):
    return "## 必备原料和工具\n" + "\n".join(f"- {item}" for item in items)


def test_peanut_allergy_excludes_peanut_dish():
    profile = parse_constraints(diet_constraints=["花生过敏"])
    assessment = assess_document(
        _doc("d1", "宫保鸡丁", _recipe("鸡胸肉", "花生米")), profile
    )
    assert assessment.excluded
    assert any("花生" in reason for reason in assessment.exclusion_reasons)
    assert assessment.allergen_hits["peanut"] == ["花生"]


def test_vegetarian_excludes_pork():
    profile = parse_constraints(text="我是素食")
    assessment = assess_document(
        _doc("d1", "红烧肉", _recipe("五花肉", "酱油")), profile
    )
    assert assessment.excluded
    assert any("素食" in reason for reason in assessment.exclusion_reasons)


def test_vegan_excludes_egg():
    profile = parse_constraints(text="我是纯素")
    assessment = assess_document(
        _doc("d1", "番茄炒蛋", _recipe("番茄", "鸡蛋")), profile
    )
    assert assessment.excluded


def test_gluten_free_excludes_flour():
    profile = parse_constraints(text="无麸质")
    assessment = assess_document(
        _doc("d1", "鸡蛋饼", _recipe("面粉", "鸡蛋")), profile
    )
    assert assessment.excluded


def test_explicit_exclusion_excludes_pork():
    profile = parse_constraints(text="不吃猪肉")
    assessment = assess_document(
        _doc("d1", "回锅肉", _recipe("五花肉", "青椒")), profile
    )
    assert assessment.excluded
    assert any("猪肉" in reason for reason in assessment.exclusion_reasons)


def test_empty_content_is_unknown_but_not_excluded():
    profile = parse_constraints(diet_constraints=["花生过敏"])
    assessment = assess_document(_doc("d1", "神秘料理", ""), profile)
    assert assessment.unknown
    assert not assessment.excluded


def test_all_candidates_excluded_falls_back():
    profile = parse_constraints(diet_constraints=["花生过敏"])
    docs = [
        _doc("d1", "宫保鸡丁", _recipe("花生米")),
        _doc("d2", "花生糖", _recipe("花生")),
    ]
    outcome = build_evaluation(docs, profile)
    assert outcome.fallback_used
    assert [
        item.metadata["id"] for item in outcome.ordered_documents
    ] == ["d1", "d2"]


def test_soft_constraints_rank_without_excluding():
    profile = parse_constraints(text="低脂")
    docs = [
        _doc("d1", "炸鸡", _recipe("鸡肉") + "\n\n## 操作\n1. 油炸"),
        _doc("d2", "清蒸鸡", _recipe("鸡肉") + "\n\n## 操作\n1. 清蒸"),
    ]
    outcome = build_evaluation(docs, profile)
    assert [
        item.metadata["id"] for item in outcome.ordered_documents
    ] == ["d2", "d1"]
    assert all(not item.excluded for item in outcome.assessments)


def test_same_soft_score_keeps_original_order():
    profile = parse_constraints(text="低脂")
    docs = [
        _doc("d1", "番茄汤", _recipe("番茄")),
        _doc("d2", "黄瓜汤", _recipe("黄瓜")),
    ]
    outcome = build_evaluation(docs, profile)
    assert [
        item.metadata["id"] for item in outcome.ordered_documents
    ] == ["d1", "d2"]


def test_dish_title_does_not_create_false_ingredient():
    profile = parse_constraints(text="对鱼过敏")
    assessment = assess_document(
        _doc("d1", "鱼香肉丝", _recipe("猪肉", "木耳", "青椒")), profile
    )
    assert not assessment.excluded


def test_find_ingredients_blocks_dish_name_false_positives():
    assert find_ingredients("鱼香肉丝") == []
    assert find_ingredients("素鸡") == []
    assert find_ingredients("花生米、鸡胸肉") == ["花生", "鸡肉"]


def test_extract_ingredients_prefers_ingredient_section():
    content = (
        "# 鱼香肉丝的做法\n\n"
        "这是一道鱼香味的菜。\n\n"
        "## 必备原料和工具\n- 猪肉\n- 木耳\n\n"
        "## 操作\n1. 炒熟\n"
    )
    assert extract_ingredients_from_document(content, "鱼香肉丝") == ["猪肉", "木耳"]


def test_low_fat_soft_miss_does_not_exclude():
    profile = parse_constraints(text="低脂")
    assessment = assess_document(
        _doc("d1", "炸鸡", _recipe("鸡肉") + "\n\n## 操作\n1. 油炸"), profile
    )
    assert not assessment.excluded
    detail = next(
        item for item in assessment.soft_details if item["constraint"].endswith("low_fat")
    )
    assert detail["hit"] is False


def test_low_sugar_penalises_rock_sugar():
    profile = parse_constraints(text="控糖")
    assessment = assess_document(
        _doc("d1", "冰糖番茄", _recipe("番茄", "冰糖")), profile
    )
    detail = next(
        item
        for item in assessment.soft_details
        if item["constraint"].endswith("low_sugar")
    )
    assert detail["hit"] is False
    assert not assessment.excluded


def test_high_protein_hits_chicken():
    profile = parse_constraints(text="高蛋白")
    assessment = assess_document(
        _doc("d1", "鸡胸肉沙拉", _recipe("鸡胸肉", "生菜")), profile
    )
    detail = next(
        item
        for item in assessment.soft_details
        if item["constraint"].endswith("high_protein")
    )
    assert detail["hit"] is True


def test_substitutions_always_need_confirmation():
    profile = parse_constraints(diet_constraints=["花生过敏"])
    assessment = assess_document(
        _doc("d1", "宫保鸡丁", _recipe("花生米")), profile
    )
    assert assessment.substitutions
    assert all("需确认" in item for item in assessment.substitutions)


def test_evaluate_documents_preserves_input_order():
    profile = parse_constraints(text="低脂")
    docs = [
        _doc("d1", "清蒸鸡", _recipe("鸡肉") + "\n\n## 操作\n1. 清蒸"),
        _doc("d2", "炸鸡", _recipe("鸡肉") + "\n\n## 操作\n1. 油炸"),
    ]
    assessments = evaluate_documents(docs, profile)
    assert [item.document_id for item in assessments] == ["d1", "d2"]
