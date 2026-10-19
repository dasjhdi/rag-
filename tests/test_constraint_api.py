"""SU-17 约束评估 API 测试（离线）。"""

from app.api.v1.endpoints.constraints import (
    ConstraintCandidate,
    ConstraintEvaluateRequest,
    evaluate_constraints,
    router,
)


def test_route_path():
    paths = {route.path for route in router.routes}
    assert "/constraints/evaluate" in paths


async def test_evaluate_endpoint_returns_kept_and_removed():
    payload = ConstraintEvaluateRequest(
        text="我对花生过敏",
        diet_constraints=["花生过敏"],
        candidates=[
            ConstraintCandidate(
                id="d1",
                title="宫保鸡丁",
                content="## 必备原料和工具\n- 花生米\n- 鸡胸肉",
            ),
            ConstraintCandidate(
                id="d2",
                title="清蒸鸡",
                content="## 必备原料和工具\n- 鸡肉",
            ),
        ],
    )
    result = await evaluate_constraints(payload)
    assert result["kept_ids"] == ["d2"]
    assert result["removed_ids"] == ["d1"]
    assert len(result["assessments"]) == 2
    assert result["profile"]["hard_count"] >= 1


async def test_evaluate_endpoint_handles_no_candidates():
    payload = ConstraintEvaluateRequest(text="花生过敏")
    result = await evaluate_constraints(payload)
    assert result["assessments"] == []
    assert result["kept_ids"] == []
    assert result["removed_ids"] == []
