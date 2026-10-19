"""
Vision Agent for CookHero
Handles image analysis and determines cooking-related intent.

This agent:
1. Analyzes uploaded images with user's text prompt
2. Determines if the content is cooking/food related
3. Generates appropriate responses or hands off to the main conversation flow
"""

import json
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, List, Optional

from app.config import settings
from app.knowledge.ontology import canonicalize_ingredients
from app.vision.provider import VisionProvider, ImageInput, vision_provider
from app.utils.structured_json import extract_first_valid_json

logger = logging.getLogger(__name__)


def _normalize_text_value(value: Any) -> str:
    """Collapse arbitrary model output into a single display string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (list, tuple, set)):
        items = [_normalize_text_value(item) for item in value]
        return "、".join(dict.fromkeys(item for item in items if item))
    return " ".join(str(value).split())


def _normalize_dish_name(value: Any) -> str:
    """Return one dish name; models sometimes return a list of candidates."""
    if isinstance(value, (list, tuple, set)):
        names = [_normalize_text_value(item) for item in value]
        return " / ".join(dict.fromkeys(name for name in names if name))
    return _normalize_text_value(value)


def _normalize_ingredients(value: Any) -> List[str]:
    """Normalize ingredients into a deduplicated list of non-empty names."""
    if isinstance(value, str):
        value = re.split(r"[,，、;；/|]+", value)
    elif not isinstance(value, (list, tuple, set)):
        return []

    result: List[str] = []
    for item in value:
        name = _normalize_text_value(item)
        if name and name not in result:
            result.append(name)
    return result


def _normalize_extracted_info(value: Any) -> dict:
    """Give every downstream consumer stable field types."""
    if not isinstance(value, dict):
        return {}
    return {
        "dish_name": _normalize_dish_name(value.get("dish_name")),
        "ingredients": _normalize_ingredients(value.get("ingredients")),
        "cooking_stage": _normalize_text_value(value.get("cooking_stage")),
        "other": _normalize_text_value(value.get("other")),
    }


def _coerce_confidence(value: Any, default: float = 0.5) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class VisionIntent(str, Enum):
    """Intent classification for vision analysis results."""

    # Food/cooking related - should continue to RAG/conversation flow
    DISH_IDENTIFICATION = "dish_identification"  # User wants to identify a dish
    RECIPE_REQUEST = "recipe_request"  # User wants recipe for shown food
    INGREDIENT_IDENTIFICATION = "ingredient_identification"  # Identify ingredients
    COOKING_GUIDANCE = "cooking_guidance"  # Cooking technique/process help
    FOOD_QUESTION = "food_question"  # General food-related question

    # Not food related - should return direct response
    GENERAL_IMAGE = "general_image"  # Non-food image
    UNCLEAR = "unclear"  # Cannot determine


@dataclass
class VisionAnalysisResult:
    """
    Result of vision analysis.

    Attributes:
        is_food_related: Whether the image is related to food/cooking
        intent: Detected intent category
        description: Description of what's in the image
        extracted_info: Structured information extracted (dish name, ingredients, etc.)
        direct_response: If not food-related, a direct response to user
        confidence: Confidence score (0-1)
        raw_response: Raw model response
    """

    is_food_related: bool
    intent: VisionIntent
    description: str
    extracted_info: dict
    direct_response: Optional[str]
    confidence: float
    raw_response: str

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "is_food_related": self.is_food_related,
            "intent": self.intent.value,
            "description": self.description,
            "extracted_info": self.extracted_info,
            "direct_response": self.direct_response,
            "confidence": self.confidence,
        }


# Vision analysis prompt template
VISION_ANALYSIS_PROMPT = """你是 CookHero 的视觉理解模块，专门用于分析用户上传的图片并结合用户的文字提问来理解用户意图。

⚠️ 严格输出要求：
仅输出一个 JSON 对象，禁止输出任何解释、前后缀、markdown 代码块或额外文本。务必遵守字段与类型。

【你的任务】
1. 仔细观察图片内容
2. 结合用户的文字提问（如果有）
3. 判断图片是否与「菜品/食材/烹饪/饮食」相关
4. 提取关键信息并进行意图分类

【意图分类说明】
- dish_identification: 用户想识别图中的菜品是什么
- recipe_request: 用户想知道图中菜品的做法/食谱
- ingredient_identification: 用户想识别图中的食材
- cooking_guidance: 用户在烹饪过程中需要指导（如火候、步骤）
- food_question: 其他与食物相关的问题
- general_image: 图片与食物/烹饪无关
- unclear: 无法确定图片内容或意图

【判定原则】
1. 如果图片中包含：菜品、食材、厨房场景、烹饪过程、餐具摆盘等，则属于「食物相关」
2. 如果图片是：风景、人物、动物、物品、文档等非食物内容，则属于「非食物相关」
3. 结合用户的文字提问来理解完整意图，不要仅凭图片判断

【用户提问】
{user_query}

【输出格式（JSON）】
你必须严格输出以下 JSON 格式（单个对象），不要输出其他任何字符：

{{
    "is_food_related": true/false,
    "intent": "意图分类（使用上述分类之一）",
    "description": "图片内容的简要描述（1-2句话）",
    "extracted_info": {{
        "dish_name": "识别出的菜品名称（如有）",
        "ingredients": ["识别出的食材列表（如有）"],
        "cooking_stage": "烹饪阶段描述（如有）",
        "other": "其他相关信息"
    }},
    "direct_response": "如果图片与食物无关，在此提供简短回复；如果食物相关则为null",
    "confidence": 0.0-1.0之间的置信度
}}

如果图片与食物相关，必须给出最可能的 dish_name 和图片中可见的 ingredients，不要留空；
无法确定具体菜名时给出候选菜名，并降低 confidence。ingredients 只列图片中可见或高度可能的食材，使用常见中文名称。
如果无法识别或不确定，也必须按此格式输出，给出最佳猜测并将简要描述写入 description。
"""


class VisionAgent:
    """
    Vision agent for analyzing images and determining intent.

    This agent processes image inputs and classifies them based on
    whether they are food/cooking related, then extracts relevant information.
    """

    MAX_RETRIEVAL_QUERY_LENGTH = 80

    def __init__(self, provider: Optional[VisionProvider] = None):
        """
        Initialize vision agent.

        Args:
            provider: Vision provider instance. Uses global instance if not provided.
        """
        self._provider = provider or vision_provider

    @property
    def is_available(self) -> bool:
        """Check if vision analysis is available."""
        return self._provider.is_enabled

    async def analyze(
        self,
        images: List[ImageInput],
        user_query: str = "",
        history_context: str = "",
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> VisionAnalysisResult:
        """
        Analyze images and determine cooking-related intent.

        Args:
            images: List of images to analyze
            user_query: User's text prompt/question
            history_context: Optional conversation history for context
            user_id: User ID for tracking (optional)
            conversation_id: Conversation ID for tracking (optional)

        Returns:
            VisionAnalysisResult with analysis details
        """
        if not self.is_available:
            logger.warning("Vision analysis not available, returning default result")
            return VisionAnalysisResult(
                is_food_related=False,
                intent=VisionIntent.UNCLEAR,
                description="视觉分析功能未启用",
                extracted_info={},
                direct_response="抱歉，图片识别功能暂时不可用。请尝试用文字描述您的问题。",
                confidence=0.0,
                raw_response="",
            )

        # Build prompt with user query
        prompt = VISION_ANALYSIS_PROMPT.format(
            user_query=user_query if user_query else "（用户没有提供文字说明）"
        )

        # Add history context if available
        if history_context:
            prompt = f"【对话上下文】\n{history_context}\n\n{prompt}"

        try:
            # Call vision model
            raw_response = await self._provider.analyze(
                text=prompt,
                images=images,
                user_id=user_id,
                conversation_id=conversation_id,
            )

            # Parse response
            result = self._parse_response(raw_response, user_query)
            return result

        except Exception as e:
            logger.error(f"Vision analysis failed: {e}", exc_info=True)
            return VisionAnalysisResult(
                is_food_related=False,
                intent=VisionIntent.UNCLEAR,
                description="图片分析过程中出现错误",
                extracted_info={},
                direct_response=f"抱歉，分析图片时遇到问题：{str(e)[:100]}。请稍后重试或用文字描述您的问题。",
                confidence=0.0,
                raw_response=str(e),
            )

    def _parse_response(
        self, raw_response: str, user_query: str
    ) -> VisionAnalysisResult:
        """Parse the model's JSON response."""
        try:
            # Extract JSON from response
            data = extract_first_valid_json(raw_response)

            if not data:
                logger.warning(
                    f"Failed to parse vision response as JSON: {raw_response[:200]}"
                )
                # Fallback: treat as food-related if response contains food keywords
                is_food = self._check_food_keywords(raw_response)
                return VisionAnalysisResult(
                    is_food_related=is_food,
                    intent=VisionIntent.FOOD_QUESTION
                    if is_food
                    else VisionIntent.GENERAL_IMAGE,
                    description=raw_response[:200],
                    extracted_info={},
                    direct_response=None if is_food else raw_response,
                    confidence=0.5,
                    raw_response=raw_response,
                )

            # Parse intent
            intent_str = data.get("intent", "unclear")
            try:
                intent = VisionIntent(intent_str)
            except ValueError:
                intent = VisionIntent.UNCLEAR

            # Build result
            is_food_related = data.get("is_food_related", False)

            return VisionAnalysisResult(
                is_food_related=is_food_related,
                intent=intent,
                description=data.get("description", ""),
                extracted_info=_normalize_extracted_info(data.get("extracted_info")),
                direct_response=data.get("direct_response")
                if not is_food_related
                else None,
                confidence=_coerce_confidence(data.get("confidence")),
                raw_response=raw_response,
            )

        except Exception as e:
            logger.error(f"Error parsing vision response: {e}", exc_info=True)
            # Graceful fallback: treat as generic response instead of raising
            is_food = self._check_food_keywords(raw_response)
            return VisionAnalysisResult(
                is_food_related=is_food,
                intent=VisionIntent.FOOD_QUESTION
                if is_food
                else VisionIntent.GENERAL_IMAGE,
                description=raw_response[:200],
                extracted_info={},
                direct_response=None if is_food else raw_response[:200],
                confidence=0.35,
                raw_response=raw_response,
            )

    def _check_food_keywords(self, text: str) -> bool:
        """Check if text contains food-related keywords."""
        keywords = settings.vision.food_related_keywords
        text_lower = text.lower()
        return any(kw in text_lower for kw in keywords)

    def build_context_for_rag(
        self, result: VisionAnalysisResult, user_query: str
    ) -> str:
        """
        Build context string for RAG pipeline based on vision analysis.

        This method creates a structured context that can be injected into
        the conversation flow when the image is food-related.

        Args:
            result: Vision analysis result
            user_query: Original user query

        Returns:
            Context string for RAG
        """
        if not result.is_food_related:
            return ""

        parts = []

        # Add image description
        if result.description:
            parts.append(f"【图片内容】{result.description}")

        # Add extracted information
        info = result.extracted_info if isinstance(result.extracted_info, dict) else {}
        if info:
            dish_name = _normalize_dish_name(info.get("dish_name"))
            ingredients = _normalize_ingredients(info.get("ingredients"))
            cooking_stage = _normalize_text_value(info.get("cooking_stage"))
            other = _normalize_text_value(info.get("other"))
            if dish_name:
                parts.append(f"【识别菜品】{dish_name}")
            if ingredients:
                parts.append(f"【识别食材】{', '.join(ingredients)}")
            if cooking_stage:
                parts.append(f"【烹饪阶段】{cooking_stage}")
            if other:
                parts.append(f"【其他信息】{other}")

        # Add intent context
        intent_map = {
            VisionIntent.DISH_IDENTIFICATION: "用户想知道图中的菜品是什么",
            VisionIntent.RECIPE_REQUEST: "用户想获取图中菜品的做法",
            VisionIntent.INGREDIENT_IDENTIFICATION: "用户想识别图中的食材",
            VisionIntent.COOKING_GUIDANCE: "用户在烹饪过程中需要指导",
            VisionIntent.FOOD_QUESTION: "用户对图中的食物有疑问",
        }
        if result.intent in intent_map:
            parts.append(f"【用户意图】{intent_map[result.intent]}")

        return "\n".join(parts)

    def build_direct_answer(
        self, result: Optional[VisionAnalysisResult]
    ) -> Optional[str]:
        """Build a deterministic answer for image identification intents.

        Dish and ingredient identification should not depend on a second LLM
        call or on recipe retrieval. The vision model already produced the
        structured result; returning it directly is both more reliable and much
        faster. Recipe requests and open-ended food questions still continue
        through the normal conversation/RAG flow.
        """
        if result is None or not result.is_food_related:
            return None
        if result.intent not in (
            VisionIntent.DISH_IDENTIFICATION,
            VisionIntent.INGREDIENT_IDENTIFICATION,
        ):
            return None

        info = result.extracted_info if isinstance(result.extracted_info, dict) else {}

        dish = _normalize_dish_name(info.get("dish_name"))
        ingredients = _normalize_ingredients(info.get("ingredients"))

        if not dish and not ingredients:
            return None

        parts: List[str] = []
        if result.confidence < 0.6:
            parts.append("识别置信度较低，以下是最可能的判断：")
        if dish:
            parts.append(f"识别结果：这道菜看起来是 **{dish}**。")
        else:
            parts.append("识别结果：图片中的菜品暂未确定具体名称。")
        if ingredients:
            parts.append(f"可见的主要原料：{'、'.join(ingredients)}。")
        if result.description:
            parts.append(f"图片描述：{result.description.strip()}")
        parts.append("以上为基于图片的识别结果，实际用料可能因做法不同而略有差异。")
        return "\n\n".join(parts)

    def build_retrieval_query(
        self, result: VisionAnalysisResult, user_query: str = ""
    ) -> Optional[str]:
        """
        Turn structured vision output into a compact retrieval query.

        Dish names and normalized ingredients are used because they are the
        signals the recipe index can match. When the image yields neither, the
        caller should fall back to the text query.
        """
        if result is None or not result.is_food_related:
            return None

        info = result.extracted_info if isinstance(result.extracted_info, dict) else {}

        dish = _normalize_dish_name(info.get("dish_name"))
        ingredients = canonicalize_ingredients(_normalize_ingredients(info.get("ingredients")))

        parts = [part for part in [dish, *ingredients] if part]
        if not parts:
            return None

        # Deduplicate while preserving order, then enforce a single line.
        query = " ".join(dict.fromkeys(parts))
        query = " ".join(query.split())
        if len(query) > self.MAX_RETRIEVAL_QUERY_LENGTH:
            query = query[: self.MAX_RETRIEVAL_QUERY_LENGTH].rstrip()

        return query or None


# Global instance
vision_agent = VisionAgent()
