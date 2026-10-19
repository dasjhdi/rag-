"""Feedback signals and recipe reviews."""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any, Iterable, Optional

from sqlalchemy import delete, select

from app.database.session import get_session_context
from app.diet.database.models import RecipeFeedbackModel, RecipeReviewModel

SIGNAL_SCORES = {
    "view": 1.0,
    "favorite": 8.0,
    "cooked": 10.0,
    "like": 6.0,
    "dislike": -12.0,
    "skip": -6.0,
}


def score_feedback_signals(signals: Iterable[str]) -> float:
    """Sum one user's recent signals for a recipe and clamp to [-30, 30]."""
    total = sum(SIGNAL_SCORES.get(str(signal), 0.0) for signal in signals or [])
    return max(-30.0, min(30.0, total))


def summarize_review_ratings(ratings: Iterable[int]) -> tuple[float, int]:
    """Return the rounded average rating and review count."""
    values = [int(value) for value in ratings or []]
    if not values:
        return 0.0, 0
    return round(sum(values) / len(values), 2), len(values)


class FeedbackService:
    async def add_feedback(
        self,
        user_id: str,
        recipe_id: str,
        signal: str,
        *,
        rating: Optional[float] = None,
        reason: Optional[str] = None,
    ) -> dict[str, Any]:
        if signal not in SIGNAL_SCORES:
            raise ValueError(f"不支持的反馈类型: {signal}")
        async with get_session_context() as session:
            record = RecipeFeedbackModel(
                user_id=str(user_id),
                recipe_id=str(recipe_id),
                signal=signal,
                rating=rating,
                reason=reason,
            )
            session.add(record)
            await session.flush()
            await session.refresh(record)
            return record.to_dict()

    async def scores(
        self, user_id: str, recipe_ids: Optional[list[str]] = None
    ) -> dict[str, float]:
        async with get_session_context() as session:
            stmt = (
                select(RecipeFeedbackModel)
                .where(RecipeFeedbackModel.user_id == str(user_id))
                .order_by(RecipeFeedbackModel.created_at.desc())
                .limit(2000)
            )
            records = list((await session.execute(stmt)).scalars().all())

        allowed = {str(item) for item in recipe_ids} if recipe_ids else None
        grouped: dict[str, list[RecipeFeedbackModel]] = defaultdict(list)
        for record in records:
            if allowed is not None and record.recipe_id not in allowed:
                continue
            if len(grouped[record.recipe_id]) < 20:
                grouped[record.recipe_id].append(record)

        return {
            recipe_id: score_feedback_signals(item.signal for item in values)
            for recipe_id, values in grouped.items()
        }

    async def upsert_review(
        self,
        user_id: str,
        recipe_id: str,
        rating: int,
        comment: Optional[str] = None,
    ) -> dict[str, Any]:
        if not 1 <= int(rating) <= 5:
            raise ValueError("评分必须在 1 到 5 之间")
        async with get_session_context() as session:
            stmt = select(RecipeReviewModel).where(
                RecipeReviewModel.user_id == str(user_id),
                RecipeReviewModel.recipe_id == str(recipe_id),
            )
            review = (await session.execute(stmt)).scalar_one_or_none()
            if review:
                review.rating = int(rating)
                review.comment = comment
            else:
                review = RecipeReviewModel(
                    user_id=str(user_id),
                    recipe_id=str(recipe_id),
                    rating=int(rating),
                    comment=comment,
                )
                session.add(review)
            await session.flush()
            await session.refresh(review)
            return review.to_dict()

    async def delete_review(self, user_id: str, recipe_id: str) -> bool:
        async with get_session_context() as session:
            stmt = delete(RecipeReviewModel).where(
                RecipeReviewModel.user_id == str(user_id),
                RecipeReviewModel.recipe_id == str(recipe_id),
            )
            result = await session.execute(stmt)
            return bool(result.rowcount)

    async def list_reviews(self, recipe_id: str) -> dict[str, Any]:
        async with get_session_context() as session:
            stmt = (
                select(RecipeReviewModel)
                .where(RecipeReviewModel.recipe_id == str(recipe_id))
                .order_by(RecipeReviewModel.updated_at.desc())
            )
            reviews = list((await session.execute(stmt)).scalars().all())
        average, count = summarize_review_ratings(
            review.rating for review in reviews
        )
        return {
            "recipe_id": str(recipe_id),
            "average_rating": average,
            "review_count": count,
            "reviews": [review.to_dict() for review in reviews],
        }


feedback_service = FeedbackService()
