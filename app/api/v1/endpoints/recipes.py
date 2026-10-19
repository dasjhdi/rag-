"""Structured recipe, feedback and review endpoints."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.diet.feedback.service import feedback_service
from app.diet.recipes.service import recipe_service

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
