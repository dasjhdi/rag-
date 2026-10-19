"""多查询检索离线 A/B 对比（SU-9）。

输入是同一批查询在单查询与多查询两套配置下的排序结果，输出两套配置的
Hit@K/MRR、逐条胜负平、分桶结果与上线建议。所有计算均为纯函数。
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from app.evaluation.semantic_metrics import average, hit_at_k, mrr


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item) for item in value]


def _record_outcome(record: Mapping[str, Any], k: int) -> tuple[float, float, float, float, str]:
    """Return (single_hit, multi_hit, single_mrr, multi_mrr, outcome)."""
    relevant = set(_as_string_list(record.get("relevant_ids")))
    single = _as_string_list(record.get("single_ranked_ids"))
    multi = _as_string_list(record.get("multi_ranked_ids"))

    single_hit = hit_at_k(single, relevant, k)
    multi_hit = hit_at_k(multi, relevant, k)
    single_mrr = mrr(single, relevant)
    multi_mrr = mrr(multi, relevant)

    if multi_hit > single_hit:
        outcome = "win"
    elif multi_hit < single_hit:
        outcome = "loss"
    elif multi_mrr > single_mrr:
        outcome = "win"
    elif multi_mrr < single_mrr:
        outcome = "loss"
    else:
        outcome = "tie"

    return single_hit, multi_hit, single_mrr, multi_mrr, outcome


def _summarize(
    outcomes: Sequence[tuple[float, float, float, float, str]], k: int
) -> dict[str, Any]:
    samples = len(outcomes)
    single_hits = [item[0] for item in outcomes]
    multi_hits = [item[1] for item in outcomes]
    single_mrrs = [item[2] for item in outcomes]
    multi_mrrs = [item[3] for item in outcomes]

    single_hit = average(single_hits)
    multi_hit = average(multi_hits)
    single_mrr = average(single_mrrs)
    multi_mrr = average(multi_mrrs)

    return {
        "samples": samples,
        "k": k,
        "configs": {
            "single": {
                "samples": samples,
                "hit_at_k": round(single_hit, 4),
                "mrr": round(single_mrr, 4),
            },
            "multi": {
                "samples": samples,
                "hit_at_k": round(multi_hit, 4),
                "mrr": round(multi_mrr, 4),
            },
        },
        "delta": {
            "hit_at_k": round(multi_hit - single_hit, 4),
            "mrr": round(multi_mrr - single_mrr, 4),
        },
        "outcomes": {
            "wins": sum(1 for item in outcomes if item[4] == "win"),
            "losses": sum(1 for item in outcomes if item[4] == "loss"),
            "ties": sum(1 for item in outcomes if item[4] == "tie"),
        },
    }


def compare_configurations(
    records: Sequence[Mapping[str, Any]], *, k: int = 5
) -> dict[str, Any]:
    """Compare single-query and multi-query rankings on the same records."""
    outcomes: list[tuple[float, float, float, float, str]] = []
    bucket_outcomes: dict[str, list[tuple[float, float, float, float, str]]] = {}

    for record in records:
        relevant = _as_string_list(record.get("relevant_ids"))
        if not relevant:
            continue

        outcome = _record_outcome(record, k)
        outcomes.append(outcome)

        bucket = record.get("bucket")
        bucket_name = str(bucket).strip() if bucket not in (None, "") else "default"
        bucket_outcomes.setdefault(bucket_name, []).append(outcome)

    result = _summarize(outcomes, k)
    result["buckets"] = {
        bucket: _summarize(items, k) for bucket, items in bucket_outcomes.items()
    }
    return result


def recommend_rollout(
    result: Mapping[str, Any],
    *,
    min_samples: int = 10,
    min_hit_delta: float = 0.0,
    min_mrr_delta: float = 0.0,
) -> dict[str, Any]:
    """Turn A/B metrics into an explicit, auditable rollout decision."""
    samples = int(result.get("samples", 0) or 0)
    delta = result.get("delta", {}) or {}
    hit_delta = float(delta.get("hit_at_k", 0.0) or 0.0)
    mrr_delta = float(delta.get("mrr", 0.0) or 0.0)
    outcomes = result.get("outcomes", {}) or {}
    wins = int(outcomes.get("wins", 0) or 0)
    losses = int(outcomes.get("losses", 0) or 0)

    reasons: list[str] = []
    if samples < min_samples:
        reasons.append(f"samples={samples} < min_samples={min_samples}")
        return {
            "action": "insufficient_data",
            "reasons": reasons,
            "samples": samples,
            "delta": {"hit_at_k": hit_delta, "mrr": mrr_delta},
        }

    if hit_delta < min_hit_delta:
        reasons.append(
            f"hit_at_k_delta={hit_delta:.4f} < min_hit_delta={min_hit_delta:.4f}"
        )
    if mrr_delta < min_mrr_delta:
        reasons.append(
            f"mrr_delta={mrr_delta:.4f} < min_mrr_delta={min_mrr_delta:.4f}"
        )
    if wins <= losses:
        reasons.append(f"wins={wins} <= losses={losses}")

    action = "keep_disabled" if reasons else "enable"
    return {
        "action": action,
        "reasons": reasons,
        "samples": samples,
        "delta": {"hit_at_k": hit_delta, "mrr": mrr_delta},
    }


__all__ = ["compare_configurations", "recommend_rollout"]
