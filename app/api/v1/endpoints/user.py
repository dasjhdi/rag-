"""
User profile endpoints: get current user and update profile.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.services.auth_service import auth_service
from app.services.user_service import user_service

router = APIRouter()
logger = logging.getLogger(__name__)


class UserProfile(BaseModel):
    username: str
    occupation: Optional[str] = None
    bio: Optional[str] = None
    profile: Optional[str] = None
    user_instruction: Optional[str] = None


class UpdateProfileRequest(BaseModel):
    username: Optional[str] = None
    occupation: Optional[str] = None
    bio: Optional[str] = None
    profile: Optional[str] = None
    user_instruction: Optional[str] = None


def _get_identity_from_auth(request: Request) -> dict:
    """身份由鉴权网关写入 request.state；此处只做存在性校验。

    网关已同时支持 Bearer 头与 HttpOnly Cookie，端点不再自行解析请求头，
    否则 Cookie 会话在这些端点上会失效。
    """
    username = getattr(request.state, "username", None)
    user_id = getattr(request.state, "user_id", None)
    if not username or not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="需要登录"
        )
    return {"username": username, "user_id": user_id}


@router.get("/user/profile", response_model=UserProfile)
async def get_profile(identity: dict = Depends(_get_identity_from_auth)):
    user = await user_service.get_user_by_username(identity["username"])
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserProfile(
        username=user.username,
        occupation=user.occupation,
        bio=user.bio,
        profile=user.profile,
        user_instruction=user.user_instruction
    )


@router.put("/user/profile", response_model=UserProfile)
async def update_profile(req: UpdateProfileRequest, identity: dict = Depends(_get_identity_from_auth)):
    try:
        user = await user_service.update_profile(identity["username"], req.dict(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return UserProfile(
        username=user.username,
        occupation=user.occupation,
        bio=user.bio,
        profile=user.profile,
        user_instruction=user.user_instruction
    )
