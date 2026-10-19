"""Weekly plan generation tests (offline, deterministic)."""

from collections import Counter
from datetime import date

from app.diet.planning.generator import (
    _feedback_bonus,
    generate_week_plan,
    replace_single_meal,
)
from app.diet.planning.service import PlanService
from app.diet.recipes.parser import ParsedIngredient, ParsedRecipe

WEEK_START = date(2026, 10, 12)


def make_recipe(
    recipe_id: str,
    calories: float,
    *,
    title: str | None = None,
    ingredient: str = "鸡胸肉",
    raw_content: str | None = None,
    minutes: float = 20,
) -> ParsedRecipe:
    return ParsedRecipe(
        recipe_id=recipe_id,
        title=title or f"菜谱-{recipe_id}",
        servings=1,
        ingredients=[
            ParsedIngredient(
                name=ingredient,
                raw_name=ingredient,
                quantity=200,
                unit="g",
                scalable=True,
            )
        ],
        nutrition={
            "totals": {
                "calories": calories,
                "protein": 30,
                "fat": 15,
                "carbs": 50,
            },
            "coverage": 1.0,
            "confidence": "high",
        },
        total_minutes=minutes,
        raw_content=raw_content or f"## 必备原料和工具\n- {ingredient} 200g",
    )


def balanced_recipes() -> list[ParsedRecipe]:
    recipes: list[ParsedRecipe] = []
    for index in range(4):
        recipes.append(make_recipe(f"b{index}", 500))
    for index in range(4):
        recipes.append(make_recipe(f"l{index}", 800))
    for index in range(4):
        recipes.append(make_recipe(f"d{index}", 700))
    return recipes


def test_generates_21_meals_for_seven_days():
    result = generate_week_plan(
        balanced_recipes(),
        {"calorie_goal": 2000, "protein_goal": 90, "household_size": 1},
        WEEK_START,
    )
    meals = result["meals"]
    assert len(meals) == 21
    assert len({meal["plan_date"] for meal in meals}) == 7
    assert result["diagnostics"]["candidate_count"] == 12


def test_no_recipe_repeats_within_same_day():
    result = generate_week_plan(
        balanced_recipes(), {"calorie_goal": 2000}, WEEK_START
    )
    for day in {meal["plan_date"] for meal in result["meals"]}:
        ids = [
            dish["recipe_id"]
            for meal in result["meals"]
            if meal["plan_date"] == day
            for dish in meal["dishes"]
        ]
        assert len(ids) == len(set(ids))


def test_recipe_appears_at_most_twice_per_week():
    result = generate_week_plan(
        balanced_recipes(), {"calorie_goal": 2000}, WEEK_START
    )
    counts = Counter(
        dish["recipe_id"]
        for meal in result["meals"]
        for dish in meal["dishes"]
    )
    assert counts
    assert max(counts.values()) <= 2


def test_total_calories_close_to_weekly_target():
    result = generate_week_plan(
        balanced_recipes(), {"calorie_goal": 2000}, WEEK_START
    )
    total = result["diagnostics"]["total_calories"]
    assert abs(total - 14000) / 14000 <= 0.15
    assert abs(result["diagnostics"]["deviation_pct"]) <= 15


def test_peanut_allergy_candidates_are_excluded_without_fallback():
    peanut = make_recipe(
        "peanut",
        700,
        title="宫保鸡丁",
        ingredient="花生",
        raw_content="## 必备原料和工具\n- 花生 100g\n- 鸡胸肉 200g",
    )
    result = generate_week_plan(
        [peanut, *balanced_recipes()],
        {"allergies": ["花生"], "calorie_goal": 2000},
        WEEK_START,
    )
    assert result["diagnostics"]["candidate_count"] == 12
    assert all(
        dish["recipe_id"] != "peanut"
        for meal in result["meals"]
        for dish in meal["dishes"]
    )


def test_no_candidates_returns_explicit_error():
    peanut = make_recipe(
        "peanut-only",
        700,
        ingredient="花生",
        raw_content="## 必备原料和工具\n- 花生 100g",
    )
    result = generate_week_plan(
        [peanut], {"allergies": ["花生"], "calorie_goal": 2000}, WEEK_START
    )
    assert result["meals"] == []
    assert result["diagnostics"]["error"] == "no_candidates"


def test_locked_meal_is_preserved_and_not_duplicated():
    locked = {
        "plan_date": "2026-10-12",
        "meal_type": "breakfast",
        "dishes": [{"recipe_id": "locked", "name": "锁定早餐", "calories": 400}],
        "total_calories": 400,
        "total_protein": 20,
        "total_fat": 10,
        "total_carbs": 40,
        "status": "planned",
        "locked": True,
    }
    result = generate_week_plan(
        balanced_recipes(),
        {"calorie_goal": 2000},
        WEEK_START,
        existing_meals=[locked],
    )
    keys = [(meal["plan_date"], meal["meal_type"]) for meal in result["meals"]]
    assert keys.count(("2026-10-12", "breakfast")) == 1
    assert len(keys) == 21
    preserved = next(
        meal
        for meal in result["meals"]
        if meal["plan_date"] == "2026-10-12" and meal["meal_type"] == "breakfast"
    )
    assert preserved["dishes"][0]["name"] == "锁定早餐"


def test_replace_single_meal_excludes_current_recipe():
    recipes = [make_recipe("a", 700), make_recipe("b", 800), make_recipe("c", 900)]
    dish = replace_single_meal(
        recipes,
        {"calorie_goal": 2000},
        meal_type="lunch",
        current_recipe_id="a",
    )
    assert dish is not None
    assert dish["recipe_id"] != "a"


def test_feedback_bonus_is_clamped():
    assert _feedback_bonus("a", None) == 0.0
    assert _feedback_bonus("a", {"a": 99}) == 30.0
    assert _feedback_bonus("a", {"a": -99}) == -30.0
    assert _feedback_bonus("a", {"a": "bad"}) == 0.0


class FakeMeal:
    def __init__(self, data: dict):
        self.data = dict(data)
        self.locked = bool(data.get("locked", False))
        self.status = data.get("status", "planned")
        self.user_id = data.get("user_id", "user-1")

    def to_dict(self) -> dict:
        return dict(self.data)


class FakePlanRepository:
    def __init__(self, existing=None):
        self.existing = list(existing or [])
        self.deleted = False
        self.added: list[dict] = []

    async def get_plan_meals_by_week(self, user_id, week_start_date):
        return self.existing

    async def delete_unlocked_week_meals(self, user_id, week_start_date):
        self.deleted = True
        return 0

    async def add_meals_batch(self, user_id, meals):
        self.added = list(meals)
        records = []
        for index, meal in enumerate(meals):
            records.append(
                FakeMeal(
                    {
                        "id": f"new-{index}",
                        "plan_date": meal["plan_date"],
                        "meal_type": meal["meal_type"],
                        "dishes": meal.get("dishes") or [],
                        "total_calories": meal.get("total_calories"),
                        "total_protein": meal.get("total_protein"),
                        "total_fat": meal.get("total_fat"),
                        "total_carbs": meal.get("total_carbs"),
                        "status": meal.get("status") or "planned",
                        "locked": bool(meal.get("locked", False)),
                        "servings": meal.get("servings"),
                    }
                )
            )
        return records


class FakeProfileService:
    async def get_profile(self, user_id):
        return {"calorie_goal": 2000, "protein_goal": 90, "household_size": 1}


class FakeRecipeService:
    async def candidates(self, user_id):
        return balanced_recipes()


class FakeFeedbackService:
    async def scores(self, user_id, recipe_ids):
        return {}


async def test_plan_service_preserves_locked_meal_and_inserts_20_new_meals():
    locked = FakeMeal(
        {
            "id": "locked-1",
            "user_id": "user-1",
            "plan_date": "2026-10-12",
            "meal_type": "breakfast",
            "dishes": [{"recipe_id": "locked", "name": "锁定早餐"}],
            "total_calories": 400,
            "status": "planned",
            "locked": True,
        }
    )
    repository = FakePlanRepository([locked])
    service = PlanService(
        repository=repository,
        profile_service=FakeProfileService(),
        recipe_service_=FakeRecipeService(),
        feedback=FakeFeedbackService(),
    )
    result = await service.generate("user-1", WEEK_START)
    assert repository.deleted is True
    assert len(repository.added) == 20
    assert all(not meal["locked"] for meal in repository.added)
    assert len(result["plan"]["meals"]) == 21
    keys = [
        (meal["plan_date"], meal["meal_type"])
        for meal in result["plan"]["meals"]
    ]
    assert keys.count(("2026-10-12", "breakfast")) == 1
