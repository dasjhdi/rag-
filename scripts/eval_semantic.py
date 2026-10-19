"""CookHero 离线语义评测 runner。

用法：

    python -m scripts.eval_semantic --predictions data/eval/intent_predictions.jsonl

每条 JSONL 可包含以下字段：

- ``gold_intent`` / ``predicted_intent``：意图分类
- ``ranked_ids`` / ``relevant_ids``：检索排序结果与相关集合
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable, Optional

from app.evaluation.semantic_metrics import (
    average,
    bucket_metrics,
    confusion_pairs,
    hit_at_k,
    intent_accuracy,
    intent_macro_f1,
    mrr,
    per_label_metrics,
)


def _load_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                item = json.loads(text)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"第 {line_number} 行不是合法 JSON：{exc}") from exc
            if isinstance(item, dict):
                records.append(item)
    return records


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item) for item in value]


def evaluate(
    records: Iterable[dict[str, Any]],
    *,
    k: int = 5,
    top_confusions: int = 10,
    bucket_key: str = "bucket",
) -> dict[str, Any]:
    """Compute intent and retrieval metrics from parsed prediction records."""
    items = list(records)

    intent_pairs = [
        (str(item["gold_intent"]), str(item["predicted_intent"]))
        for item in items
        if "gold_intent" in item and "predicted_intent" in item
    ]

    hit_values: list[float] = []
    reciprocal_ranks: list[float] = []
    for item in items:
        ranked = _string_list(item.get("ranked_ids"))
        relevant = set(_string_list(item.get("relevant_ids")))
        if not ranked and not relevant:
            continue
        hit_values.append(hit_at_k(ranked, relevant, k))
        reciprocal_ranks.append(mrr(ranked, relevant))

    label_metrics = per_label_metrics(intent_pairs)

    return {
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
        "per_intent": {
            label: metrics.to_dict() for label, metrics in label_metrics.items()
        },
        "confusions": [
            {"gold": gold, "predicted": predicted, "count": count}
            for gold, predicted, count in confusion_pairs(
                intent_pairs, limit=top_confusions
            )
        ],
        "buckets": bucket_metrics(items, bucket_key=bucket_key, k=k),
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="CookHero 离线语义评测")
    parser.add_argument(
        "--predictions",
        default="data/eval/intent_predictions.jsonl",
        help="JSONL 预测文件路径",
    )
    parser.add_argument("--k", type=int, default=5, help="Hit@K 的 K 值")
    parser.add_argument(
        "--top-confusions", type=int, default=10, help="最多输出的混淆对数量"
    )
    parser.add_argument(
        "--bucket-key", default="bucket", help="分桶字段名（默认 bucket）"
    )
    args = parser.parse_args(argv)

    path = Path(args.predictions)
    if not path.exists():
        raise SystemExit(f"找不到预测文件：{path}")

    summary = evaluate(
        _load_records(path),
        k=args.k,
        top_confusions=args.top_confusions,
        bucket_key=args.bucket_key,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
