"""Deterministic nutrition lookup and kitchen unit conversion."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Optional

from app.knowledge.ontology import normalize_ingredient

logger = logging.getLogger(__name__)

_DATA_PATH = Path(__file__).resolve().parent / "data" / "foods.json"

_MASS_TO_GRAMS = {
    "g": 1.0,
    "克": 1.0,
    "gram": 1.0,
    "grams": 1.0,
    "kg": 1000.0,
    "千克": 1000.0,
    "公斤": 1000.0,
    "mg": 0.001,
    "毫克": 0.001,
    "oz": 28.3495,
    "盎司": 28.3495,
    "lb": 453.592,
    "磅": 453.592,
}

_VOLUME_TO_ML = {
    "ml": 1.0,
    "毫升": 1.0,
    "l": 1000.0,
    "升": 1000.0,
    "cup": 240.0,
    "杯": 240.0,
    "tbsp": 15.0,
    "汤匙": 15.0,
    "大勺": 15.0,
    "tsp": 5.0,
    "茶匙": 5.0,
    "小勺": 5.0,
}

_DENSITY = {
    "牛奶": 1.03,
    "酸奶": 1.03,
    "豆浆": 1.02,
    "橄榄油": 0.92,
    "食用油": 0.92,
    "蜂蜜": 1.42,
    "酱油": 1.15,
    "醋": 1.01,
}

_UNKNOWN_UNITS = {"", "适量", "少许", "若干", "根据需要"}


def _clean_unit(unit: Any) -> str:
    if unit is None:
        return ""
    return str(unit).strip().casefold()


def _clean_name(name: Any) -> str:
    if not isinstance(name, str):
        return ""
    return name.strip()


@lru_cache(maxsize=1)
def _load_foods() -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    try:
        raw = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load nutrition table: %s", exc)
        return {}, {}

    records: dict[str, dict[str, Any]] = {}
    aliases: dict[str, str] = {}
    for item in raw.get("foods", []):
        name = _clean_name(item.get("name"))
        if not name:
            continue
        records[name] = item
        aliases[name.casefold()] = name
        for alias in item.get("aliases", []):
            cleaned = _clean_name(alias)
            if cleaned:
                aliases[cleaned.casefold()] = name
    return records, aliases


def lookup_food(name: str) -> Optional[dict[str, Any]]:
    """Look up a food by canonical name, alias, or conservative substring."""
    cleaned = _clean_name(name)
    if not cleaned:
        return None

    records, aliases = _load_foods()
    canonical = normalize_ingredient(cleaned)
    for candidate in (cleaned.casefold(), canonical.casefold()):
        match = aliases.get(candidate)
        if match:
            return records[match]

    # Prefer the longest alias contained in the input, so "鸡蛋灌饼" can still
    # identify egg while "蛋白粉" does not silently become egg.
    best: tuple[int, str] | None = None
    folded = cleaned.casefold()
    for alias, canonical_name in aliases.items():
        if len(alias) >= 2 and alias in folded:
            if best is None or len(alias) > best[0]:
                best = (len(alias), canonical_name)
    return records[best[1]] if best else None


def search_foods(query: str = "", limit: int = 20) -> list[dict[str, Any]]:
    """Search the local nutrition table by canonical name or alias."""
    records, aliases = _load_foods()
    cleaned = _clean_name(query).casefold()
    matched: list[dict[str, Any]] = []
    seen: set[str] = set()
    for alias, canonical_name in aliases.items():
        if cleaned and cleaned not in alias:
            continue
        if canonical_name in seen:
            continue
        record = records.get(canonical_name)
        if not record:
            continue
        seen.add(canonical_name)
        matched.append(
            {
                "name": record.get("name"),
                "aliases": list(record.get("aliases") or []),
                "per_100g": dict(record.get("per_100g") or {}),
                "default_unit": record.get("default_unit") or "g",
                "unit_grams": dict(record.get("unit_grams") or {}),
            }
        )
        if len(matched) >= max(1, min(int(limit or 20), 100)):
            break
    matched.sort(key=lambda item: item["name"])
    return matched


def _food_unit_grams(food: dict[str, Any], unit: str) -> Optional[float]:
    units = food.get("unit_grams") or {}
    for key, value in units.items():
        if _clean_unit(key) == unit:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    return None


def convert_quantity(
    quantity: Optional[float],
    unit: str,
    food_name: str = "",
) -> dict[str, Any]:
    """Convert a kitchen quantity to grams.

    Returns a dict with ``grams``, ``confidence``, ``reason`` and ``known_unit``.
    Unknown units never silently become grams.
    """
    cleaned_unit = _clean_unit(unit)
    food = lookup_food(food_name) if food_name else None

    if cleaned_unit in _UNKNOWN_UNITS:
        return {
            "grams": None,
            "confidence": "low",
            "reason": "用量为适量/少许或单位缺失，无法精确换算",
            "known_unit": False,
        }

    if quantity is None:
        return {
            "grams": None,
            "confidence": "low",
            "reason": "缺少数量",
            "known_unit": cleaned_unit in _MASS_TO_GRAMS
            or cleaned_unit in _VOLUME_TO_ML,
        }

    try:
        amount = float(quantity)
    except (TypeError, ValueError):
        return {
            "grams": None,
            "confidence": "low",
            "reason": "数量不是数字",
            "known_unit": False,
        }

    if amount < 0:
        return {
            "grams": None,
            "confidence": "low",
            "reason": "数量不能为负数",
            "known_unit": False,
        }

    if cleaned_unit in _MASS_TO_GRAMS:
        grams = amount * _MASS_TO_GRAMS[cleaned_unit]
        return {
            "grams": round(grams, 2),
            "confidence": "high",
            "reason": "质量单位直接换算",
            "known_unit": True,
        }

    if cleaned_unit in _VOLUME_TO_ML:
        ml = amount * _VOLUME_TO_ML[cleaned_unit]
        density = _DENSITY.get(food.get("name") if food else "", 1.0)
        return {
            "grams": round(ml * density, 2),
            "milliliters": round(ml, 2),
            "confidence": "medium" if density != 1.0 else "high",
            "reason": "体积按密度换算",
            "known_unit": True,
        }

    if food:
        unit_grams = _food_unit_grams(food, cleaned_unit)
        if unit_grams is not None:
            return {
                "grams": round(amount * unit_grams, 2),
                "confidence": "medium",
                "reason": f"按食物标准重量换算（1 {unit} ≈ {unit_grams:g}g）",
                "known_unit": True,
            }

    return {
        "grams": None,
        "confidence": "low",
        "reason": f"无法识别的单位或食物换算关系：{unit or '空单位'}",
        "known_unit": False,
    }


def estimate_nutrition(items: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Estimate nutrition for a list of food items.

    Each item may contain ``food_name``/``name``, ``quantity``/``weight_g`` and
    ``unit``. Missing values are filled when a local record exists.
    """
    totals = {"calories": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0}
    results: list[dict[str, Any]] = []
    known_count = 0
    total_count = 0
    weight_total = 0.0

    for raw in items or []:
        total_count += 1
        item = dict(raw or {})
        name = _clean_name(item.get("food_name") or item.get("name"))
        food = lookup_food(name)
        unit = str(item.get("unit") or "")

        if item.get("weight_g") is not None:
            grams = float(item["weight_g"])
            conversion = {
                "grams": grams,
                "confidence": "high" if food else "low",
                "reason": "直接提供重量",
                "known_unit": True,
            }
        else:
            conversion = convert_quantity(
                item.get("quantity"), unit, food_name=name
            )
            grams = conversion.get("grams")

        enriched = {
            "food_name": name,
            "weight_g": round(grams, 2) if grams is not None else None,
            "unit": unit or None,
            "nutrition_source": None,
            "nutrition_confidence": "low",
        }

        if food and grams is not None:
            per_100g = food.get("per_100g") or {}
            ratio = grams / 100.0
            enriched.update(
                {
                    "calories": round(float(per_100g.get("calories", 0)) * ratio, 2),
                    "protein": round(float(per_100g.get("protein", 0)) * ratio, 2),
                    "fat": round(float(per_100g.get("fat", 0)) * ratio, 2),
                    "carbs": round(float(per_100g.get("carbs", 0)) * ratio, 2),
                    "nutrition_source": "local_food_table",
                    "nutrition_confidence": conversion.get("confidence", "medium"),
                }
            )
            known_count += 1
            weight_total += grams
            for key in totals:
                totals[key] += enriched[key]
        else:
            for key in ("calories", "protein", "fat", "carbs"):
                value = item.get(key)
                if value is not None:
                    enriched[key] = float(value)
                    totals[key] += float(value)
            enriched["nutrition_confidence"] = "low"
            enriched["nutrition_reason"] = conversion.get("reason")

        results.append(enriched)

    coverage = (known_count / total_count) if total_count else 0.0
    confidence = (
        "high"
        if total_count and coverage >= 0.8
        else "medium"
        if coverage >= 0.5
        else "low"
    )
    return {
        "items": results,
        "totals": {key: round(value, 2) for key, value in totals.items()},
        "coverage": round(coverage, 3),
        "confidence": confidence,
        "known_items": known_count,
        "total_items": total_count,
        "known_weight_g": round(weight_total, 2),
    }


def enrich_food_item(item: dict[str, Any]) -> dict[str, Any]:
    """Fill missing nutrition fields for one diet-log item."""
    enriched = dict(item or {})
    estimate = estimate_nutrition([enriched])["items"][0]

    for key in ("weight_g", "calories", "protein", "fat", "carbs"):
        if enriched.get(key) is None and estimate.get(key) is not None:
            enriched[key] = estimate[key]

    if not enriched.get("nutrition_source"):
        enriched["nutrition_source"] = estimate.get("nutrition_source")
    if not enriched.get("nutrition_confidence"):
        enriched["nutrition_confidence"] = estimate.get("nutrition_confidence")
    if estimate.get("nutrition_reason") and not enriched.get("notes"):
        enriched["notes"] = estimate["nutrition_reason"]
    return enriched


def nutrition_coverage(items: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Return how many logged items have a local, traceable nutrition source."""
    values = list(items or [])
    if not values:
        return {"coverage": 0.0, "known_items": 0, "total_items": 0, "confidence": "low"}

    known = sum(
        1
        for item in values
        if item.get("nutrition_source") == "local_food_table"
        or item.get("nutrition_confidence") in {"high", "medium"}
    )
    coverage = known / len(values)
    return {
        "coverage": round(coverage, 3),
        "known_items": known,
        "total_items": len(values),
        "confidence": "high" if coverage >= 0.8 else "medium" if coverage >= 0.5 else "low",
    }
