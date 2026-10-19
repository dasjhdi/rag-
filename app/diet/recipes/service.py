"""Recipe retrieval, parsing, scaling and filtering."""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from app.diet.recipes.parser import ParsedRecipe, parse_recipe_document
from app.diet.recipes.images import image_override_version
from app.diet.recipes.repository import RecipeRepository, recipe_repository
from app.knowledge.ontology import allergens_for, normalize_ingredient

logger = logging.getLogger(__name__)


class RecipeService:
    def __init__(self, repository: Optional[RecipeRepository] = None) -> None:
        self.repository = repository or recipe_repository
        self._cache: dict[str, tuple[str, str, ParsedRecipe]] = {}
        # Library facet cache: {version: {parsed, counts, ts}}. Single entry,
        # refreshed when the image override version changes or after 5 minutes.
        self._library_cache: dict[str, dict[str, Any]] = {}
        self._LIBRARY_TTL = 300.0

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

    async def library(
        self,
        user_id: Optional[str] = None,
        *,
        category: Optional[str] = None,
        difficulty: Optional[str] = None,
        ingredient: Optional[str] = None,
        feedback: Optional[str] = None,
        sort: Optional[str] = None,
        has_step_images: Optional[bool] = None,
        query: Optional[str] = None,
        offset: int = 0,
        limit: int = 24,
        feedback_signals: Optional[dict[str, set[str]]] = None,
    ) -> tuple[list[dict[str, Any]], int, dict[str, int], dict[str, int], list[dict[str, Any]], list[dict[str, Any]]]:
        """Return a paginated slice of all recipes plus facet counts.

        Facet counts are computed over the unfiltered set so the sidebar totals
        stay stable as the user toggles filters. Results are cached for a few
        minutes keyed by the image-override version.
        """
        parsed = await self._all_parsed(user_id, query=query)
        facets = self._library_facets(parsed)

        filtered: list[ParsedRecipe] = list(parsed)
        if category:
            filtered = [r for r in filtered if (r.category or "未分类") == category]
        if difficulty:
            filtered = [r for r in filtered if (r.difficulty or "未知") == difficulty]
        if ingredient:
            target = normalize_ingredient(ingredient) or ingredient
            filtered = [
                r for r in filtered
                if any(ing.name == target for ing in r.ingredients)
            ]
        if has_step_images:
            filtered = [
                r for r in filtered
                if any(step.image_url for step in r.steps)
            ]
        if feedback and feedback in ("want", "favorite", "cooked"):
            if feedback_signals is None:
                feedback_signals = {}
            filtered = [
                r for r in filtered
                if feedback in feedback_signals.get(r.recipe_id, set())
            ]

        self._sort_library(filtered, sort or "name")

        total = len(filtered)
        offset = max(0, int(offset))
        limit = max(1, min(int(limit or 24), 60))
        page = filtered[offset : offset + limit]
        items = [
            self._summary(recipe, feedback_signals=feedback_signals)
            for recipe in page
        ]
        return (
            items,
            total,
            facets["category_counts"],
            facets["difficulty_counts"],
            facets["ingredient_facets"],
            facets["minutes_buckets"],
        )

    def _sort_library(self, recipes: list[ParsedRecipe], sort: str) -> None:
        if sort == "minutes":
            recipes.sort(key=lambda r: (float(r.total_minutes or 1e9), r.title))
        elif sort == "calories":
            def cal(r: ParsedRecipe) -> float:
                totals = (r.nutrition or {}).get("totals", {}) if r.nutrition else {}
                value = totals.get("calories") if isinstance(totals, dict) else None
                return float(value) if isinstance(value, (int, float)) and value else 1e9
            recipes.sort(key=cal)
        elif sort == "ingredients":
            recipes.sort(key=lambda r: (-len(r.ingredients), r.title))
        else:  # name
            recipes.sort(key=lambda r: r.title)

    async def _all_parsed(
        self, user_id: Optional[str], *, query: Optional[str] = None
    ) -> list[ParsedRecipe]:
        documents = await self.repository.list_documents(
            user_id, query=query, limit=1000
        )
        return [self._parse_document(document) for document in documents]

    def _library_facets(
        self, parsed: list[ParsedRecipe]
    ) -> dict[str, Any]:
        version = image_override_version()
        cached = self._library_cache.get(version)
        if cached and (time.time() - cached["ts"]) < self._LIBRARY_TTL:
            return cached
        category_counts: dict[str, int] = {}
        difficulty_counts: dict[str, int] = {}
        ingredient_counts: dict[str, int] = {}
        for recipe in parsed:
            cat = recipe.category or "未分类"
            category_counts[cat] = category_counts.get(cat, 0) + 1
            diff = recipe.difficulty or "未知"
            difficulty_counts[diff] = difficulty_counts.get(diff, 0) + 1
            for ingredient in recipe.ingredients:
                if ingredient.name:
                    ingredient_counts[ingredient.name] = (
                        ingredient_counts.get(ingredient.name, 0) + 1
                    )
        ingredient_facets = [
            {"value": name, "label": name, "count": count}
            for name, count in sorted(
                ingredient_counts.items(), key=lambda kv: (-kv[1], kv[0])
            )[:24]
        ]
        # Minutes distribution buckets for the sidebar mini chart.
        minutes_buckets = [
            {"value": "0-15", "label": "≤15 分钟", "count": 0},
            {"value": "16-30", "label": "16-30 分钟", "count": 0},
            {"value": "31-60", "label": "31-60 分钟", "count": 0},
            {"value": "60+", "label": ">60 分钟", "count": 0},
            {"value": "unknown", "label": "时间未知", "count": 0},
        ]
        for recipe in parsed:
            minutes = recipe.total_minutes
            if not minutes:
                minutes_buckets[4]["count"] += 1
            elif minutes <= 15:
                minutes_buckets[0]["count"] += 1
            elif minutes <= 30:
                minutes_buckets[1]["count"] += 1
            elif minutes <= 60:
                minutes_buckets[2]["count"] += 1
            else:
                minutes_buckets[3]["count"] += 1
        facets = {
            "category_counts": category_counts,
            "difficulty_counts": difficulty_counts,
            "ingredient_facets": ingredient_facets,
            "minutes_buckets": minutes_buckets,
            "ts": time.time(),
        }
        self._library_cache = {version: facets}
        return facets

    async def similar(
        self,
        recipe_id: str,
        user_id: Optional[str] = None,
        *,
        limit: int = 6,
    ) -> list[dict[str, Any]]:
        """Find recipes that share the most ingredients with the given one.

        Shared ingredients are weighted by inverse document frequency so that
        rare ingredients (e.g. lamb, oysters) matter more than universal
        staples (soy sauce, salt) when ranking similarity.
        """
        parsed = await self._all_parsed(user_id)
        target = next((r for r in parsed if r.recipe_id == recipe_id), None)
        if not target:
            return []
        target_ingredients = {ing.name for ing in target.ingredients if ing.name}
        if not target_ingredients:
            return []

        # IDF over the corpus.
        doc_freq: dict[str, int] = {}
        for recipe in parsed:
            for name in {ing.name for ing in recipe.ingredients if ing.name}:
                doc_freq[name] = doc_freq.get(name, 0) + 1
        import math
        n_docs = max(1, len(parsed))

        def idf(name: str) -> float:
            return math.log((n_docs + 1) / (doc_freq.get(name, 0) + 1)) + 1.0

        target_weight = sum(idf(name) for name in target_ingredients)
        scored: list[tuple[float, str, ParsedRecipe]] = []
        for recipe in parsed:
            if recipe.recipe_id == recipe_id:
                continue
            names = {ing.name for ing in recipe.ingredients if ing.name}
            if not names:
                continue
            overlap = target_ingredients & names
            if not overlap:
                continue
            overlap_weight = sum(idf(name) for name in overlap)
            other_weight = sum(idf(name) for name in names)
            # Soft Jaccard weighted by IDF.
            union_weight = target_weight + other_weight - overlap_weight
            score = overlap_weight / union_weight if union_weight else 0.0
            # Bonus for sharing the same category so e.g. fish dishes surface
            # other fish dishes even when the protein names differ.
            if target.category and recipe.category == target.category:
                score += 0.15
            scored.append((score, recipe.title, recipe))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [self._summary(recipe) for _, _, recipe in scored[:limit]]

    def _summary(
        self,
        recipe: ParsedRecipe,
        *,
        feedback_signals: Optional[dict[str, set[str]]] = None,
    ) -> dict[str, Any]:
        nutrition = recipe.nutrition or {}
        totals = nutrition.get("totals", {}) if isinstance(nutrition, dict) else {}
        calories = totals.get("calories") if isinstance(totals, dict) else None
        images_count = len(recipe.images)
        main_ingredients = [
            ing.name for ing in recipe.ingredients if ing.name
        ][:8]
        has_step_images = any(step.image_url for step in recipe.steps)
        signals = (feedback_signals or {}).get(recipe.recipe_id, set())
        return {
            "recipe_id": recipe.recipe_id,
            "title": recipe.title,
            "description": recipe.description,
            "category": recipe.category,
            "difficulty": recipe.difficulty,
            "total_minutes": recipe.total_minutes,
            "calories": round(calories) if isinstance(calories, (int, float)) and calories else None,
            "image_url": recipe.image_url,
            "images_count": images_count or (1 if recipe.image_url else 0),
            "ingredients_count": len(recipe.ingredients),
            "main_ingredients": main_ingredients,
            "has_step_images": has_step_images,
            "diet_tags": list(recipe.diet_tags)[:4],
            "allergens": list(recipe.allergens),
            "feedback": sorted(s for s in signals if s in ("want", "favorite", "cooked")),
        }

    def _parse_document(self, document: Any) -> ParsedRecipe:
        document_id = str(document.id)
        updated_at = str(getattr(document, "updated_at", "") or "")
        override_version = image_override_version()
        cached = self._cache.get(document_id)
        if (
            cached
            and cached[0] == updated_at
            and cached[1] == override_version
        ):
            return cached[2]

        recipe = parse_recipe_document(
            recipe_id=document_id,
            title=document.dish_name,
            content=document.content,
            category=document.category,
            difficulty=document.difficulty,
            source=document.source,
        )
        self._cache[document_id] = (updated_at, override_version, recipe)
        return recipe


recipe_service = RecipeService()
