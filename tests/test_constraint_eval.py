"""SU-18 离线评测与配置测试。"""

import json
from pathlib import Path

from app.config.constraint_config import ConstraintReasoningConfig
from app.reasoning.constraints.service import ConstraintReasoner
from scripts.eval_constraints import evaluate_cases, main


CASES_PATH = Path("data/eval/constraint_cases.jsonl")


def _load_cases():
    cases = []
    for line in CASES_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            cases.append(json.loads(line))
    return cases


def test_eval_dataset_has_at_least_twelve_cases():
    assert len(_load_cases()) >= 12


def test_all_eval_cases_pass():
    report = evaluate_cases(_load_cases())
    assert report["total"] >= 12
    assert report["failed"] == 0
    assert report["pass_rate"] == 1.0


def test_failed_case_is_reported():
    cases = [
        {
            "id": "wrong",
            "text": "花生过敏",
            "candidates": [
                {
                    "id": "d1",
                    "title": "宫保鸡丁",
                    "content": "## 必备原料和工具\n- 花生米",
                }
            ],
            "expect_kept": ["d1"],
            "expect_removed": ["d1"],
        }
    ]
    report = evaluate_cases(cases)
    assert report["failed"] == 1
    assert report["results"][0]["passed"] is False


def test_main_returns_zero_for_dataset(capsys):
    code = main(["--cases", str(CASES_PATH)])
    assert code == 0
    output = capsys.readouterr().out
    assert "通过率 100.00%" in output


def test_main_returns_one_for_wrong_expectation(capsys):
    path = Path("tests/_tmp_constraint_cases.jsonl")
    path.write_text(
        json.dumps(
            {
                "id": "wrong",
                "text": "花生过敏",
                "candidates": [
                    {
                        "id": "d1",
                        "title": "宫保鸡丁",
                        "content": "## 必备原料和工具\n- 花生米",
                    }
                ],
                "expect_kept": ["d1"],
                "expect_removed": ["d1"],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    try:
        code = main(["--cases", str(path)])
    finally:
        path.unlink(missing_ok=True)
    assert code == 1
    assert "[FAIL] wrong" in capsys.readouterr().out


def test_config_defaults_are_safe():
    config = ConstraintReasoningConfig()
    assert config.enabled is True
    assert config.strict_allergens is True
    assert config.max_candidates == 20


def test_disabled_config_skips_reasoning():
    reasoner = ConstraintReasoner(ConstraintReasoningConfig(enabled=False))
    decision = reasoner.analyze(text="花生过敏")
    assert decision.enabled is False
    assert not decision.has_constraints
