"""Structured recipe, feedback and review endpoints."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.diet.feedback.service import feedback_service
from app.diet.recipes.importer import RecipeImportError, recipe_import_service
from app.diet.recipes.service import recipe_service

logger = logging.getLogger(__name__)
router = APIRouter()


def get_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="需要登录")
    return str(user_id)


class FeedbackRequest(BaseModel):
    signal: str = Field(..., description="view/favorite/cooked/like/dislike/skip")
    rating: Optional[float] = Field(None, ge=1, le=5)
    reason: Optional[str] = None


class ReviewRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=2000)


class RecipeImportUrlRequest(BaseModel):
    url: str = Field(..., min_length=8, max_length=2048)


class RecipeImportImageRequest(BaseModel):
    image_base64: str = Field(..., min_length=32, max_length=16 * 1024 * 1024)
    mime_type: str = Field("image/jpeg", max_length=64)
    filename: Optional[str] = Field(None, max_length=255)


@router.get("/recipes/search")
async def search_recipes(
    request: Request,
    q: Optional[str] = Query(None, description="搜索关键词"),
    category: Optional[str] = Query(None),
    diet_tag: Optional[str] = Query(None),
    exclude_allergens: Optional[str] = Query(
        None, description="排除的过敏原或食材，逗号分隔"
    ),
    max_minutes: Optional[float] = Query(None, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> Dict[str, Any]:
    user_id = get_user_id(request)
    excluded = [
        item.strip()
        for item in (exclude_allergens or "").split(",")
        if item.strip()
    ]
    items = await recipe_service.search(
        user_id,
        query=q,
        category=category,
        diet_tag=diet_tag,
        exclude_allergens=excluded,
        max_minutes=max_minutes,
        limit=limit,
    )
    return {"items": items, "count": len(items)}


@router.get("/recipes/recommendations")
async def recommend_recipes(
    request: Request,
    limit: int = Query(10, ge=1, le=50),
) -> Dict[str, Any]:
    user_id = get_user_id(request)
    recipes = await recipe_service.candidates(user_id)
    scores = await feedback_service.scores(
        user_id, [recipe.recipe_id for recipe in recipes]
    )
    ranked = sorted(
        recipes,
        key=lambda recipe: (
            -float(scores.get(recipe.recipe_id, 0.0)),
            -float((recipe.nutrition or {}).get("coverage", 0) or 0),
            float(recipe.total_minutes or 9999),
            recipe.title,
        ),
    )
    items = [recipe.to_dict() for recipe in ranked[:limit]]
    return {"items": items, "count": len(items)}


@router.get("/recipes/library")
async def recipe_library(
    request: Request,
    category: Optional[str] = Query(None, description="按分类筛选"),
    difficulty: Optional[str] = Query(None, description="按难度筛选"),
    ingredient: Optional[str] = Query(None, description="按主食材筛选"),
    feedback: Optional[str] = Query(
        None, description="按用户反馈筛选：want/favorite/cooked"
    ),
    sort: Optional[str] = Query(
        None, description="排序：name/minutes/calories/ingredients"
    ),
    has_step_images: Optional[bool] = Query(
        None, description="仅看有步骤图的菜谱"
    ),
    q: Optional[str] = Query(None, description="关键词（菜名/正文）"),
    offset: int = Query(0, ge=0, description="分页偏移"),
    limit: int = Query(24, ge=1, le=60, description="每页数量"),
) -> Dict[str, Any]:
    """Browse all recipes with pagination, facet counts and rich filters."""
    user_id = get_user_id(request)
    feedback_signals: Optional[dict[str, set[str]]] = None
    if feedback:
        feedback_signals = await feedback_service.user_signals(user_id)
    items, total, category_counts, difficulty_counts, ingredient_facets, minutes_buckets = (
        await recipe_service.library(
            user_id,
            category=category,
            difficulty=difficulty,
            ingredient=ingredient,
            feedback=feedback,
            sort=sort,
            has_step_images=has_step_images,
            query=q,
            offset=offset,
            limit=limit,
            feedback_signals=feedback_signals,
        )
    )
    return {
        "items": items,
        "total": total,
        "offset": offset,
        "limit": limit,
        "categories": [
            {"value": key, "label": key, "count": value}
            for key, value in sorted(category_counts.items())
        ],
        "difficulties": [
            {"value": key, "label": key, "count": value}
            for key, value in sorted(difficulty_counts.items())
        ],
        "ingredients": ingredient_facets,
        "minutes_buckets": minutes_buckets,
    }


@router.post("/recipes/import/url", status_code=201)
async def import_recipe_from_url(
    payload: RecipeImportUrlRequest, request: Request
) -> Dict[str, Any]:
    """Fetch a public recipe page and save it as a personal recipe."""
    user_id = get_user_id(request)
    try:
        return await recipe_import_service.import_from_url(user_id, payload.url)
    except RecipeImportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Recipe URL import failed: %s", exc)
        raise HTTPException(status_code=500, detail="导入失败，请稍后重试") from exc


@router.post("/recipes/import/image", status_code=201)
async def import_recipe_from_image(
    payload: RecipeImportImageRequest, request: Request
) -> Dict[str, Any]:
    """Extract a recipe from a photo and save it as a personal recipe."""
    user_id = get_user_id(request)
    try:
        return await recipe_import_service.import_from_image(
            user_id,
            payload.image_base64,
            mime_type=payload.mime_type,
            filename=payload.filename or "",
        )
    except RecipeImportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Recipe image import failed: %s", exc)
        raise HTTPException(status_code=500, detail="图片识别失败，请稍后重试") from exc


@router.get("/recipes/{recipe_id}/similar")
async def similar_recipes(
    recipe_id: str,
    request: Request,
    limit: int = Query(6, ge=1, le=12),
) -> Dict[str, Any]:
    """Return recipes that share the most ingredients with the given one."""
    get_user_id(request)
    items = await recipe_service.similar(recipe_id, limit=limit)
    return {"items": items, "count": len(items)}


@router.get("/recipes/{recipe_id}")
async def get_recipe(
    recipe_id: str,
    request: Request,
    servings: Optional[float] = Query(None, gt=0),
    unit_system: str = Query("metric", pattern="^(metric|imperial)$"),
) -> Dict[str, Any]:
    user_id = get_user_id(request)
    recipe = await recipe_service.get_recipe(
        recipe_id, user_id, servings=servings, unit_system=unit_system
    )
    if not recipe:
        raise HTTPException(status_code=404, detail="菜谱不存在或无权访问")
    return recipe


@router.post("/recipes/{recipe_id}/feedback")
async def add_recipe_feedback(
    recipe_id: str, payload: FeedbackRequest, request: Request
) -> Dict[str, Any]:
    user_id = get_user_id(request)
    try:
        record = await feedback_service.add_feedback(
            user_id,
            recipe_id,
            payload.signal,
            rating=payload.rating,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"feedback": record}


@router.get("/recipes/{recipe_id}/reviews")
async def list_recipe_reviews(recipe_id: str, request: Request) -> Dict[str, Any]:
    get_user_id(request)
    return await feedback_service.list_reviews(recipe_id)


@router.put("/recipes/{recipe_id}/review")
async def upsert_recipe_review(
    recipe_id: str, payload: ReviewRequest, request: Request
) -> Dict[str, Any]:
    user_id = get_user_id(request)
    try:
        review = await feedback_service.upsert_review(
            user_id, recipe_id, payload.rating, payload.comment
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"review": review}


@router.delete("/recipes/{recipe_id}/review")
async def delete_recipe_review(recipe_id: str, request: Request) -> Dict[str, Any]:
    user_id = get_user_id(request)
    deleted = await feedback_service.delete_review(user_id, recipe_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="评价不存在")
    return {"message": "评价已删除"}
