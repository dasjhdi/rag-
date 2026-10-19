"""Community review constraints and summary tests."""

import pytest
from pydantic import ValidationError

from app.api.v1.endpoints.recipes import ReviewRequest
from app.diet.database.models import RecipeReviewModel
from app.diet.feedback.service import summarize_review_ratings


def test_review_unique_per_user_and_recipe():
    indexes = {
        index.name: index for index in RecipeReviewModel.__table__.indexes
    }
    unique_index = indexes["ix_review_user_recipe"]
    assert unique_index.unique is True
    assert [column.name for column in unique_index.columns] == [
        "user_id",
        "recipe_id",
    ]


def test_review_request_rejects_out_of_range_rating():
    with pytest.raises(ValidationError):
        ReviewRequest(rating=0)
    with pytest.raises(ValidationError):
        ReviewRequest(rating=6)
    assert ReviewRequest(rating=5, comment="好吃").rating == 5


def test_review_average_is_rounded():
    average, count = summarize_review_ratings([5, 4, 4])
    assert average == 4.33
    assert count == 3


def test_review_comment_length_is_bounded():
    with pytest.raises(ValidationError):
        ReviewRequest(rating=5, comment="x" * 2001)
