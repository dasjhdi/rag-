"""Family member CRUD and merged household constraints."""

from __future__ import annotations

import uuid
from typing import Any, Iterable, Optional

from sqlalchemy import delete, select

from app.database.session import get_session_context
from app.diet.database.models import FamilyMemberModel


def merge_family_members(members: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Merge family members into hard constraints and household targets."""
    member_list = list(members or [])
    allergies: list[str] = []
    restrictions: list[str] = []
    avoided: list[str] = []
    calorie_total = 0
    servings = 0.0
    for member in member_list:
        for value in member.get("allergies") or []:
            if value not in allergies:
                allergies.append(value)
        for value in member.get("dietary_restrictions") or []:
            if value not in restrictions:
                restrictions.append(value)
        for value in member.get("disliked_foods") or []:
            if value not in avoided:
                avoided.append(value)
        calorie_total += int(member.get("calorie_goal") or 2000)
        servings += float(member.get("servings_factor") or 1.0)
    return {
        "allergies": allergies,
        "dietary_restrictions": restrictions,
        "avoided_foods": avoided,
        "calorie_goal": calorie_total or None,
        "household_size": max(1.0, servings),
        "family_member_count": len(member_list),
    }


class FamilyService:
    async def list_members(self, owner_user_id: str) -> list[dict[str, Any]]:
        async with get_session_context() as session:
            stmt = (
                select(FamilyMemberModel)
                .where(FamilyMemberModel.owner_user_id == str(owner_user_id))
                .order_by(FamilyMemberModel.created_at)
            )
            records = list((await session.execute(stmt)).scalars().all())
            return [record.to_dict() for record in records]

    async def create_member(self, owner_user_id: str, **kwargs: Any) -> dict[str, Any]:
        async with get_session_context() as session:
            record = FamilyMemberModel(
                owner_user_id=str(owner_user_id),
                name=str(kwargs.get("name") or "家庭成员"),
                relation=kwargs.get("relation"),
                birth_year=kwargs.get("birth_year"),
                sex=kwargs.get("sex"),
                allergies=list(kwargs.get("allergies") or []),
                dietary_restrictions=list(kwargs.get("dietary_restrictions") or []),
                disliked_foods=list(kwargs.get("disliked_foods") or []),
                calorie_goal=kwargs.get("calorie_goal"),
                servings_factor=float(kwargs.get("servings_factor") or 1.0),
                notes=kwargs.get("notes"),
            )
            session.add(record)
            await session.flush()
            await session.refresh(record)
            return record.to_dict()

    async def update_member(
        self, owner_user_id: str, member_id: str, **kwargs: Any
    ) -> Optional[dict[str, Any]]:
        try:
            member_uuid = uuid.UUID(str(member_id))
        except (ValueError, TypeError):
            return None
        async with get_session_context() as session:
            stmt = select(FamilyMemberModel).where(
                FamilyMemberModel.id == member_uuid,
                FamilyMemberModel.owner_user_id == str(owner_user_id),
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

    async def delete_member(self, owner_user_id: str, member_id: str) -> bool:
        try:
            member_uuid = uuid.UUID(str(member_id))
        except (ValueError, TypeError):
            return False
        async with get_session_context() as session:
            stmt = delete(FamilyMemberModel).where(
                FamilyMemberModel.id == member_uuid,
                FamilyMemberModel.owner_user_id == str(owner_user_id),
            )
            result = await session.execute(stmt)
            return bool(result.rowcount)

    async def merged_context(self, owner_user_id: str) -> dict[str, Any]:
        members = await self.list_members(owner_user_id)
        return merge_family_members(members)


family_service = FamilyService()
