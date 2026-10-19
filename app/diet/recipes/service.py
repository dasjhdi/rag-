"""Recipe retrieval, parsing, scaling and filtering."""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.diet.recipes.parser import ParsedRecipe, parse_recipe_document
from app.diet.recipes.repository import RecipeRepository, recipe_repository
from app.knowledge.ontology import allergens_for, normalize_ingredient

logger = logging.getLogger(__name__)


class RecipeService:
    def __init__(self, repository: Optional[RecipeRepository] = None) -> None:
        self.repository = repository or recipe_repository
        self._cache: dict[str, tuple[str, ParsedRecipe]] = {}

    async def get_recipe(
        self,
        recipe_id: str,
        user_id: Optional[str] = None,
        *,
        servings: Optional[float] = None,
        unit_system: str = "metric",
    ) -> Optional[dict[str, Any]]:
        document = await self.repository.get_document(recipe_id, user_id)
        if not document:
            return None
        recipe = self._parse_document(document)
        return recipe.to_dict(servings=servings, unit_system=unit_system)

    async def get_parsed_recipe(
        self, recipe_id: str, user_id: Optional[str] = None
    ) -> Optional[ParsedRecipe]:
        document = await self.repository.get_document(recipe_id, user_id)
        return self._parse_document(document) if document else None

    async def search(
        self,
        user_id: Optional[str] = None,
        *,
        query: Optional[str] = None,
        category: Optional[str] = None,
        diet_tag: Optional[str] = None,
        exclude_allergens: Optional[list[str]] = None,
        max_minutes: Optional[float] = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        documents = await self.repository.list_documents(
            user_id, query=query, limit=500
        )
        excluded_terms = [
            str(item).strip() for item in (exclude_allergens or []) if str(item).strip()
        ]
        excluded_allergens: set[str] = set()
        excluded_ingredients: set[str] = set()
        for term in excluded_terms:
            excluded_allergens.update(allergens_for([term]))
            canonical = normalize_ingredient(term)
            if canonical:
                excluded_ingredients.add(canonical)
        results: list[dict[str, Any]] = []

        for document in documents:
            recipe = self._parse_document(document)
            if category and category.casefold() not in {
                recipe.category.casefold(),
                recipe.title.casefold(),
            }:
                continue
            if diet_tag and diet_tag.casefold() not in {
                tag.casefold() for tag in recipe.diet_tags
            }:
                continue
            if excluded_terms:
                recipe_allergens = {tag.casefold() for tag in recipe.allergens}
                if excluded_allergens.intersection(recipe_allergens):
                    continue
                if any(
                    ingredient.name in excluded_ingredients
                    for ingredient in recipe.ingredients
                ):
                    continue
            if max_minutes and recipe.total_minutes and recipe.total_minutes > max_minutes:
                continue
            results.append(recipe.to_dict())

        results.sort(
            key=lambda item: (
                -float((item.get("nutrition") or {}).get("coverage", 0) or 0),
                float(item.get("total_minutes") or 9999),
                item.get("title") or "",
            )
        )
        return results[: max(1, min(int(limit or 20), 100))]

    async def candidates(
        self, user_id: Optional[str] = None, limit: int = 500
    ) -> list[ParsedRecipe]:
        documents = await self.repository.list_documents(user_id, limit=limit)
        return [self._parse_document(document) for document in documents]

    def _parse_document(self, document: Any) -> ParsedRecipe:
        document_id = str(document.id)
        updated_at = str(getattr(document, "updated_at", "") or "")
        cached = self._cache.get(document_id)
        if cached and cached[0] == updated_at:
            return cached[1]

        recipe = parse_recipe_document(
            recipe_id=document_id,
            title=document.dish_name,
            content=document.content,
            category=document.category,
            difficulty=document.difficulty,
            source=document.source,
        )
        self._cache[document_id] = (updated_at, recipe)
        return recipe


recipe_service = RecipeService()
