"""成本 / 错误率告警。

设计取舍：
* **不引入调度库**：一个 asyncio 后台任务 + 固定间隔足够，少一个依赖。
* **先落库再通知**：通知失败也要能在后台看到「告警确实触发过」。
* **冷却窗口**：同类告警在冷却期内只推送一次，避免每 5 分钟刷屏；
  冷却状态优先放 Redis，没有 Redis 时回退到查库。
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from sqlalchemy import func, select

from app.config import settings
from app.database.models import (
    AlertEventModel,
    LLMUsageLogModel,
    RAGEvaluationModel,
)
from app.database.session import get_session_context
from app.services import pricing

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _redis_safe(key: str) -> str:
    return key[:200]


class AlertingService:
    """周期性评估阈值并推送告警。"""

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._redis: Any = None
        self._running = False
        self.last_run_at: Optional[datetime] = None
        self.last_error: Optional[str] = None

    def set_redis(self, redis_client: Any) -> None:
        self._redis = redis_client

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    async def start(self) -> None:
        cfg = settings.alerts
        if not cfg.enabled:
            logger.info("Alerting disabled by configuration.")
            return
        if self._task and not self._task.done():
            return
        self._running = True
        self._task = asyncio.create_task(self._run_forever(), name="alerting-loop")
        logger.info(
            "Alerting started: interval=%ss, channel=%s",
            cfg.interval_seconds,
            cfg.channel,
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run_forever(self) -> None:
        interval = max(30, int(settings.alerts.interval_seconds))
        # 启动后先等一个间隔，避免和数据库初始化抢资源
        while self._running:
            try:
                await asyncio.sleep(interval)
                if not self._running:
                    break
                await self.check_and_notify()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # 单次失败不终止巡检
                self.last_error = str(exc)[:300]
                logger.warning("Alert evaluation failed: %s", exc)

    # ------------------------------------------------------------------
    # 指标采集
    # ------------------------------------------------------------------
    async def _cost_metrics(self) -> dict:
        """今日成本 vs 前 7 日日均。"""
        today_start = _utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        since = today_start - timedelta(days=7)

        async with get_session_context() as session:
            rows = (
                await session.execute(
                    select(
                        func.date(LLMUsageLogModel.created_at).label("day"),
                        LLMUsageLogModel.model_name,
                        func.coalesce(func.sum(LLMUsageLogModel.input_tokens), 0),
                        func.coalesce(func.sum(LLMUsageLogModel.output_tokens), 0),
                    )
                    .where(LLMUsageLogModel.created_at >= since)
                    .group_by(
                        func.date(LLMUsageLogModel.created_at),
                        LLMUsageLogModel.model_name,
                    )
                )
            ).all()

        today = today_start.date()
        daily: dict[str, float] = {}
        for day, model, in_tok, out_tok in rows:
            key = str(day)
            daily[key] = daily.get(key, 0.0) + pricing.estimate_cost(model, in_tok, out_tok)

        cost_today = daily.get(str(today), 0.0)
        history = [value for day, value in daily.items() if day != str(today)]
        baseline = sum(history) / len(history) if history else 0.0
        return {
            "cost_today": round(cost_today, 4),
            "baseline": round(baseline, 4),
            "days": len(history),
            "currency": pricing.currency(),
        }

    async def _error_metrics(self) -> dict:
        """今日 LLM 调用错误率。"""
        today_start = _utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        async with get_session_context() as session:
            total = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(LLMUsageLogModel)
                        .where(LLMUsageLogModel.created_at >= today_start)
                    )
                ).scalar()
                or 0
            )
            failed = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(LLMUsageLogModel)
                        .where(LLMUsageLogModel.created_at >= today_start)
                        .where(LLMUsageLogModel.status != "success")
                    )
                ).scalar()
                or 0
            )
        return {
            "samples": total,
            "failed": failed,
            "rate": round(failed / total, 4) if total else 0.0,
        }

    async def _evaluation_metrics(self) -> dict:
        """近 24 小时 RAGAS 评测失败率。"""
        since = _utcnow() - timedelta(hours=24)
        async with get_session_context() as session:
            total = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(RAGEvaluationModel)
                        .where(RAGEvaluationModel.created_at >= since)
                    )
                ).scalar()
                or 0
            )
            failed = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(RAGEvaluationModel)
                        .where(RAGEvaluationModel.created_at >= since)
                        .where(RAGEvaluationModel.evaluation_status == "failed")
                    )
                ).scalar()
                or 0
            )
        return {
            "samples": total,
            "failed": failed,
            "rate": round(failed / total, 4) if total else 0.0,
        }

    # ------------------------------------------------------------------
    # 阈值判定
    # ------------------------------------------------------------------
    async def evaluate(self) -> list[dict]:
        """返回本次触发的告警（不落库、不通知）。"""
        cfg = settings.alerts
        thresholds = cfg.thresholds
        triggered: list[dict] = []

        try:
            cost = await self._cost_metrics()
            if (
                cost["cost_today"] >= thresholds.cost_min_amount
                and cost["baseline"] > 0
                and cost["cost_today"] >= cost["baseline"] * thresholds.cost_spike_ratio
            ):
                ratio = cost["cost_today"] / cost["baseline"]
                triggered.append(
                    {
                        "kind": "cost_spike",
                        "severity": "warning",
                        "title": "今日 LLM 成本异常上涨",
                        "message": (
                            f"今日成本 {cost['currency']}{cost['cost_today']:.2f}，"
                            f"是前 {cost['days']} 日均值 "
                            f"{cost['currency']}{cost['baseline']:.2f} 的 {ratio:.1f} 倍。"
                        ),
                        "metrics": {**cost, "ratio": round(ratio, 2)},
                    }
                )
        except Exception as exc:
            logger.warning("Cost metrics failed: %s", exc)

        try:
            err = await self._error_metrics()
            if (
                err["samples"] >= thresholds.error_min_samples
                and err["rate"] >= thresholds.error_rate
            ):
                triggered.append(
                    {
                        "kind": "llm_error_rate",
                        "severity": "critical",
                        "title": "LLM 调用错误率超阈值",
                        "message": (
                            f"今日 {err['samples']} 次调用中失败 {err['failed']} 次，"
                            f"错误率 {err['rate'] * 100:.1f}% "
                            f"（阈值 {thresholds.error_rate * 100:.0f}%）。"
                        ),
                        "metrics": err,
                    }
                )
        except Exception as exc:
            logger.warning("Error metrics failed: %s", exc)

        try:
            ev = await self._evaluation_metrics()
            if (
                ev["samples"] >= thresholds.eval_min_samples
                and ev["rate"] >= thresholds.eval_error_rate
            ):
                triggered.append(
                    {
                        "kind": "evaluation_failure",
                        "severity": "warning",
                        "title": "RAG 质量评测失败率偏高",
                        "message": (
                            f"近 24 小时 {ev['samples']} 次评测中失败 {ev['failed']} 次，"
                            f"失败率 {ev['rate'] * 100:.1f}% "
                            f"（阈值 {thresholds.eval_error_rate * 100:.0f}%）。"
                        ),
                        "metrics": ev,
                    }
                )
        except Exception as exc:
            logger.warning("Evaluation metrics failed: %s", exc)

        return triggered

    # ------------------------------------------------------------------
    # 冷却 + 通知
    # ------------------------------------------------------------------
    async def _in_cooldown(self, kind: str) -> bool:
        minutes = max(1, int(settings.alerts.cooldown_minutes))
        if self._redis is not None:
            try:
                if await self._redis.exists(_redis_safe(f"alert:cooldown:{kind}")):
                    return True
                await self._redis.setex(
                    _redis_safe(f"alert:cooldown:{kind}"), minutes * 60, "1"
                )
                return False
            except Exception as exc:
                logger.debug("Alert cooldown via redis failed: %s", exc)

        # 回退：查最近一条同类事件
        since = _utcnow() - timedelta(minutes=minutes)
        async with get_session_context() as session:
            exists = (
                await session.execute(
                    select(AlertEventModel.id)
                    .where(AlertEventModel.kind == kind)
                    .where(AlertEventModel.created_at >= since)
                    .limit(1)
                )
            ).scalar_one_or_none()
        return exists is not None

    async def _notify(self, title: str, message: str, severity: str) -> tuple[bool, str]:
        cfg = settings.alerts
        if not cfg.should_notify():
            return False, "未配置通知渠道"

        text = f"{cfg.title_prefix} [{severity.upper()}] {title}\n{message}"
        url = cfg.webhook_url.strip()
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                if "qyapi.weixin.qq.com" in url:
                    payload = {"msgtype": "text", "text": {"content": text}}
                else:
                    payload = {
                        "source": "cookhero",
                        "severity": severity,
                        "title": title,
                        "message": message,
                        "timestamp": _utcnow().isoformat() + "Z",
                    }
                resp = await client.post(url, json=payload)
                if resp.status_code >= 300:
                    return False, f"HTTP {resp.status_code}: {resp.text[:150]}"
            return True, "webhook"
        except Exception as exc:
            return False, str(exc)[:200]

    async def send_test(self) -> tuple[bool, str]:
        """发送一条固定测试消息，用于验证 webhook 是否真的通。

        不写入 alert_events：测试不是真实告警，避免污染告警列表与冷却窗口。
        """
        cfg = settings.alerts
        if not cfg.should_notify():
            return False, "未配置通知渠道：需要 channel=webhook 且 webhook_url 非空"
        return await self._notify(
            "告警通道测试",
            f"这是一条测试消息，来自 {cfg.title_prefix} 后台；收到即表示 webhook 配置正确。",
            "info",
        )

    async def check_and_notify(self) -> list[dict]:
        """评估 → 冷却过滤 → 落库 → 推送。返回本次新产生的告警。"""
        self.last_run_at = _utcnow()
        triggered = await self.evaluate()
        if not triggered:
            self.last_error = None
            return []

        created: list[dict] = []
        for alert in triggered:
            if await self._in_cooldown(alert["kind"]):
                logger.info("Alert %s in cooldown, skipped.", alert["kind"])
                continue

            notified, channel_or_error = await self._notify(
                alert["title"], alert["message"], alert["severity"]
            )
            event = AlertEventModel(
                kind=alert["kind"],
                severity=alert["severity"],
                title=alert["title"],
                message=alert["message"],
                metrics=alert["metrics"],
                channel=channel_or_error if notified else settings.alerts.channel,
                notified=notified,
                notify_error=None if notified else channel_or_error,
            )
            async with get_session_context() as session:
                session.add(event)
                await session.flush()
                payload = event.to_dict()

            created.append(payload)
            logger.warning("Alert triggered: %s | %s", alert["title"], alert["message"])

        self.last_error = None
        return created

    async def recent_events(self, limit: int = 20) -> list[dict]:
        async with get_session_context() as session:
            rows = (
                await session.execute(
                    select(AlertEventModel)
                    .order_by(AlertEventModel.created_at.desc())
                    .limit(max(1, min(limit, 100)))
                )
            ).scalars()
            return [row.to_dict() for row in rows]


alerting_service = AlertingService()
