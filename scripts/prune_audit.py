"""审计日志保留期清理。

`admin_audit_logs` 只增不减，长期运行会拖慢列表查询。这个脚本按天裁剪，
默认保留 180 天，建议由系统计划任务在低峰期执行。

用法（仓库根目录）：

    python -m scripts.prune_audit --dry-run          # 先看会删多少
    python -m scripts.prune_audit                    # 删除 180 天前的记录
    python -m scripts.prune_audit --days 90
    python -m scripts.prune_audit --vacuum           # 删除后顺手回收空间

注意：
* 失败记录同样会被裁剪，如果合规要求更长留存，把 --days 调大；
* 想归档而不是删除，请先用 pg_dump 导出目标区间，再执行本脚本。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select, text

from app.database.models import AdminAuditLogModel
from app.database.session import _engine, close_db, get_session_context, init_db


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="清理过期的后台审计日志")
    parser.add_argument("--days", type=int, default=180, help="保留天数，默认 180")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不删除")
    parser.add_argument("--vacuum", action="store_true", help="删除后执行 VACUUM ANALYZE")
    return parser.parse_args()


async def _run(days: int, dry_run: bool, vacuum: bool) -> int:
    # 与库中一致的 naive UTC
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)

    async with get_session_context() as session:
        total = int(
            (await session.execute(select(func.count()).select_from(AdminAuditLogModel))).scalar()
            or 0
        )
        expired = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(AdminAuditLogModel)
                    .where(AdminAuditLogModel.created_at < cutoff)
                )
            ).scalar()
            or 0
        )

        print(f"审计总数 {total}，{cutoff:%Y-%m-%d %H:%M} 之前 {expired} 条")
        if dry_run or not expired:
            return 0

        await session.execute(
            delete(AdminAuditLogModel).where(AdminAuditLogModel.created_at < cutoff)
        )

    if vacuum:
        # VACUUM 不能在事务块里执行，单独用一个 AUTOCOMMIT 连接
        async with _engine.connect() as connection:
            await connection.execution_options(isolation_level="AUTOCOMMIT")
            await connection.execute(text("VACUUM ANALYZE admin_audit_logs"))
        print("已执行 VACUUM ANALYZE")

    print(f"已删除 {expired} 条，剩余 {total - expired} 条")
    return 0


def main() -> int:
    args = _parse_args()
    if args.days < 1:
        print("--days 必须大于 0")
        return 1

    async def runner() -> int:
        await init_db()
        try:
            return await _run(args.days, args.dry_run, args.vacuum)
        finally:
            await close_db()

    return asyncio.run(runner())


if __name__ == "__main__":
    sys.exit(main())
