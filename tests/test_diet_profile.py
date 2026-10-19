"""Structured diet profile tests with an in-memory repository."""

from app.api.v1.endpoints.diet import UpdatePreferenceRequest, build_profile_update
from app.diet.profile.service import DietProfileService


class FakePreference:
    def __init__(self, data: dict):
        self.data = dict(data)

    def to_dict(self) -> dict:
        return dict(self.data)


class FakeRepository:
    def __init__(self):
        self.data: dict | None = None

    async def get_user_preference(self, user_id: str):
        if self.data is None:
            return None
        return FakePreference(self.data)

    async def upsert_user_preference(self, user_id: str, **kwargs):
        if self.data is None:
            self.data = {"id": "pref-1", "user_id": user_id}
        self.data.update(kwargs)
        return FakePreference(self.data)


async def test_default_profile_when_missing():
    service = DietProfileService(repository=FakeRepository())
    profile = await service.get_profile("user-1")
    assert profile["exists"] is False
    assert profile["calorie_goal"] == 2000
    assert profile["meals_per_day"] == 3
    assert profile["unit_system"] == "metric"


async def test_update_and_read_back_all_fields():
    service = DietProfileService(repository=FakeRepository())
    updated = await service.update_profile(
        "user-1",
        allergies=["花生", "花生", "牛奶"],
        dietary_restrictions=["vegetarian"],
        health_conditions=["高血压"],
        avoided_foods=["香菜"],
        preferred_foods=["番茄"],
        favorite_cuisines=["川菜"],
        calorie_goal=1800,
        protein_goal=100,
        fiber_goal=30,
        meals_per_day=4,
        cooking_skill="beginner",
        max_cook_minutes=30,
        budget_level="low",
        household_size=3,
        unit_system="imperial",
        spice_level="mild",
    )
    assert updated["allergies"] == ["花生", "牛奶"]
    profile = await service.get_profile("user-1")
    assert profile["exists"] is True
    assert profile["dietary_restrictions"] == ["vegetarian"]
    assert profile["health_conditions"] == ["高血压"]
    assert profile["avoided_foods"] == ["香菜"]
    assert profile["preferred_foods"] == ["番茄"]
    assert profile["favorite_cuisines"] == ["川菜"]
    assert profile["calorie_goal"] == 1800
    assert profile["protein_goal"] == 100
    assert profile["fiber_goal"] == 30
    assert profile["meals_per_day"] == 4
    assert profile["cooking_skill"] == "beginner"
    assert profile["max_cook_minutes"] == 30
    assert profile["budget_level"] == "low"
    assert profile["household_size"] == 3
    assert profile["unit_system"] == "imperial"
    assert profile["spice_level"] == "mild"


async def test_partial_update_keeps_existing_fields_and_increments_version():
    service = DietProfileService(repository=FakeRepository())
    first = await service.update_profile("user-1", calorie_goal=1900)
    assert first["version"] == 2
    second = await service.update_profile("user-1", protein_goal=110)
    assert second["version"] == 3
    assert second["calorie_goal"] == 1900
    assert second["protein_goal"] == 110


async def test_effective_constraints_and_plan_targets():
    service = DietProfileService(repository=FakeRepository())
    await service.update_profile(
        "user-1",
        allergies=["花生"],
        dietary_restrictions=["vegetarian"],
        health_conditions=["高血压"],
        calorie_goal=1800,
        protein_goal=100,
        max_cook_minutes=30,
    )
    constraints = await service.effective_constraints("user-1")
    assert constraints == ["花生过敏", "vegetarian", "高血压"]
    targets = await service.plan_targets("user-1")
    assert targets["calories"] == 1800
    assert targets["protein"] == 100
    assert targets["max_cook_minutes"] == 30


def test_legacy_disliked_foods_maps_to_avoided_foods():
    payload = UpdatePreferenceRequest(disliked_foods=["香菜"], calorie_goal=1800)
    data = build_profile_update(payload)
    assert data["avoided_foods"] == ["香菜"]
    assert "disliked_foods" not in data
    assert data["calorie_goal"] == 1800


def test_explicit_avoided_foods_wins_over_legacy_field():
    payload = UpdatePreferenceRequest(
        disliked_foods=["香菜"], avoided_foods=["芹菜"]
    )
    data = build_profile_update(payload)
    assert data["avoided_foods"] == ["芹菜"]
    assert "disliked_foods" not in data
