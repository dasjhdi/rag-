"""约束推理配置（SU-18）。"""

from pydantic import BaseModel, Field


class ConstraintReasoningConfig(BaseModel):
    """约束推理开关与安全默认值。"""

    enabled: bool = True
    strict_allergens: bool = True
    max_candidates: int = Field(default=20, ge=1)


__all__ = ["ConstraintReasoningConfig"]
