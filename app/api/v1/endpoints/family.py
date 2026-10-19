"""Family member profile endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.diet.family.service import family_service

router = APIRouter()


def get_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="需要登录")
    return str(user_id)


class FamilyMemberRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    relation: Optional[str] = Field(None, max_length=50)
    birth_year: Optional[int] = Field(None, ge=1900, le=2100)
    sex: Optional[str] = None
    allergies: Optional[List[str]] = None
    dietary_restrictions: Optional[List[str]] = None
    disliked_foods: Optional[List[str]] = None
    calorie_goal: Optional[int] = Field(None, ge=500, le=10000)
    servings_factor: Optional[float] = Field(None, gt=0, le=10)
    notes: Optional[str] = None


@router.get("/family/members")
async def list_members(request: Request) -> Dict[str, Any]:
    owner_user_id = get_user_id(request)
    members = await family_service.list_members(owner_user_id)
    return {
        "members": members,
        "count": len(members),
        "merged": await family_service.merged_context(owner_user_id),
    }


@router.post("/family/members", status_code=201)
async def create_member(
    payload: FamilyMemberRequest, request: Request
) -> Dict[str, Any]:
    owner_user_id = get_user_id(request)
    if not payload.name:
        raise HTTPException(status_code=422, detail="name 参数是必需的")
    return await family_service.create_member(
        owner_user_id, **payload.model_dump(exclude_unset=True)
    )


@router.patch("/family/members/{member_id}")
async def update_member(
    member_id: str, payload: FamilyMemberRequest, request: Request
) -> Dict[str, Any]:
    owner_user_id = get_user_id(request)
    member = await family_service.update_member(
        owner_user_id, member_id, **payload.model_dump(exclude_unset=True)
    )
    if not member:
        raise HTTPException(status_code=404, detail="家庭成员不存在或无权访问")
    return member


@router.delete("/family/members/{member_id}")
async def delete_member(member_id: str, request: Request) -> Dict[str, str]:
    owner_user_id = get_user_id(request)
    deleted = await family_service.delete_member(owner_user_id, member_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="家庭成员不存在或无权访问")
    return {"message": "家庭成员已删除"}
