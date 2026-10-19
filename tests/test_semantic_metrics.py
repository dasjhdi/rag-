"""SU-7 语义评测指标与 runner 测试（离线）。"""

import json

import pytest

from app.evaluation.semantic_metrics import (
    average,
    hit_at_k,
    intent_accuracy,
    intent_macro_f1,
    mrr,
)
from scripts.eval_semantic import evaluate, main


def test_intent_accuracy_basic_and_empty():
    assert intent_accuracy([("a", "a"), ("b", "c")]) == 0.5
    assert intent_accuracy([]) == 0.0


def test_intent_macro_f1_perfect_predictions():
    pairs = [("a", "a"), ("b", "b"), ("c", "c")]
    assert intent_macro_f1(pairs) == 1.0


def test_intent_macro_f1_partial_predictions():
    pairs = [("a", "a"), ("b", "a"), ("c", "c")]
    score = intent_macro_f1(pairs)
    assert 0.0 < score < 1.0


def test_intent_macro_f1_empty():
    assert intent_macro_f1([]) == 0.0


def test_hit_at_k_hit_and_miss():
    assert hit_at_k(["x", "y", "z"], {"y"}, 2) == 1.0
    assert hit_at_k(["x", "y", "z"], {"y"}, 1) == 0.0
    assert hit_at_k(["x", "y", "z"], {"z"}, 3) == 1.0


def test_hit_at_k_boundaries():
    assert hit_at_k(["x"], {"x"}, 0) == 0.0
    assert hit_at_k(["x"], {"x"}, -1) == 0.0
    assert hit_at_k(["x"], set(), 5) == 0.0
    assert hit_at_k([], {"x"}, 5) == 0.0


def test_mrr_first_third_and_miss():
    assert mrr(["a", "b"], {"a"}) == 1.0
    assert mrr(["a", "b", "c"], {"c"}) == pytest.approx(1 / 3)
    assert mrr(["a", "b"], {"z"}) == 0.0
    assert mrr([], {"z"}) == 0.0


def test_average():
    assert average([1.0, 0.0, 0.5]) == pytest.approx(0.5)
    assert average([]) == 0.0


def test_evaluate_combines_intent_and_retrieval_metrics():
    records = [
        {
            "gold_intent": "a",
            "predicted_intent": "a",
            "ranked_ids": ["r1"],
            "relevant_ids": ["r1"],
        },
        {
            "gold_intent": "b",
            "predicted_intent": "a",
            "ranked_ids": ["r2", "r3"],
            "relevant_ids": ["r3"],
        },
    ]

    summary = evaluate(records, k=5)

    assert summary["records"] == 2
    assert summary["intent"]["accuracy"] == 0.5
    assert summary["retrieval"]["samples"] == 2
    assert summary["retrieval"]["hit_at_k"] == 1.0
    assert summary["retrieval"]["mrr"] == pytest.approx(0.75)


def test_main_runs_against_repository_fixture(capsys):
    exit_code = main(
        ["--predictions", "data/eval/intent_predictions.jsonl", "--k", "5"]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["records"] == 45
    assert output["intent"]["samples"] == 45
    assert output["retrieval"]["samples"] == 36
    assert output["intent"]["accuracy"] == pytest.approx(0.8889)
    assert output["retrieval"]["hit_at_k"] == pytest.approx(0.8889)
    assert output["retrieval"]["mrr"] == pytest.approx(0.7778)
    assert set(output["per_intent"]) == {
        "recipe_search",
        "cooking_tips",
        "ingredient_info",
        "recommendation",
        "general_chat",
    }
    assert set(output["buckets"]) == {
        "recipe",
        "ingredient",
        "technique",
        "recommendation",
        "chat",
    }
    assert output["confusions"]


def test_main_rejects_missing_file():
    with pytest.raises(SystemExit):
        main(["--predictions", "data/eval/does-not-exist.jsonl"])
