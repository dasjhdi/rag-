"""Recommendation feedback scoring and review validation tests."""

import pytest

from app.diet.feedback.service import (
    SIGNAL_SCORES,
    FeedbackService,
    score_feedback_signals,
    summarize_review_ratings,
)


def test_signal_scores_match_product_rules():
    assert SIGNAL_SCORES["favorite"] == 8.0
    assert SIGNAL_SCORES["cooked"] == 10.0
    assert SIGNAL_SCORES["dislike"] == -12.0
    assert SIGNAL_SCORES["skip"] == -6.0


def test_positive_and_negative_signals_change_score():
    assert score_feedback_signals(["like"]) == 6.0
    assert score_feedback_signals(["dislike"]) == -12.0
    assert score_feedback_signals(["favorite", "cooked"]) == 18.0
    assert score_feedback_signals([]) == 0.0


def test_feedback_score_is_clamped():
    assert score_feedback_signals(["cooked"] * 10) == 30.0
    assert score_feedback_signals(["dislike"] * 10) == -30.0


def test_unknown_signal_is_ignored():
    assert score_feedback_signals(["unknown", "view"]) == 1.0


async def test_add_feedback_rejects_unknown_signal_before_db():
    service = FeedbackService()
    with pytest.raises(ValueError, match="不支持的反馈类型"):
        await service.add_feedback("user-1", "recipe-1", "angry")


async def test_upsert_review_rejects_out_of_range_rating_before_db():
    service = FeedbackService()
    with pytest.raises(ValueError, match="评分"):
        await service.upsert_review("user-1", "recipe-1", 6)


def test_review_summary_average_and_count():
    average, count = summarize_review_ratings([5, 4, 3])
    assert average == 4.0
    assert count == 3
    assert summarize_review_ratings([]) == (0.0, 0)
