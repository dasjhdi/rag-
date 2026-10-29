/**
 * Admin console · Metrics tab
 *
 * 进程内指标（重启清零）：视觉链路的耗时/超时/重试/体积压缩，
 * 以及意图识别、检索与重排的命中情况。用于判断「模型侧是否变慢」。
 */

import { useCallback, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import {
  Activity,
  AlertTriangle,
  Gauge,
  Image as ImageIcon,
  Loader2,
  RefreshCcw,
  Timer,
  TrendingDown,
} from 'lucide-react';
import type { SemanticMetrics } from '../../services/api/admin';
import { getSemanticMetrics } from '../../services/api/admin';

const REFRESH_MS = 30_000;

const pct = (value: number) => `${(value * 100).toFixed(1)}%`;
const ms = (value: number) =>
  value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${Math.round(value)} ms`;
const bytes = (value: number) => {
  if (!value) return '0 KB';
  if (value >= 1024 * 1024) return `${(value / 1024 / 1024).toFixed(2)} MB`;
  return `${Math.round(value / 1024)} KB`;
};

function Stat({
  label,
  value,
  hint,
  tone = 'default',
  icon: Icon,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: 'default' | 'good' | 'warn' | 'bad';
  icon: typeof Gauge;
}) {
  const toneClass =
    tone === 'bad'
      ? 'text-red-600 dark:text-red-400'
      : tone === 'warn'
        ? 'text-amber-600 dark:text-amber-400'
        : tone === 'good'
          ? 'text-emerald-600 dark:text-emerald-400'
          : 'text-gray-800 dark:text-gray-100';
  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900/60 p-4">
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
        <Icon className="w-3.5 h-3.5" />
        {label}
      </div>
      <div className={`mt-2 text-2xl font-semibold tabular-nums ${toneClass}`}>{value}</div>
      {hint && <div className="mt-1 text-xs text-gray-400">{hint}</div>}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-dashed border-gray-100 dark:border-gray-800 py-1.5 text-sm last:border-0">
      <span className="text-gray-500 dark:text-gray-400">{label}</span>
      <b className="font-medium tabular-nums text-gray-700 dark:text-gray-200">{value}</b>
    </div>
  );
}

function Card({
  title,
  icon: Icon,
  children,
}: {
  title: string;
  icon: typeof Gauge;
  children: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900/60 p-4">
      <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
        <Icon className="w-3.5 h-3.5" />
        {title}
      </div>
      {children}
    </div>
  );
}

export default function AdminMetrics({ token }: { token: string }) {
  const [data, setData] = useState<SemanticMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  const load = useCallback(
    async (silent = false) => {
      if (!silent) setLoading(true);
      setError(null);
      try {
        setData(await getSemanticMetrics(token));
        setUpdatedAt(new Date());
      } catch (err) {
        setError(err instanceof Error ? err.message : '加载失败');
      } finally {
        setLoading(false);
      }
    },
    [token]
  );

  useEffect(() => {
    load();
    // 指标是运行态数据，30s 轮询一次即可，不必 SSE
    const timer = window.setInterval(() => load(true), REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [load]);

  const vision = data?.vision;
  const total = vision?.total ?? 0;
  const timeoutTone =
    (vision?.timeout_rate ?? 0) >= 0.1 ? 'bad' : (vision?.timeout_rate ?? 0) > 0.02 ? 'warn' : 'default';
  const successRate = vision?.success_rate ?? 0;
  const successTone =
    total === 0 ? 'default' : successRate >= 0.95 ? 'good' : successRate >= 0.85 ? 'warn' : 'bad';
  const p95 = vision?.latency_ms.p95 ?? 0;
  const p95Tone = total === 0 ? 'default' : p95 >= 10_000 ? 'bad' : p95 >= 5_000 ? 'warn' : 'good';

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => load()}
          className="p-2 rounded-lg text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800"
          title="刷新"
        >
          <RefreshCcw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
        <span className="text-xs text-gray-400">
          {updatedAt ? `更新于 ${updatedAt.toLocaleTimeString('zh-CN')} · 每 30s 自动刷新` : '加载中…'}
        </span>
        <span className="ml-auto text-xs text-gray-400">进程内计数，后端重启后清零</span>
      </div>

      {error ? (
        <div className="rounded-lg border border-red-200 dark:border-red-900/50 bg-red-50 dark:bg-red-900/20 px-4 py-3 text-sm text-red-600 dark:text-red-300">
          {error}
        </div>
      ) : loading && !data ? (
        <div className="flex items-center justify-center py-16 text-gray-500">
          <Loader2 className="w-5 h-5 animate-spin mr-2" />
          <span className="text-sm">加载中…</span>
        </div>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Stat
              label="视觉调用"
              value={String(total)}
              hint={`成功 ${vision?.success ?? 0} · 失败 ${vision?.failed ?? 0}`}
              icon={ImageIcon}
            />
            <Stat
              label="成功率"
              value={total ? pct(vision?.success_rate ?? 0) : '—'}
              hint="低于 95% 需要看日志"
              tone={successTone}
              icon={Activity}
            />
            <Stat
              label="P95 延迟"
              value={total ? ms(vision?.latency_ms.p95 ?? 0) : '—'}
              hint={`P50 ${ms(vision?.latency_ms.p50 ?? 0)} · 样本 ${vision?.latency_ms.samples ?? 0}`}
              tone={p95Tone}
              icon={Timer}
            />
            <Stat
              label="超时率"
              value={total ? pct(vision?.timeout_rate ?? 0) : '—'}
              hint={`超时重试 ${vision?.retries_smaller ?? 0} 次`}
              tone={timeoutTone}
              icon={AlertTriangle}
            />
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <Card title="视觉延迟与稳定性" icon={Timer}>
              <Row label="平均耗时" value={ms(vision?.latency_ms.avg ?? 0)} />
              <Row label="P50 / P95" value={`${ms(vision?.latency_ms.p50 ?? 0)} / ${ms(vision?.latency_ms.p95 ?? 0)}`} />
              <Row label="最大耗时" value={ms(vision?.latency_ms.max ?? 0)} />
              <Row label="超时次数" value={String(vision?.timeouts ?? 0)} />
              <Row label="缩图重试" value={String(vision?.retries_smaller ?? 0)} />
              <Row label="模型回退" value={String(vision?.fallbacks ?? 0)} />
            </Card>

            <Card title="送入模型的图片体积" icon={TrendingDown}>
              <Row label="压缩前" value={bytes(vision?.payload.input_bytes ?? 0)} />
              <Row label="压缩后" value={bytes(vision?.payload.output_bytes ?? 0)} />
              <Row
                label="节省比例"
                value={vision?.payload.input_bytes ? pct(vision?.payload.saved_ratio ?? 0) : '—'}
              />
              <p className="mt-2 text-xs leading-relaxed text-gray-400">
                归一化在服务端完成：长边 1024、JPEG q85；足够小的图原样透传。
                体积下降通常同时降低延迟与图片 token 成本。
              </p>
            </Card>
          </div>

          {total > 0 && Object.keys(vision?.by_model ?? {}).length > 0 && (
            <Card title="按模型分布" icon={Gauge}>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs uppercase tracking-wider text-gray-400">
                      <th className="py-1.5 pr-3 font-medium">模型</th>
                      <th className="py-1.5 pr-3 font-medium">调用</th>
                      <th className="py-1.5 pr-3 font-medium">成功</th>
                      <th className="py-1.5 font-medium">失败</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(vision?.by_model ?? {}).map(([model, stats]) => (
                      <tr key={model} className="border-t border-gray-100 dark:border-gray-800">
                        <td className="py-1.5 pr-3 font-mono text-xs text-gray-600 dark:text-gray-300">
                          {model}
                        </td>
                        <td className="py-1.5 pr-3 tabular-nums">{stats.total}</td>
                        <td className="py-1.5 pr-3 tabular-nums text-emerald-600 dark:text-emerald-400">
                          {stats.success}
                        </td>
                        <td className="py-1.5 tabular-nums text-red-500">{stats.failed || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          <div className="grid gap-3 md:grid-cols-3">
            <Card title="意图识别" icon={Activity}>
              <Row label="总次数" value={String(data?.intent.total ?? 0)} />
              <Row label="低置信率" value={pct(data?.intent.low_confidence_rate ?? 0)} />
              <Row label="澄清信号率" value={pct(data?.intent.clarification_signal_rate ?? 0)} />
              {Object.entries(data?.intent.by_intent ?? {})
                .slice(0, 5)
                .map(([label, count]) => (
                  <Row key={label} label={label} value={String(count)} />
                ))}
            </Card>

            <Card title="检索" icon={Gauge}>
              <Row label="总次数" value={String(data?.retrieval.total ?? 0)} />
              <Row label="命中率" value={pct(data?.retrieval.hit_rate ?? 0)} />
              <Row label="空结果率" value={pct(data?.retrieval.empty_rate ?? 0)} />
              <Row label="缓存命中率" value={pct(data?.retrieval.cache_hit_rate ?? 0)} />
            </Card>

            <Card title="重排" icon={TrendingDown}>
              <Row label="总次数" value={String(data?.rerank.total ?? 0)} />
              <Row label="回退次数" value={String(data?.rerank.fallbacks ?? 0)} />
              <Row label="回退率" value={pct(data?.rerank.fallback_rate ?? 0)} />
            </Card>
          </div>

          {total === 0 && (
            <div className="flex flex-col items-center justify-center py-12 text-gray-400">
              <ImageIcon className="w-9 h-9 mb-2 text-gray-300" />
              <p className="text-sm">还没有视觉调用</p>
              <p className="mt-1 text-xs">在对话或 Agent 里发一张图片，这里就会出现耗时与超时数据</p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
