"""自然语言饮食约束解析（SU-13）。

解析器只做确定性词表匹配，不调用模型。无法识别的约束进入
``unknown_terms``，调用方不得把它当作“无约束”或“安全”。
"""

from __future__ import annotations

import re
from typing import Iterable

from app.knowledge.ontology import find_ingredients, normalize_ingredient
from app.reasoning.constraints.models import (
    Constraint,
    ConstraintKind,
    ConstraintProfile,
    ConstraintSeverity,
)


ALLERGEN_TERMS: dict[str, str] = {
    "花生": "peanut",
    "花生米": "peanut",
    "peanut": "peanut",
    "坚果": "tree_nut",
    "树坚果": "tree_nut",
    "核桃": "tree_nut",
    "杏仁": "tree_nut",
    "腰果": "tree_nut",
    "牛奶": "milk",
    "乳制品": "milk",
    "奶制品": "milk",
    "乳糖": "milk",
    "milk": "milk",
    "鸡蛋": "egg",
    "蛋类": "egg",
    "蛋": "egg",
    "egg": "egg",
    "海鲜": "shellfish",
    "贝类": "shellfish",
    "甲壳类": "shellfish",
    "虾": "shellfish",
    "蟹": "shellfish",
    "螃蟹": "shellfish",
    "鱼": "fish",
    "鱼类": "fish",
    "fish": "fish",
    "大豆": "soy",
    "黄豆": "soy",
    "豆制品": "soy",
    "soy": "soy",
    "小麦": "wheat",
    "麸质": "wheat",
    "面筋": "wheat",
    "wheat": "wheat",
    "芝麻": "sesame",
    "sesame": "sesame",
}

ALLERGEN_LABELS: dict[str, str] = {
    "peanut": "花生",
    "tree_nut": "坚果",
    "milk": "牛奶/乳制品",
    "egg": "鸡蛋",
    "shellfish": "海鲜/贝类",
    "fish": "鱼",
    "soy": "大豆",
    "wheat": "小麦/麸质",
    "sesame": "芝麻",
}

DIET_TERMS: dict[str, tuple[str, ...]] = {
    "素食": ("vegetarian",),
    "吃素": ("vegetarian",),
    "vegetarian": ("vegetarian",),
    "纯素": ("vegan", "vegetarian"),
    "全素": ("vegan", "vegetarian"),
    "严格素食": ("vegan", "vegetarian"),
    "vegan": ("vegan", "vegetarian"),
    "无麸质": ("gluten_free",),
    "不吃麸质": ("gluten_free",),
    "gluten free": ("gluten_free",),
    "gluten_free": ("gluten_free",),
}

DIET_LABELS: dict[str, str] = {
    "vegetarian": "素食",
    "vegan": "纯素",
    "gluten_free": "无麸质",
}

NUTRITION_TERMS: dict[str, str] = {
    "低脂": "low_fat",
    "低脂肪": "low_fat",
    "减脂": "low_fat",
    "少油": "low_fat",
    "控糖": "low_sugar",
    "低糖": "low_sugar",
    "少糖": "low_sugar",
    "无糖": "low_sugar",
    "高蛋白": "high_protein",
    "多蛋白": "high_protein",
    "低盐": "low_salt",
    "少盐": "low_salt",
    "清淡": "low_salt",
}

NUTRITION_LABELS: dict[str, str] = {
    "low_fat": "低脂",
    "low_sugar": "控糖/低糖",
    "high_protein": "高蛋白",
    "low_salt": "低盐/清淡",
}

TASTE_TERMS: dict[str, str] = {
    "不辣": "mild",
    "微辣": "mild",
    "少辣": "mild",
    "清淡": "light",
    "重辣": "spicy",
    "很辣": "spicy",
    "香辣": "spicy",
}

TASTE_LABELS: dict[str, str] = {
    "mild": "不辣/微辣",
    "light": "清淡",
    "spicy": "偏辣",
}


_ALLERGEN_PATTERN = re.compile(
    r"(?:对\s*)?(?P<term>[\u4e00-\u9fffA-Za-z]{1,6}?)\s*过敏"
)
_EXCLUSION_PATTERN = re.compile(
    r"(?:不要放|不能吃|不吃|不要|忌口|忌|避免|别放|不放|不含|去除|去掉|戒)"
    r"(?P<tail>[^，。；;！!？?\n]{0,12})"
)
_INCLUDE_PATTERN = re.compile(
    r"(?:想吃|要吃|要用|想用|必须放|要加|需要放)"
    r"(?P<tail>[^，。；;！!？?\n]{0,10})"
)
_LEADING_NOISE = re.compile(r"^[放吃用加要再点儿些个\s]+")
_TRAILING_NOISE = re.compile(r"[了的吧呀\s]+$")


def _clean_phrase(value: str) -> str:
    text = _LEADING_NOISE.sub("", value.strip())
    text = _TRAILING_NOISE.sub("", text)
    return text.strip()


def _match_term(text: str, terms: dict[str, str]) -> str | None:
    folded = text.casefold()
    for term, value in sorted(terms.items(), key=lambda item: -len(item[0])):
        if term.casefold() in folded:
            return value
    return None


def _match_multi_term(
    text: str, terms: dict[str, tuple[str, ...]]
) -> tuple[str, ...]:
    folded = text.casefold()
    result: list[str] = []
    for term, values in sorted(terms.items(), key=lambda item: -len(item[0])):
        if term.casefold() in folded:
            for value in values:
                if value not in result:
                    result.append(value)
    return tuple(result)


class _ProfileBuilder:
    def __init__(self) -> None:
        self._constraints: dict[tuple[ConstraintKind, str], Constraint] = {}
        self._unknown: list[str] = []

    def add(
        self,
        kind: ConstraintKind,
        value: str,
        severity: ConstraintSeverity,
        *,
        source: str,
        label: str,
    ) -> None:
        if not value:
            return
        key = (kind, value)
        existing = self._constraints.get(key)
        if existing is not None and not (
            existing.source == "text" and source == "slot"
        ):
            return
        self._constraints[key] = Constraint(
            kind=kind,
            value=value,
            severity=severity,
            source=source,
            label=label,
        )

    def add_unknown(self, term: str) -> None:
        cleaned = term.strip()
        if cleaned and cleaned not in self._unknown:
            self._unknown.append(cleaned)

    def add_allergen(self, value: str, *, source: str) -> None:
        self.add(
            ConstraintKind.ALLERGEN,
            value,
            ConstraintSeverity.HARD,
            source=source,
            label=f"过敏原：{ALLERGEN_LABELS.get(value, value)}",
        )

    def add_diet(self, value: str, *, source: str) -> None:
        self.add(
            ConstraintKind.DIET,
            value,
            ConstraintSeverity.HARD,
            source=source,
            label=f"饮食模式：{DIET_LABELS.get(value, value)}",
        )

    def add_nutrition(self, value: str, *, source: str) -> None:
        self.add(
            ConstraintKind.NUTRITION,
            value,
            ConstraintSeverity.SOFT,
            source=source,
            label=f"营养目标：{NUTRITION_LABELS.get(value, value)}",
        )

    def add_taste(self, value: str, *, source: str) -> None:
        self.add(
            ConstraintKind.TASTE,
            value,
            ConstraintSeverity.SOFT,
            source=source,
            label=f"口味偏好：{TASTE_LABELS.get(value, value)}",
        )

    def add_exclude(self, value: str, *, source: str) -> None:
        self.add(
            ConstraintKind.EXCLUDE_INGREDIENT,
            value,
            ConstraintSeverity.HARD,
            source=source,
            label=f"不吃：{value}",
        )

    def add_include(self, value: str, *, source: str) -> None:
        self.add(
            ConstraintKind.INCLUDE_INGREDIENT,
            value,
            ConstraintSeverity.SOFT,
            source=source,
            label=f"想吃：{value}",
        )

    def add_from_text(self, text: str, *, source: str) -> int:
        """解析一段文本，返回新增约束数量（用于判断未知项）。"""
        if not isinstance(text, str) or not text.strip():
            return 0

        before = len(self._constraints)

        for match in _ALLERGEN_PATTERN.finditer(text):
            term = _clean_phrase(match.group("term"))
            value = _match_term(term, ALLERGEN_TERMS)
            if value:
                self.add_allergen(value, source=source)

        for match in _EXCLUSION_PATTERN.finditer(text):
            phrase = _clean_phrase(match.group("tail"))
            if not phrase:
                continue
            ingredients = find_ingredients(phrase)
            if ingredients:
                for ingredient in ingredients:
                    self.add_exclude(ingredient, source=source)
                continue
            allergen = _match_term(phrase, ALLERGEN_TERMS)
            if allergen:
                self.add_allergen(allergen, source=source)
                continue
            diets = _match_multi_term(phrase, DIET_TERMS)
            if diets:
                for diet in diets:
                    self.add_diet(diet, source=source)
                continue
            nutrition = _match_term(phrase, NUTRITION_TERMS)
            if nutrition:
                self.add_nutrition(nutrition, source=source)
                continue
            self.add_unknown(phrase)

        for diet in _match_multi_term(text, DIET_TERMS):
            self.add_diet(diet, source=source)

        for term, value in NUTRITION_TERMS.items():
            if term.casefold() in text.casefold():
                self.add_nutrition(value, source=source)

        for term, value in TASTE_TERMS.items():
            if term.casefold() in text.casefold():
                self.add_taste(value, source=source)

        for match in _INCLUDE_PATTERN.finditer(text):
            phrase = _clean_phrase(match.group("tail"))
            for ingredient in find_ingredients(phrase):
                self.add_include(ingredient, source=source)

        return len(self._constraints) - before

    def build(self) -> ConstraintProfile:
        return ConstraintProfile(
            constraints=list(self._constraints.values()),
            unknown_terms=list(self._unknown),
        )


def parse_constraints(
    *,
    text: str = "",
    diet_constraints: Iterable[str] = (),
    ingredients: Iterable[str] = (),
    tastes: Iterable[str] = (),
    profile_constraints: Iterable[str] = (),
) -> ConstraintProfile:
    """把用户原文与意图槽位解析为结构化约束画像。"""
    builder = _ProfileBuilder()

    if isinstance(text, str) and text.strip():
        builder.add_from_text(text, source="text")

    for raw in diet_constraints or ():
        value = str(raw).strip()
        if not value:
            continue
        if builder.add_from_text(value, source="slot") == 0:
            builder.add_unknown(value)

    for raw in tastes or ():
        value = str(raw).strip()
        if not value:
            continue
        matched = _match_term(value, TASTE_TERMS)
        if matched:
            builder.add_taste(matched, source="slot")
            continue
        nutrition = _match_term(value, NUTRITION_TERMS)
        if nutrition:
            builder.add_nutrition(nutrition, source="slot")
            continue
        builder.add_taste(value, source="slot")

    for raw in ingredients or ():
        value = str(raw).strip()
        if not value:
            continue
        builder.add_include(normalize_ingredient(value), source="slot")

    for raw in profile_constraints or ():
        value = str(raw).strip()
        if not value:
            continue
        if builder.add_from_text(value, source="profile") == 0:
            builder.add_unknown(value)

    return builder.build()


__all__ = [
    "ALLERGEN_TERMS",
    "DIET_TERMS",
    "NUTRITION_TERMS",
    "TASTE_TERMS",
    "parse_constraints",
]
