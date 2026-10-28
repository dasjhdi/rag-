"""运维兜底：清除指定账号的双因子绑定。

适用场景：管理员换了手机、恢复码也丢了。执行后该账号可重新用密码登录，
并会立刻吊销其所有已签发的令牌。

用法（在仓库根目录执行）：

    python -m scripts.reset_totp --username liyuntao
    python -m scripts.reset_totp --username liyuntao --yes   # 跳过确认
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.database.session import close_db, init_db
from app.services.totp_service import admin_reset


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="清除账号的 TOTP 绑定")
    parser.add_argument("--username", required=True, help="要重置的账号名")
    parser.add_argument("--yes", action="store_true", help="跳过交互确认")
    return parser.parse_args()


async def _run(username: str) -> int:
    await init_db()
    try:
        ok = await admin_reset(username)
    finally:
        await close_db()
    if not ok:
        print(f"未找到账号：{username}")
        return 1
    print(f"已清除 {username} 的 TOTP 绑定，且其现有令牌已失效。")
    return 0


def main() -> int:
    args = _parse_args()
    if not args.yes:
        answer = input(f"确认清除 {args.username} 的双因子绑定？[y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("已取消。")
            return 1
    return asyncio.run(_run(args.username))


if __name__ == "__main__":
    sys.exit(main())
