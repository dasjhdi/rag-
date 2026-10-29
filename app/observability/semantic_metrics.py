"""进程内语义观测指标（SU-10）。

只记录计数、标签与来源名，不记录用户原始查询、密钥或文档正文。
所有方法均为常数时间字典更新，并通过线程锁保证并发安全。
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict, deque
from typing import Any, Iterable

logger = logging.getLogger(__name__)


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _percentile(values: Iterable[int], quantile: float) -> int:
    """离散分位数：样本量小的时候比插值更直观，也不会给出小数毫秒。"""
    ordered = sorted(values)
    if not ordered:
        return 0
    index = int(round((len(ordered) - 1) * quantile))
    return ordered[max(0, min(index, len(ordered) - 1))]


class SemanticMetricsCollector:
    """Thread-safe in-process counters for semantic pipeline events."""

    LOW_CONFIDENCE_THRESHOLD = 0.5

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._reset_unlocked()

    def _reset_unlocked(self) -> None:
        self._intent_total = 0
        self._intent_low_confidence = 0
        self._intent_clarification_signals = 0
        self._intent_by_label: dict[str, int] = defaultdict(int)

        self._retrieval_total = 0
        self._retrieval_hit = 0
        self._retrieval_empty = 0
        self._cache_hits = 0
        self._cache_misses = 0
        self._retrieval_by_source: dict[str, dict[str, int]] = defaultdict(
            lambda: {"total": 0, "hit": 0, "empty": 0}
        )

        self._rerank_total = 0
        self._rerank_fallbacks = 0

        # 视觉链路：耗时、超时、重试与体积压缩
        self._vision_total = 0
        self._vision_success = 0
        self._vision_failed = 0
        self._vision_timeouts = 0
        self._vision_retries = 0
        self._vision_fallbacks = 0
        self._vision_bytes_in = 0
        self._vision_bytes_out = 0
        # 只保留最近 200 次耗时做分位数，内存恒定
        self._vision_durations: deque[int] = deque(maxlen=200)
        self._vision_by_model: dict[str, dict[str, int]] = defaultdict(
            lambda: {"total": 0, "success": 0, "failed": 0}
        )

    def record_intent(
        self, *, intent: str, confidence: float, needs_clarification: bool
    ) -> None:
        """Record one intent detection result."""
        try:
            label = str(intent or "unknown")
            score = float(confidence)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Skipping invalid intent metric: %s", exc)
            return

        with self._lock:
            self._intent_total += 1
            self._intent_by_label[label] += 1
            if score < self.LOW_CONFIDENCE_THRESHOLD:
                self._intent_low_confidence += 1
            if needs_clarification:
                self._intent_clarification_signals += 1

    def record_retrieval(
        self,
        *,
        source: str,
        doc_count: int,
        cache_hit: bool,
        cache_checked: bool = True,
    ) -> None:
        """Record one retrieval call and whether it returned documents."""
        try:
            count = int(doc_count)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Skipping invalid retrieval metric: %s", exc)
            return

        source_name = str(source or "unknown")
        with self._lock:
            self._retrieval_total += 1
            if cache_checked:
                if cache_hit:
                    self._cache_hits += 1
                else:
                    self._cache_misses += 1

            source_stats = self._retrieval_by_source[source_name]
            source_stats["total"] += 1
            if count > 0:
                self._retrieval_hit += 1
                source_stats["hit"] += 1
            else:
                self._retrieval_empty += 1
                source_stats["empty"] += 1

    def record_rerank(self, *, fallback_used: bool) -> None:
        """Record one rerank call and whether a fallback was used."""
        with self._lock:
            self._rerank_total += 1
            if fallback_used:
                self._rerank_fallbacks += 1

    def record_vision(
        self,
        *,
        success: bool,
        duration_ms: int,
        model: str | None = None,
        timeout: bool = False,
        retried_smaller: bool = False,
        fallback: bool = False,
        images: int = 1,
        input_bytes: int = 0,
        output_bytes: int = 0,
    ) -> None:
        """记录一次视觉模型调用（成功或失败）。

        只记计数、耗时与体积，不记图片内容或用户问题。
        """
        try:
            elapsed = max(0, int(duration_ms))
            model_name = str(model or "unknown")
            in_bytes = max(0, int(input_bytes or 0))
            out_bytes = max(0, int(output_bytes or 0))
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Skipping invalid vision metric: %s", exc)
            return

        with self._lock:
            self._vision_total += 1
            self._vision_durations.append(elapsed)
            stats = self._vision_by_model[model_name]
            stats["total"] += 1

            if success:
                self._vision_success += 1
                stats["success"] += 1
            else:
                self._vision_failed += 1
                stats["failed"] += 1

            if timeout:
                self._vision_timeouts += 1
            if retried_smaller:
                self._vision_retries += 1
            if fallback:
                self._vision_fallbacks += 1

            self._vision_bytes_in += in_bytes
            self._vision_bytes_out += out_bytes

    def snapshot(self) -> dict[str, Any]:
        """Return counters plus derived rates."""
        with self._lock:
            cache_total = self._cache_hits + self._cache_misses
            return {
                "intent": {
                    "total": self._intent_total,
                    "low_confidence": self._intent_low_confidence,
                    "clarification_signals": self._intent_clarification_signals,
                    "low_confidence_rate": _rate(
                        self._intent_low_confidence, self._intent_total
                    ),
                    "clarification_signal_rate": _rate(
                        self._intent_clarification_signals, self._intent_total
                    ),
                    "by_intent": dict(self._intent_by_label),
                },
                "retrieval": {
                    "total": self._retrieval_total,
                    "hit": self._retrieval_hit,
                    "empty": self._retrieval_empty,
                    "cache_hits": self._cache_hits,
                    "cache_misses": self._cache_misses,
                    "hit_rate": _rate(self._retrieval_hit, self._retrieval_total),
                    "empty_rate": _rate(
                        self._retrieval_empty, self._retrieval_total
                    ),
                    "cache_hit_rate": _rate(self._cache_hits, cache_total),
                    "by_source": {
                        source: dict(stats)
                        for source, stats in self._retrieval_by_source.items()
                    },
                },
                "rerank": {
                    "total": self._rerank_total,
                    "fallbacks": self._rerank_fallbacks,
                    "fallback_rate": _rate(
                        self._rerank_fallbacks, self._rerank_total
                    ),
                },
                "vision": {
                    "total": self._vision_total,
                    "success": self._vision_success,
                    "failed": self._vision_failed,
                    "timeouts": self._vision_timeouts,
                    "retries_smaller": self._vision_retries,
                    "fallbacks": self._vision_fallbacks,
                    "success_rate": _rate(self._vision_success, self._vision_total),
                    "failure_rate": _rate(self._vision_failed, self._vision_total),
                    "timeout_rate": _rate(self._vision_timeouts, self._vision_total),
                    "retry_rate": _rate(self._vision_retries, self._vision_total),
                    "latency_ms": {
                        "avg": (
                            round(sum(self._vision_durations) / len(self._vision_durations))
                            if self._vision_durations
                            else 0
                        ),
                        "p50": _percentile(self._vision_durations, 0.5),
                        "p95": _percentile(self._vision_durations, 0.95),
                        "max": max(self._vision_durations, default=0),
                        "samples": len(self._vision_durations),
                    },
                    "payload": {
                        "input_bytes": self._vision_bytes_in,
                        "output_bytes": self._vision_bytes_out,
                        "saved_ratio": (
                            round(
                                1 - self._vision_bytes_out / self._vision_bytes_in, 4
                            )
                            if self._vision_bytes_in
                            else 0.0
                        ),
                    },
                    "by_model": {
                        model: dict(stats)
                        for model, stats in self._vision_by_model.items()
                    },
                },
            }

    def reset(self) -> None:
        """Clear all counters. Intended for tests and process restarts."""
        with self._lock:
            self._reset_unlocked()


semantic_metrics = SemanticMetricsCollector()

__all__ = ["SemanticMetricsCollector", "semantic_metrics"]
