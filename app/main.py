# app/main.py
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.endpoints import (
    conversation,
    auth,
    personal_docs,
    user,
    evaluation,
    llm_stats,
    agent,
    diet,
    semantic_metrics,
    constraints,
    recipes,
    pantry,
    nutrition,
    family,
    admin,
)
from app.config import settings
from app.database.session import init_db, close_db
from app.database.document_repository import DocumentRepository
from app.services.auth_service import auth_service
from app.services.rag_service import rag_service_instance
from app.security.middleware.rate_limiter import rate_limiter
from app.security.session_cookies import ACCESS_COOKIE
from app.security.token_version import token_version_service
from app.security.sanitizer import setup_secure_logging
from app.security.audit import audit_logger
from app.api import media as media_api
import logging

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Setup secure logging with sensitive data filtering
setup_secure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup/shutdown events."""
    # Startup

    # Security check: Validate JWT secret key
    if not settings.JWT_SECRET_KEY:
        logger.error("SECURITY ERROR: JWT_SECRET_KEY environment variable is not set!")
        logger.error(
            "Please set JWT_SECRET_KEY in your .env file or environment variables."
        )
        raise RuntimeError("JWT_SECRET_KEY must be configured for security")

    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized.")

    # Initialize Agent module (registers default agent, tools, skills)
    logger.info("Initializing Agent module...")
    from app.agent import setup_agent_module, setup_mcp_servers

    setup_agent_module()
    logger.info("Agent module initialized.")

    # Register MCP servers (async)
    logger.info("Registering MCP servers...")
    try:
        await setup_mcp_servers()
        logger.info("MCP servers registered.")
    except Exception as e:
        logger.warning(f"Failed to register MCP servers: {e}")

    # Initialize metadata cache (load all global + user metadata at startup)
    logger.info("Initializing metadata cache...")
    await DocumentRepository.init_all_metadata_cache()
    logger.info("Metadata cache initialized.")

    # Clear Redis cache on startup and initialize rate limiter
    if (
        rag_service_instance.cache_manager
        and rag_service_instance.cache_manager.redis_client
    ):
        # Initialize rate limiter with Redis client
        rate_limiter.set_redis(rag_service_instance.cache_manager.redis_client)
        logger.info("Rate limiter initialized with Redis.")
        # Initialize auth service with Redis client for login tracking
        auth_service.set_redis(rag_service_instance.cache_manager.redis_client)
        logger.info("Auth service initialized with Redis for login tracking.")
        # Token version cache shares the same Redis client
        token_version_service.set_redis(rag_service_instance.cache_manager.redis_client)
        logger.info("Token version cache initialized with Redis.")
        # 告警冷却窗口复用同一 Redis（没有 Redis 时自动回退查库）
        from app.services.alerting_service import alerting_service

        alerting_service.set_redis(rag_service_instance.cache_manager.redis_client)

    from app.services.alerting_service import alerting_service

    await alerting_service.start()

    yield

    await alerting_service.stop()
    # Shutdown
    logger.info("Closing database connections...")
    await close_db()
    logger.info("Database connections closed.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="The backend API for the CookHero intelligent dietary assistant.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware for frontend development
# 允许来源由配置驱动（CORS_ORIGINS），生产只放行正式域名
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


EXEMPT_PATHS = {
    f"{settings.API_V1_STR}/auth/login",
    # 第二步动态码校验：此时用户还没有访问令牌
    f"{settings.API_V1_STR}/auth/login/totp",
    f"{settings.API_V1_STR}/auth/register",
    f"{settings.API_V1_STR}/auth/refresh",
}


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)

    # Security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = (
        "geolocation=(), microphone=(self), camera=()"
    )

    # Add rate limit headers if available
    if hasattr(request.state, "rate_limit_remaining"):
        response.headers["X-RateLimit-Remaining"] = str(
            request.state.rate_limit_remaining
        )
        response.headers["X-RateLimit-Limit"] = str(request.state.rate_limit_limit)

    return response


_ADMIN_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _admin_action_of(route_path: str) -> tuple[str, str]:
    """把路由模板映射成审计动作名，失败记录也能看出「想做什么」。"""
    suffix_map = {
        "/status": ("user.status", "user"),
        "/role": ("user.role", "user"),
        "/reset-password": ("user.reset_password", "user"),
        "/alerts/check": ("alert.check", "alert"),
        "/alerts/test": ("alert.test", "alert"),
    }
    for suffix, mapped in suffix_map.items():
        if route_path.endswith(suffix):
            return mapped
    if route_path.endswith("/users"):
        return "user.create", "user"
    if "/users/{user_id}" in route_path:
        return "user.delete", "user"
    return "admin.write", "admin"


@app.middleware("http")
async def admin_audit_middleware(request: Request, call_next):
    """后台写操作失败也要留痕：记录操作人、目标、错误与请求号。

    成功路径由各端点在同一事务内落审计；这里只兜失败（4xx/5xx），
    因为失败会让业务事务回滚，必须用独立事务写。
    """
    path = request.url.path
    admin_prefix = f"{settings.API_V1_STR}/admin"
    if not path.startswith(admin_prefix) or request.method not in _ADMIN_WRITE_METHODS:
        return await call_next(request)

    response = await call_next(request)
    if response.status_code < 400 or response.status_code == 401:
        return response

    # 读取响应体以拿到 detail（后台写操作都是 JSON，不是流式）
    body = b""
    if hasattr(response, "body_iterator"):
        async for chunk in response.body_iterator:
            body += chunk
    detail_text = ""
    if body:
        try:
            import json as _json

            payload = _json.loads(body.decode("utf-8"))
            detail = payload.get("detail")
            detail_text = detail if isinstance(detail, str) else _json.dumps(
                detail, ensure_ascii=False
            )
        except Exception:
            detail_text = body.decode("utf-8", errors="ignore")

    route = request.scope.get("route")
    route_path = getattr(route, "path", path)
    action, target_type = _admin_action_of(route_path)
    path_params = request.scope.get("path_params") or {}

    from app.api.v1.endpoints.admin import record_failed_action

    await record_failed_action(
        request=request,
        actor_username=getattr(request.state, "username", None),
        actor_id=getattr(request.state, "user_id", None),
        action=action,
        target_type=target_type,
        target_id=path_params.get("user_id"),
        error=detail_text or f"HTTP {response.status_code}",
        detail={"path": path, "method": request.method, "status_code": response.status_code},
    )

    from fastapi.responses import Response

    return Response(
        content=body,
        status_code=response.status_code,
        headers=dict(response.headers),
        media_type=response.media_type,
    )


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Rate limiting middleware using Redis."""
    # Check rate limit
    rate_limit_response = await rate_limiter.check_rate_limit(request)
    if rate_limit_response:
        # Log rate limit exceeded
        denied_limit, denied_current = getattr(
            request.state, "rate_limit_denied", (0, 0)
        )
        audit_logger.rate_limit_exceeded(
            request=request,
            user_id=getattr(request.state, "user_id", None),
            endpoint=str(request.url.path),
            limit=denied_limit,
            current=denied_current,
        )
        return rate_limit_response

    return await call_next(request)


@app.middleware("http")
async def auth_gateway(request: Request, call_next):
    """Simple gateway: require JWT for all routes except login/register/docs/root."""
    path = request.url.path
    if (
        path in EXEMPT_PATHS
        or path == "/"
        or path.startswith("/docs")
        or path.startswith("/redoc")
        or path.startswith("/openapi")
        or path.startswith("/static")
        or path.startswith("/media")
    ):
        return await call_next(request)

    auth_header = request.headers.get("Authorization")
    cookie_token = request.cookies.get(ACCESS_COOKIE)
    token = None
    auth_source = None
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        auth_source = "bearer"
    elif cookie_token:
        token = cookie_token
        auth_source = "cookie"

    if not token:
        return JSONResponse(status_code=401, content={"detail": "需要登录"})

    identity = auth_service.decode_token(token)
    if not identity or not identity.get("username"):
        return JSONResponse(
            status_code=401, content={"detail": "登录已失效，请重新登录"}
        )

    # 令牌版本校验：改密 / 管理员重置 / 主动登出后，旧令牌立即失效
    if not await token_version_service.matches(
        identity.get("user_id"), identity.get("tv")
    ):
        return JSONResponse(
            status_code=401, content={"detail": "登录已失效，请重新登录"}
        )

    # CSRF 防护：Cookie 会自动随请求发送，因此对写操作校验来源。
    # SameSite=Lax 已拦截跨站 POST；这里再对"跨站但已带上 Cookie"的
    # 边缘情况做一层显式校验。
    if auth_source == "cookie" and request.method not in {"GET", "HEAD", "OPTIONS"}:
        if not _same_origin_request(request):
            return JSONResponse(status_code=403, content={"detail": "请求来源不被允许"})

    # Attach user info to request state for downstream use (e.g., filtering by user)
    request.state.username = identity.get("username")
    request.state.user_id = identity.get("user_id")

    return await call_next(request)


def _origin_of(url: str) -> str:
    """scheme://host[:port] for an absolute URL (empty string when invalid)."""
    from urllib.parse import urlsplit

    try:
        parts = urlsplit(url)
    except ValueError:
        return ""
    if not parts.scheme or not parts.netloc:
        return ""
    return f"{parts.scheme}://{parts.netloc}".lower()


def _same_origin_request(request: Request) -> bool:
    """True when Origin/Referer matches the request host or an allowed origin."""
    allowed = {origin.rstrip("/").lower() for origin in settings.CORS_ORIGINS}
    host_origin = _origin_of(str(request.base_url))
    if host_origin:
        allowed.add(host_origin)

    origin = request.headers.get("Origin")
    if origin:
        return origin.rstrip("/").lower() in allowed

    referer = request.headers.get("Referer")
    if referer:
        return _origin_of(referer) in allowed

    # 非浏览器客户端（cURL、脚本）通常不带这两个头。
    # 它们无法被第三方网页借用来发请求，故放行。
    return True


# Include the API routers
app.include_router(media_api.router, tags=["Media"])
app.include_router(
    conversation.router, prefix=settings.API_V1_STR, tags=["Conversation"]
)
app.include_router(auth.router, prefix=settings.API_V1_STR, tags=["Auth"])
app.include_router(user.router, prefix=settings.API_V1_STR, tags=["User"])
app.include_router(
    personal_docs.router, prefix=settings.API_V1_STR, tags=["KnowledgeBase"]
)
app.include_router(evaluation.router, prefix=settings.API_V1_STR, tags=["Evaluation"])
app.include_router(
    llm_stats.router, prefix=settings.API_V1_STR, tags=["LLM Statistics"]
)
app.include_router(agent.router, prefix=settings.API_V1_STR, tags=["Agent"])
app.include_router(diet.router, prefix=settings.API_V1_STR, tags=["Diet"])
app.include_router(recipes.router, prefix=settings.API_V1_STR, tags=["Recipes"])
app.include_router(pantry.router, prefix=settings.API_V1_STR, tags=["Pantry"])
app.include_router(
    nutrition.router, prefix=settings.API_V1_STR, tags=["Nutrition"]
)
app.include_router(family.router, prefix=settings.API_V1_STR, tags=["Family"])
app.include_router(
    semantic_metrics.router,
    prefix=settings.API_V1_STR,
    tags=["Semantic Metrics"],
)
app.include_router(
    constraints.router,
    prefix=settings.API_V1_STR,
    tags=["Constraints"],
)
app.include_router(admin.router, prefix=settings.API_V1_STR, tags=["Admin"])


@app.get("/")
async def root():
    """
    Root endpoint to check API status.
    """
    return {"message": "Welcome to CookHero API!"}
