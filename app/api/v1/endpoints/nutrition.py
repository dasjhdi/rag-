"""Local nutrition lookup and kitchen unit conversion endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.diet.nutrition.service import (
    convert_quantity,
    estimate_nutrition,
    search_foods,
)

router = APIRouter()


class ConvertRequest(BaseModel):
    quantity: Optional[float] = None
    unit: str = Field(..., description="克、千克、个、杯、毫升等")
    food_name: str = Field("", description="食物名称，用于计件换算")


class EstimateItem(BaseModel):
    food_name: str = Field(..., min_length=1)
    quantity: Optional[float] = None
    unit: Optional[str] = None
    weight_g: Optional[float] = None


class EstimateRequest(BaseModel):
    items: List[EstimateItem] = Field(..., min_length=1)


@router.get("/nutrition/foods")
async def list_foods(
    q: str = Query("", description="食物名称或别名"),
    limit: int = Query(20, ge=1, le=100),
) -> Dict[str, Any]:
    items = search_foods(q, limit)
    return {"items": items, "count": len(items)}


@router.post("/nutrition/convert")
async def convert_unit(payload: ConvertRequest) -> Dict[str, Any]:
    return convert_quantity(payload.quantity, payload.unit, payload.food_name)


@router.post("/nutrition/estimate")
async def estimate(payload: EstimateRequest) -> Dict[str, Any]:
    return estimate_nutrition([item.model_dump() for item in payload.items])
