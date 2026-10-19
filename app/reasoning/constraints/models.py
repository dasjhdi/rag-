"""约束推理的数据模型（SU-13、SU-14）。

该模块只定义纯数据结构和少量便捷视图，不含任何解析或评估逻辑，
方便被解析器、评估器、冲突检测与服务层共享。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ConstraintKind(str, Enum):
    """约束种类。"""

    ALLERGEN = "allergen"
    DIET = "diet"
    EXCLUDE_INGREDIENT = "exclude_ingredient"
    INCLUDE_INGREDIENT = "include_ingredient"
    NUTRITION = "nutrition"
    TASTE = "taste"


class ConstraintSeverity(str, Enum):
    """约束严重级别：硬约束排除候选，软约束只影响排序。"""

    HARD = "hard"
    SOFT = "soft"


@dataclass(frozen=True)
class Constraint:
    """单条结构化约束。"""

    kind: ConstraintKind
    value: str
    severity: ConstraintSeverity
    source: str = "slot"
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "value": self.value,
            "severity": self.severity.value,
            "source": self.source,
            "label": self.label or self.value,
        }


@dataclass
class ConstraintProfile:
    """一次请求解析出的全部约束、来源与未知项。"""

    constraints: list[Constraint] = field(default_factory=list)
    unknown_terms: list[str] = field(default_factory=list)

    @property
    def hard_constraints(self) -> list[Constraint]:
        return [
            item
            for item in self.constraints
            if item.severity is ConstraintSeverity.HARD
        ]

    @property
    def soft_constraints(self) -> list[Constraint]:
        return [
            item
            for item in self.constraints
            if item.severity is ConstraintSeverity.SOFT
        ]

    @property
    def is_empty(self) -> bool:
        return not self.constraints

    def to_dict(self) -> dict[str, Any]:
        return {
            "constraints": [item.to_dict() for item in self.constraints],
            "hard_count": len(self.hard_constraints),
            "soft_count": len(self.soft_constraints),
            "unknown_terms": list(self.unknown_terms),
        }


@dataclass
class DishAssessment:
    """单个候选菜谱的评估结果。"""

    index: int
    document_id: str
    title: str
    ingredients: list[str] = field(default_factory=list)
    unknown: bool = False
    excluded: bool = False
    exclusion_reasons: list[str] = field(default_factory=list)
    allergen_hits: dict[str, list[str]] = field(default_factory=dict)
    soft_score: float = 1.0
    soft_details: list[dict[str, Any]] = field(default_factory=list)
    substitutions: list[str] = field(default_factory=list)

    @property
    def kept(self) -> bool:
        return not self.excluded

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "document_id": self.document_id,
            "title": self.title,
            "ingredients": list(self.ingredients),
            "unknown": self.unknown,
            "excluded": self.excluded,
            "kept": self.kept,
            "exclusion_reasons": list(self.exclusion_reasons),
            "allergen_hits": {k: list(v) for k, v in self.allergen_hits.items()},
            "soft_score": round(self.soft_score, 4),
            "soft_details": [dict(item) for item in self.soft_details],
            "substitutions": list(self.substitutions),
        }


@dataclass
class ConstraintDecision:
    """约束推理的完整决策结果。"""

    profile: ConstraintProfile = field(default_factory=ConstraintProfile)
    conflicts: list[str] = field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    assessments: list[DishAssessment] = field(default_factory=list)
    filtered_documents: list[Any] = field(default_factory=list)
    ordered_kept_ids: list[str] = field(default_factory=list)
    fallback_used: bool = False
    prompt_block: str = ""
    enabled: bool = True

    @property
    def has_constraints(self) -> bool:
        return not self.profile.is_empty

    @property
    def hard_count(self) -> int:
        return len(self.profile.hard_constraints)

    @property
    def soft_count(self) -> int:
        return len(self.profile.soft_constraints)

    @property
    def kept_ids(self) -> list[str]:
        if self.ordered_kept_ids:
            return list(self.ordered_kept_ids)
        if self.fallback_used:
            return [item.document_id for item in self.assessments]
        return [item.document_id for item in self.assessments if item.kept]

    @property
    def removed_ids(self) -> list[str]:
        if self.fallback_used:
            return []
        return [item.document_id for item in self.assessments if item.excluded]

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "profile": self.profile.to_dict(),
            "conflicts": list(self.conflicts),
            "needs_clarification": self.needs_clarification,
            "clarification_question": self.clarification_question,
            "assessments": [item.to_dict() for item in self.assessments],
            "kept_ids": self.kept_ids,
            "removed_ids": self.removed_ids,
            "fallback_used": self.fallback_used,
            "prompt_block": self.prompt_block,
        }


__all__ = [
    "ConstraintKind",
    "ConstraintSeverity",
    "Constraint",
    "ConstraintProfile",
    "DishAssessment",
    "ConstraintDecision",
]
