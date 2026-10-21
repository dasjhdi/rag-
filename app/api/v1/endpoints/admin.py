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
* 权限按能力（capability）划分，而不是"能进后台"一刀切：
  viewer 只读、support 可看会话、ops 可管账号、super_admin 全权。
* 每个请求都回查数据库，因此改角色、禁用账号立即生效，无需重新登录。
* 写操作先落审计再返回；危险操作带护栏（不能禁用自己、不能移除最后一个超管）。
* 聚合全部下推 SQL，不做 Python 侧全表遍历。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.database.models import AgentMessageModel, AgentSessionModel
from app.database.models import (
    ADMIN_ROLES,
    AdminAuditLogModel,
    ConversationModel,
    KnowledgeDocumentModel,
    LLMUsageLogModel,
    UserModel,
)
from app.database.session import get_session_context
from app.diet.database.models import (
    DietLogItemModel,
    PantryItemModel,
    RecipeFeedbackModel,
)
from app.security.admin_rate_limit import admin_rate_limit
from app.services import pricing

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(admin_rate_limit)],
)

# 能力矩阵：角色 -> 允许的操作。新增能力时只改这一处。
CAPABILITIES: dict[str, frozenset[str]] = {
    "viewer": frozenset({"read"}),
    "support": frozenset({"read", "sessions"}),
    "ops": frozenset({"read", "sessions", "user_status", "user_password"}),
    "super_admin": frozenset(
        {
            "read",
            "sessions",
            "user_status",
            "user_password",
            "user_role",
            "audit",
        }
    ),
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


async def require_admin(user: UserModel = Depends(get_current_user)) -> UserModel:
    """Any admin role passes."""
    if user.role not in ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无后台访问权限")
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

    return _dep


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


async def _audit(
    session: AsyncSession,
    actor: UserModel,
    request: Request,
    action: str,
    target_type: str,
    target_id: Optional[str],
    detail: Optional[dict] = None,
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
            ip=_client_ip(request),
        )
    )


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
            detail={"username": target.username, "before": before, "after": payload.is_active},
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
            detail={"username": target.username, "before": before, "after": new_role},
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
    admin: UserModel = Depends(require_capability("user_password")),
) -> dict[str, Any]:
    """Reset a password. Existing JWTs stay valid until they expire."""
    async with get_session_context() as session:
        target = await _get_target_user(session, user_id)

        target.password_hash = bcrypt.hashpw(
            payload.new_password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")
        await _audit(
            session,
            admin,
            request,
            action="user.reset_password",
            target_type="user",
            target_id=str(target.id),
            detail={"username": target.username},
        )
        await session.flush()

    return {
        "id": user_id,
        "reset": True,
        "note": "已重置。该用户已签发的令牌在过期前仍然有效。",
    }


# ---------------------------------------------------------------------------
# GET /admin/audit
# ---------------------------------------------------------------------------
@router.get("/audit")
async def list_audit(
    admin: UserModel = Depends(require_capability("audit")),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """Paginated audit trail, newest first."""
    offset = (page - 1) * page_size
    async with get_session_context() as session:
        total = await _scalar(session, select(func.count()).select_from(AdminAuditLogModel))
        rows = list(
            (
                await session.execute(
                    select(AdminAuditLogModel)
                    .order_by(AdminAuditLogModel.created_at.desc())
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
