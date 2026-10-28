"""
Vision Configuration
Configures domain detection settings for vision analysis.
Model configuration is now handled by LLMConfig.vision (VisionLLMConfig).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ImageGenerationConfig(BaseModel):
    """
    Configuration for image generation using OpenAI-compatible API (DALL-E 3, etc.).
    """

    enabled: bool = True
    api_key: str | None = None  # Loaded from .env (OPENAI_IMAGE_API_KEY)
    base_url: str | None = None  # Optional custom base URL for OpenAI-compatible APIs
    model: str = "dall-e-3"
    temperature: float = 1.0  # Only used for some compatible APIs


class ImageStorageConfig(BaseModel):
    """Where uploaded chat/generated images are persisted.

    ``provider`` 决定落点：
    - ``minio``  —— 自托管对象存储（默认），图片不上传第三方；
    - ``imgbb``  —— 旧的第三方图床，保留以兼容已有部署。
    """

    enabled: bool = True
    provider: str = "minio"  # "minio" | "imgbb"

    # --- imgbb（仅 provider=imgbb 时使用）---
    api_key: str | None = None  # Loaded from .env (IMGBB_STORAGE_API_KEY)
    upload_url: str = "https://api.imgbb.com/1/upload"
    expiration: int | None = None  # Optional expiration in seconds (60-15552000), None = never

    # --- MinIO（provider=minio 时使用）---
    minio_endpoint: str = "localhost:9001"  # 宿主端口（compose 把容器 9000 映射到 9001）
    minio_access_key: str | None = None  # Loaded from .env (MINIO_ACCESS_KEY)
    minio_secret_key: str | None = None  # Loaded from .env (MINIO_SECRET_KEY)
    minio_bucket: str = "cookhero-media"
    minio_secure: bool = False
    # 对外可访问前缀；留空则返回相对路径 /media/uploads/<name>，由后端代理
    public_base: str = ""
    # 生成缩略图的最大边长（像素）
    thumbnail_max_px: int = 512


class VisionConfig(BaseModel):
    """
    Vision configuration for domain detection.
    Model configuration is now in LLMConfig.vision.
    """

    # Domain detection settings
    food_related_keywords: list[str] = Field(
        default_factory=lambda: [
            "菜品", "食材", "烹饪", "做菜", "食物", "美食", "饭菜",
            "炒", "煮", "蒸", "烤", "煎", "炸", "焖", "炖",
            "蔬菜", "水果", "肉类", "海鲜", "调料", "配料",
            "早餐", "午餐", "晚餐", "甜点", "饮品",
            "厨房", "刀工", "火候", "调味"
        ]
    )
