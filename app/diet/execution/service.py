"""Today view, adherence and weekly review."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable, Optional

from app.diet.database.repository import DietRepository, diet_repository
from app.diet.service import get_week_start_date

MEAL_ORDER = {"breakfast": 0, "lunch": 1, "dinner": 2, "snack": 3}


def summarize_adherence(
    meals: Iterable[dict[str, Any]],
    logs: Iterable[dict[str, Any]],
    *,
    week_start_date: date,
    today: Optional[date] = None,
) -> dict[str, Any]:
    meal_list = list(meals or [])
    log_list = list(logs or [])
    today = today or date.today()

    logged_meal_ids = {
        str(item.get("plan_meal_id"))
        for item in log_list
        if item.get("plan_meal_id")
    }
    logged_keys = {
        (str(item.get("log_date")), str(item.get("meal_type"))) for item in log_list
    }

    planned = len(meal_list)
    eaten = 0
    skipped = 0
    missed = 0
    details: list[dict[str, Any]] = []
    for meal in meal_list:
        status = str(meal.get("status") or "planned")
        meal_id = str(meal.get("id") or "")
        key = (str(meal.get("plan_date")), str(meal.get("meal_type")))
        if status == "eaten" or meal_id in logged_meal_ids or key in logged_keys:
            status = "eaten"
            eaten += 1
        elif status == "skipped":
            skipped += 1
        elif str(meal.get("plan_date")) < today.isoformat():
            missed += 1
        details.append({**meal, "effective_status": status})

    denominator = max(planned, 1)
    execution_rate = round(eaten / denominator, 3) if planned else 0.0
    completed = [
        day
        for day in (week_start_date + timedelta(days=index) for index in range(7))
        if day <= today
    ]
    streak = 0
    for day in reversed(completed):
        day_meals = [meal for meal in meal_list if meal.get("plan_date") == day.isoformat()]
        if not day_meals:
            break
        day_eaten = [
            meal
            for meal in details
            if meal.get("plan_date") == day.isoformat()
            and meal.get("effective_status") in {"eaten", "skipped"}
        ]
        if len(day_eaten) == len(day_meals):
            streak += 1
        else:
            break

    suggestion = "本周执行稳定，可以保持当前计划。"
    if planned == 0:
        suggestion = "本周还没有计划，先生成一周计划再开始执行。"
    elif execution_rate < 0.5:
        suggestion = "执行率偏低，建议减少计划餐次或选择更快的菜谱。"
    elif missed:
        suggestion = f"有 {missed} 个历史餐次未记录，可以补记或顺延到下周。"

    return {
        "week_start_date": week_start_date.isoformat(),
        "planned_meals": planned,
        "eaten_meals": eaten,
        "skipped_meals": skipped,
        "missed_meals": missed,
        "execution_rate": execution_rate,
        "streak_days": streak,
        "meals": sorted(
            details,
            key=lambda item: (item.get("plan_date") or "", MEAL_ORDER.get(item.get("meal_type"), 9)),
        ),
        "suggestion": suggestion,
    }


class ExecutionService:
    def __init__(self, repository: Optional[DietRepository] = None) -> None:
        self.repository = repository or diet_repository

    async def today(self, user_id: str, target_date: Optional[date] = None) -> dict[str, Any]:
        target = target_date or date.today()
        week_start = get_week_start_date(target)
        meals = await self.repository.get_plan_meals_by_week(user_id, week_start)
        day_meals = [meal.to_dict() for meal in meals if meal.plan_date == target]
        items = await self.repository.get_log_items_by_date(user_id, target)
        logs = [item.to_dict() for item in items]
        summary = summarize_adherence(
            day_meals, logs, week_start_date=week_start, today=target
        )
        next_meal = next(
            (
                meal
                for meal in summary["meals"]
                if meal.get("effective_status") == "planned"
            ),
            None,
        )
        return {
            "date": target.isoformat(),
            "has_plan": bool(day_meals),
            "meals": summary["meals"],
            "next_meal": next_meal,
            "eaten_meals": summary["eaten_meals"],
            "skipped_meals": summary["skipped_meals"],
        }

    async def adherence(
        self, user_id: str, week_start_date: Optional[date] = None
    ) -> dict[str, Any]:
        week_start = week_start_date or get_week_start_date(date.today())
        meals = await self.repository.get_plan_meals_by_week(user_id, week_start)
        end = week_start + timedelta(days=6)
        items = await self.repository.get_log_items_by_date_range(user_id, week_start, end)
        return summarize_adherence(
            [meal.to_dict() for meal in meals],
            [item.to_dict() for item in items],
            week_start_date=week_start,
            today=date.today(),
        )


execution_service = ExecutionService()
