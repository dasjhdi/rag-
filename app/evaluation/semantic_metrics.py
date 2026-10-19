"""语义理解评测指标（SU-7）。

所有函数都是纯函数，不依赖网络、数据库或模型，方便在 CI 与本地离线运行。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class LabelMetrics:
    """Per-label classification metrics."""

    precision: float
    recall: float
    f1: float
    support: int

    def to_dict(self) -> dict[str, float | int]:
        return {
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "support": self.support,
        }


def intent_accuracy(pairs: Sequence[tuple[str, str]]) -> float:
    """Return the fraction of (gold, predicted) pairs that match exactly."""
    if not pairs:
        return 0.0
    correct = sum(1 for gold, predicted in pairs if gold == predicted)
    return correct / len(pairs)


def intent_macro_f1(pairs: Sequence[tuple[str, str]]) -> float:
    """Return macro-averaged F1 over every label seen in gold or predictions."""
    if not pairs:
        return 0.0

    labels = sorted({label for pair in pairs for label in pair})
    scores: list[float] = []

    for label in labels:
        true_positive = sum(
            1 for gold, predicted in pairs if gold == label and predicted == label
        )
        false_positive = sum(
            1 for gold, predicted in pairs if gold != label and predicted == label
        )
        false_negative = sum(
            1 for gold, predicted in pairs if gold == label and predicted != label
        )

        precision = (
            true_positive / (true_positive + false_positive)
            if true_positive + false_positive
            else 0.0
        )
        recall = (
            true_positive / (true_positive + false_negative)
            if true_positive + false_negative
            else 0.0
        )
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
        scores.append(f1)

    return sum(scores) / len(scores)


def hit_at_k(ranked_ids: Sequence[str], relevant: set[str], k: int) -> float:
    """Return 1.0 when any relevant item appears in the first ``k`` results."""
    if k <= 0 or not relevant:
        return 0.0
    return 1.0 if set(ranked_ids[:k]) & set(relevant) else 0.0


def mrr(ranked_ids: Sequence[str], relevant: set[str]) -> float:
    """Return the reciprocal rank of the first relevant item, or 0.0."""
    if not relevant:
        return 0.0
    for index, item in enumerate(ranked_ids, start=1):
        if item in relevant:
            return 1.0 / index
    return 0.0


def average(values: Sequence[float]) -> float:
    """Return the arithmetic mean, or 0.0 for an empty sequence."""
    items = list(values)
    if not items:
        return 0.0
    return sum(items) / len(items)


def per_label_metrics(
    pairs: Sequence[tuple[str, str]],
) -> dict[str, LabelMetrics]:
    """Compute precision/recall/F1/support for every observed label."""
    labels = sorted({label for pair in pairs for label in pair})
    result: dict[str, LabelMetrics] = {}

    for label in labels:
        true_positive = sum(
            1 for gold, predicted in pairs if gold == label and predicted == label
        )
        false_positive = sum(
            1 for gold, predicted in pairs if gold != label and predicted == label
        )
        false_negative = sum(
            1 for gold, predicted in pairs if gold == label and predicted != label
        )
        support = sum(1 for gold, _ in pairs if gold == label)

        precision = (
            true_positive / (true_positive + false_positive)
            if true_positive + false_positive
            else 0.0
        )
        recall = (
            true_positive / (true_positive + false_negative)
            if true_positive + false_negative
            else 0.0
        )
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
        result[label] = LabelMetrics(
            precision=precision,
            recall=recall,
            f1=f1,
            support=support,
        )

    return result


def confusion_pairs(
    pairs: Sequence[tuple[str, str]], *, limit: int = 10
) -> list[tuple[str, str, int]]:
    """Return the most frequent (gold, predicted) mistakes."""
    counts: dict[tuple[str, str], int] = {}
    for gold, predicted in pairs:
        if gold == predicted:
            continue
        counts[(gold, predicted)] = counts.get((gold, predicted), 0) + 1

    ordered = sorted(
        counts.items(),
        key=lambda item: (-item[1], item[0][0], item[0][1]),
    )
    max_items = max(0, int(limit))
    return [(gold, predicted, count) for (gold, predicted), count in ordered[:max_items]]


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item) for item in value]


def bucket_metrics(
    records: Sequence[Mapping[str, Any]],
    *,
    bucket_key: str = "bucket",
    k: int = 5,
) -> dict[str, dict[str, Any]]:
    """Compute intent and retrieval metrics per business bucket."""
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for record in records:
        bucket = record.get(bucket_key)
        bucket_name = str(bucket).strip() if bucket not in (None, "") else "default"
        grouped.setdefault(bucket_name, []).append(record)

    result: dict[str, dict[str, Any]] = {}
    for bucket_name, items in grouped.items():
        intent_pairs = [
            (str(item["gold_intent"]), str(item["predicted_intent"]))
            for item in items
            if "gold_intent" in item and "predicted_intent" in item
        ]

        hit_values: list[float] = []
        reciprocal_ranks: list[float] = []
        for item in items:
            ranked = _as_string_list(item.get("ranked_ids"))
            relevant = set(_as_string_list(item.get("relevant_ids")))
            if not ranked and not relevant:
                continue
            hit_values.append(hit_at_k(ranked, relevant, k))
            reciprocal_ranks.append(mrr(ranked, relevant))

        result[bucket_name] = {
            "records": len(items),
            "intent": {
                "samples": len(intent_pairs),
                "accuracy": round(intent_accuracy(intent_pairs), 4),
                "macro_f1": round(intent_macro_f1(intent_pairs), 4),
            },
            "retrieval": {
                "samples": len(hit_values),
                "hit_at_k": round(average(hit_values), 4),
                "mrr": round(average(reciprocal_ranks), 4),
                "k": k,
            },
        }

    return result


__all__ = [
    "intent_accuracy",
    "intent_macro_f1",
    "hit_at_k",
    "mrr",
    "average",
    "LabelMetrics",
    "per_label_metrics",
    "confusion_pairs",
    "bucket_metrics",
]
