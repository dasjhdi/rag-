"""Admin console APIs.

Phase v1.1 – v1.3:

Read-only
- ``GET /admin/whoami``          当前账号的角色与可用能力（普通用户也能调用）
- ``GET /admin/overview``        账号 / 内容 / 会话 / Token / 成本总览
- ``GET /admin/users``           用户目录（分页、搜索、每人用量）
- ``GET /admin/usage``           LLM 用量与成本（按天 / 模块 / 模型 / Top 用户）
- ``GET /admin/audit``           后台操作审计
- ``GET /admin/sessions``        Agent 会话列表（排障入口）
- ``GET /admin/sessions/{id}``   会话详情：消息流 + 工具调用轨迹

Write (all audited)
- ``POST /admin/users/{id}/status``          启用 / 禁用
- ``POST /admin/users/{id}/role``            调整角色
- ``POST /admin/users/{id}/reset-password``  重置密码

设计约束
--------
* 账号角色只有三种：user（普通用户）、admin（管理员）、super_admin（超级管理员）。
  只有 admin / super_admin 能进入后台；进入后仍按能力（capability）细分：
  admin 可读数据、看会话、启停与重置**普通用户**；super_admin 额外拥有改角色、
  建号、删号、审计与重置任意密码。
* 每个请求都回查数据库，因此改角色、禁用账号立即生效，无需重新登录。
* 写操作先落审计再返回；危险操作带护栏（不能禁用自己、不能移除最后一个超管）。
* 聚合全部下推 SQL，不做 Python 侧全表遍历。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.agent.database.models import (
    AgentMCPServerModel,
    AgentMessageModel,
    AgentSessionModel,
    AgentSubagentConfigModel,
)
from app.database.models import (
    ADMIN_ROLES,
    AdminAuditLogModel,
    ConversationModel,
    KnowledgeDocumentModel,
    LLMUsageLogModel,
    MessageModel,
    RAGEvaluationModel,
    UserModel,
)
from app.database.session import get_session_context
from app.diet.database.models import (
    DietLogItemModel,
    DietPlanMealModel,
    FamilyMemberModel,
    PantryItemModel,
    RecipeFeedbackModel,
    RecipeReviewModel,
    ShoppingListItemModel,
    UserFoodPreferenceModel,
)
from app.security.admin_rate_limit import admin_rate_limit
from app.services import totp_service
from app.security.token_version import token_version_service
from app.services import pricing

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(admin_rate_limit)],
)

# 能力矩阵：角色 -> 允许的操作。新增能力时只改这一处。
CAPABILITIES: dict[str, frozenset[str]] = {
    # 管理员：只读 + 会话排障 + 管理普通用户（仅限级别低于自己，见 _can_manage_account）
    "admin": frozenset(
        {"read", "sessions", "user_status", "user_password:self_tier"}
    ),
    # 超级管理员：全权
    "super_admin": frozenset(
        {
            "read",
            "sessions",
            "user_status",
            "user_password:all",
            "user_role",
            "user_delete",
            "user_create",
            "audit",
            "alerts",
        }
    ),
}

# 角色级别：用于判定「能否操作某个账号」。普通用户为 0。
ROLE_RANK: dict[str, int] = {
    "user": 0,
    "admin": 1,
    "super_admin": 2,
}

ASSIGNABLE_ROLES = ("user", *sorted(ADMIN_ROLES))
MIN_PASSWORD_LENGTH = 8


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------
async def get_current_user(request: Request) -> UserModel:
    """Load the authenticated user from the DB (401 when missing/disabled)."""
    user_id = getattr(request.state, "user_id", None)
    username = getattr(request.state, "username", None)

    if not user_id and not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="需要登录")

    async with get_session_context() as session:
        stmt = (
            select(UserModel).where(UserModel.id == user_id)
            if user_id
            else select(UserModel).where(UserModel.username == username)
        )
        try:
            user = (await session.execute(stmt)).scalar_one_or_none()
        except Exception:  # malformed uuid in an old token
            user = None

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")
    return user


def _assert_totp_policy(user: UserModel) -> None:
    """超管未绑定双因子时，后台 API 一律拒绝（前端据此只显示绑定页）。

    细节用结构化 detail 返回，前端可以按 code 分支，而不用匹配中文文案。
    """
    if totp_service.is_required_for(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "totp_setup_required",
                "message": "超级管理员需先绑定双因子（TOTP）才能访问后台数据",
            },
        )


async def require_admin(user: UserModel = Depends(get_current_user)) -> UserModel:
    """Any admin role passes."""
    if user.role not in ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无后台访问权限")
    _assert_totp_policy(user)
    return user


def require_capability(capability: str):
    """Dependency factory: require a specific capability."""

    async def _dep(user: UserModel = Depends(require_admin)) -> UserModel:
        allowed = CAPABILITIES.get(user.role, frozenset())
        if capability not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"当前角色（{user.role}）无此操作权限：{capability}",
            )
        return user

    # Expose the requirement for introspection: route-level tests assert that
    # every operations endpoint is guarded and which capability it requires.
    _dep.capability = capability  # type: ignore[attr-defined]
    return _dep


def require_password_reset(user: UserModel = Depends(require_admin)) -> UserModel:
    """重置密码的能力入口：超管持 :all，ops 持 :self_tier。

    两者共用同一端点，具体到「能操作哪个账号」由 _can_manage_account 判定。
    """
    allowed = CAPABILITIES.get(user.role, frozenset())
    if not ({"user_password:all", "user_password:self_tier"} & allowed):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"当前角色（{user.role}）无此操作权限：user_password",
        )
    return user


def _can_manage_account(admin: UserModel, target: UserModel) -> bool:
    """是否允许操作目标账号。

    规则：超级管理员不受级别限制；管理员只能操作**严格低于**自己级别的账号，
    即只能动普通用户，不能动其他管理员或超管，堵住「重置同级/超管密码后登录」
    的提权路径。
    """
    if admin.role == "super_admin":
        return True
    return ROLE_RANK.get(target.role, 0) < ROLE_RANK.get(admin.role, 0)


def _assert_can_manage_account(
    admin: UserModel, target: UserModel, action: str
) -> None:
    if not _can_manage_account(admin, target):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"不能{action}同级或更高级别的账号"
                f"（当前 {admin.role} → 目标 {target.role}）"
            ),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _utcnow() -> datetime:
    """Naive UTC, matching how timestamps are stored."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host if request.client else None


async def _scalar(session: AsyncSession, stmt) -> int:
    value = (await session.execute(stmt)).scalar()
    return int(value or 0)


def _request_id(request: Request) -> str:
    """优先复用上游传入的请求号，便于和应用日志对齐。"""
    incoming = request.headers.get("X-Request-ID") or request.headers.get("X-Request-Id")
    if incoming:
        return incoming.strip()[:64]
    return uuid.uuid4().hex[:16]


def _user_agent(request: Request) -> Optional[str]:
    value = request.headers.get("User-Agent")
    return value.strip()[:300] if value else None


async def _audit(
    session: AsyncSession,
    actor: UserModel,
    request: Request,
    action: str,
    target_type: str,
    target_id: Optional[str],
    detail: Optional[dict] = None,
    *,
    before: Optional[dict] = None,
    after: Optional[dict] = None,
    success: bool = True,
    error: Optional[str] = None,
) -> None:
    """Append an audit record. Callers write it in the same transaction."""
    session.add(
        AdminAuditLogModel(
            actor_id=str(actor.id),
            actor_username=actor.username,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=detail,
            before=before,
            after=after,
            success=success,
            error=(error or None) and error[:300],
            request_id=_request_id(request),
            user_agent=_user_agent(request),
            ip=_client_ip(request),
        )
    )


async def record_failed_action(
    *,
    request: Request,
    actor_username: Optional[str],
    actor_id: Optional[str],
    action: str,
    target_type: str,
    target_id: Optional[str],
    error: str,
    detail: Optional[dict] = None,
) -> None:
    """失败路径的审计：独立事务写入，避免随业务事务一起回滚。

    由 main.py 的中间件在 ``/api/v1/admin`` 写操作返回 4xx/5xx 时调用。
    """
    try:
        async with get_session_context() as session:
            session.add(
                AdminAuditLogModel(
                    actor_id=str(actor_id) if actor_id else None,
                    actor_username=actor_username or "anonymous",
                    action=action,
                    target_type=target_type,
                    target_id=target_id,
                    detail=detail,
                    success=False,
                    error=(error or "")[:300],
                    request_id=_request_id(request),
                    user_agent=_user_agent(request),
                    ip=_client_ip(request),
                )
            )
    except Exception as exc:  # 审计失败不能影响主响应
        logger.warning("Failed to record admin failure audit: %s", exc)


def _serialize_user(user: UserModel, counts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    user_counts = counts.get(str(user.id), {})
    return {
        "id": str(user.id),
        "username": user.username,
        "role": user.role,
        "is_active": bool(user.is_active),
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "occupation": user.occupation,
        "counts": {
            "conversations": int(user_counts.get("conversations", 0)),
            "agent_sessions": int(user_counts.get("agent_sessions", 0)),
            "diet_log_items": int(user_counts.get("diet_log_items", 0)),
            "pantry_items": int(user_counts.get("pantry_items", 0)),
            "llm_calls": int(user_counts.get("llm_calls", 0)),
            "tokens": int(user_counts.get("tokens", 0)),
        },
    }


async def _active_super_admin_count(session: AsyncSession, exclude_id: Optional[str] = None) -> int:
    stmt = (
        select(func.count())
        .select_from(UserModel)
        .where(UserModel.role == "super_admin")
        .where(UserModel.is_active.is_(True))
    )
    if exclude_id:
        stmt = stmt.where(UserModel.id != exclude_id)
    return await _scalar(session, stmt)


async def _get_target_user(session: AsyncSession, user_id: str) -> UserModel:
    try:
        user = (
            await session.execute(select(UserModel).where(UserModel.id == user_id))
        ).scalar_one_or_none()
    except Exception:
        user = None
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return user


# ---------------------------------------------------------------------------
# GET /admin/whoami  (any logged-in user)
# ---------------------------------------------------------------------------
@router.get("/whoami")
async def whoami(user: UserModel = Depends(get_current_user)) -> dict[str, Any]:
    """Return the current role so the frontend can decide whether to show the entry."""
    return {
        "username": user.username,
        "role": user.role,
        "is_admin": user.role in ADMIN_ROLES,
        "capabilities": sorted(CAPABILITIES.get(user.role, frozenset())),
    }


# ---------------------------------------------------------------------------
# GET /admin/overview
# ---------------------------------------------------------------------------
@router.get("/overview")
async def get_overview(
    admin: UserModel = Depends(require_capability("read")),
) -> dict[str, Any]:
    """Top-line counters, including today's estimated spend."""
    now = _utcnow()
    since_7d = now - timedelta(days=7)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    async with get_session_context() as session:
        total_users = await _scalar(session, select(func.count()).select_from(UserModel))
        active_users = await _scalar(
            session, select(func.count()).select_from(UserModel).where(UserModel.is_active.is_(True))
        )
        admin_users = await _scalar(
            session,
            select(func.count()).select_from(UserModel).where(UserModel.role.in_(tuple(ADMIN_ROLES))),
        )
        new_users_7d = await _scalar(
            session,
            select(func.count()).select_from(UserModel).where(UserModel.created_at >= since_7d),
        )
        logged_in_7d = await _scalar(
            session,
            select(func.count()).select_from(UserModel).where(UserModel.last_login_at >= since_7d),
        )

        conversations = await _scalar(session, select(func.count()).select_from(ConversationModel))
        agent_sessions = await _scalar(session, select(func.count()).select_from(AgentSessionModel))

        diet_logs = await _scalar(session, select(func.count()).select_from(DietLogItemModel))
        pantry_items = await _scalar(session, select(func.count()).select_from(PantryItemModel))
        feedbacks = await _scalar(session, select(func.count()).select_from(RecipeFeedbackModel))

        global_docs = await _scalar(
            session,
            select(func.count())
            .select_from(KnowledgeDocumentModel)
            .where(KnowledgeDocumentModel.user_id.is_(None)),
        )
        personal_docs = await _scalar(
            session,
            select(func.count())
            .select_from(KnowledgeDocumentModel)
            .where(KnowledgeDocumentModel.user_id.is_not(None)),
        )

        calls_today = await _scalar(
            session,
            select(func.count())
            .select_from(LLMUsageLogModel)
            .where(LLMUsageLogModel.created_at >= today_start),
        )
        tokens_today = await _scalar(
            session,
            select(func.coalesce(func.sum(LLMUsageLogModel.total_tokens), 0)).where(
                LLMUsageLogModel.created_at >= today_start
            ),
        )
        calls_7d = await _scalar(
            session,
            select(func.count())
            .select_from(LLMUsageLogModel)
            .where(LLMUsageLogModel.created_at >= since_7d),
        )
        tokens_7d = await _scalar(
            session,
            select(func.coalesce(func.sum(LLMUsageLogModel.total_tokens), 0)).where(
                LLMUsageLogModel.created_at >= since_7d
            ),
        )

        # Cost grouped by model so per-model pricing applies.
        cost_rows_today = (
            await session.execute(
                select(
                    LLMUsageLogModel.model_name,
                    func.coalesce(func.sum(LLMUsageLogModel.input_tokens), 0),
                    func.coalesce(func.sum(LLMUsageLogModel.output_tokens), 0),
                )
                .where(LLMUsageLogModel.created_at >= today_start)
                .group_by(LLMUsageLogModel.model_name)
            )
        ).all()
        cost_today = round(
            sum(pricing.estimate_cost(model, i, o) for model, i, o in cost_rows_today), 4
        )

        cost_rows_7d = (
            await session.execute(
                select(
                    LLMUsageLogModel.model_name,
                    func.coalesce(func.sum(LLMUsageLogModel.input_tokens), 0),
                    func.coalesce(func.sum(LLMUsageLogModel.output_tokens), 0),
                )
                .where(LLMUsageLogModel.created_at >= since_7d)
                .group_by(LLMUsageLogModel.model_name)
            )
        ).all()
        cost_7d = round(
            sum(pricing.estimate_cost(model, i, o) for model, i, o in cost_rows_7d), 4
        )

    return {
        "generated_at": now.isoformat(),
        "users": {
            "total": total_users,
            "active": active_users,
            "admins": admin_users,
            "new_7d": new_users_7d,
            "logged_in_7d": logged_in_7d,
        },
        "content": {
            "global_documents": global_docs,
            "personal_documents": personal_docs,
        },
        "activity": {
            "conversations": conversations,
            "agent_sessions": agent_sessions,
            "diet_log_items": diet_logs,
            "pantry_items": pantry_items,
            "recipe_feedback": feedbacks,
        },
        "llm": {
            "calls_today": calls_today,
            "tokens_today": tokens_today,
            "calls_7d": calls_7d,
            "tokens_7d": tokens_7d,
            "cost_today": cost_today,
            "cost_7d": cost_7d,
            "currency": pricing.currency(),
        },
    }


# ---------------------------------------------------------------------------
# GET /admin/users
# ---------------------------------------------------------------------------
@router.get("/users")
async def list_users(
    admin: UserModel = Depends(require_capability("read")),
    q: Optional[str] = Query(None, description="按用户名模糊搜索"),
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    sort: str = Query("created_at", pattern="^(created_at|last_login_at|username)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
) -> dict[str, Any]:
    """Paginated user directory with per-user activity counters."""
    offset = (page - 1) * page_size

    async with get_session_context() as session:
        base = select(UserModel)
        count_stmt = select(func.count()).select_from(UserModel)

        keyword = (q or "").strip()
        if keyword:
            pattern = f"%{keyword}%"
            base = base.where(UserModel.username.ilike(pattern))
            count_stmt = count_stmt.where(UserModel.username.ilike(pattern))

        total = await _scalar(session, count_stmt)

        sort_col = {
            "created_at": UserModel.created_at,
            "last_login_at": UserModel.last_login_at,
            "username": UserModel.username,
        }[sort]
        base = base.order_by(sort_col.desc() if order == "desc" else sort_col.asc())

        users = list((await session.execute(base.offset(offset).limit(page_size))).scalars())
        user_ids = [str(u.id) for u in users]

        counts: dict[str, dict[str, Any]] = {}
        if user_ids:

            def _merge(rows, key: str) -> None:
                for uid, value in rows:
                    if uid is None:
                        continue
                    counts.setdefault(str(uid), {})[key] = value

            _merge(
                (
                    await session.execute(
                        select(ConversationModel.user_id, func.count())
                        .where(ConversationModel.user_id.in_(user_ids))
                        .group_by(ConversationModel.user_id)
                    )
                ).all(),
                "conversations",
            )
            _merge(
                (
                    await session.execute(
                        select(AgentSessionModel.user_id, func.count())
                        .where(AgentSessionModel.user_id.in_(user_ids))
                        .group_by(AgentSessionModel.user_id)
                    )
                ).all(),
                "agent_sessions",
            )
            _merge(
                (
                    await session.execute(
                        select(DietLogItemModel.user_id, func.count())
                        .where(DietLogItemModel.user_id.in_(user_ids))
                        .group_by(DietLogItemModel.user_id)
                    )
                ).all(),
                "diet_log_items",
            )
            _merge(
                (
                    await session.execute(
                        select(PantryItemModel.user_id, func.count())
                        .where(PantryItemModel.user_id.in_(user_ids))
                        .group_by(PantryItemModel.user_id)
                    )
                ).all(),
                "pantry_items",
            )
            _merge(
                (
                    await session.execute(
                        select(LLMUsageLogModel.user_id, func.count())
                        .where(LLMUsageLogModel.user_id.in_(user_ids))
                        .group_by(LLMUsageLogModel.user_id)
                    )
                ).all(),
                "llm_calls",
            )
            _merge(
                (
                    await session.execute(
                        select(
                            LLMUsageLogModel.user_id,
                            func.coalesce(func.sum(LLMUsageLogModel.total_tokens), 0),
                        )
                        .where(LLMUsageLogModel.user_id.in_(user_ids))
                        .group_by(LLMUsageLogModel.user_id)
                    )
                ).all(),
                "tokens",
            )

    return {
        "items": [_serialize_user(u, counts) for u in users],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if page_size else 0,
    }


# ---------------------------------------------------------------------------
# POST /admin/users/{id}/status
# ---------------------------------------------------------------------------
class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=MIN_PASSWORD_LENGTH, max_length=128)
    role: str = "user"


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: CreateUserRequest,
    request: Request,
    admin: UserModel = Depends(require_capability("user_create")),
) -> dict[str, Any]:
    """由超管直接创建账号（可选初始角色）。

    与公开注册接口的区别：可以指定角色、不受注册开关/登录限流影响，并写审计。
    """
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="用户名不能为空")
    if payload.role not in ASSIGNABLE_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"角色不合法，可选值：{', '.join(ASSIGNABLE_ROLES)}",
        )
    # 纵深防御：非超管即便拿到能力也不能创建超管
    if payload.role == "super_admin" and admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="只有超级管理员可以创建超级管理员")

    async with get_session_context() as session:
        existing = (
            await session.execute(
                select(UserModel).where(UserModel.username == username)
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="用户名已存在"
            )

        user = UserModel(
            username=username,
            password_hash=bcrypt.hashpw(
                payload.password.encode("utf-8"), bcrypt.gensalt()
            ).decode("utf-8"),
            role=payload.role,
            is_active=True,
        )
        session.add(user)
        await _audit(
            session,
            admin,
            request,
            action="user.create",
            target_type="user",
            target_id=str(user.id),
            detail={"username": username, "role": payload.role},
            after={"username": username, "role": payload.role, "is_active": True},
        )
        await session.flush()

    logger.info("Admin %s created user %s (role=%s)", admin.username, username, payload.role)
    return {
        "id": str(user.id),
        "username": user.username,
        "role": user.role,
        "is_active": bool(user.is_active),
    }


class UserStatusRequest(BaseModel):
    is_active: bool


@router.post("/users/{user_id}/status")
async def set_user_status(
    user_id: str,
    payload: UserStatusRequest,
    request: Request,
    admin: UserModel = Depends(require_capability("user_status")),
) -> dict[str, Any]:
    """Enable or disable an account. Disabled accounts cannot log in."""
    async with get_session_context() as session:
        target = await _get_target_user(session, user_id)

        if str(target.id) == str(admin.id) and not payload.is_active:
            raise HTTPException(status_code=400, detail="不能禁用当前登录的账号")
        # 与重置密码同一条级别规则：管理员不能动管理员/超管
        _assert_can_manage_account(admin, target, "启用或禁用")
        if target.role == "super_admin" and not payload.is_active:
            remaining = await _active_super_admin_count(session, exclude_id=str(target.id))
            if remaining < 1:
                raise HTTPException(status_code=400, detail="系统至少需要保留一个可用的超级管理员")

        before = bool(target.is_active)
        target.is_active = payload.is_active
        await _audit(
            session,
            admin,
            request,
            action="user.enable" if payload.is_active else "user.disable",
            target_type="user",
            target_id=str(target.id),
            detail={"username": target.username},
            before={"is_active": before},
            after={"is_active": payload.is_active},
        )
        await session.flush()

    return {"id": user_id, "is_active": payload.is_active}


# ---------------------------------------------------------------------------
# POST /admin/users/{id}/role
# ---------------------------------------------------------------------------
class UserRoleRequest(BaseModel):
    role: str


@router.post("/users/{user_id}/role")
async def set_user_role(
    user_id: str,
    payload: UserRoleRequest,
    request: Request,
    admin: UserModel = Depends(require_capability("user_role")),
) -> dict[str, Any]:
    """Change a user's role. Only super_admin may call this."""
    new_role = (payload.role or "").strip()
    if new_role not in ASSIGNABLE_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"role 必须是 {', '.join(ASSIGNABLE_ROLES)} 之一",
        )

    async with get_session_context() as session:
        target = await _get_target_user(session, user_id)

        if str(target.id) == str(admin.id) and new_role != "super_admin":
            raise HTTPException(status_code=400, detail="不能降低当前登录账号的权限")
        if target.role == "super_admin" and new_role != "super_admin":
            remaining = await _active_super_admin_count(session, exclude_id=str(target.id))
            if remaining < 1:
                raise HTTPException(status_code=400, detail="系统至少需要保留一个超级管理员")

        before = target.role
        target.role = new_role
        await _audit(
            session,
            admin,
            request,
            action="user.role",
            target_type="user",
            target_id=str(target.id),
            detail={"username": target.username},
            before={"role": before},
            after={"role": new_role},
        )
        await session.flush()

    return {"id": user_id, "role": new_role}


# ---------------------------------------------------------------------------
# POST /admin/users/{id}/reset-password
# ---------------------------------------------------------------------------
class ResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=MIN_PASSWORD_LENGTH)


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: str,
    payload: ResetPasswordRequest,
    request: Request,
    admin: UserModel = Depends(require_password_reset),
) -> dict[str, Any]:
    """Reset a password and revoke every token already issued to that user.

    ops 只能重置级别更低的账号；超管（user_password:all）不受限制。
    """
    async with get_session_context() as session:
        target = await _get_target_user(session, user_id)
        _assert_can_manage_account(admin, target, "重置密码")

        target.password_hash = bcrypt.hashpw(
            payload.new_password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")
        # 递增令牌版本，使旧令牌立即失效（改密即登出所有设备）
        old_version = int(getattr(target, "token_version", 0) or 0)
        target.token_version = old_version + 1
        await _audit(
            session,
            admin,
            request,
            action="user.reset_password",
            target_type="user",
            target_id=str(target.id),
            detail={"username": target.username, "tokens_revoked": True},
            before={"token_version": old_version},
            after={"token_version": old_version + 1},
        )
        await session.flush()

    # 同步刷新缓存，避免旧版本短时间内仍被命中
    await token_version_service.set_cached(user_id, int(target.token_version))

    return {
        "id": user_id,
        "reset": True,
        "note": "已重置，该用户此前签发的令牌已失效。",
    }


# ---------------------------------------------------------------------------
# DELETE /admin/users/{id}
# ---------------------------------------------------------------------------
async def _owned_data_counts(session: AsyncSession, user_id: Any) -> dict[str, int]:
    """统计账号名下的数据量，用于删除前确认与审计留痕。"""
    uid = str(user_id)
    conv_ids = (
        (
            await session.execute(
                select(ConversationModel.id).where(ConversationModel.user_id == uid)
            )
        )
        .scalars()
        .all()
    )
    session_ids = (
        (
            await session.execute(
                select(AgentSessionModel.id).where(AgentSessionModel.user_id == uid)
            )
        )
        .scalars()
        .all()
    )

    async def count(model: Any, condition: Any) -> int:
        result = await session.execute(
            select(func.count()).select_from(model).where(condition)
        )
        return int(result.scalar_one())

    counts = {
        "conversations": len(conv_ids),
        "messages": (
            await count(MessageModel, MessageModel.conversation_id.in_(conv_ids))
            if conv_ids
            else 0
        ),
        "agent_sessions": len(session_ids),
        "agent_messages": (
            await count(AgentMessageModel, AgentMessageModel.session_id.in_(session_ids))
            if session_ids
            else 0
        ),
        "knowledge_documents": await count(
            KnowledgeDocumentModel, KnowledgeDocumentModel.user_id == user_id
        ),
        "diet_log_items": await count(DietLogItemModel, DietLogItemModel.user_id == uid),
        "diet_plan_meals": await count(
            DietPlanMealModel, DietPlanMealModel.user_id == uid
        ),
        "pantry_items": await count(PantryItemModel, PantryItemModel.user_id == uid),
        "shopping_list_items": await count(
            ShoppingListItemModel, ShoppingListItemModel.user_id == uid
        ),
        "family_members": await count(
            FamilyMemberModel, FamilyMemberModel.owner_user_id == uid
        ),
        "recipe_feedback": await count(
            RecipeFeedbackModel, RecipeFeedbackModel.user_id == uid
        ),
        "recipe_reviews": await count(
            RecipeReviewModel, RecipeReviewModel.user_id == uid
        ),
        "llm_usage_logs": await count(LLMUsageLogModel, LLMUsageLogModel.user_id == uid),
    }
    return counts


_COUNT_LABELS = {
    "conversations": "会话",
    "messages": "消息",
    "agent_sessions": "Agent 会话",
    "agent_messages": "Agent 消息",
    "knowledge_documents": "知识库文档",
    "diet_log_items": "饮食记录",
    "diet_plan_meals": "饮食计划餐次",
    "pantry_items": "库存条目",
    "shopping_list_items": "采购清单项",
    "family_members": "家庭成员",
    "recipe_feedback": "菜谱反馈",
    "recipe_reviews": "菜谱评价",
    "llm_usage_logs": "用量日志",
}


def _describe_counts(counts: dict[str, int]) -> str:
    parts = [
        f"{_COUNT_LABELS.get(key, key)} {value}"
        for key, value in counts.items()
        if value
    ]
    return "、".join(parts)


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    request: Request,
    force: bool = Query(
        False, description="true 时连带删除该账号名下全部数据；false 遇到有数据则拒绝"
    ),
    admin: UserModel = Depends(require_capability("user_delete")),
) -> dict[str, Any]:
    """删除账号。

    默认保守：账号名下有数据时返回 409，避免误删；
    确认后传 ``force=true``，在同一事务内按依赖顺序清理数据再删除账号。
    """
    async with get_session_context() as session:
        target = await _get_target_user(session, user_id)

        if str(target.id) == str(admin.id):
            raise HTTPException(status_code=400, detail="不能删除当前登录的账号")
        _assert_can_manage_account(admin, target, "删除")
        if target.role == "super_admin":
            remaining = await _active_super_admin_count(
                session, exclude_id=str(target.id)
            )
            if remaining < 1:
                raise HTTPException(
                    status_code=400, detail="系统至少需要保留一个可用的超级管理员"
                )

        counts = await _owned_data_counts(session, target.id)
        owned = {key: value for key, value in counts.items() if value}
        if owned and not force:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"该账号名下仍有数据：{_describe_counts(owned)}。"
                    "请改用禁用账号，或确认后传 force=true 连带删除。"
                ),
            )

        uid = str(target.id)
        conv_ids = (
            (
                await session.execute(
                    select(ConversationModel.id).where(ConversationModel.user_id == uid)
                )
            )
            .scalars()
            .all()
        )
        session_ids = (
            (
                await session.execute(
                    select(AgentSessionModel.id).where(
                        AgentSessionModel.user_id == uid
                    )
                )
            )
            .scalars()
            .all()
        )

        # 按依赖顺序清理（除 knowledge_documents 外，其余外键关系在库层面未声明）
        if conv_ids:
            await session.execute(
                delete(MessageModel).where(MessageModel.conversation_id.in_(conv_ids))
            )
        await session.execute(
            delete(RAGEvaluationModel).where(RAGEvaluationModel.user_id == uid)
        )
        await session.execute(
            delete(ConversationModel).where(ConversationModel.user_id == uid)
        )
        if session_ids:
            await session.execute(
                delete(AgentMessageModel).where(
                    AgentMessageModel.session_id.in_(session_ids)
                )
            )
        await session.execute(
            delete(AgentSessionModel).where(AgentSessionModel.user_id == uid)
        )
        for model, column in (
            (AgentMCPServerModel, AgentMCPServerModel.user_id),
            (AgentSubagentConfigModel, AgentSubagentConfigModel.user_id),
            (DietLogItemModel, DietLogItemModel.user_id),
            (DietPlanMealModel, DietPlanMealModel.user_id),
            (PantryItemModel, PantryItemModel.user_id),
            (ShoppingListItemModel, ShoppingListItemModel.user_id),
            (UserFoodPreferenceModel, UserFoodPreferenceModel.user_id),
            (RecipeFeedbackModel, RecipeFeedbackModel.user_id),
            (RecipeReviewModel, RecipeReviewModel.user_id),
            (LLMUsageLogModel, LLMUsageLogModel.user_id),
            (FamilyMemberModel, FamilyMemberModel.owner_user_id),
        ):
            await session.execute(delete(model).where(column == uid))

        # knowledge_documents.user_id 是 uuid 类型（且带 ON DELETE CASCADE），单独处理
        await session.execute(
            delete(KnowledgeDocumentModel).where(
                KnowledgeDocumentModel.user_id == target.id
            )
        )

        await session.execute(delete(UserModel).where(UserModel.id == target.id))
        await _audit(
            session,
            admin,
            request,
            action="user.delete",
            target_type="user",
            target_id=uid,
            detail={
                "username": target.username,
                "role": target.role,
                "force": force,
                "counts": counts,
            },
            before={
                "username": target.username,
                "role": target.role,
                "is_active": bool(target.is_active),
            },
        )
        await session.flush()

    logger.info("Admin %s deleted user %s (force=%s)", admin.username, uid, force)
    return {
        "id": user_id,
        "deleted": True,
        "counts": counts,
    }



# ---------------------------------------------------------------------------
# GET /admin/audit
# ---------------------------------------------------------------------------
@router.get("/audit")
async def list_audit(
    admin: UserModel = Depends(require_capability("audit")),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action: Optional[str] = Query(None, description="按动作前缀过滤，如 user."),
    success: Optional[bool] = Query(None, description="只看成功/失败"),
    actor: Optional[str] = Query(None, description="按操作人用户名过滤"),
) -> dict[str, Any]:
    """Paginated audit trail, newest first. 失败记录同样可查。"""
    offset = (page - 1) * page_size
    conditions = []
    if action:
        conditions.append(AdminAuditLogModel.action.like(f"{action}%"))
    if success is not None:
        conditions.append(AdminAuditLogModel.success.is_(success))
    if actor:
        conditions.append(AdminAuditLogModel.actor_username == actor)

    async with get_session_context() as session:
        count_stmt = select(func.count()).select_from(AdminAuditLogModel)
        rows_stmt = select(AdminAuditLogModel)
        for condition in conditions:
            count_stmt = count_stmt.where(condition)
            rows_stmt = rows_stmt.where(condition)
        total = await _scalar(session, count_stmt)
        rows = list(
            (
                await session.execute(
                    rows_stmt.order_by(AdminAuditLogModel.created_at.desc())
                    .offset(offset)
                    .limit(page_size)
                )
            ).scalars()
        )
    return {
        "items": [r.to_dict() for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if page_size else 0,
    }


# ---------------------------------------------------------------------------
# GET /admin/sessions
# ---------------------------------------------------------------------------
@router.get("/sessions")
async def list_sessions(
    admin: UserModel = Depends(require_capability("sessions")),
    q: Optional[str] = Query(None, description="按会话标题模糊搜索"),
    days: int = Query(30, ge=1, le=365),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """Agent sessions, newest first — the entry point for troubleshooting."""
    offset = (page - 1) * page_size
    since = _utcnow() - timedelta(days=days)
    keyword = (q or "").strip()

    async with get_session_context() as session:
        base = select(AgentSessionModel).where(AgentSessionModel.updated_at >= since)
        count_stmt = (
            select(func.count())
            .select_from(AgentSessionModel)
            .where(AgentSessionModel.updated_at >= since)
        )
        if keyword:
            pattern = f"%{keyword}%"
            base = base.where(AgentSessionModel.title.ilike(pattern))
            count_stmt = count_stmt.where(AgentSessionModel.title.ilike(pattern))

        total = await _scalar(session, count_stmt)
        sessions = list(
            (
                await session.execute(
                    base.order_by(AgentSessionModel.updated_at.desc())
                    .offset(offset)
                    .limit(page_size)
                )
            ).scalars()
        )

        session_ids = [s.id for s in sessions]
        user_ids = list({s.user_id for s in sessions if s.user_id})

        message_counts: dict[str, int] = {}
        if session_ids:
            for sid, cnt in (
                await session.execute(
                    select(AgentMessageModel.session_id, func.count())
                    .where(AgentMessageModel.session_id.in_(session_ids))
                    .group_by(AgentMessageModel.session_id)
                )
            ).all():
                message_counts[str(sid)] = int(cnt)

        name_map: dict[str, str] = {}
        if user_ids:
            for uid, uname in (
                await session.execute(
                    select(UserModel.id, UserModel.username).where(UserModel.id.in_(user_ids))
                )
            ).all():
                name_map[str(uid)] = uname

    items = []
    for s in sessions:
        items.append(
            {
                "id": str(s.id),
                "user_id": s.user_id,
                "username": name_map.get(str(s.user_id), "已删除用户"),
                "title": s.title or "未命名会话",
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
                "message_count": message_counts.get(str(s.id), 0),
                "compressed": bool(s.compressed_summary),
            }
        )

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if page_size else 0,
    }


# ---------------------------------------------------------------------------
# GET /admin/sessions/{id}
# ---------------------------------------------------------------------------
@router.get("/sessions/{session_id}")
async def get_session_detail(
    session_id: str,
    admin: UserModel = Depends(require_capability("sessions")),
) -> dict[str, Any]:
    """Full message flow with tool-call traces, for one Agent session."""
    async with get_session_context() as session:
        try:
            agent_session = (
                await session.execute(
                    select(AgentSessionModel).where(AgentSessionModel.id == session_id)
                )
            ).scalar_one_or_none()
        except Exception:
            agent_session = None
        if agent_session is None:
            raise HTTPException(status_code=404, detail="会话不存在")

        messages = list(
            (
                await session.execute(
                    select(AgentMessageModel)
                    .where(AgentMessageModel.session_id == agent_session.id)
                    .order_by(AgentMessageModel.created_at.asc())
                )
            ).scalars()
        )

        username = "已删除用户"
        if agent_session.user_id:
            row = (
                await session.execute(
                    select(UserModel.username).where(UserModel.id == agent_session.user_id)
                )
            ).scalar_one_or_none()
            if row:
                username = row

    def _trim(text: Optional[str], limit: int = 4000) -> str:
        if not text:
            return ""
        return text if len(text) <= limit else text[:limit] + f"\n…（已截断，原长 {len(text)} 字符）"

    payload = []
    for m in messages:
        payload.append(
            {
                "id": str(m.id),
                "role": m.role,
                "content": _trim(m.content),
                "tool_name": m.tool_name,
                "tool_calls": m.tool_calls,
                "trace": m.trace,
                "thinking_ms": m.thinking_duration_ms,
                "answer_ms": m.answer_duration_ms,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
        )

    return {
        "id": str(agent_session.id),
        "username": username,
        "user_id": agent_session.user_id,
        "title": agent_session.title or "未命名会话",
        "created_at": agent_session.created_at.isoformat() if agent_session.created_at else None,
        "updated_at": agent_session.updated_at.isoformat() if agent_session.updated_at else None,
        "messages": payload,
    }


# ---------------------------------------------------------------------------
# GET /admin/usage
# ---------------------------------------------------------------------------
@router.get("/usage")
async def get_usage(
    admin: UserModel = Depends(require_capability("read")),
    days: int = Query(7, ge=1, le=90, description="统计最近 N 天"),
) -> dict[str, Any]:
    """LLM usage with estimated cost, by day / module / model / top users."""
    since = _utcnow() - timedelta(days=days)

    async with get_session_context() as session:
        total_calls = await _scalar(
            session,
            select(func.count())
            .select_from(LLMUsageLogModel)
            .where(LLMUsageLogModel.created_at >= since),
        )
        totals_row = (
            await session.execute(
                select(
                    func.coalesce(func.sum(LLMUsageLogModel.input_tokens), 0),
                    func.coalesce(func.sum(LLMUsageLogModel.output_tokens), 0),
                    func.coalesce(func.sum(LLMUsageLogModel.total_tokens), 0),
                    func.coalesce(func.avg(LLMUsageLogModel.duration_ms), 0),
                ).where(LLMUsageLogModel.created_at >= since)
            )
        ).one()

        daily_rows = (
            await session.execute(
                select(
                    func.date(LLMUsageLogModel.created_at).label("day"),
                    func.count().label("calls"),
                    func.coalesce(func.sum(LLMUsageLogModel.total_tokens), 0).label("tokens"),
                )
                .where(LLMUsageLogModel.created_at >= since)
                .group_by(func.date(LLMUsageLogModel.created_at))
                .order_by(func.date(LLMUsageLogModel.created_at))
            )
        ).all()

        module_rows = (
            await session.execute(
                select(
                    LLMUsageLogModel.module_name,
                    func.count().label("calls"),
                    func.coalesce(func.sum(LLMUsageLogModel.total_tokens), 0).label("tokens"),
                )
                .where(LLMUsageLogModel.created_at >= since)
                .group_by(LLMUsageLogModel.module_name)
                .order_by(func.count().desc())
            )
        ).all()

        model_rows = (
            await session.execute(
                select(
                    LLMUsageLogModel.model_name,
                    func.count().label("calls"),
                    func.coalesce(func.sum(LLMUsageLogModel.input_tokens), 0).label("in_tokens"),
                    func.coalesce(func.sum(LLMUsageLogModel.output_tokens), 0).label("out_tokens"),
                )
                .where(LLMUsageLogModel.created_at >= since)
                .group_by(LLMUsageLogModel.model_name)
                .order_by(func.count().desc())
            )
        ).all()

        # Daily cost needs the (day, model) split to apply per-model pricing.
        daily_cost_rows = (
            await session.execute(
                select(
                    func.date(LLMUsageLogModel.created_at).label("day"),
                    LLMUsageLogModel.model_name,
                    func.coalesce(func.sum(LLMUsageLogModel.input_tokens), 0),
                    func.coalesce(func.sum(LLMUsageLogModel.output_tokens), 0),
                )
                .where(LLMUsageLogModel.created_at >= since)
                .group_by(func.date(LLMUsageLogModel.created_at), LLMUsageLogModel.model_name)
            )
        ).all()

        top_rows = (
            await session.execute(
                select(
                    LLMUsageLogModel.user_id,
                    func.count().label("calls"),
                    func.coalesce(func.sum(LLMUsageLogModel.total_tokens), 0).label("tokens"),
                )
                .where(LLMUsageLogModel.created_at >= since)
                .where(LLMUsageLogModel.user_id.is_not(None))
                .group_by(LLMUsageLogModel.user_id)
                .order_by(func.coalesce(func.sum(LLMUsageLogModel.total_tokens), 0).desc())
                .limit(10)
            )
        ).all()

        top_ids = [row[0] for row in top_rows if row[0]]
        name_map: dict[str, str] = {}
        if top_ids:
            for uid, uname in (
                await session.execute(
                    select(UserModel.id, UserModel.username).where(UserModel.id.in_(top_ids))
                )
            ).all():
                name_map[str(uid)] = uname

    daily_cost: dict[str, float] = {}
    for day, model, in_tok, out_tok in daily_cost_rows:
        key = str(day)
        daily_cost[key] = round(
            daily_cost.get(key, 0.0) + pricing.estimate_cost(model, in_tok, out_tok), 4
        )

    by_model = []
    for model, calls, in_tok, out_tok in model_rows:
        by_model.append(
            {
                "model": model or "unknown",
                "calls": int(calls),
                "input_tokens": int(in_tok),
                "output_tokens": int(out_tok),
                "tokens": int(in_tok) + int(out_tok),
                "cost": pricing.estimate_cost(model, in_tok, out_tok),
            }
        )

    return {
        "range_days": days,
        "since": since.isoformat(),
        "currency": pricing.currency(),
        "totals": {
            "calls": total_calls,
            "input_tokens": int(totals_row[0] or 0),
            "output_tokens": int(totals_row[1] or 0),
            "tokens": int(totals_row[2] or 0),
            "avg_duration_ms": round(float(totals_row[3] or 0), 1),
            "cost": round(sum(item["cost"] for item in by_model), 4),
        },
        "daily": [
            {
                "date": str(day),
                "calls": int(calls),
                "tokens": int(tokens),
                "cost": daily_cost.get(str(day), 0.0),
            }
            for day, calls, tokens in daily_rows
        ],
        "by_module": [
            {"module": module or "unknown", "calls": int(calls), "tokens": int(tokens)}
            for module, calls, tokens in module_rows
        ],
        "by_model": by_model,
        "top_users": [
            {
                "user_id": str(uid),
                "username": name_map.get(str(uid), "已删除用户"),
                "calls": int(calls),
                "tokens": int(tokens),
            }
            for uid, calls, tokens in top_rows
        ],
    }


# ---------------------------------------------------------------------------
# GET /admin/alerts  (告警事件与巡检状态)
# ---------------------------------------------------------------------------
@router.get("/alerts")
async def list_alerts(
    admin: UserModel = Depends(require_capability("read")),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """最近的告警事件，附当前阈值与巡检状态，便于判断「没告警」是正常还是没跑。"""
    from app.services.alerting_service import alerting_service

    items = await alerting_service.recent_events(limit)
    cfg = settings.alerts
    return {
        "items": items,
        "config": {
            "enabled": cfg.enabled,
            "channel": cfg.channel,
            "notify_ready": cfg.should_notify(),
            "interval_seconds": cfg.interval_seconds,
            "cooldown_minutes": cfg.cooldown_minutes,
            "thresholds": {
                "cost_spike_ratio": cfg.thresholds.cost_spike_ratio,
                "cost_min_amount": cfg.thresholds.cost_min_amount,
                "error_rate": cfg.thresholds.error_rate,
                "error_min_samples": cfg.thresholds.error_min_samples,
                "eval_error_rate": cfg.thresholds.eval_error_rate,
                "eval_min_samples": cfg.thresholds.eval_min_samples,
            },
        },
        "last_run_at": (
            alerting_service.last_run_at.isoformat()
            if alerting_service.last_run_at
            else None
        ),
        "last_error": alerting_service.last_error,
    }


@router.post("/alerts/check")
async def run_alert_check(
    request: Request,
    admin: UserModel = Depends(require_capability("alerts")),
) -> dict[str, Any]:
    """立即执行一次巡检（会按冷却窗口推送），用于验证阈值与 webhook 配置。"""
    from app.services.alerting_service import alerting_service

    created = await alerting_service.check_and_notify()

    async with get_session_context() as session:
        await _audit(
            session,
            admin,
            request,
            action="alert.check",
            target_type="alert",
            target_id=None,
            detail={"triggered": len(created), "kinds": [item["kind"] for item in created]},
            after={"triggered": len(created)},
        )
        await session.flush()

    return {"triggered": len(created), "items": created}


@router.post("/alerts/test")
async def send_alert_test(
    request: Request,
    admin: UserModel = Depends(require_capability("alerts")),
) -> dict[str, Any]:
    """发送一条测试消息，验证 webhook 是否配通（不写告警事件表）。"""
    from app.services.alerting_service import alerting_service

    notified, info = await alerting_service.send_test()

    if not notified:
        # 失败由 main.py 的中间件统一记录（动作 alert.test），避免重复两条
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=info)

    async with get_session_context() as session:
        await _audit(
            session,
            admin,
            request,
            action="alert.test",
            target_type="alert",
            target_id=None,
            detail={"channel": info},
            after={"notified": True},
        )
        await session.flush()

    return {"notified": True, "channel": info}
