"""Database access for structured recipe sources."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import or_, select

from app.database.models import KnowledgeDocumentModel
from app.database.session import get_session_context


class RecipeRepository:
    async def get_document(
        self, recipe_id: str, user_id: Optional[str] = None
    ) -> Optional[KnowledgeDocumentModel]:
        try:
            document_id = uuid.UUID(str(recipe_id))
        except (ValueError, TypeError):
            return None

        async with get_session_context() as session:
            stmt = select(KnowledgeDocumentModel).where(
                KnowledgeDocumentModel.id == document_id
            )
            document = (await session.execute(stmt)).scalar_one_or_none()
            if not document:
                return None
            if document.user_id is None:
                return document
            if user_id and str(document.user_id) == str(user_id):
                return document
            return None

    async def list_documents(
        self,
        user_id: Optional[str] = None,
        *,
        query: Optional[str] = None,
        limit: int = 500,
    ) -> list[KnowledgeDocumentModel]:
        limit = max(1, min(int(limit or 500), 1000))
        async with get_session_context() as session:
            conditions = [
                KnowledgeDocumentModel.source_type.in_(("recipes", "recipe")),
                KnowledgeDocumentModel.is_dish_index.is_(False),
            ]
            ownership = [KnowledgeDocumentModel.user_id.is_(None)]
            if user_id:
                try:
                    ownership.append(
                        KnowledgeDocumentModel.user_id == uuid.UUID(str(user_id))
                    )
                except (ValueError, TypeError):
                    pass
            conditions.append(or_(*ownership))
            if query:
                pattern = f"%{query.strip()}%"
                conditions.append(
                    or_(
                        KnowledgeDocumentModel.dish_name.ilike(pattern),
                        KnowledgeDocumentModel.content.ilike(pattern),
                    )
                )

            stmt = (
                select(KnowledgeDocumentModel)
                .where(*conditions)
                .order_by(KnowledgeDocumentModel.dish_name)
                .limit(limit)
            )
            return list((await session.execute(stmt)).scalars().all())


recipe_repository = RecipeRepository()
