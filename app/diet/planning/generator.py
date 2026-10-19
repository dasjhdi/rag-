"""Pure weekly meal-plan generation.

The generator deliberately avoids LLM calls. It ranks parsed recipes with a
transparent score so failures are reproducible and testable.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import Any, Iterable, Optional

from langchain_core.documents import Document

from app.diet.recipes.parser import ParsedRecipe, scale_recipe
from app.reasoning.constraints.evaluator import build_evaluation
from app.reasoning.constraints.service import constraint_reasoner

MEAL_CALORIE_SHARES = {
    "breakfast": 0.25,
    "lunch": 0.40,
    "dinner": 0.35,
}


def _recipe_nutrition(recipe: ParsedRecipe, servings: float) -> dict[str, float]:
    scaled = scale_recipe(recipe, servings)
    totals = (scaled.nutrition or {}).get("totals", {})
    return {
        "calories": float(totals.get("calories") or 0),
        "protein": float(totals.get("protein") or 0),
        "fat": float(totals.get("fat") or 0),
        "carbs": float(totals.get("carbs") or 0),
    }


def _fallback_nutrition(recipe: ParsedRecipe, servings: float) -> dict[str, float]:
    """Conservative estimate when the local table cannot cover the recipe."""
    nutrition = _recipe_nutrition(recipe, servings)
    if nutrition["calories"] > 0:
        return nutrition
    # Category-neutral fallback: a main dish serving is roughly 350 kcal.
    ratio = max(servings, 1.0)
    return {
        "calories": 350.0 * ratio,
        "protein": 18.0 * ratio,
        "fat": 14.0 * ratio,
        "carbs": 40.0 * ratio,
    }


def _profile_terms(profile: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for allergen in profile.get("allergies") or []:
        values.append(f"{allergen}过敏")
    values.extend(str(item) for item in profile.get("dietary_restrictions") or [])
    values.extend(str(item) for item in profile.get("health_conditions") or [])
    values.extend(f"不吃{item}" for item in profile.get("avoided_foods") or [])
    return values


def _filter_recipes(
    recipes: Iterable[ParsedRecipe], profile: dict[str, Any]
) -> list[ParsedRecipe]:
    candidates = list(recipes or [])
    terms = _profile_terms(profile)
    if not terms:
        return candidates

    documents = [
        Document(
            page_content=recipe.raw_content,
            metadata={"id": recipe.recipe_id, "dish_name": recipe.title},
        )
        for recipe in candidates
    ]
    decision = constraint_reasoner.analyze(slots={"diet_constraints": terms})
    outcome = build_evaluation(
        documents,
        decision.profile,
        strict_allergens=True,
        max_candidates=len(documents),
    )
    # Never fall back to excluded candidates: allergen safety is a hard rule.
    excluded_ids = {
        assessment.document_id
        for assessment in outcome.assessments
        if assessment.excluded
    }
    return [
        recipe for recipe in candidates if recipe.recipe_id not in excluded_ids
    ]


def _feedback_bonus(recipe_id: str, feedback_scores: Optional[dict[str, float]]) -> float:
    if not feedback_scores:
        return 0.0
    try:
        return max(-30.0, min(30.0, float(feedback_scores.get(recipe_id, 0.0))))
    except (TypeError, ValueError):
        return 0.0


def _score_recipe(
    recipe: ParsedRecipe,
    *,
    meal_type: str,
    target_calories: float,
    target_protein: float,
    servings: float,
    repeat_count: int,
    same_day: bool,
    profile: dict[str, Any],
    feedback_scores: Optional[dict[str, float]],
) -> float:
    nutrition = _fallback_nutrition(recipe, servings)
    calories = nutrition["calories"]
    protein = nutrition["protein"]
    calorie_error = abs(calories - target_calories) / max(target_calories, 1.0)
    protein_error = abs(protein - target_protein) / max(target_protein, 1.0)

    score = -calorie_error * 100.0 - protein_error * 30.0
    score -= repeat_count * 25.0
    if same_day:
        score -= 1000.0

    max_minutes = float(profile.get("max_cook_minutes") or 60)
    if recipe.total_minutes and recipe.total_minutes > max_minutes:
        score -= (recipe.total_minutes - max_minutes) * 0.5

    favorite_cuisines = {
        str(item).casefold() for item in profile.get("favorite_cuisines") or []
    }
    if recipe.category and recipe.category.casefold() in favorite_cuisines:
        score += 8.0
    if recipe.title and any(
        cuisine and cuisine in recipe.title.casefold() for cuisine in favorite_cuisines
    ):
        score += 4.0

    score += _feedback_bonus(recipe.recipe_id, feedback_scores)
    coverage = float((recipe.nutrition or {}).get("coverage") or 0)
    score += coverage * 10.0
    return score


def _dish_payload(recipe: ParsedRecipe, servings: float) -> dict[str, Any]:
    nutrition = _fallback_nutrition(recipe, servings)
    scaled = scale_recipe(recipe, servings)
    return {
        "recipe_id": recipe.recipe_id,
        "name": recipe.title,
        "servings": servings,
        "ingredients": [item.to_dict() for item in scaled.ingredients],
        "calories": round(nutrition["calories"], 1),
        "protein": round(nutrition["protein"], 1),
        "fat": round(nutrition["fat"], 1),
        "carbs": round(nutrition["carbs"], 1),
        "nutrition_confidence": (recipe.nutrition or {}).get("confidence", "low"),
        "total_minutes": recipe.total_minutes,
    }


def generate_week_plan(
    recipes: Iterable[ParsedRecipe],
    profile: dict[str, Any],
    week_start_date: date,
    *,
    existing_meals: Optional[list[dict[str, Any]]] = None,
    feedback_scores: Optional[dict[str, float]] = None,
    max_recipe_repeats: int = 2,
) -> dict[str, Any]:
    """Generate a seven-day plan and return it with diagnostics."""
    candidates = _filter_recipes(recipes, profile)
    existing = list(existing_meals or [])
    locked = [
        meal
        for meal in existing
        if meal.get("locked") or meal.get("status") in {"eaten", "skipped"}
    ]
    locked_keys = {
        (meal.get("plan_date"), meal.get("meal_type")) for meal in locked
    }

    target_calories = float(profile.get("calorie_goal") or 2000)
    target_protein = float(profile.get("protein_goal") or 90)
    household_size = float(profile.get("household_size") or 1)
    servings = max(1.0, household_size)
    repeats: Counter[str] = Counter(
        str(dish.get("recipe_id"))
        for meal in locked
        for dish in meal.get("dishes") or []
        if dish.get("recipe_id")
    )

    planned: list[dict[str, Any]] = []
    warnings: list[str] = []
    if not candidates:
        return {
            "meals": [],
            "diagnostics": {
                "candidate_count": 0,
                "error": "no_candidates",
                "message": "没有满足当前约束的候选菜谱",
            },
        }

    for day_index in range(7):
        current_date = week_start_date + timedelta(days=day_index)
        day_key = current_date.isoformat()
        used_today: set[str] = set()
        for meal_type, share in MEAL_CALORIE_SHARES.items():
            if (day_key, meal_type) in locked_keys:
                continue
            meal_target = target_calories * share
            meal_protein = target_protein * share
            scored = []
            for recipe in candidates:
                if recipe.recipe_id in used_today:
                    continue
                if repeats[recipe.recipe_id] >= max_recipe_repeats:
                    continue
                scored.append(
                    (
                        _score_recipe(
                            recipe,
                            meal_type=meal_type,
                            target_calories=meal_target,
                            target_protein=meal_protein,
                            servings=servings,
                            repeat_count=repeats[recipe.recipe_id],
                            same_day=recipe.recipe_id in used_today,
                            profile=profile,
                            feedback_scores=feedback_scores,
                        ),
                        recipe,
                    )
                )
            if not scored:
                warnings.append(
                    f"{day_key} {meal_type} 无可用候选（候选不足或已达重复上限）"
                )
                continue
            scored.sort(key=lambda item: item[0], reverse=True)
            chosen = scored[0][1]
            repeats[chosen.recipe_id] += 1
            used_today.add(chosen.recipe_id)
            dish = _dish_payload(chosen, servings)
            planned.append(
                {
                    "plan_date": day_key,
                    "meal_type": meal_type,
                    "dishes": [dish],
                    "total_calories": dish["calories"],
                    "total_protein": dish["protein"],
                    "total_fat": dish["fat"],
                    "total_carbs": dish["carbs"],
                    "servings": servings,
                    "status": "planned",
                    "locked": False,
                    "notes": "由 CookHero 自动生成",
                }
            )

    meals = sorted(locked + planned, key=lambda item: (item["plan_date"], item["meal_type"]))
    total_calories = sum(float(meal.get("total_calories") or 0) for meal in meals)
    target_total = target_calories * 7
    deviation_pct = (
        round((total_calories - target_total) / target_total * 100, 1)
        if target_total
        else 0.0
    )
    return {
        "meals": meals,
        "diagnostics": {
            "candidate_count": len(candidates),
            "target_calories_per_day": target_calories,
            "target_protein_per_day": target_protein,
            "total_calories": round(total_calories, 1),
            "deviation_pct": deviation_pct,
            "warnings": warnings,
        },
    }


def replace_single_meal(
    recipes: Iterable[ParsedRecipe],
    profile: dict[str, Any],
    *,
    meal_type: str,
    current_recipe_id: str,
    feedback_scores: Optional[dict[str, float]] = None,
) -> Optional[dict[str, Any]]:
    candidates = [
        recipe
        for recipe in _filter_recipes(recipes, profile)
        if recipe.recipe_id != current_recipe_id
    ]
    if not candidates:
        return None
    target = float(profile.get("calorie_goal") or 2000) * MEAL_CALORIE_SHARES.get(
        meal_type, 0.33
    )
    servings = max(1.0, float(profile.get("household_size") or 1))
    ranked = sorted(
        (
            _score_recipe(
                recipe,
                meal_type=meal_type,
                target_calories=target,
                target_protein=float(profile.get("protein_goal") or 90)
                * MEAL_CALORIE_SHARES.get(meal_type, 0.33),
                servings=servings,
                repeat_count=0,
                same_day=False,
                profile=profile,
                feedback_scores=feedback_scores,
            ),
            recipe,
        )
        for recipe in candidates
    )
    ranked.sort(key=lambda item: item[0], reverse=True)
    return _dish_payload(ranked[0][1], servings)
