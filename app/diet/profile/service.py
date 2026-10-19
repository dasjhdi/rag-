"""Single source of truth for structured dietary profiles."""

from __future__ import annotations

from typing import Any, Optional

from app.diet.database.repository import DietRepository, diet_repository

_LIST_FIELDS = {
    "allergies",
    "dietary_restrictions",
    "favorite_cuisines",
    "preferred_foods",
    "health_conditions",
    "avoided_foods",
}

_DEFAULT_PROFILE = {
    "allergies": [],
    "allergy_severity": {},
    "dietary_restrictions": [],
    "favorite_cuisines": [],
    "preferred_foods": [],
    "health_conditions": [],
    "avoided_foods": [],
    "calorie_goal": 2000,
    "protein_goal": 90.0,
    "fat_goal": 67.0,
    "carbs_goal": 250.0,
    "fiber_goal": 25.0,
    "sodium_goal": 2000.0,
    "meals_per_day": 3,
    "cooking_skill": "intermediate",
    "max_cook_minutes": 60,
    "budget_level": "medium",
    "household_size": 1,
    "unit_system": "metric",
    "spice_level": "medium",
    "version": 1,
}


class DietProfileService:
    def __init__(self, repository: Optional[DietRepository] = None) -> None:
        self.repository = repository or diet_repository

    async def get_profile(self, user_id: str) -> dict[str, Any]:
        preference = await self.repository.get_user_preference(user_id)
        if not preference:
            return {**_DEFAULT_PROFILE, "user_id": user_id, "exists": False}
        data = preference.to_dict()
        for key, value in _DEFAULT_PROFILE.items():
            data.setdefault(key, value)
        data["exists"] = True
        return data

    async def update_profile(self, user_id: str, **kwargs: Any) -> dict[str, Any]:
        update_data: dict[str, Any] = {}
        for key, value in kwargs.items():
            if value is None:
                continue
            if key in _LIST_FIELDS:
                update_data[key] = _normalize_list(value)
            elif key == "allergy_severity":
                update_data[key] = dict(value or {})
            else:
                update_data[key] = value

        current = await self.get_profile(user_id)
        update_data["version"] = int(current.get("version") or 1) + 1
        preference = await self.repository.upsert_user_preference(
            user_id, **update_data
        )
        return preference.to_dict()

    async def effective_constraints(self, user_id: str) -> list[str]:
        profile = await self.get_profile(user_id)
        constraints: list[str] = []
        for allergen in profile.get("allergies") or []:
            constraints.append(f"{allergen}过敏")
        for restriction in profile.get("dietary_restrictions") or []:
            constraints.append(str(restriction))
        for condition in profile.get("health_conditions") or []:
            constraints.append(str(condition))
        return constraints

    async def plan_targets(self, user_id: str) -> dict[str, float]:
        profile = await self.get_profile(user_id)
        return {
            "calories": float(profile.get("calorie_goal") or 2000),
            "protein": float(profile.get("protein_goal") or 90),
            "fat": float(profile.get("fat_goal") or 67),
            "carbs": float(profile.get("carbs_goal") or 250),
            "fiber": float(profile.get("fiber_goal") or 25),
            "sodium": float(profile.get("sodium_goal") or 2000),
            "max_cook_minutes": float(profile.get("max_cook_minutes") or 60),
        }


def _normalize_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    result: list[str] = []
    seen: set[str] = set()
    for item in value or []:
        text = str(item).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


diet_profile_service = DietProfileService()
