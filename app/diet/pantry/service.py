"""Pantry inventory, shopping-list aggregation and cookable ranking."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any, Iterable, Optional

from sqlalchemy import delete, select

from app.database.session import get_session_context
from app.diet.database.models import PantryItemModel, ShoppingListItemModel
from app.diet.database.repository import DietRepository, diet_repository
from app.diet.recipes.parser import ParsedRecipe
from app.diet.recipes.service import RecipeService, recipe_service
from app.knowledge.ontology import normalize_ingredient


def aggregate_plan_ingredients(meals: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate all planned ingredients by normalized name and unit."""
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for meal in meals or []:
        for dish in meal.get("dishes") or []:
            recipe_id = str(dish.get("recipe_id") or "")
            ingredients = dish.get("ingredients") or []
            if ingredients:
                for ingredient in ingredients:
                    raw_name = str(
                        ingredient.get("name") or ingredient.get("raw_name") or ""
                    ).strip()
                    if not raw_name:
                        continue
                    normalized = normalize_ingredient(raw_name) or raw_name
                    unit = str(ingredient.get("unit") or "适量")
                    quantity = ingredient.get("quantity")
                    try:
                        amount = float(quantity) if quantity is not None else 1.0
                    except (TypeError, ValueError):
                        amount = 1.0
                    key = (normalized, unit)
                    item = grouped.setdefault(
                        key,
                        {
                            "name": raw_name,
                            "normalized_name": normalized,
                            "quantity": 0.0,
                            "unit": unit,
                            "recipe_ids": [],
                        },
                    )
                    item["quantity"] += amount
                    if recipe_id and recipe_id not in item["recipe_ids"]:
                        item["recipe_ids"].append(recipe_id)
            else:
                name = str(dish.get("name") or "未命名菜品").strip()
                normalized = normalize_ingredient(name) or name
                key = (normalized, "份")
                item = grouped.setdefault(
                    key,
                    {
                        "name": name,
                        "normalized_name": normalized,
                        "quantity": 0.0,
                        "unit": "份",
                        "recipe_ids": [],
                    },
                )
                item["quantity"] += 1.0
                if recipe_id and recipe_id not in item["recipe_ids"]:
                    item["recipe_ids"].append(recipe_id)

    for item in grouped.values():
        item["quantity"] = round(item["quantity"], 2)
    return sorted(grouped.values(), key=lambda item: (item["unit"], item["name"]))


def apply_inventory(
    requirements: Iterable[dict[str, Any]],
    pantry_items: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Subtract pantry quantities and keep only positive requirements."""
    inventory: dict[tuple[str, str], float] = {}
    for item in pantry_items or []:
        name = normalize_ingredient(str(item.get("normalized_name") or item.get("name") or ""))
        unit = str(item.get("unit") or "g")
        try:
            quantity = float(item.get("quantity") or 0)
        except (TypeError, ValueError):
            quantity = 0.0
        key = (name, unit)
        inventory[key] = inventory.get(key, 0.0) + quantity

    result: list[dict[str, Any]] = []
    for requirement in requirements or []:
        item = dict(requirement)
        raw_name = str(
            item.get("normalized_name") or item.get("name") or ""
        ).strip()
        normalized = normalize_ingredient(raw_name) or raw_name
        key = (normalized, str(item.get("unit") or "g"))
        available = inventory.get(key, 0.0)
        remaining = float(item.get("quantity") or 0) - available
        if remaining <= 0:
            continue
        item["normalized_name"] = normalized
        item["quantity"] = round(remaining, 2)
        result.append(item)
    return result


def coverage_for_recipe(
    recipe: ParsedRecipe, pantry_names: set[str]
) -> dict[str, Any]:
    ingredients = [
        normalize_ingredient(item.name) or item.name
        for item in recipe.ingredients
        if item.name and item.name != "适量"
    ]
    if not ingredients:
        return {"coverage": 0.0, "matched": [], "missing": []}
    matched = [name for name in ingredients if name in pantry_names]
    missing = [name for name in ingredients if name not in pantry_names]
    return {
        "coverage": round(len(matched) / len(ingredients), 3),
        "matched": matched,
        "missing": missing,
    }


def select_expiring_items(
    items: Iterable[dict[str, Any]],
    days: int = 3,
    *,
    today: Optional[date] = None,
) -> list[dict[str, Any]]:
    """Filter and sort pantry items by expiry date without touching the database."""
    current = today or date.today()
    cutoff = current + timedelta(days=max(0, int(days)))
    selected: list[dict[str, Any]] = []
    for item in items or []:
        raw_expiry = item.get("expires_on")
        if not raw_expiry:
            continue
        if isinstance(raw_expiry, date):
            expires_on = raw_expiry
        else:
            try:
                expires_on = date.fromisoformat(str(raw_expiry)[:10])
            except ValueError:
                continue
        if expires_on <= cutoff:
            copy = dict(item)
            copy["expires_on"] = expires_on.isoformat()
            selected.append(copy)
    selected.sort(
        key=lambda item: (str(item.get("expires_on") or ""), str(item.get("name") or ""))
    )
    return selected


def rank_cookable_recipes(
    recipes: Iterable[ParsedRecipe],
    pantry_names: set[str],
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Rank recipes by pantry coverage, then by missing ingredient count."""
    ranked: list[dict[str, Any]] = []
    for recipe in recipes:
        coverage = coverage_for_recipe(recipe, pantry_names)
        ranked.append(
            {
                "recipe_id": recipe.recipe_id,
                "title": recipe.title,
                "coverage": coverage["coverage"],
                "matched": coverage["matched"],
                "missing": coverage["missing"],
                "total_minutes": recipe.total_minutes,
            }
        )
    ranked.sort(
        key=lambda item: (-item["coverage"], len(item["missing"]), item["title"])
    )
    return ranked[: max(1, min(int(limit or 20), 100))]


class PantryService:
    def __init__(
        self,
        repository: Optional[DietRepository] = None,
        recipes: Optional[RecipeService] = None,
    ) -> None:
        self.repository = repository or diet_repository
        self.recipes = recipes or recipe_service

    async def list_items(self, user_id: str) -> list[dict[str, Any]]:
        async with get_session_context() as session:
            stmt = (
                select(PantryItemModel)
                .where(PantryItemModel.user_id == str(user_id))
                .order_by(PantryItemModel.expires_on, PantryItemModel.name)
            )
            return [
                record.to_dict()
                for record in (await session.execute(stmt)).scalars().all()
            ]

    async def add_item(self, user_id: str, **kwargs: Any) -> dict[str, Any]:
        name = str(kwargs.get("name") or "").strip()
        if not name:
            raise ValueError("食材名称不能为空")
        async with get_session_context() as session:
            record = PantryItemModel(
                user_id=str(user_id),
                name=name,
                normalized_name=normalize_ingredient(name) or name,
                quantity=float(kwargs.get("quantity") or 0),
                unit=str(kwargs.get("unit") or "g"),
                category=kwargs.get("category"),
                expires_on=kwargs.get("expires_on"),
                location=kwargs.get("location"),
                notes=kwargs.get("notes"),
            )
            session.add(record)
            await session.flush()
            await session.refresh(record)
            return record.to_dict()

    async def update_item(
        self, user_id: str, item_id: str, **kwargs: Any
    ) -> Optional[dict[str, Any]]:
        try:
            item_uuid = uuid.UUID(str(item_id))
        except (ValueError, TypeError):
            return None
        async with get_session_context() as session:
            stmt = select(PantryItemModel).where(
                PantryItemModel.id == item_uuid,
                PantryItemModel.user_id == str(user_id),
            )
            record = (await session.execute(stmt)).scalar_one_or_none()
            if not record:
                return None
            for key, value in kwargs.items():
                if value is not None and hasattr(record, key):
                    setattr(record, key, value)
            if "name" in kwargs and kwargs.get("name"):
                record.normalized_name = normalize_ingredient(str(kwargs["name"]))
            await session.flush()
            await session.refresh(record)
            return record.to_dict()

    async def delete_item(self, user_id: str, item_id: str) -> bool:
        try:
            item_uuid = uuid.UUID(str(item_id))
        except (ValueError, TypeError):
            return False
        async with get_session_context() as session:
            stmt = delete(PantryItemModel).where(
                PantryItemModel.id == item_uuid,
                PantryItemModel.user_id == str(user_id),
            )
            result = await session.execute(stmt)
            return bool(result.rowcount)

    async def expiring(self, user_id: str, days: int = 3) -> list[dict[str, Any]]:
        async with get_session_context() as session:
            stmt = (
                select(PantryItemModel)
                .where(
                    PantryItemModel.user_id == str(user_id),
                    PantryItemModel.expires_on.is_not(None),
                )
                .order_by(PantryItemModel.expires_on)
            )
            records = (await session.execute(stmt)).scalars().all()
        return select_expiring_items(
            [record.to_dict() for record in records], days
        )

    async def generate_shopping_list(
        self, user_id: str, week_start_date: date
    ) -> dict[str, Any]:
        meals = await self.repository.get_plan_meals_by_week(user_id, week_start_date)
        requirements = aggregate_plan_ingredients([meal.to_dict() for meal in meals])
        pantry = await self.list_items(user_id)
        remaining = apply_inventory(requirements, pantry)

        async with get_session_context() as session:
            await session.execute(
                delete(ShoppingListItemModel).where(
                    ShoppingListItemModel.user_id == str(user_id),
                    ShoppingListItemModel.week_start_date == week_start_date,
                )
            )
            records = []
            for item in remaining:
                record = ShoppingListItemModel(
                    user_id=str(user_id),
                    week_start_date=week_start_date,
                    name=item["name"],
                    normalized_name=item["normalized_name"],
                    quantity=item["quantity"],
                    unit=item["unit"],
                    checked=False,
                    source="plan",
                    recipe_ids=item.get("recipe_ids") or [],
                )
                session.add(record)
                records.append(record)
            await session.flush()
            for record in records:
                await session.refresh(record)
            return {
                "week_start_date": week_start_date.isoformat(),
                "items": [record.to_dict() for record in records],
                "saved_by_pantry": len(requirements) - len(remaining),
            }

    async def list_shopping(
        self, user_id: str, week_start_date: date
    ) -> list[dict[str, Any]]:
        async with get_session_context() as session:
            stmt = (
                select(ShoppingListItemModel)
                .where(
                    ShoppingListItemModel.user_id == str(user_id),
                    ShoppingListItemModel.week_start_date == week_start_date,
                )
                .order_by(ShoppingListItemModel.unit, ShoppingListItemModel.name)
            )
            return [
                record.to_dict()
                for record in (await session.execute(stmt)).scalars().all()
            ]

    async def update_shopping_item(
        self, user_id: str, item_id: str, **kwargs: Any
    ) -> Optional[dict[str, Any]]:
        try:
            item_uuid = uuid.UUID(str(item_id))
        except (ValueError, TypeError):
            return None
        async with get_session_context() as session:
            stmt = select(ShoppingListItemModel).where(
                ShoppingListItemModel.id == item_uuid,
                ShoppingListItemModel.user_id == str(user_id),
            )
            record = (await session.execute(stmt)).scalar_one_or_none()
            if not record:
                return None
            for key, value in kwargs.items():
                if value is not None and hasattr(record, key):
                    setattr(record, key, value)
            await session.flush()
            await session.refresh(record)
            return record.to_dict()

    async def cookable(
        self, user_id: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        pantry = await self.list_items(user_id)
        pantry_names = {
            normalize_ingredient(str(item.get("normalized_name") or item.get("name")))
            for item in pantry
        }
        recipes = await self.recipes.candidates(user_id)
        return rank_cookable_recipes(recipes, pantry_names, limit)


pantry_service = PantryService()
