"""约束推理对外编排入口（SU-17）。"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Optional, Sequence

from langchain_core.documents import Document

from app.reasoning.constraints.conflicts import (
    build_clarification_question,
    detect_conflicts,
)
from app.reasoning.constraints.evaluator import build_evaluation
from app.reasoning.constraints.models import ConstraintDecision
from app.reasoning.constraints.parser import parse_constraints

logger = logging.getLogger(__name__)


def _load_default_config() -> Any:
    try:
        from app.config import settings

        config = getattr(settings, "constraint_reasoning", None)
        if config is not None:
            return config
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to load constraint config: %s", exc)

    from app.config.constraint_config import ConstraintReasoningConfig

    return ConstraintReasoningConfig()


def _slot_values(slots: Any, name: str) -> list[str]:
    if slots is None:
        return []
    if isinstance(slots, dict):
        value = slots.get(name, [])
    else:
        value = getattr(slots, name, [])
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    try:
        return [str(item) for item in value if item is not None]
    except TypeError:
        return []


def rebuild_retrieval_result(
    retrieval_result: Any,
    decision: ConstraintDecision,
    sources_builder: Any,
) -> Any:
    """Rebuild context/documents/sources after constraint filtering."""
    documents = list(getattr(decision, "filtered_documents", []) or [])
    if not documents:
        documents = list(getattr(retrieval_result, "documents", []) or [])

    context = "\n\n".join(
        str(getattr(document, "page_content", "") or "")
        for document in documents
    )
    try:
        sources = list(sources_builder(documents) or [])
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to rebuild sources: %s", exc)
        sources = list(getattr(retrieval_result, "sources", []) or [])

    return type(retrieval_result)(
        original_query=getattr(retrieval_result, "original_query", ""),
        rewritten_query=getattr(retrieval_result, "rewritten_query", ""),
        context=context,
        documents=documents,
        sources=sources,
    )


class ConstraintReasoner:
    """把解析、冲突检测、候选评估与提示词拼装串起来。"""

    def __init__(self, config: Any = None) -> None:
        self.config = config or _load_default_config()

    @property
    def enabled(self) -> bool:
        return bool(getattr(self.config, "enabled", True))

    @property
    def strict_allergens(self) -> bool:
        return bool(getattr(self.config, "strict_allergens", True))

    @property
    def max_candidates(self) -> int:
        try:
            value = int(getattr(self.config, "max_candidates", 20))
        except (TypeError, ValueError):
            return 20
        return value if value > 0 else 20

    def analyze(
        self,
        *,
        text: str = "",
        slots: Any = None,
        profile: Any = None,
    ) -> ConstraintDecision:
        """解析用户约束；任何异常都降级为空画像。"""
        if not self.enabled:
            return ConstraintDecision(enabled=False)

        try:
            parsed_profile = parse_constraints(
                text=text or "",
                diet_constraints=_slot_values(slots, "diet_constraints"),
                ingredients=_slot_values(slots, "ingredients"),
                tastes=_slot_values(slots, "tastes"),
                profile_constraints=_profile_constraints(profile),
            )
            conflicts = detect_conflicts(parsed_profile)
            decision = ConstraintDecision(
                profile=parsed_profile,
                conflicts=conflicts,
                needs_clarification=bool(conflicts),
                clarification_question=build_clarification_question(conflicts),
                enabled=True,
            )
            decision.prompt_block = self.build_prompt_block(decision)
            return decision
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Constraint analysis failed: %s", exc)
            return ConstraintDecision(enabled=True)

    def evaluate_documents(
        self,
        documents: Sequence[Any],
        decision: Optional[ConstraintDecision],
    ) -> ConstraintDecision:
        """按硬约束过滤、软约束排序，并更新决策中的文档顺序。"""
        if decision is None:
            return ConstraintDecision(enabled=False)
        if not decision.enabled or not self.enabled:
            decision.enabled = False
            return decision

        documents = list(documents or [])
        if documents:
            try:
                outcome = build_evaluation(
                    documents,
                    decision.profile,
                    strict_allergens=self.strict_allergens,
                    max_candidates=self.max_candidates,
                )
                decision.assessments = outcome.assessments
                decision.filtered_documents = outcome.ordered_documents
                decision.fallback_used = outcome.fallback_used
                index_by_identity = {
                    id(document): index
                    for index, document in enumerate(documents)
                }
                decision.ordered_kept_ids = [
                    outcome.assessments[index_by_identity[id(document)]].document_id
                    for document in outcome.ordered_documents
                    if id(document) in index_by_identity
                ]
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Constraint evaluation failed: %s", exc)
                decision.filtered_documents = documents
                decision.assessments = []
                decision.ordered_kept_ids = []
                decision.fallback_used = False
        else:
            decision.assessments = []
            decision.filtered_documents = []
            decision.ordered_kept_ids = []
            decision.fallback_used = False

        decision.prompt_block = self.build_prompt_block(
            decision, include_evaluation=bool(decision.profile.constraints)
        )
        return decision

    def build_prompt_block(
        self,
        decision: ConstraintDecision,
        *,
        include_evaluation: bool = False,
    ) -> str:
        """生成注入到主提示词中的约束说明。"""
        if decision is None or not decision.enabled:
            return ""

        profile = decision.profile
        if profile.is_empty and not profile.unknown_terms and not decision.conflicts:
            return ""

        lines: list[str] = []
        hard = profile.hard_constraints
        soft = profile.soft_constraints

        if hard:
            lines.append("【饮食约束（硬性要求）】")
            for item in hard:
                lines.append(f"- {item.label or item.value}")
            lines.append(
                "以上为硬性要求，任何违反的候选都必须排除；不得以“少量”“可能没事”为由推荐。"
            )

        if soft:
            lines.append("【饮食偏好（仅影响排序）】")
            for item in soft:
                lines.append(f"- {item.label or item.value}")
            lines.append("在不违反硬约束的前提下优先满足这些偏好。")

        if profile.unknown_terms:
            lines.append("【无法确认的约束】")
            for term in profile.unknown_terms:
                lines.append(f"- {term}")
            lines.append(
                "这些约束无法被当前规则识别，请向用户确认；不要假设它们已经满足或安全。"
            )

        if decision.conflicts:
            lines.append("【约束冲突】")
            for conflict in decision.conflicts:
                lines.append(f"- {conflict}")
            if decision.clarification_question:
                lines.append(decision.clarification_question)
            lines.append(
                "请先澄清，或在回答开头明确说明冲突；不得静默替用户选择其一。"
            )

        if include_evaluation and decision.assessments:
            removed = [item for item in decision.assessments if item.excluded]
            unknown = [item for item in decision.assessments if item.unknown]
            lines.append("【候选约束评估】")
            if removed:
                lines.append(f"已排除 {len(removed)} 个候选：")
                for item in removed[:5]:
                    reason = "；".join(item.exclusion_reasons) or "违反硬约束"
                    lines.append(f"- {item.title or item.document_id}：{reason}")
            if unknown:
                lines.append(
                    f"有 {len(unknown)} 个候选无法识别食材，无法确认是否满足硬约束，"
                    "请在回答中说明这一限制。"
                )
            if decision.fallback_used:
                lines.append(
                    "没有找到完全满足硬约束的候选，已回退展示原候选；"
                    "请说明限制并给出替代方向。"
                )

            suggestions: list[str] = []
            for item in removed:
                suggestions.extend(item.substitutions)
            if suggestions:
                lines.append("【替代方向（需确认）】")
                for suggestion in list(dict.fromkeys(suggestions))[:5]:
                    lines.append(f"- {suggestion}")

        return "\n".join(lines)

    def evaluate_candidates(
        self,
        *,
        text: str = "",
        diet_constraints: Iterable[str] = (),
        ingredients: Iterable[str] = (),
        tastes: Iterable[str] = (),
        candidates: Sequence[dict[str, Any]] = (),
    ) -> dict[str, Any]:
        """供只读 API 使用：解析并评估一组候选。"""
        slots = {
            "diet_constraints": list(diet_constraints or ()),
            "ingredients": list(ingredients or ()),
            "tastes": list(tastes or ()),
        }
        decision = self.analyze(text=text, slots=slots)
        documents = [
            Document(
                page_content=str(candidate.get("content") or ""),
                metadata={
                    "id": str(candidate.get("id") or f"doc-{index}"),
                    "dish_name": str(candidate.get("title") or ""),
                },
            )
            for index, candidate in enumerate(candidates or ())
        ]
        decision = self.evaluate_documents(documents, decision)
        return decision.to_dict()


def _profile_constraints(profile: Any) -> list[str]:
    """Translate a structured diet profile into parser-friendly constraint terms."""
    if not profile:
        return []
    if isinstance(profile, dict):
        getter = profile.get
    else:
        getter = lambda key, default=None: getattr(profile, key, default)

    values: list[str] = []
    for allergen in getter("allergies", []) or []:
        text = str(allergen).strip()
        if text:
            values.append(f"{text}过敏")
    for restriction in getter("dietary_restrictions", []) or []:
        text = str(restriction).strip()
        if text:
            values.append(text)
    for condition in getter("health_conditions", []) or []:
        text = str(condition).strip()
        if text:
            values.append(text)
    for food in getter("avoided_foods", []) or []:
        text = str(food).strip()
        if text:
            values.append(f"不吃{text}")
    return values


constraint_reasoner = ConstraintReasoner()


__all__ = [
    "ConstraintReasoner",
    "constraint_reasoner",
    "rebuild_retrieval_result",
]
