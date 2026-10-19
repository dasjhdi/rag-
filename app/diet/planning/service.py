"""Plan generation orchestration."""

from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import Any, Optional

from app.diet.database.repository import DietRepository, diet_repository
from app.diet.feedback.service import FeedbackService, feedback_service
from app.diet.planning.generator import generate_week_plan, replace_single_meal
from app.diet.profile.service import DietProfileService, diet_profile_service
from app.diet.recipes.service import RecipeService, recipe_service

logger = logging.getLogger(__name__)


class PlanService:
    def __init__(
        self,
        repository: Optional[DietRepository] = None,
        profile_service: Optional[DietProfileService] = None,
        recipe_service_: Optional[RecipeService] = None,
        feedback: Optional[FeedbackService] = None,
    ) -> None:
        self.repository = repository or diet_repository
        self.profile_service = profile_service or diet_profile_service
        self.recipes = recipe_service_ or recipe_service
        self.feedback = feedback or feedback_service

    async def generate(
        self,
        user_id: str,
        week_start_date: date,
        *,
        include_family: bool = False,
    ) -> dict[str, Any]:
        profile = await self.profile_service.get_profile(user_id)
        if include_family:
            try:
                from app.diet.family.service import family_service

                family = await family_service.merged_context(user_id)
                profile = {**profile, **family}
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Failed to merge family context: %s", exc)

        recipes = await self.recipes.candidates(user_id)
        feedback_scores = await self.feedback.scores(
            user_id, [recipe.recipe_id for recipe in recipes]
        )
        existing = await self.repository.get_plan_meals_by_week(
            user_id, week_start_date
        )
        existing_payload = [meal.to_dict() for meal in existing]
        preserved_records = [
            meal
            for meal in existing
            if meal.locked or meal.status in {"eaten", "skipped"}
        ]

        result = generate_week_plan(
            recipes,
            profile,
            week_start_date,
            existing_meals=existing_payload,
            feedback_scores=feedback_scores,
        )
        diagnostics = result.get("diagnostics", {})
        if diagnostics.get("error") == "no_candidates":
            return {"plan": None, "diagnostics": diagnostics}

        batch_id = uuid.uuid4().hex
        new_meals = [
            meal
            for meal in result["meals"]
            if not meal.get("locked") and meal.get("status") not in {"eaten", "skipped"}
        ]
        for meal in new_meals:
            meal["generation_batch_id"] = batch_id

        await self.repository.delete_unlocked_week_meals(user_id, week_start_date)
        records = await self.repository.add_meals_batch(user_id, new_meals)
        combined = [record.to_dict() for record in preserved_records]
        combined.extend(record.to_dict() for record in records)
        combined.sort(key=lambda item: (item["plan_date"], item["meal_type"]))
        return {
            "plan": {
                "user_id": user_id,
                "week_start_date": week_start_date.isoformat(),
                "meals": combined,
            },
            "diagnostics": diagnostics,
        }

    async def replace_meal(self, user_id: str, meal_id: str) -> Optional[dict[str, Any]]:
        meal = await self.repository.get_meal(meal_id)
        if not meal or str(meal.user_id) != str(user_id):
            return None
        if meal.locked or meal.status in {"eaten", "skipped"}:
            return None

        profile = await self.profile_service.get_profile(user_id)
        recipes = await self.recipes.candidates(user_id)
        current_recipe_id = ""
        for dish in meal.dishes or []:
            if dish.get("recipe_id"):
                current_recipe_id = str(dish["recipe_id"])
                break
        feedback_scores = await self.feedback.scores(
            user_id, [recipe.recipe_id for recipe in recipes]
        )
        dish = replace_single_meal(
            recipes,
            profile,
            meal_type=meal.meal_type,
            current_recipe_id=current_recipe_id,
            feedback_scores=feedback_scores,
        )
        if not dish:
            return None

        updated = await self.repository.update_meal(
            meal_id,
            dishes=[dish],
            total_calories=dish["calories"],
            total_protein=dish["protein"],
            total_fat=dish["fat"],
            total_carbs=dish["carbs"],
            status="planned",
        )
        return updated.to_dict() if updated else None

    async def set_status(
        self, user_id: str, meal_id: str, status: str
    ) -> Optional[dict[str, Any]]:
        meal = await self.repository.get_meal(meal_id)
        if not meal or str(meal.user_id) != str(user_id):
            return None
        if status not in {"planned", "eaten", "skipped"}:
            raise ValueError("无效的餐次状态")
        updated = await self.repository.update_meal(meal_id, status=status)
        return updated.to_dict() if updated else None


plan_service = PlanService()
