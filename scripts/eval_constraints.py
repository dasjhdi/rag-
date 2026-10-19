"""离线约束推理评测（SU-18）。

不依赖网络、Milvus、Redis、PostgreSQL 或模型下载。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Optional, Sequence

from app.reasoning.constraints import constraint_reasoner


def _load_cases(path: str | Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def _evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    result = constraint_reasoner.evaluate_candidates(
        text=str(case.get("text") or ""),
        diet_constraints=case.get("diet_constraints") or [],
        ingredients=case.get("ingredients") or [],
        tastes=case.get("tastes") or [],
        candidates=case.get("candidates") or [],
    )

    failures: list[str] = []
    kept_ids = list(result.get("kept_ids") or [])
    removed_ids = list(result.get("removed_ids") or [])
    unknown_terms = list(result.get("profile", {}).get("unknown_terms") or [])
    assessments = list(result.get("assessments") or [])
    unknown_docs = [
        item.get("document_id") for item in assessments if item.get("unknown")
    ]

    if "expect_kept" in case and kept_ids != list(case["expect_kept"]):
        failures.append(
            f"kept_ids 期望 {case['expect_kept']}，实际 {kept_ids}"
        )
    if "expect_removed" in case and sorted(removed_ids) != sorted(
        case["expect_removed"]
    ):
        failures.append(
            f"removed_ids 期望 {case['expect_removed']}，实际 {removed_ids}"
        )
    if "expect_conflict" in case and bool(result.get("conflicts")) != bool(
        case["expect_conflict"]
    ):
        failures.append(
            f"conflict 期望 {case['expect_conflict']}，实际 {result.get('conflicts')}"
        )
    if "expect_fallback" in case and bool(result.get("fallback_used")) != bool(
        case["expect_fallback"]
    ):
        failures.append(
            f"fallback 期望 {case['expect_fallback']}，实际 {result.get('fallback_used')}"
        )
    for term in case.get("expect_unknown_contains") or []:
        if term not in unknown_terms:
            failures.append(f"unknown_terms 缺少「{term}」：{unknown_terms}")
    for document_id in case.get("expect_unknown_docs") or []:
        if document_id not in unknown_docs:
            failures.append(
                f"候选「{document_id}」未被标记 unknown：{unknown_docs}"
            )

    return {
        "id": str(case.get("id") or ""),
        "passed": not failures,
        "failures": failures,
        "kept_ids": kept_ids,
        "removed_ids": removed_ids,
        "conflicts": list(result.get("conflicts") or []),
        "unknown_terms": unknown_terms,
        "fallback_used": bool(result.get("fallback_used")),
    }


def evaluate_cases(cases: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """逐条评估并返回汇总结果。"""
    results = [_evaluate_case(case) for case in cases]
    total = len(results)
    passed = sum(1 for item in results if item["passed"])
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": (passed / total) if total else 1.0,
        "results": results,
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="CookHero 约束推理离线评测")
    parser.add_argument(
        "--cases",
        default="data/eval/constraint_cases.jsonl",
        help="JSONL 评测集路径",
    )
    args = parser.parse_args(argv)

    cases = _load_cases(args.cases)
    report = evaluate_cases(cases)

    for item in report["results"]:
        if item["passed"]:
            print(f"[PASS] {item['id']}")
        else:
            print(f"[FAIL] {item['id']}: {'；'.join(item['failures'])}")

    print(
        f"总计 {report['total']} 条，通过 {report['passed']} 条，"
        f"失败 {report['failed']} 条，通过率 {report['pass_rate']:.2%}"
    )
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
