"""Today view and adherence tests using pure aggregation."""

from datetime import date

from app.diet.execution.service import summarize_adherence

WEEK_START = date(2026, 10, 12)


def meal(meal_id, day, meal_type, status="planned"):
    return {
        "id": meal_id,
        "plan_date": day,
        "meal_type": meal_type,
        "dishes": [{"name": "测试菜"}],
        "status": status,
    }


def test_adherence_counts_eaten_skipped_and_missed():
    meals = [
        meal("m1", "2026-10-12", "breakfast", "eaten"),
        meal("m2", "2026-10-12", "lunch", "skipped"),
        meal("m3", "2026-10-13", "breakfast"),
        meal("m4", "2026-10-14", "breakfast"),
        meal("m5", "2026-10-14", "lunch"),
    ]
    logs = [
        {"plan_meal_id": "m4", "log_date": "2026-10-14", "meal_type": "breakfast"}
    ]
    summary = summarize_adherence(
        meals,
        logs,
        week_start_date=WEEK_START,
        today=date(2026, 10, 14),
    )
    assert summary["planned_meals"] == 5
    assert summary["eaten_meals"] == 2
    assert summary["skipped_meals"] == 1
    assert summary["missed_meals"] == 1
    assert summary["execution_rate"] == 0.4
    statuses = {item["id"]: item["effective_status"] for item in summary["meals"]}
    assert statuses["m4"] == "eaten"
    assert statuses["m5"] == "planned"


def test_log_date_and_meal_type_also_marks_meal_eaten():
    meals = [meal("m1", "2026-10-14", "lunch")]
    logs = [{"log_date": "2026-10-14", "meal_type": "lunch"}]
    summary = summarize_adherence(
        meals, logs, week_start_date=WEEK_START, today=date(2026, 10, 14)
    )
    assert summary["eaten_meals"] == 1
    assert summary["meals"][0]["effective_status"] == "eaten"


def test_no_plan_returns_explicit_empty_state():
    summary = summarize_adherence(
        [], [], week_start_date=WEEK_START, today=date(2026, 10, 14)
    )
    assert summary["planned_meals"] == 0
    assert summary["execution_rate"] == 0.0
    assert "还没有计划" in summary["suggestion"]


def test_streak_counts_consecutive_completed_days():
    meals = [
        meal("m1", "2026-10-12", "breakfast", "eaten"),
        meal("m2", "2026-10-12", "lunch", "eaten"),
        meal("m3", "2026-10-13", "breakfast", "eaten"),
        meal("m4", "2026-10-13", "lunch", "skipped"),
    ]
    summary = summarize_adherence(
        meals, [], week_start_date=WEEK_START, today=date(2026, 10, 13)
    )
    assert summary["streak_days"] == 2


def test_meals_are_sorted_by_date_and_meal_order():
    meals = [
        meal("dinner", "2026-10-12", "dinner"),
        meal("breakfast", "2026-10-12", "breakfast"),
        meal("lunch", "2026-10-12", "lunch"),
    ]
    summary = summarize_adherence(
        meals, [], week_start_date=WEEK_START, today=date(2026, 10, 12)
    )
    assert [item["id"] for item in summary["meals"]] == [
        "breakfast",
        "lunch",
        "dinner",
    ]
