"""New API route and request-model contract tests (no database)."""

from datetime import date

from app.api.v1.endpoints import diet, family, nutrition, pantry, recipes
from app.api.v1.endpoints.diet import (
    DishSchema,
    GeneratePlanRequest,
    build_profile_update,
    UpdatePreferenceRequest,
)


def route_paths(router) -> set[str]:
    return {route.path for route in router.routes}


def test_diet_routes_are_registered():
    paths = route_paths(diet.router)
    assert {
        "/diet/plans/generate",
        "/diet/plans/meals/{meal_id}/replace",
        "/diet/plans/meals/{meal_id}/skip",
        "/diet/today",
        "/diet/analysis/adherence",
        "/diet/profile",
        "/diet/profile/effective-constraints",
    }.issubset(paths)


def test_recipe_routes_are_registered_before_dynamic_route():
    paths = [route.path for route in recipes.router.routes]
    assert "/recipes/search" in paths
    assert "/recipes/recommendations" in paths
    assert "/recipes/{recipe_id}" in paths
    assert paths.index("/recipes/search") < paths.index("/recipes/{recipe_id}")
    assert {
        "/recipes/{recipe_id}/feedback",
        "/recipes/{recipe_id}/reviews",
        "/recipes/{recipe_id}/review",
    }.issubset(paths)


def test_pantry_nutrition_family_routes_are_registered():
    assert {
        "/pantry/items",
        "/pantry/items/{item_id}",
        "/pantry/expiring",
        "/pantry/shopping-list/generate",
        "/pantry/shopping-list",
        "/pantry/shopping-list/{item_id}",
        "/pantry/cookable",
    }.issubset(route_paths(pantry.router))
    assert {
        "/nutrition/foods",
        "/nutrition/convert",
        "/nutrition/estimate",
    }.issubset(route_paths(nutrition.router))
    assert {
        "/family/members",
        "/family/members/{member_id}",
    }.issubset(route_paths(family.router))


def test_dish_schema_accepts_fractional_calories():
    dish = DishSchema(name="番茄炒蛋", calories=320.5, servings=2)
    assert dish.calories == 320.5
    assert dish.servings == 2


def test_generate_plan_request_defaults():
    payload = GeneratePlanRequest()
    assert payload.week_start_date is None
    assert payload.include_family is False
    payload = GeneratePlanRequest(week_start_date=date(2026, 10, 12), include_family=True)
    assert payload.week_start_date == date(2026, 10, 12)


def test_profile_update_legacy_mapping_via_api_model():
    payload = UpdatePreferenceRequest(disliked_foods=["香菜"])
    data = build_profile_update(payload)
    assert data == {"avoided_foods": ["香菜"]}
