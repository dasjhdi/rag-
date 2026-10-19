"""Convert Markdown recipe documents into structured, testable recipes."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from app.diet.nutrition.service import estimate_nutrition
from app.knowledge.ontology import (
    allergens_for,
    diet_tags_for,
    extract_ingredients_from_document,
    normalize_ingredient,
)

_INGREDIENT_HEADING = re.compile(
    r"(?mi)^(?P<hashes>#{1,6})[ \t]*"
    r"(?P<name>必备原料和工具|必备原料|原料|食材|配料|主料|辅料|用料)[ \t]*$"
)
_STEP_HEADING = re.compile(
    r"(?mi)^(?P<hashes>#{1,6})[ \t]*"
    r"(?P<name>操作|步骤|做法|烹饪步骤|制作|制作步骤)[ \t]*$"
)
_HEADING = re.compile(r"(?m)^(?P<hashes>#{1,6})[ \t]+(?P<name>[^\n]+)$")
_SERVINGS = re.compile(r"(?P<count>\d+(?:\.\d+)?)\s*人份")
_TIMER = re.compile(
    r"(?P<count>\d+(?:\.\d+)?)\s*(?P<unit>小时|分钟|分|秒钟|秒|hours?|minutes?|mins?|seconds?|secs?)",
    re.IGNORECASE,
)
_FRACTION = re.compile(r"^(?P<whole>\d+)?\s*(?P<num>\d+)/(?P<den>\d+)$")

_UNITS = (
    "千克",
    "公斤",
    "毫升",
    "汤匙",
    "茶匙",
    "大勺",
    "小勺",
    "盎司",
    "磅",
    "克",
    "千克",
    "个",
    "只",
    "枚",
    "颗",
    "根",
    "片",
    "瓣",
    "把",
    "碗",
    "份",
    "杯",
    "勺",
    "条",
    "块",
    "朵",
    "头",
    "kg",
    "g",
    "mg",
    "ml",
    "l",
    "oz",
    "lb",
    "cup",
    "tbsp",
    "tsp",
)
_UNIT_PATTERN = "|".join(re.escape(unit) for unit in sorted(_UNITS, key=len, reverse=True))
_TRAILING_QUANTITY = re.compile(
    rf"^(?P<name>.+?)\s*(?P<quantity>\d+(?:\.\d+)?(?:\s*\d+/\d+)?)\s*(?P<unit>{_UNIT_PATTERN})\s*$",
    re.IGNORECASE,
)
_LEADING_QUANTITY = re.compile(
    rf"^(?P<quantity>\d+(?:\.\d+)?(?:\s*\d+/\d+)?)\s*(?P<unit>{_UNIT_PATTERN})\s*(?P<name>.+)$",
    re.IGNORECASE,
)
_LIST_MARKER = re.compile(r"^\s*(?:[-*+]|\d+[.)、])\s*")


@dataclass
class ParsedIngredient:
    name: str
    raw_name: str
    quantity: Optional[float] = None
    unit: str = "适量"
    raw: str = ""
    scalable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "raw_name": self.raw_name,
            "quantity": self.quantity,
            "unit": self.unit,
            "raw": self.raw,
            "scalable": self.scalable,
        }


@dataclass
class ParsedStep:
    index: int
    text: str
    timer_seconds: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "text": self.text,
            "timer_seconds": self.timer_seconds,
        }


@dataclass
class ParsedRecipe:
    recipe_id: str
    title: str
    description: str = ""
    category: str = ""
    difficulty: str = ""
    source: str = ""
    servings: float = 2.0
    ingredients: list[ParsedIngredient] = field(default_factory=list)
    steps: list[ParsedStep] = field(default_factory=list)
    allergens: list[str] = field(default_factory=list)
    diet_tags: list[str] = field(default_factory=list)
    nutrition: dict[str, Any] = field(default_factory=dict)
    total_minutes: Optional[float] = None
    warnings: list[str] = field(default_factory=list)
    raw_content: str = ""

    def to_dict(self, servings: Optional[float] = None, unit_system: str = "metric") -> dict[str, Any]:
        target = float(servings) if servings and servings > 0 else self.servings
        scaled = scale_recipe(self, target)
        payload = {
            "recipe_id": self.recipe_id,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "difficulty": self.difficulty,
            "source": self.source,
            "servings": target,
            "base_servings": self.servings,
            "ingredients": [
                _format_ingredient(item, unit_system) for item in scaled.ingredients
            ],
            "steps": [step.to_dict() for step in scaled.steps],
            "allergens": list(scaled.allergens),
            "diet_tags": list(scaled.diet_tags),
            "nutrition": scaled.nutrition,
            "total_minutes": scaled.total_minutes,
            "warnings": list(scaled.warnings),
            "raw_content": self.raw_content,
            "unit_system": unit_system,
        }
        return payload


def _parse_number(value: str) -> Optional[float]:
    text = value.strip()
    fraction = _FRACTION.match(text)
    if fraction:
        whole = float(fraction.group("whole") or 0)
        return whole + float(fraction.group("num")) / float(fraction.group("den"))
    try:
        return float(text)
    except ValueError:
        return None


def _parse_ingredient_line(line: str) -> Optional[ParsedIngredient]:
    raw = _LIST_MARKER.sub("", line).strip()
    if not raw or raw.startswith("#"):
        return None

    match = _TRAILING_QUANTITY.match(raw) or _LEADING_QUANTITY.match(raw)
    if match:
        quantity = _parse_number(match.group("quantity"))
        name = match.group("name").strip(" ：:，,、")
        unit = match.group("unit").strip()
        if name:
            return ParsedIngredient(
                name=normalize_ingredient(name),
                raw_name=name,
                quantity=quantity,
                unit=unit,
                raw=raw,
                scalable=quantity is not None,
            )

    # "盐 适量" / "食用油 少许"
    parts = re.split(r"\s+", raw, maxsplit=1)
    if len(parts) == 2 and parts[1] in {"适量", "少许", "若干"}:
        return ParsedIngredient(
            name=normalize_ingredient(parts[0]),
            raw_name=parts[0],
            quantity=None,
            unit=parts[1],
            raw=raw,
            scalable=False,
        )

    return ParsedIngredient(
        name=normalize_ingredient(raw),
        raw_name=raw,
        quantity=None,
        unit="适量",
        raw=raw,
        scalable=False,
    )


def _section_lines(content: str, pattern: re.Pattern[str]) -> tuple[list[str], bool]:
    lines = content.splitlines()
    matches: list[tuple[int, int]] = []
    for match in pattern.finditer(content):
        level = len(match.group("hashes"))
        start = content.count("\n", 0, match.end())
        end = len(lines)
        for index in range(start + 1, len(lines)):
            heading = re.match(r"^(#{1,6})\s+", lines[index])
            if heading and len(heading.group(1)) <= level:
                end = index
                break
        matches.append((start, end))

    collected: list[str] = []
    for start, end in matches:
        collected.extend(lines[start:end])
    return [line for line in collected if line.strip()], bool(matches)


def _extract_steps(content: str) -> list[ParsedStep]:
    lines, found = _section_lines(content, _STEP_HEADING)
    if not found:
        lines = [line for line in content.splitlines() if line.strip()]

    steps: list[ParsedStep] = []
    buffer: list[str] = []

    def flush() -> None:
        if not buffer:
            return
        text = " ".join(part.strip() for part in buffer).strip()
        buffer.clear()
        if not text or text.startswith("#"):
            return
        timer = None
        match = _TIMER.search(text)
        if match:
            amount = float(match.group("count"))
            unit = match.group("unit").lower()
            if unit.startswith("小时") or unit.startswith("hour"):
                timer = int(amount * 3600)
            elif unit.startswith("秒") or unit.startswith("second") or unit.startswith("sec"):
                timer = int(amount)
            else:
                timer = int(amount * 60)
        steps.append(ParsedStep(index=len(steps) + 1, text=text, timer_seconds=timer))

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            flush()
            continue
        if re.match(r"^\s*(?:[-*+]|\d+[.)、])\s+", line):
            flush()
            buffer.append(_LIST_MARKER.sub("", line).strip())
        else:
            buffer.append(stripped)
    flush()
    return steps


def _extract_description(content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not _LIST_MARKER.match(stripped):
            return stripped[:300]
    return ""


def _parse_servings(content: str) -> float:
    match = _SERVINGS.search(content)
    if not match:
        return 2.0
    try:
        value = float(match.group("count"))
        return value if value > 0 else 2.0
    except ValueError:
        return 2.0


def _estimate_total_minutes(steps: list[ParsedStep]) -> Optional[float]:
    timers = [step.timer_seconds for step in steps if step.timer_seconds]
    if not timers:
        return None
    return round(sum(timers) / 60.0, 1)


def parse_recipe_document(
    recipe_id: str,
    title: str,
    content: str,
    *,
    category: str = "",
    difficulty: str = "",
    source: str = "",
) -> ParsedRecipe:
    """Parse a Markdown recipe; never raises on malformed content."""
    safe_content = content if isinstance(content, str) else ""
    warnings: list[str] = []

    ingredient_lines, found_section = _section_lines(safe_content, _INGREDIENT_HEADING)
    ingredients: list[ParsedIngredient] = []
    for line in ingredient_lines:
        parsed = _parse_ingredient_line(line)
        if parsed:
            ingredients.append(parsed)

    if not ingredients:
        fallback_names = extract_ingredients_from_document(safe_content, title)
        ingredients = [
            ParsedIngredient(
                name=name,
                raw_name=name,
                quantity=None,
                unit="适量",
                raw=name,
                scalable=False,
            )
            for name in fallback_names
        ]
        warnings.append("未找到标准原料章节，已回退到全文食材识别")
    elif not found_section:
        warnings.append("原料章节未闭合，解析结果可能不完整")

    steps = _extract_steps(safe_content)
    if not steps:
        warnings.append("未识别到烹饪步骤，请查看原文")

    names = [item.name for item in ingredients if item.name]
    nutrition_items = [
        {
            "food_name": item.raw_name,
            "quantity": item.quantity,
            "unit": item.unit,
        }
        for item in ingredients
    ]
    nutrition = estimate_nutrition(nutrition_items)

    recipe = ParsedRecipe(
        recipe_id=recipe_id,
        title=title or "未命名菜谱",
        description=_extract_description(safe_content),
        category=category,
        difficulty=difficulty,
        source=source,
        servings=_parse_servings(safe_content),
        ingredients=ingredients,
        steps=steps,
        allergens=sorted(allergens_for(names)),
        diet_tags=sorted(diet_tags_for(names)),
        nutrition={
            "totals": nutrition["totals"],
            "coverage": nutrition["coverage"],
            "confidence": nutrition["confidence"],
            "source": "local_food_table",
        },
        total_minutes=_estimate_total_minutes(steps),
        warnings=warnings,
        raw_content=safe_content,
    )
    return recipe


def scale_recipe(recipe: ParsedRecipe, target_servings: float) -> ParsedRecipe:
    """Return a copy scaled to ``target_servings``."""
    if not target_servings or target_servings <= 0:
        target_servings = recipe.servings
    ratio = target_servings / max(recipe.servings, 0.01)

    scaled_ingredients: list[ParsedIngredient] = []
    for item in recipe.ingredients:
        quantity = item.quantity
        if item.scalable and quantity is not None:
            quantity = round(quantity * ratio, 2)
        scaled_ingredients.append(
            ParsedIngredient(
                name=item.name,
                raw_name=item.raw_name,
                quantity=quantity,
                unit=item.unit,
                raw=item.raw,
                scalable=item.scalable,
            )
        )

    nutrition_totals = recipe.nutrition.get("totals", {}) if recipe.nutrition else {}
    scaled_totals = {
        key: round(float(value or 0) * ratio, 2) for key, value in nutrition_totals.items()
    }
    return ParsedRecipe(
        recipe_id=recipe.recipe_id,
        title=recipe.title,
        description=recipe.description,
        category=recipe.category,
        difficulty=recipe.difficulty,
        source=recipe.source,
        servings=target_servings,
        ingredients=scaled_ingredients,
        steps=list(recipe.steps),
        allergens=list(recipe.allergens),
        diet_tags=list(recipe.diet_tags),
        nutrition={**recipe.nutrition, "totals": scaled_totals},
        total_minutes=recipe.total_minutes,
        warnings=list(recipe.warnings),
        raw_content=recipe.raw_content,
    )


def _format_quantity(value: float) -> str:
    if abs(value - round(value)) < 1e-6:
        return str(int(round(value)))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _format_ingredient(item: ParsedIngredient, unit_system: str) -> dict[str, Any]:
    quantity = item.quantity
    unit = item.unit
    display_quantity = _format_quantity(quantity) if quantity is not None else None

    if quantity is not None and unit_system == "imperial":
        if unit.lower() in {"g", "克"}:
            quantity = round(quantity / 28.3495, 2)
            unit = "oz"
        elif unit.lower() in {"kg", "千克", "公斤"}:
            quantity = round(quantity * 35.274, 2)
            unit = "oz"
        elif unit.lower() in {"ml", "毫升"}:
            quantity = round(quantity / 240.0, 2)
            unit = "cup"
        elif unit.lower() in {"l", "升"}:
            quantity = round(quantity * 1000 / 240.0, 2)
            unit = "cup"
        display_quantity = _format_quantity(quantity)

    return {
        "name": item.name,
        "raw_name": item.raw_name,
        "quantity": quantity,
        "unit": unit,
        "display": (
            f"{display_quantity} {unit}".strip()
            if display_quantity is not None
            else item.unit
        ),
        "scalable": item.scalable,
        "raw": item.raw,
    }
