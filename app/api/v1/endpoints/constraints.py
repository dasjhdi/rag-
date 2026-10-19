"""只读约束评估 API（SU-17）。"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.reasoning.constraints import constraint_reasoner

router = APIRouter()


class ConstraintCandidate(BaseModel):
    """待评估候选。"""

    id: str = ""
    title: str = ""
    content: str = ""


class ConstraintEvaluateRequest(BaseModel):
    """约束评估请求。"""

    text: str = ""
    diet_constraints: list[str] = Field(default_factory=list)
    ingredients: list[str] = Field(default_factory=list)
    tastes: list[str] = Field(default_factory=list)
    candidates: list[ConstraintCandidate] = Field(default_factory=list)


@router.post("/constraints/evaluate")
async def evaluate_constraints(payload: ConstraintEvaluateRequest) -> dict:
    """解析约束并评估候选；纯计算，不写库、不调用模型。"""
    return constraint_reasoner.evaluate_candidates(
        text=payload.text,
        diet_constraints=payload.diet_constraints,
        ingredients=payload.ingredients,
        tastes=payload.tastes,
        candidates=[item.model_dump() for item in payload.candidates],
    )


__all__ = [
    "ConstraintCandidate",
    "ConstraintEvaluateRequest",
    "evaluate_constraints",
    "router",
]
