# app/config/config.py
"""
Unified configuration module for CookHero.
Provides a single entry point for all application configuration.

Design:
- Settings: Top-level configuration class containing global and module configs
- All configs loaded from config.yml + .env secrets
- Environment variables are loaded via load_dotenv in config_loader
"""

import os

from typing import Optional

from pydantic import BaseModel

from app.config.database_config import DatabaseConfig
from app.config.llm_config import LLMConfig
from app.config.rag_config import RAGConfig
from app.config.web_search_config import WebSearchConfig, DeepResearchConfig
from app.config.vision_config import VisionConfig, ImageGenerationConfig, ImageStorageConfig
from app.config.evaluation_config import EvaluationConfig
from app.config.mcp_config import MCPConfig
from app.config.constraint_config import ConstraintReasoningConfig
from app.config.alerts_config import AlertsConfig
from app.config.config_loader import (
    load_database_config,
    load_llm_config,
    load_rag_config,
    load_web_search_config,
    load_deep_research_config,
    load_vision_config,
    load_evaluation_config,
    load_mcp_config,
    load_constraint_config,
    load_image_generation_config,
    load_image_storage_config,
    load_alerts_config,
)


class Settings(BaseModel):
    """
    Top-level application settings.
    
    Contains:
    1. Global configuration (API prefix, project name, etc.)
    2. Global LLM provider configuration
    3. Database configurations (PostgreSQL, Redis, Milvus)
    4. Module-specific configurations (RAG, Web Search, etc.)
    """
    # ==========================================================================
    # Global Configuration
    # ==========================================================================
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "CookHero"
    DEBUG: bool = False

    # ==========================================================================
    # Auth / Security
    # Note: Environment variables are already loaded via load_dotenv in config_loader
    # SECURITY: JWT_SECRET_KEY must be set via environment variable in production
    # ==========================================================================
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    # Default to 60 minutes (was 10080 = 7 days, too long for security)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    # Refresh token expiration (7 days)
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

    # --- 会话 Cookie（同域部署，浏览器持有 HttpOnly 会话）---
    # 生产必须为 true（仅 HTTPS 发送）；本地 http 调试设为 false
    COOKIE_SECURE: bool = os.getenv("COOKIE_SECURE", "false").lower() == "true"
    # 留空表示仅当前主机生效；跨子域时填 .example.com
    COOKIE_DOMAIN: Optional[str] = os.getenv("COOKIE_DOMAIN") or None
    # 允许的来源（CSRF Origin 校验与 CORS 共用），逗号分隔
    CORS_ORIGINS: list[str] = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://localhost:8080"
        ).split(",")
        if origin.strip()
    ]

    # ==========================================================================
    # Rate Limiting Configuration (Strict Mode)
    # ==========================================================================
    RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "false").lower() == "true"
    RATE_LIMIT_LOGIN_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_LOGIN_PER_MINUTE", "5"))
    RATE_LIMIT_CONVERSATION_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_CONVERSATION_PER_MINUTE", "30"))
    RATE_LIMIT_GLOBAL_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_GLOBAL_PER_MINUTE", "100"))
    # 后台写操作独立限流：按 admin 账号计（不是 IP），与全局桶分开
    RATE_LIMIT_ADMIN_WRITE_PER_MINUTE: int = int(
        os.getenv("RATE_LIMIT_ADMIN_WRITE_PER_MINUTE", "20")
    )

    # ==========================================================================
    # Security Configuration
    # ==========================================================================
    # Login security: lock account after N failed attempts
    LOGIN_MAX_FAILED_ATTEMPTS: int = int(os.getenv("LOGIN_MAX_FAILED_ATTEMPTS", "5"))
    LOGIN_LOCKOUT_MINUTES: int = int(os.getenv("LOGIN_LOCKOUT_MINUTES", "15"))
    # Input validation limits
    MAX_MESSAGE_LENGTH: int = int(os.getenv("MAX_MESSAGE_LENGTH", "10000"))
    MAX_IMAGE_SIZE_MB: int = int(os.getenv("MAX_IMAGE_SIZE_MB", "5"))
    # Prompt injection protection
    PROMPT_GUARD_ENABLED: bool = os.getenv("PROMPT_GUARD_ENABLED", "true").lower() == "true"

    # --- 双因子（TOTP）---
    # 关掉后：已绑定的账号仍可用动态码登录，但不再强制超管绑定
    TOTP_ENABLED: bool = os.getenv("TOTP_ENABLED", "true").lower() == "true"
    TOTP_ISSUER: str = os.getenv("TOTP_ISSUER", "CookHero")
    # 超管不绑定 TOTP 就拿不到后台数据（仍可登录，以便进入绑定页）
    TOTP_REQUIRED_FOR_SUPER_ADMIN: bool = (
        os.getenv("TOTP_REQUIRED_FOR_SUPER_ADMIN", "true").lower() == "true"
    )
    
    # ==========================================================================
    # Module Configurations
    # ==========================================================================
    # Global LLM provider configuration (layered: fast/normal)
    llm: LLMConfig = load_llm_config()

    # Database configurations (PostgreSQL, Redis, Milvus)
    database: DatabaseConfig = load_database_config()

    # RAG configuration loaded from config.yml
    # Note: RAG reranker api_key may fall back to normal LLM api_key
    rag: RAGConfig = load_rag_config(llm.normal)
    
    # Web Search configuration loaded from config.yml
    web_search: WebSearchConfig = load_web_search_config()

    # Deep Research configuration loaded from config.yml
    deep_research: DeepResearchConfig = load_deep_research_config()
    
    # Vision/Multimodal configuration loaded from config.yml
    vision: VisionConfig = load_vision_config()

    # RAG Evaluation configuration loaded from config.yml
    evaluation: EvaluationConfig = load_evaluation_config()

    # MCP configuration loaded from config.yml
    mcp: MCPConfig = load_mcp_config()

    # Image Generation configuration loaded from config.yml
    image_generation: ImageGenerationConfig = load_image_generation_config()

    # Image Storage configuration loaded from config.yml (imgbb)
    image_storage: ImageStorageConfig = load_image_storage_config()

    # Constraint reasoning configuration loaded from config.yml
    constraint_reasoning: ConstraintReasoningConfig = load_constraint_config()

    # Cost / error-rate alerting (config.yml: alerts)
    alerts: AlertsConfig = load_alerts_config()

    class Config:
        arbitrary_types_allowed = True


# Single global settings instance
settings = Settings()

# Convenience alias for backward compatibility
DefaultRAGConfig = settings.rag
