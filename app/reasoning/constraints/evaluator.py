"""候选菜谱评估：食材提取、硬约束过滤、软约束打分（SU-14、SU-15）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from app.knowledge.ontology import (
    diet_tags_for,
    explain_allergens,
    extract_ingredients_from_document,
    is_known_ingredient,
    normalize_ingredient,
)
from app.reasoning.constraints.models import (
    Constraint,
    ConstraintKind,
    ConstraintProfile,
    DishAssessment,
)
from app.reasoning.constraints.substitutions import suggest_substitutions

# 同一食材家族：用户说“不吃猪肉”时也应覆盖五花肉、香肠等。
_INGREDIENT_GROUPS: dict[str, tuple[str, ...]] = {
    "猪肉": ("五花肉", "香肠", "培根", "火腿", "午餐肉"),
    "五花肉": ("猪肉", "香肠", "培根", "火腿", "午餐肉"),
    "鸡蛋": ("鸭蛋", "鹌鹑蛋", "皮蛋"),
    "牛奶": ("酸奶", "奶油", "黄油", "奶酪"),
    "花生": ("花生酱",),
    "芝麻": ("香油",),
    "鱼": ("鲈鱼", "三文鱼", "带鱼"),
}


@dataclass(frozen=True)
class _SoftRule:
    label: str
    mode: str
    positive: tuple[str, ...]
    negative: tuple[str, ...] = ()


_SOFT_RULES: dict[str, _SoftRule] = {
    "low_fat": _SoftRule(
        label="低脂",
        mode="absence",
        positive=("清蒸", "水煮", "凉拌", "少油", "蒸", "煮", "焯"),
        negative=("油炸", "炸", "黄油", "奶油", "五花肉", "肥肉", "猪油", "煎"),
    ),
    "low_sugar": _SoftRule(
        label="控糖/低糖",
        mode="absence",
        positive=("无糖", "低糖", "控糖", "代糖"),
        negative=("冰糖", "白糖", "砂糖", "蜂蜜", "蛋糕", "奶茶", "炼乳", "糖"),
    ),
    "high_protein": _SoftRule(
        label="高蛋白",
        mode="presence",
        positive=(
            "鸡蛋",
            "鸡肉",
            "鸡胸肉",
            "牛肉",
            "鱼",
            "虾",
            "豆腐",
            "牛奶",
            "瘦肉",
            "里脊",
        ),
    ),
    "low_salt": _SoftRule(
        label="低盐/清淡",
        mode="absence",
        positive=("少盐", "低盐", "清淡", "不放盐"),
        negative=("酱油", "生抽", "老抽", "蚝油", "豆瓣酱", "腌", "咸", "盐"),
    ),
    "light": _SoftRule(
        label="清淡",
        mode="absence",
        positive=("清淡", "清蒸", "水煮", "白灼"),
        negative=("辣椒", "小米辣", "花椒", "豆瓣酱", "重辣", "香辣"),
    ),
    "mild": _SoftRule(
        label="不辣/微辣",
        mode="absence",
        positive=("不辣", "微辣", "少辣"),
        negative=("重辣", "很辣", "香辣", "小米辣", "辣椒", "麻辣"),
    ),
    "spicy": _SoftRule(
        label="偏辣",
        mode="presence",
        positive=("重辣", "很辣", "香辣", "麻辣", "辣椒", "小米辣"),
    ),
}


def ingredient_matches(excluded: str, ingredients: Sequence[str]) -> bool:
    """判断忌口食材是否命中候选食材（含同族食材）。"""
    target = normalize_ingredient(excluded)
    if not target:
        return False
    targets = {target}
    targets.update(
        normalize_ingredient(item)
        for item in _INGREDIENT_GROUPS.get(target, ())
    )
    return any(
        normalize_ingredient(item) in targets for item in ingredients or ()
    )


def diet_offenders(value: str, ingredients: Sequence[str]) -> list[str]:
    """Return known ingredients that violate the requested diet.

    Empty diet tags mean "known non-vegetarian food" for vegetarian/vegan,
    but "tag data unavailable" for gluten-free (meat and fish are gluten-free).
    Unknown ingredients are skipped rather than assumed safe.
    """
    offenders: list[str] = []
    for ingredient in ingredients or ():
        canonical = normalize_ingredient(ingredient)
        if not is_known_ingredient(canonical):
            continue
        tags = diet_tags_for([canonical])
        if value in tags:
            continue
        if value == "gluten_free" and not tags:
            continue
        offenders.append(canonical)
    return offenders


def _metadata(document: Any) -> dict[str, Any]:
    value = getattr(document, "metadata", None)
    return value if isinstance(value, dict) else {}


def _page_content(document: Any) -> str:
    value = getattr(document, "page_content", "")
    return value if isinstance(value, str) else ""


def _document_title(document: Any) -> str:
    metadata = _metadata(document)
    return str(
        metadata.get("dish_name")
        or metadata.get("title")
        or metadata.get("source_title")
        or ""
    )


def _document_id(document: Any, index: int) -> str:
    metadata = _metadata(document)
    value = metadata.get("id") or metadata.get("document_id")
    if value:
        return str(value)
    title = _document_title(document)
    return title or f"doc-{index}"


def _soft_detail(
    constraint: Constraint,
    *,
    ingredients: Sequence[str],
    content: str,
) -> dict[str, Any] | None:
    if constraint.kind is ConstraintKind.INCLUDE_INGREDIENT:
        hit = any(
            ingredient_matches(constraint.value, [item]) for item in ingredients
        )
        return {
            "constraint": f"include_ingredient:{constraint.value}",
            "label": constraint.label,
            "hit": hit,
            "reason": (
                f"包含用户想吃的食材「{constraint.value}」"
                if hit
                else f"未包含用户想吃的食材「{constraint.value}」"
            ),
            "evidence": list(ingredients),
        }

    rule = _SOFT_RULES.get(constraint.value)
    if rule is None:
        # 未识别约束不参与打分。
        return None

    positive_hits = [term for term in rule.positive if term in content]
    negative_hits = [term for term in rule.negative if term in content]

    if rule.mode == "presence":
        hit = bool(positive_hits)
        evidence = positive_hits
        reason = (
            f"命中{rule.label}信号：{'、'.join(positive_hits[:3])}"
            if hit
            else f"未发现{rule.label}信号"
        )
    elif positive_hits:
        hit = True
        evidence = positive_hits
        reason = f"命中{rule.label}正向信号：{'、'.join(positive_hits[:3])}"
    elif negative_hits:
        hit = False
        evidence = negative_hits
        reason = f"命中{rule.label}负向信号：{'、'.join(negative_hits[:3])}"
    else:
        hit = True
        evidence = []
        reason = f"未发现与{rule.label}冲突的信号"

    return {
        "constraint": f"{constraint.kind.value}:{constraint.value}",
        "label": constraint.label,
        "hit": hit,
        "reason": reason,
        "evidence": evidence,
    }


def assess_document(
    document: Any,
    profile: ConstraintProfile,
    *,
    index: int = 0,
    strict_allergens: bool = True,
) -> DishAssessment:
    """评估单个候选菜谱。"""
    content = _page_content(document)
    title = _document_title(document)
    ingredients = extract_ingredients_from_document(content, title)
    assessment = DishAssessment(
        index=index,
        document_id=_document_id(document, index),
        title=title,
        ingredients=ingredients,
        unknown=not ingredients,
    )

    if profile is None or profile.is_empty:
        return assessment

    if not ingredients:
        # 未知食材不视为安全，也不生成硬排除。
        return assessment

    allergen_explanation = explain_allergens(ingredients)
    substitutions: list[str] = []
    soft_misses = 0
    soft_hits = 0

    for constraint in profile.constraints:
        if constraint.kind is ConstraintKind.ALLERGEN:
            contributors = allergen_explanation.get(constraint.value, [])
            if not contributors:
                continue
            if strict_allergens:
                assessment.excluded = True
                assessment.allergen_hits[constraint.value] = list(contributors)
                assessment.exclusion_reasons.append(
                    f"命中过敏原「{constraint.label or constraint.value}」"
                    f"（来源：{'、'.join(contributors)}）"
                )
                for contributor in contributors:
                    substitutions.extend(suggest_substitutions(contributor))
            else:
                soft_misses += 1
                assessment.soft_details.append(
                    {
                        "constraint": f"allergen:{constraint.value}",
                        "label": constraint.label,
                        "hit": False,
                        "reason": "过敏原命中（当前为非严格模式，仅降低排序）",
                        "evidence": list(contributors),
                    }
                )

        elif constraint.kind is ConstraintKind.DIET:
            offenders = diet_offenders(constraint.value, ingredients)
            if not offenders:
                continue
            assessment.excluded = True
            assessment.exclusion_reasons.append(
                f"不符合饮食模式「{constraint.label or constraint.value}」"
                f"（冲突食材：{'、'.join(offenders)}）"
            )
            for ingredient in offenders:
                substitutions.extend(suggest_substitutions(ingredient))

        elif constraint.kind is ConstraintKind.EXCLUDE_INGREDIENT:
            matched = [
                ingredient
                for ingredient in ingredients
                if ingredient_matches(constraint.value, [ingredient])
            ]
            if not matched:
                continue
            assessment.excluded = True
            assessment.exclusion_reasons.append(
                f"包含忌口食材「{constraint.value}」"
                f"（命中：{'、'.join(matched)}）"
            )
            for ingredient in matched:
                substitutions.extend(suggest_substitutions(ingredient))

        else:
            detail = _soft_detail(
                constraint,
                ingredients=ingredients,
                content=content,
            )
            if detail is None:
                continue
            assessment.soft_details.append(detail)
            if detail["hit"]:
                soft_hits += 1
            else:
                soft_misses += 1

    assessment.substitutions = list(dict.fromkeys(substitutions))
    score = 1.0 - 0.12 * soft_misses + 0.03 * soft_hits
    assessment.soft_score = max(0.0, min(1.0, score))
    return assessment


def evaluate_documents(
    documents: Sequence[Any],
    profile: ConstraintProfile,
    *,
    strict_allergens: bool = True,
    max_candidates: int | None = None,
) -> list[DishAssessment]:
    """评估全部候选，返回与输入同序的评估列表。"""
    documents = list(documents or [])
    limit = len(documents)
    if max_candidates is not None and max_candidates > 0:
        limit = min(limit, max_candidates)

    assessments: list[DishAssessment] = []
    for index, document in enumerate(documents):
        if index >= limit:
            assessments.append(
                DishAssessment(
                    index=index,
                    document_id=_document_id(document, index),
                    title=_document_title(document),
                    unknown=True,
                )
            )
            continue
        assessments.append(
            assess_document(
                document,
                profile,
                index=index,
                strict_allergens=strict_allergens,
            )
        )
    return assessments


@dataclass
class EvaluationOutcome:
    """评估后的保留/排除与排序结果。"""

    assessments: list[DishAssessment]
    kept: list[DishAssessment] = field(default_factory=list)
    removed: list[DishAssessment] = field(default_factory=list)
    ordered_documents: list[Any] = field(default_factory=list)
    fallback_used: bool = False


def build_evaluation(
    documents: Sequence[Any],
    profile: ConstraintProfile,
    *,
    strict_allergens: bool = True,
    max_candidates: int | None = None,
) -> EvaluationOutcome:
    """评估并生成过滤、排序后的文档顺序。"""
    documents = list(documents or [])
    assessments = evaluate_documents(
        documents,
        profile,
        strict_allergens=strict_allergens,
        max_candidates=max_candidates,
    )

    kept = [item for item in assessments if not item.excluded]
    removed = [item for item in assessments if item.excluded]
    fallback_used = bool(documents) and not kept

    if fallback_used:
        kept = list(assessments)
        removed = []
        ordered = list(documents)
    else:
        limit = len(documents)
        if max_candidates is not None and max_candidates > 0:
            limit = min(limit, max_candidates)
        head = [item for item in kept if item.index < limit]
        head.sort(key=lambda item: (-item.soft_score, item.index))
        ordered = [documents[item.index] for item in head]
        ordered.extend(documents[limit:])

    return EvaluationOutcome(
        assessments=assessments,
        kept=kept,
        removed=removed,
        ordered_documents=ordered,
        fallback_used=fallback_used,
    )


__all__ = [
    "assess_document",
    "evaluate_documents",
    "build_evaluation",
    "EvaluationOutcome",
    "ingredient_matches",
    "diet_offenders",
]
