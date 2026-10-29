"""
Vision Model Provider
Provides vision model access using the unified LLMProvider infrastructure.
"""

import asyncio
import base64
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple, Union

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.config import settings
from app.config.llm_config import VisionLLMConfig
from app.llm import get_usage_callbacks, llm_context
from app.vision.image_prep import prepare_image

logger = logging.getLogger(__name__)


@dataclass
class ImageInput:
    """
    Represents an image input for vision processing.

    Supports two modes:
    - URL mode: image_url is a direct URL to the image
    - Base64 mode: image_data is base64-encoded image bytes with mime_type
    """

    image_url: Optional[str] = None
    image_data: Optional[str] = None  # Base64 encoded
    mime_type: str = "image/jpeg"

    def to_message_content(self) -> dict:
        """Convert to LangChain message content format."""
        if self.image_url:
            return {"type": "image_url", "image_url": {"url": self.image_url}}
        elif self.image_data:
            # Use data URL format for base64 images
            data_url = f"data:{self.mime_type};base64,{self.image_data}"
            return {"type": "image_url", "image_url": {"url": data_url}}
        else:
            raise ValueError("Either image_url or image_data must be provided")

    @classmethod
    def from_url(cls, url: str) -> "ImageInput":
        """Create from URL."""
        return cls(image_url=url)

    @classmethod
    def from_base64(cls, data: str, mime_type: str = "image/jpeg") -> "ImageInput":
        """Create from base64 encoded data."""
        return cls(image_data=data, mime_type=mime_type)

    @classmethod
    def from_bytes(cls, data: bytes, mime_type: str = "image/jpeg") -> "ImageInput":
        """Create from raw bytes."""
        encoded = base64.b64encode(data).decode("utf-8")
        return cls(image_data=encoded, mime_type=mime_type)


class VisionProvider:
    """
    Provider for vision/multimodal model access.
    Uses the unified LLMProvider infrastructure with llm_type="vision".
    """

    MODULE_NAME = "vision_understanding"

    def __init__(self):
        """
        Initialize vision provider using LLMProvider.
        """
        from app.llm.provider import LLMProvider

        self._provider = LLMProvider(settings.llm)
        self._invoker = self._provider.create_invoker(llm_type="vision")
        self._callbacks = get_usage_callbacks()

    @property
    def config(self) -> VisionLLMConfig:
        """Get vision configuration."""
        profile = self._provider.get_profile("vision")
        # Cast to VisionLLMConfig since we know it's the vision profile
        return profile  # type: ignore

    @property
    def is_enabled(self) -> bool:
        """Check if vision is enabled."""
        return bool(self.config.api_key)

    def build_multimodal_message(
        self,
        text: str,
        images: List[ImageInput],
    ) -> HumanMessage:
        """
        Build a multimodal message with text and images.

        Args:
            text: Text prompt/question
            images: List of image inputs

        Returns:
            HumanMessage with multimodal content
        """
        content: List[Union[str, dict]] = []

        # Add text content first
        if text:
            content.append({"type": "text", "text": text})

        # Add image contents
        for image in images:
            content.append(image.to_message_content())

        return HumanMessage(content=content)  # type: ignore

    def _prepare_images(
        self,
        images: List[ImageInput],
        max_edge: int,
        quality: int,
        max_bytes: int,
    ) -> Tuple[List[ImageInput], int, int]:
        """把 base64 图片按需压缩到模型友好的尺寸；URL 模式原样透传。

        返回 (处理后的图片, 处理前总字节, 处理后总字节)，用于日志度量。
        """
        prepared: List[ImageInput] = []
        before = 0
        after = 0
        max_bytes = max(256 * 1024, max_bytes)

        for image in images:
            if not image.image_data:
                prepared.append(image)
                continue

            result = prepare_image(
                image.image_data,
                image.mime_type,
                max_edge=max_edge,
                quality=quality,
                max_bytes=max_bytes,
            )
            before += result.original_bytes
            after += result.output_bytes
            prepared.append(ImageInput.from_base64(result.data, result.mime_type))

            if result.resized:
                logger.info(
                    "Vision image normalized: %s -> %s, %.0fKB -> %.0fKB",
                    result.original_size,
                    result.output_size,
                    result.original_bytes / 1024,
                    result.output_bytes / 1024,
                )
            elif result.reason not in ("unchanged",):
                logger.warning(
                    "Vision image kept as-is (%s), %.0fKB",
                    result.reason,
                    result.original_bytes / 1024,
                )

        return prepared, before, after

    @staticmethod
    def _looks_like_timeout(exc: BaseException) -> bool:
        text = str(exc).lower()
        return (
            isinstance(exc, asyncio.TimeoutError)
            or "timed out" in text
            or "timeout" in text
        )

    def _build_messages(
        self,
        text: str,
        images: List[ImageInput],
        system_prompt: Optional[str],
    ) -> List[BaseMessage]:
        messages: List[BaseMessage] = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(self.build_multimodal_message(text, images))
        return messages

    async def _invoke(
        self,
        messages: List[BaseMessage],
        model: Optional[str],
        user_id: Optional[str],
        conversation_id: Optional[str],
    ) -> str:
        with llm_context(self.MODULE_NAME, user_id, conversation_id):
            response = await self._invoker.ainvoke(
                messages,
                model=model,
                response_format={"type": "json_object"},  # Best effort
            )
        return str(response.content)

    async def analyze(
        self,
        text: str,
        images: List[ImageInput],
        system_prompt: Optional[str] = None,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> str:
        """分析图片并返回模型输出。

        送模型前会按 `max_image_edge` / `jpeg_quality` 归一化：手机原图常见
        3–8MB、长边 3000+，直接发容易读超时；缩到 1024px 后通常 2–4s 返回。
        若仍超时，会用更小的图重试一次，再走模型回退。
        """
        if not self.is_enabled:
            raise RuntimeError("Vision module is not enabled or API key is missing")

        if not images:
            raise ValueError("At least one image is required")

        config = self.config
        # 老配置对象可能没有这些字段，取默认值兜底
        max_edge = int(getattr(config, "max_image_edge", 1024))
        quality = int(getattr(config, "jpeg_quality", 85))
        max_payload_mb = float(getattr(config, "max_payload_mb", 2.0))
        max_bytes = int(max_payload_mb * 1024 * 1024)

        prepared, before_bytes, after_bytes = self._prepare_images(
            images, max_edge, quality, max_bytes
        )
        if before_bytes:
            logger.info(
                "Vision payload: %.0fKB -> %.0fKB (images=%d, edge=%d)",
                before_bytes / 1024,
                after_bytes / 1024,
                len(images),
                max_edge,
            )

        messages = self._build_messages(text, prepared, system_prompt)

        logger.info(
            "Vision analysis: text='%s...', images=%d, model=%s",
            text[:50],
            len(images),
            config.model_names[0] if config.model_names else None,
        )

        models = list(config.model_names) or [None]
        last_error: Optional[Exception] = None
        retried_smaller = False

        for index, model in enumerate(models):
            try:
                return await self._invoke(messages, model, user_id, conversation_id)
            except Exception as exc:
                error: Exception = exc

                # 超时优先用更小的图重试同一条模型，而不是立刻换模型：
                # 换模型往往更慢，缩小图片才是对症的。
                if not retried_smaller and self._looks_like_timeout(exc):
                    retried_smaller = True
                    smaller_edge = max(512, int(max_edge * 0.75))
                    smaller, _, _ = self._prepare_images(
                        images, smaller_edge, max(60, quality - 10), max_bytes
                    )
                    messages = self._build_messages(text, smaller, system_prompt)
                    logger.warning(
                        "Vision call timed out; retrying with edge=%d", smaller_edge
                    )
                    try:
                        return await self._invoke(
                            messages, model, user_id, conversation_id
                        )
                    except Exception as second_exc:
                        error = second_exc

                last_error = error
                if index < len(models) - 1:
                    logger.warning(
                        "Vision model %s failed (%s); trying fallback %s",
                        model,
                        error,
                        models[index + 1],
                    )
                    continue

                logger.error("Vision analysis failed: %s", error, exc_info=True)
                raise error

        assert last_error is not None
        raise last_error

    def validate_image(
        self, mime_type: str, size_bytes: int
    ) -> tuple[bool, Optional[str]]:
        """
        Validate image format and size.

        Args:
            mime_type: MIME type of the image
            size_bytes: Size of the image in bytes

        Returns:
            Tuple of (is_valid, error_message)
        """
        config = self.config

        # Check format
        if mime_type not in config.supported_formats:
            return (
                False,
                f"Unsupported image format: {mime_type}. Supported: {config.supported_formats}",
            )

        # Check size
        max_size_bytes = config.max_image_size_mb * 1024 * 1024
        if size_bytes > max_size_bytes:
            return (
                False,
                f"Image too large: {size_bytes / 1024 / 1024:.2f}MB. Maximum: {config.max_image_size_mb}MB",
            )

        return True, None


# Global instance
vision_provider = VisionProvider()
