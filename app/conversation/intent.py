"""
用户意图识别与检索决策（SU-2）

在原有「是否需要 RAG」二值判断的基础上，升级为：

- 多标签意图：一次输出可包含多个意图（如同时需要菜谱与烹饪技巧）
- 领域槽位：食材、菜名、口味、餐次、时间预算、饮食约束、人数
- 置信度：低置信度时给出澄清信号，而不是直接猜测

兼容性约定：

- ``IntentDetectionResult.need_rag`` / ``intent`` / ``reason`` 语义保持不变，
  既有调用方无需改动。
- 旧版单标签 JSON（``{"need_rag":..., "intent":..., "reason":...}``）仍可解析。
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field, field_validator

from app.config import settings, LLMType
from app.llm import LLMProvider, llm_context
from app.llm.structured import StructuredOutputError, invoke_structured
from app.observability import semantic_metrics

logger = logging.getLogger(__name__)


class QueryIntent(Enum):
    """Enum representing the detected intent of a user query."""

    RECIPE_SEARCH = "recipe_search"
    COOKING_TIPS = "cooking_tips"
    INGREDIENT_INFO = "ingredient_info"
    GENERAL_CHAT = "general_chat"
    RECOMMENDATION = "recommendation"


INTENT_MAP: dict[str, QueryIntent] = {
    "recipe_search": QueryIntent.RECIPE_SEARCH,
    "cooking_tips": QueryIntent.COOKING_TIPS,
    "ingredient_info": QueryIntent.INGREDIENT_INFO,
    "recommendation": QueryIntent.RECOMMENDATION,
    "general_chat": QueryIntent.GENERAL_CHAT,
}

MEAL_TYPE_MAP: dict[str, str] = {
    "breakfast": "breakfast",
    "lunch": "lunch",
    "dinner": "dinner",
    "snack": "snack",
    "早餐": "breakfast",
    "早饭": "breakfast",
    "午餐": "lunch",
    "午饭": "lunch",
    "中饭": "lunch",
    "晚餐": "dinner",
    "晚饭": "dinner",
    "加餐": "snack",
    "夜宵": "snack",
    "零食": "snack",
}

_LIST_SEPARATORS = re.compile(r"[,，、/;；\n]+")


# =============================================================================
# 传输层模型（LLM 输出 → 结构化）
# =============================================================================


def _coerce_str_list(value: Any) -> list[str]:
    """把模型可能给出的各种形态统一成字符串列表。"""
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in _LIST_SEPARATORS.split(value) if part.strip()]
    if isinstance(value, (list, tuple, set)):
        items: list[str] = []
        for item in value:
            if item is None:
                continue
            if isinstance(item, str):
                items.append(item.strip())
            elif isinstance(item, (int, float)):
                items.append(str(item))
        return items
    return []


def _coerce_optional_str(value: Any) -> Optional[str]:
    if isinstance(value, str):
        return value.strip() or None
    return None


def _coerce_optional_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class SlotsPayload(BaseModel):
    """LLM 输出的原始槽位（宽松接收，严格清洗在 QuerySlots 中完成）。"""

    ingredients: list[str] = Field(default_factory=list)
    dish_names: list[str] = Field(default_factory=list)
    tastes: list[str] = Field(default_factory=list)
    meal_type: Optional[str] = None
    time_budget_minutes: Any = None
    diet_constraints: list[str] = Field(default_factory=list)
    servings: Any = None

    @field_validator(
        "ingredients", "dish_names", "tastes", "diet_constraints", mode="before"
    )
    @classmethod
    def _normalize_list(cls, value: Any) -> list[str]:
        return _coerce_str_list(value)

    @field_validator("meal_type", mode="before")
    @classmethod
    def _normalize_meal_type(cls, value: Any) -> Optional[str]:
        return _coerce_optional_str(value)


class IntentPayload(BaseModel):
    """LLM 输出的意图载荷。"""

    intents: list[str] = Field(default_factory=list)
    # 兼容字段：旧版单标签输出
    intent: Optional[str] = None
    need_rag: Optional[bool] = None
    confidence: Optional[float] = None
    reason: str = ""
    slots: SlotsPayload = Field(default_factory=SlotsPayload)

    @field_validator("intents", mode="before")
    @classmethod
    def _normalize_intents(cls, value: Any) -> list[str]:
        return _coerce_str_list(value)

    @field_validator("intent", mode="before")
    @classmethod
    def _normalize_intent(cls, value: Any) -> Optional[str]:
        return _coerce_optional_str(value)

    @field_validator("confidence", mode="before")
    @classmethod
    def _normalize_confidence(cls, value: Any) -> Optional[float]:
        return _coerce_optional_float(value)

    @field_validator("reason", mode="before")
    @classmethod
    def _normalize_reason(cls, value: Any) -> str:
        return value.strip() if isinstance(value, str) else ""


# =============================================================================
# 领域对象
# =============================================================================


def _clean_str_list(values: Any) -> list[str]:
    """去空白、去空串、按大小写不敏感去重（保留首次出现的写法）。"""
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in _coerce_str_list(values):
        text = item.strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned


def _normalize_meal_type(value: Any) -> Optional[str]:
    text = _coerce_optional_str(value)
    if not text:
        return None
    return MEAL_TYPE_MAP.get(text.casefold())


def _normalize_positive_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


@dataclass
class QuerySlots:
    """从用户查询中抽取的领域槽位。"""

    ingredients: list[str] = field(default_factory=list)
    dish_names: list[str] = field(default_factory=list)
    tastes: list[str] = field(default_factory=list)
    meal_type: Optional[str] = None
    time_budget_minutes: Optional[int] = None
    diet_constraints: list[str] = field(default_factory=list)
    servings: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ingredients": list(self.ingredients),
            "dish_names": list(self.dish_names),
            "tastes": list(self.tastes),
            "meal_type": self.meal_type,
            "time_budget_minutes": self.time_budget_minutes,
            "diet_constraints": list(self.diet_constraints),
            "servings": self.servings,
        }

    @classmethod
    def from_payload(cls, payload: Optional[SlotsPayload]) -> "QuerySlots":
        if payload is None:
            return cls()
        return cls(
            ingredients=_clean_str_list(payload.ingredients),
            dish_names=_clean_str_list(payload.dish_names),
            tastes=_clean_str_list(payload.tastes),
            meal_type=_normalize_meal_type(payload.meal_type),
            time_budget_minutes=_normalize_positive_int(payload.time_budget_minutes),
            diet_constraints=_clean_str_list(payload.diet_constraints),
            servings=_normalize_positive_int(payload.servings),
        )


@dataclass
class IntentDetectionResult:
    """Structured intent detection result with room for future extensions."""

    need_rag: bool
    intent: QueryIntent
    reason: str
    raw: dict
    intents: list[QueryIntent] = field(default_factory=list)
    confidence: float = 0.0
    slots: QuerySlots = field(default_factory=QuerySlots)
    needs_clarification: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "need_rag": self.need_rag,
            "intent": self.intent.value,
            "intents": [intent.value for intent in self.intents],
            "confidence": self.confidence,
            "needs_clarification": self.needs_clarification,
            "reason": self.reason,
            "slots": self.slots.to_dict(),
        }


# =============================================================================
# Prompt
# =============================================================================


INTENT_DETECTION_PROMPT_TEMPLATE = """
你是 CookHero 的「用户意图识别与检索决策模块」。你的任务是：结合【当前问题】与【对话历史上下文】，
判断是否需要查询烹饪知识库（RAG），同时抽取结构化意图标签与领域槽位。

【核心决策原则】

只有当**当前问题需要依赖具体菜谱、做法步骤、烹饪技巧或可执行方案**时，need_rag 才为 true。

如果仅是：
- 观点性、解释性、确认性
- 闲聊或情绪回应
- 与“如何做菜”无直接关系
则 need_rag 为 false。

【need_rag = true 的典型情况】
1. 菜谱 / 做法查询（“X 怎么做”“做 X 需要什么”）
2. 基于食材 / 条件的可执行建议（“有 A、B、C 能做什么菜”）
3. 烹饪技巧与操作问题（火候、调味、失败补救）
4. 承接式问题（“这个怎么做”“第二种呢”，需结合上下文）

【need_rag = false 的典型情况】
1. 纯对话或流程控制（闲聊、感谢、寒暄、“好的”“继续”）
2. 确认 / 澄清 / 选择类问题（“这个可以吗？”）
3. 与烹饪无关的内容

【意图分类说明】
- recipe_search：查询具体菜品、完整做法、步骤流程
- cooking_tips：烹饪技巧、经验、火候、调味、失败处理
- ingredient_info：食材相关问题
- recommendation：菜品推荐、菜单搭配、场景化建议
- general_chat：闲聊、确认、情绪回应、非任务性对话

一个查询可以同时属于多个意图，例如“推荐几道快手菜并告诉我怎么做”应同时包含
recommendation 与 recipe_search。无法判断时输出 ["general_chat"]。

【槽位抽取规则】
- 只抽取用户**明确表达**的信息，禁止推断或补全
- ingredients / dish_names / tastes / diet_constraints 输出字符串数组，没有就给空数组
- meal_type 只能取 breakfast / lunch / dinner / snack 或 null
- time_budget_minutes 与 servings 为整数或 null；无法确定时为 null
- diet_constraints 记录过敏、忌口、素食、减脂、控糖等约束

【置信度】
confidence 取 0.0-1.0：
- 意图明确、槽位清晰 → 0.8-1.0
- 大体可判断但存在歧义 → 0.5-0.8
- 明显模糊、需要向用户澄清 → 0.0-0.5

{history}

【输出格式（强约束）】

你 **必须且只能** 输出以下 JSON，对象结构固定，不得添加或省略字段，不得输出任何多余文本：

{{
    "intents": ["intent_type"],
    "need_rag": true/false,
    "confidence": 0.0,
    "reason": "简短、明确的判断理由",
    "slots": {{
        "ingredients": [],
        "dish_names": [],
        "tastes": [],
        "meal_type": null,
        "time_budget_minutes": null,
        "diet_constraints": [],
        "servings": null
    }}
}}
"""

INTENT_DETECTION_PROMPT = ChatPromptTemplate.from_template(
    INTENT_DETECTION_PROMPT_TEMPLATE
)


# =============================================================================
# Detector
# =============================================================================


class IntentDetector:
    """
    Detects user intent to determine if RAG retrieval is needed.
    """

    MODULE_NAME = "intent_detector"

    # 低于该置信度时，认为需要向用户澄清
    CONFIDENCE_THRESHOLD = 0.5
    # 旧格式未提供置信度时的默认值（视为正常可信）
    DEFAULT_CONFIDENCE = 0.5

    def __init__(
        self,
        llm_type: LLMType | str = LLMType.FAST,
        provider: LLMProvider | None = None,
        *,
        max_attempts: int = 2,
        use_native_schema: bool = True,
    ):
        """Initialize the intent detector with global or overridden LLM config."""
        self._llm_type = llm_type
        self._provider = provider or LLMProvider(settings.llm)
        # Use tracked invoker for usage statistics
        self._llm = self._provider.create_invoker(llm_type, temperature=0.0)
        self.max_attempts = max(1, int(max_attempts))
        self.use_native_schema = bool(use_native_schema)

    async def detect(
        self,
        history_text: Optional[str] = None,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> IntentDetectionResult:
        """Detect intent, slots and whether RAG retrieval is needed.

        Args:
            history_text: Pre-formatted history text (already concatenated by ContextManager).
            user_id: User ID for tracking (optional).
            conversation_id: Conversation ID for tracking (optional).
        """
        history_str = history_text or ""

        try:
            template = INTENT_DETECTION_PROMPT.format_prompt(history=history_str)
            # Use llm_context for usage tracking
            with llm_context(self.MODULE_NAME, user_id, conversation_id):
                payload = await invoke_structured(
                    self._llm,
                    list(template.messages),
                    IntentPayload,
                    max_attempts=self.max_attempts,
                    validator=self._validate_payload,
                    use_native_schema=self.use_native_schema,
                )
            result = self._build_result(payload)

        except StructuredOutputError as exc:
            logger.warning(
                "Intent detection failed after %d attempt(s): %s", exc.attempts, exc
            )
            result = self._safe_default()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Intent detection failed: %s", exc)
            result = self._safe_default()

        self._record_metrics(result)
        return result

    @staticmethod
    def _record_metrics(result: IntentDetectionResult) -> None:
        """Record intent metrics without ever breaking the main flow."""
        try:
            semantic_metrics.record_intent(
                intent=result.intent.value,
                confidence=result.confidence,
                needs_clarification=result.needs_clarification,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to record intent metrics: %s", exc)

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_payload(payload: IntentPayload) -> None:
        """拒绝完全空白的载荷，触发修复重试。"""
        if not payload.intents and not payload.intent and not payload.reason.strip():
            raise ValueError("payload must contain intents/intent or a reason")

    @staticmethod
    def _normalize_intents(payload: IntentPayload) -> list[QueryIntent]:
        raw: list[str] = list(payload.intents or [])
        if not raw and payload.intent:
            raw = [payload.intent]

        intents: list[QueryIntent] = []
        seen: set[QueryIntent] = set()
        for item in raw:
            if not isinstance(item, str):
                continue
            intent = INTENT_MAP.get(item.strip().casefold())
            if intent is None or intent in seen:
                continue
            seen.add(intent)
            intents.append(intent)

        return intents or [QueryIntent.GENERAL_CHAT]

    @staticmethod
    def _normalize_confidence(payload: IntentPayload) -> float:
        value = payload.confidence
        if value is None:
            return IntentDetector.DEFAULT_CONFIDENCE
        return max(0.0, min(1.0, float(value)))

    def _build_result(self, payload: IntentPayload) -> IntentDetectionResult:
        intents = self._normalize_intents(payload)
        confidence = self._normalize_confidence(payload)

        # need_rag 与 intents 保持一致：含任一非闲聊意图即需要检索
        need_rag = any(intent is not QueryIntent.GENERAL_CHAT for intent in intents)
        needs_clarification = confidence < self.CONFIDENCE_THRESHOLD

        return IntentDetectionResult(
            need_rag=need_rag,
            intent=intents[0],
            reason=payload.reason.strip(),
            raw=payload.model_dump(),
            intents=intents,
            confidence=confidence,
            slots=QuerySlots.from_payload(payload.slots),
            needs_clarification=needs_clarification,
        )

    def _safe_default(self) -> IntentDetectionResult:
        """安全默认：不检索、按闲聊处理。"""
        return IntentDetectionResult(
            need_rag=False,
            intent=QueryIntent.GENERAL_CHAT,
            reason="Detection failed, using default",
            raw={},
            intents=[QueryIntent.GENERAL_CHAT],
            confidence=0.0,
            slots=QuerySlots(),
            needs_clarification=False,
        )
