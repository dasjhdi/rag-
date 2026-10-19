"""多查询检索离线 A/B runner（SU-9）。

用法：

    python -m scripts.eval_multi_query_ab --predictions data/eval/multi_query_ab.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Optional

from app.evaluation.ab_compare import compare_configurations, recommend_rollout


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


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="CookHero 多查询 A/B 离线评测")
    parser.add_argument(
        "--predictions",
        default="data/eval/multi_query_ab.jsonl",
        help="JSONL 预测文件路径",
    )
    parser.add_argument("--k", type=int, default=5, help="Hit@K 的 K 值")
    parser.add_argument(
        "--min-samples", type=int, default=10, help="给出开启建议所需的最少样本数"
    )
    parser.add_argument(
        "--min-hit-delta", type=float, default=0.0, help="允许开启的最小 Hit@K 增益"
    )
    parser.add_argument(
        "--min-mrr-delta", type=float, default=0.0, help="允许开启的最小 MRR 增益"
    )
    args = parser.parse_args(argv)

    path = Path(args.predictions)
    if not path.exists():
        raise SystemExit(f"找不到预测文件：{path}")

    result = compare_configurations(_load_records(path), k=args.k)
    result["recommendation"] = recommend_rollout(
        result,
        min_samples=args.min_samples,
        min_hit_delta=args.min_hit_delta,
        min_mrr_delta=args.min_mrr_delta,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
