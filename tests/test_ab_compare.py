"""SU-9 多查询离线 A/B 测试（离线）。"""

import json

import pytest

from app.evaluation.ab_compare import compare_configurations, recommend_rollout
from scripts.eval_multi_query_ab import main


def _record(single, multi, relevant=None, bucket="recipe"):
    return {
        "query": "测试查询",
        "bucket": bucket,
        "relevant_ids": ["r1"] if relevant is None else relevant,
        "single_ranked_ids": single,
        "multi_ranked_ids": multi,
    }


def test_multi_wins_when_hit_at_k_improves():
    result = compare_configurations([_record(["x1"], ["r1"])], k=5)

    assert result["outcomes"] == {"wins": 1, "losses": 0, "ties": 0}
    assert result["configs"]["single"]["hit_at_k"] == 0.0
    assert result["configs"]["multi"]["hit_at_k"] == 1.0


def test_multi_wins_when_hit_ties_but_mrr_improves():
    result = compare_configurations([_record(["x1", "r1"], ["r1"])], k=5)

    assert result["configs"]["single"]["hit_at_k"] == 1.0
    assert result["configs"]["multi"]["hit_at_k"] == 1.0
    assert result["configs"]["single"]["mrr"] == 0.5
    assert result["configs"]["multi"]["mrr"] == 1.0
    assert result["outcomes"]["wins"] == 1


def test_tie_when_hit_and_mrr_are_equal():
    result = compare_configurations([_record(["r1"], ["r1"])], k=5)

    assert result["outcomes"] == {"wins": 0, "losses": 0, "ties": 1}
    assert result["delta"] == {"hit_at_k": 0.0, "mrr": 0.0}


def test_single_wins_when_multi_is_worse():
    result = compare_configurations([_record(["r1"], ["x1"])], k=5)

    assert result["outcomes"] == {"wins": 0, "losses": 1, "ties": 0}
    assert result["delta"]["hit_at_k"] == -1.0


def test_records_without_relevant_ids_are_skipped():
    result = compare_configurations([_record(["x1"], ["r1"], relevant=[])], k=5)

    assert result["samples"] == 0
    assert result["configs"]["single"]["hit_at_k"] == 0.0


def test_missing_ranking_list_is_treated_as_empty():
    record = {
        "bucket": "recipe",
        "relevant_ids": ["r1"],
        "multi_ranked_ids": ["r1"],
    }

    result = compare_configurations([record], k=5)

    assert result["configs"]["single"]["hit_at_k"] == 0.0
    assert result["outcomes"]["wins"] == 1


def test_recommend_rollout_insufficient_data():
    result = compare_configurations([_record(["x1"], ["r1"])], k=5)

    decision = recommend_rollout(result, min_samples=10)

    assert decision["action"] == "insufficient_data"
    assert decision["reasons"]


def test_recommend_rollout_enable():
    records = [_record(["x1"], ["r1"]) for _ in range(10)]
    result = compare_configurations(records, k=5)

    decision = recommend_rollout(result, min_samples=10)

    assert decision["action"] == "enable"
    assert decision["reasons"] == []
    assert decision["delta"] == {"hit_at_k": 1.0, "mrr": 1.0}


def test_recommend_rollout_keeps_disabled_when_mrr_drops():
    records = [_record(["r1"], ["x1", "r1"]) for _ in range(10)]
    result = compare_configurations(records, k=5)

    decision = recommend_rollout(result, min_samples=10)

    assert decision["action"] == "keep_disabled"
    assert any("mrr" in reason for reason in decision["reasons"])


def test_bucket_metrics_include_delta_and_outcomes():
    records = [
        _record(["x1"], ["r1"], bucket="recipe"),
        _record(["r1"], ["x1"], bucket="ingredient"),
    ]

    result = compare_configurations(records, k=5)

    assert set(result["buckets"]) == {"recipe", "ingredient"}
    assert result["buckets"]["recipe"]["delta"]["hit_at_k"] == 1.0
    assert result["buckets"]["ingredient"]["outcomes"]["losses"] == 1


def test_script_runs_against_repository_fixture(capsys):
    exit_code = main(["--predictions", "data/eval/multi_query_ab.jsonl"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["samples"] == 15
    assert output["recommendation"]["action"] == "enable"
    assert output["outcomes"]["wins"] > output["outcomes"]["losses"]
    assert output["buckets"]
