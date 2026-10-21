"""Read-only admin console APIs.

Scope of this module (P0):
- ``GET /admin/overview``  aggregate counters for the dashboard header
- ``GET /admin/users``     paginated user directory with per-user activity counts
- ``GET /admin/usage``     LLM usage aggregation (daily / module / model / top users)

Design notes
------------
* Every route depends on :func:`require_admin`, which re-reads the user from the
  database instead of trusting a role claim in the JWT. Admin traffic is low, and
  this makes role changes / account disabling take effect immediately.
* Nothing here mutates data. Write operations (disable user, reset password, ...)
  belong to a later phase and must write an audit record.
* Aggregations are pushed into SQL. No Python-side loops over full tables.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.database.models import AgentSessionModel
from app.database.models import (
    ADMIN_ROLES,
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------
async def require_admin(request: Request) -> UserModel:
    """Return the current user if they hold an admin role, else raise 403.

    ``auth_gateway`` middleware has already validated the JWT and put
    ``username`` / ``user_id`` on ``request.state``.
    """
    user_id = getattr(request.state, "user_id", None)
    username = getattr(request.state, "username", None)

    if not user_id and not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="需要登录"
        )

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
    if user.role not in ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无后台访问权限")
    return user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _utcnow() -> datetime:
    """Naive UTC, matching how timestamps are stored elsewhere in the project."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _scalar(session: AsyncSession, stmt) -> int:
    value = (await session.execute(stmt)).scalar()
    return int(value or 0)


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


# ---------------------------------------------------------------------------
# GET /admin/overview
# ---------------------------------------------------------------------------
@router.get("/overview")
async def get_overview(
    admin: UserModel = Depends(require_admin),
) -> dict[str, Any]:
    """Top-line counters for the admin dashboard."""
    now = _utcnow()
    since_7d = now - timedelta(days=7)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    async with get_session_context() as session:
        total_users = await _scalar(session, select(func.count()).select_from(UserModel))
        active_users = await _scalar(
            session,
            select(func.count()).select_from(UserModel).where(UserModel.is_active.is_(True)),
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

        conversations = await _scalar(
            session, select(func.count()).select_from(ConversationModel)
        )
        agent_sessions = await _scalar(
            session, select(func.count()).select_from(AgentSessionModel)
        )

        diet_logs = await _scalar(
            session, select(func.count()).select_from(DietLogItemModel)
        )
        pantry_items = await _scalar(
            session, select(func.count()).select_from(PantryItemModel)
        )
        feedbacks = await _scalar(
            session, select(func.count()).select_from(RecipeFeedbackModel)
        )

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
        },
    }


# ---------------------------------------------------------------------------
# GET /admin/users
# ---------------------------------------------------------------------------
@router.get("/users")
async def list_users(
    admin: UserModel = Depends(require_admin),
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
# GET /admin/usage
# ---------------------------------------------------------------------------
@router.get("/usage")
async def get_usage(
    admin: UserModel = Depends(require_admin),
    days: int = Query(7, ge=1, le=90, description="统计最近 N 天"),
) -> dict[str, Any]:
    """LLM usage broken down by day, module, model and top users."""
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
                    func.coalesce(func.sum(LLMUsageLogModel.total_tokens), 0).label("tokens"),
                )
                .where(LLMUsageLogModel.created_at >= since)
                .group_by(LLMUsageLogModel.model_name)
                .order_by(func.count().desc())
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

        # Resolve usernames in one query instead of N+1
        top_ids = [row[0] for row in top_rows if row[0]]
        name_map: dict[str, str] = {}
        if top_ids:
            for uid, uname in (
                await session.execute(
                    select(UserModel.id, UserModel.username).where(UserModel.id.in_(top_ids))
                )
            ).all():
                name_map[str(uid)] = uname

    return {
        "range_days": days,
        "since": since.isoformat(),
        "totals": {
            "calls": total_calls,
            "input_tokens": int(totals_row[0] or 0),
            "output_tokens": int(totals_row[1] or 0),
            "tokens": int(totals_row[2] or 0),
            "avg_duration_ms": round(float(totals_row[3] or 0), 1),
        },
        "daily": [
            {"date": str(day), "calls": int(calls), "tokens": int(tokens)}
            for day, calls, tokens in daily_rows
        ],
        "by_module": [
            {"module": module or "unknown", "calls": int(calls), "tokens": int(tokens)}
            for module, calls, tokens in module_rows
        ],
        "by_model": [
            {"model": model or "unknown", "calls": int(calls), "tokens": int(tokens)}
            for model, calls, tokens in model_rows
        ],
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
