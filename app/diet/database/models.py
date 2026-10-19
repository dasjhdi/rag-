"""
饮食模块数据库模型

包含饮食计划目标、计划餐次、记录食品项和用户偏好数据模型。
"""

import uuid
from datetime import datetime, date
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models import Base


class MealType(str, Enum):
    """餐次类型"""

    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"


class DayOfWeek(int, Enum):
    """星期几 (0=周一, 6=周日)"""

    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6


class DataSource(str, Enum):
    """数据来源"""

    MANUAL = "manual"
    AI_TEXT = "ai_text"
    AI_IMAGE = "ai_image"


class DietPlanMealModel(Base):
    """计划中的一餐"""

    __tablename__ = "diet_plan_meals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    plan_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    meal_type: Mapped[str] = mapped_column(String(20), nullable=False)
    dishes: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    total_calories: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_protein: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_fat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_carbs: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="planned", nullable=False
    )
    locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    generation_batch_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    servings: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_diet_plan_meals_user_date", "user_id", "plan_date"),
        Index(
            "ix_diet_plan_meals_user_date_meal",
            "user_id",
            "plan_date",
            "meal_type",
        ),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "plan_date": self.plan_date.isoformat(),
            "meal_type": self.meal_type,
            "dishes": self.dishes or [],
            "total_calories": self.total_calories,
            "total_protein": self.total_protein,
            "total_fat": self.total_fat,
            "total_carbs": self.total_carbs,
            "notes": self.notes,
            "status": self.status,
            "locked": self.locked,
            "generation_batch_id": self.generation_batch_id,
            "servings": self.servings,
        }


class DietLogItemModel(Base):
    """饮食记录中的食品项"""

    __tablename__ = "diet_log_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    log_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    log_date: Mapped[date] = mapped_column(Date, nullable=False)
    meal_type: Mapped[str] = mapped_column(String(20), nullable=False)
    plan_meal_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("diet_plan_meals.id", ondelete="SET NULL"),
        nullable=True,
    )
    food_name: Mapped[str] = mapped_column(String(255), nullable=False)
    weight_g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    calories: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    protein: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    carbs: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(
        String(20), default=DataSource.MANUAL.value, nullable=False
    )
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    nutrition_source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    nutrition_confidence: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_diet_log_items_user_date", "user_id", "log_date"),
        Index("ix_diet_log_items_user_date_meal", "user_id", "log_date", "meal_type"),
        Index("ix_diet_log_items_log_id", "log_id"),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "log_id": str(self.log_id),
            "user_id": self.user_id,
            "log_date": self.log_date.isoformat(),
            "meal_type": self.meal_type,
            "plan_meal_id": str(self.plan_meal_id) if self.plan_meal_id else None,
            "food_name": self.food_name,
            "weight_g": self.weight_g,
            "unit": self.unit,
            "calories": self.calories,
            "protein": self.protein,
            "fat": self.fat,
            "carbs": self.carbs,
            "source": self.source,
            "confidence_score": self.confidence_score,
            "nutrition_source": self.nutrition_source,
            "nutrition_confidence": self.nutrition_confidence,
            "created_at": self.created_at.isoformat(),
        }


class UserFoodPreferenceModel(Base):
    """用户饮食偏好（个性化学习结果）"""

    __tablename__ = "user_food_preferences"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    common_foods: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    avoided_foods: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    diet_tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    allergies: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    allergy_severity: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    dietary_restrictions: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    favorite_cuisines: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    preferred_foods: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    health_conditions: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    avg_daily_calories_min: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    avg_daily_calories_max: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    calorie_goal: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    protein_goal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fat_goal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    carbs_goal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fiber_goal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sodium_goal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    meals_per_day: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    cooking_skill: Mapped[str] = mapped_column(
        String(20), default="intermediate", nullable=False
    )
    max_cook_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    budget_level: Mapped[str] = mapped_column(
        String(20), default="medium", nullable=False
    )
    household_size: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit_system: Mapped[str] = mapped_column(
        String(20), default="metric", nullable=False
    )
    spice_level: Mapped[str] = mapped_column(
        String(20), default="medium", nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    deviation_patterns: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    stats: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "user_id": self.user_id,
            "common_foods": self.common_foods or [],
            "avoided_foods": self.avoided_foods or [],
            "diet_tags": self.diet_tags or [],
            "allergies": self.allergies or [],
            "allergy_severity": self.allergy_severity or {},
            "dietary_restrictions": self.dietary_restrictions or [],
            "favorite_cuisines": self.favorite_cuisines or [],
            "preferred_foods": self.preferred_foods or [],
            "health_conditions": self.health_conditions or [],
            "avg_daily_calories_min": self.avg_daily_calories_min,
            "avg_daily_calories_max": self.avg_daily_calories_max,
            "calorie_goal": self.calorie_goal,
            "protein_goal": self.protein_goal,
            "fat_goal": self.fat_goal,
            "carbs_goal": self.carbs_goal,
            "fiber_goal": self.fiber_goal,
            "sodium_goal": self.sodium_goal,
            "meals_per_day": self.meals_per_day,
            "cooking_skill": self.cooking_skill,
            "max_cook_minutes": self.max_cook_minutes,
            "budget_level": self.budget_level,
            "household_size": self.household_size,
            "unit_system": self.unit_system,
            "spice_level": self.spice_level,
            "version": self.version,
            "deviation_patterns": self.deviation_patterns or [],
            "stats": self.stats or {},
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class PantryItemModel(Base):
    """用户食材库存。"""

    __tablename__ = "pantry_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    quantity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    unit: Mapped[str] = mapped_column(String(50), default="g", nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    expires_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_pantry_user_name", "user_id", "normalized_name"),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "user_id": self.user_id,
            "name": self.name,
            "normalized_name": self.normalized_name,
            "quantity": self.quantity,
            "unit": self.unit,
            "category": self.category,
            "expires_on": self.expires_on.isoformat() if self.expires_on else None,
            "location": self.location,
            "notes": self.notes,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class ShoppingListItemModel(Base):
    """按周生成的购物清单项。"""

    __tablename__ = "shopping_list_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    week_start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    unit: Mapped[str] = mapped_column(String(50), default="g", nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    checked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source: Mapped[str] = mapped_column(String(50), default="plan", nullable=False)
    recipe_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_shopping_user_week", "user_id", "week_start_date"),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "user_id": self.user_id,
            "week_start_date": self.week_start_date.isoformat(),
            "name": self.name,
            "normalized_name": self.normalized_name,
            "quantity": self.quantity,
            "unit": self.unit,
            "category": self.category,
            "checked": self.checked,
            "source": self.source,
            "recipe_ids": self.recipe_ids or [],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class RecipeFeedbackModel(Base):
    """菜谱反馈事件。"""

    __tablename__ = "recipe_feedback"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    recipe_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    signal: Mapped[str] = mapped_column(String(20), nullable=False)
    rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_feedback_user_recipe", "user_id", "recipe_id"),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "user_id": self.user_id,
            "recipe_id": self.recipe_id,
            "signal": self.signal,
            "rating": self.rating,
            "reason": self.reason,
            "created_at": self.created_at.isoformat(),
        }


class RecipeReviewModel(Base):
    """菜谱评分与评论。"""

    __tablename__ = "recipe_reviews"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    recipe_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_review_user_recipe", "user_id", "recipe_id", unique=True),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "user_id": self.user_id,
            "recipe_id": self.recipe_id,
            "rating": self.rating,
            "comment": self.comment,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class FamilyMemberModel(Base):
    """家庭成员饮食档案。"""

    __tablename__ = "family_members"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_user_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    relation: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    birth_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sex: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    allergies: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    dietary_restrictions: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    disliked_foods: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    calorie_goal: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    servings_factor: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "owner_user_id": self.owner_user_id,
            "name": self.name,
            "relation": self.relation,
            "birth_year": self.birth_year,
            "sex": self.sex,
            "allergies": self.allergies or [],
            "dietary_restrictions": self.dietary_restrictions or [],
            "disliked_foods": self.disliked_foods or [],
            "calorie_goal": self.calorie_goal,
            "servings_factor": self.servings_factor,
            "notes": self.notes,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
