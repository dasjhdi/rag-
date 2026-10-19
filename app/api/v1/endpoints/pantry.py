"""Pantry inventory, shopping list and cookable recipe endpoints."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.diet.pantry.service import pantry_service

router = APIRouter()


def get_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="需要登录")
    return str(user_id)


class PantryItemRequest(BaseModel):
    name: Optional[str] = None
    quantity: Optional[float] = Field(None, ge=0)
    unit: Optional[str] = None
    category: Optional[str] = None
    expires_on: Optional[date] = None
    location: Optional[str] = None
    notes: Optional[str] = None


class ShoppingListGenerateRequest(BaseModel):
    week_start_date: Optional[date] = None


class ShoppingItemUpdateRequest(BaseModel):
    quantity: Optional[float] = Field(None, ge=0)
    unit: Optional[str] = None
    checked: Optional[bool] = None
    category: Optional[str] = None


def _default_week_start(target: Optional[date] = None) -> date:
    current = target or date.today()
    return current - timedelta(days=current.weekday())


@router.get("/pantry/items")
async def list_pantry_items(request: Request) -> Dict[str, Any]:
    user_id = get_user_id(request)
    items = await pantry_service.list_items(user_id)
    return {"items": items, "count": len(items)}


@router.post("/pantry/items", status_code=201)
async def add_pantry_item(
    payload: PantryItemRequest, request: Request
) -> Dict[str, Any]:
    user_id = get_user_id(request)
    if not payload.name:
        raise HTTPException(status_code=422, detail="name 参数是必需的")
    return await pantry_service.add_item(
        user_id, **payload.model_dump(exclude_unset=True)
    )


@router.patch("/pantry/items/{item_id}")
async def update_pantry_item(
    item_id: str, payload: PantryItemRequest, request: Request
) -> Dict[str, Any]:
    user_id = get_user_id(request)
    item = await pantry_service.update_item(
        user_id, item_id, **payload.model_dump(exclude_unset=True)
    )
    if not item:
        raise HTTPException(status_code=404, detail="库存项不存在或无权访问")
    return item


@router.delete("/pantry/items/{item_id}")
async def delete_pantry_item(item_id: str, request: Request) -> Dict[str, str]:
    user_id = get_user_id(request)
    deleted = await pantry_service.delete_item(user_id, item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="库存项不存在或无权访问")
    return {"message": "库存项已删除"}


@router.get("/pantry/expiring")
async def list_expiring_items(
    request: Request,
    days: int = Query(3, ge=0, le=30),
) -> Dict[str, Any]:
    user_id = get_user_id(request)
    items = await pantry_service.expiring(user_id, days)
    return {"items": items, "count": len(items), "days": days}


@router.post("/pantry/shopping-list/generate")
async def generate_shopping_list(
    payload: ShoppingListGenerateRequest, request: Request
) -> Dict[str, Any]:
    user_id = get_user_id(request)
    week_start = payload.week_start_date or _default_week_start()
    return await pantry_service.generate_shopping_list(user_id, week_start)


@router.get("/pantry/shopping-list")
async def get_shopping_list(
    request: Request,
    week_start_date: Optional[date] = Query(None),
) -> Dict[str, Any]:
    user_id = get_user_id(request)
    week_start = week_start_date or _default_week_start()
    items = await pantry_service.list_shopping(user_id, week_start)
    return {
        "week_start_date": week_start.isoformat(),
        "items": items,
        "count": len(items),
    }


@router.patch("/pantry/shopping-list/{item_id}")
async def update_shopping_item(
    item_id: str, payload: ShoppingItemUpdateRequest, request: Request
) -> Dict[str, Any]:
    user_id = get_user_id(request)
    item = await pantry_service.update_shopping_item(
        user_id, item_id, **payload.model_dump(exclude_unset=True)
    )
    if not item:
        raise HTTPException(status_code=404, detail="购物清单项不存在或无权访问")
    return item


@router.get("/pantry/cookable")
async def list_cookable_recipes(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
) -> Dict[str, Any]:
    user_id = get_user_id(request)
    items = await pantry_service.cookable(user_id, limit)
    return {"items": items, "count": len(items)}
