"""SU-8 分意图、分桶与混淆对测试（离线）。"""

import pytest

from app.evaluation.semantic_metrics import (
    bucket_metrics,
    confusion_pairs,
    per_label_metrics,
)


def test_per_label_metrics_covers_gold_and_predicted_labels():
    pairs = [("a", "a"), ("a", "b"), ("b", "a")]

    metrics = per_label_metrics(pairs)

    assert set(metrics) == {"a", "b"}
    assert metrics["a"].precision == pytest.approx(0.5)
    assert metrics["a"].recall == pytest.approx(0.5)
    assert metrics["a"].f1 == pytest.approx(0.5)
    assert metrics["a"].support == 2
    assert metrics["b"].support == 1
    assert metrics["b"].precision == 0.0
    assert metrics["b"].recall == 0.0


def test_per_label_metrics_empty():
    assert per_label_metrics([]) == {}


def test_confusion_pairs_sorted_by_count_then_label():
    pairs = [("a", "b"), ("a", "b"), ("b", "a")]

    assert confusion_pairs(pairs) == [("a", "b", 2), ("b", "a", 1)]


def test_confusion_pairs_limit():
    pairs = [("a", "b"), ("b", "a")]
    assert confusion_pairs(pairs, limit=1) == [("a", "b", 1)]
    assert confusion_pairs(pairs, limit=0) == []


def test_confusion_pairs_ignores_correct_predictions():
    assert confusion_pairs([("a", "a"), ("b", "b")]) == []


def test_bucket_metrics_groups_and_defaults_missing_bucket():
    records = [
        {
            "bucket": "recipe",
            "gold_intent": "recipe_search",
            "predicted_intent": "recipe_search",
            "ranked_ids": ["r1"],
            "relevant_ids": ["r1"],
        },
        {
            "gold_intent": "cooking_tips",
            "predicted_intent": "cooking_tips",
            "ranked_ids": [],
            "relevant_ids": [],
        },
    ]

    result = bucket_metrics(records, k=5)

    assert set(result) == {"recipe", "default"}
    assert result["recipe"]["records"] == 1
    assert result["recipe"]["intent"]["accuracy"] == 1.0
    assert result["recipe"]["retrieval"]["hit_at_k"] == 1.0
    assert result["default"]["records"] == 1
    assert result["default"]["retrieval"]["samples"] == 0


def test_bucket_metrics_empty():
    assert bucket_metrics([]) == {}


def test_bucket_metrics_custom_bucket_key():
    records = [
        {
            "scene": "weeknight",
            "gold_intent": "recipe_search",
            "predicted_intent": "recipe_search",
        }
    ]

    result = bucket_metrics(records, bucket_key="scene")

    assert set(result) == {"weeknight"}
