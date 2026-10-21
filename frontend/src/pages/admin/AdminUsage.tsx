/**
 * Admin console · LLM usage tab
 *
 * 聚合全部来自 `/admin/usage`（GROUP BY 在 SQL 侧完成）；成本按 config.yml
 * 的 pricing 估算，只用于趋势判断，不是账单。
 * 每日柱状图用纯 div 绘制，避免为一个页面引入图表库。
 */

import { useCallback, useEffect, useState } from 'react';
import { Activity, BarChart3, Download, Loader2, RefreshCcw, Timer, Zap } from 'lucide-react';
import type { AdminUsage } from '../../services/api/admin';
import { getAdminUsage } from '../../services/api/admin';
import { exportCsv, formatMoney } from './ui';

const RANGES = [7, 30, 90];

function compact(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

function StatCard({
  icon,
  label,
  value,
  hint,
  accent,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  hint?: string;
  accent?: boolean;
}) {
  return (
    <div
      className={`rounded-2xl shadow-sm p-4 border ${
        accent
          ? 'bg-orange-50 dark:bg-orange-500/10 border-orange-200 dark:border-orange-500/20'
          : 'bg-white dark:bg-gray-900/60 border-gray-200 dark:border-gray-800'
      }`}
    >
      <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400 text-xs">
        {icon}
        <span>{label}</span>
      </div>
      <p
        className={`mt-2 text-2xl font-bold tabular-nums ${
          accent ? 'text-orange-600 dark:text-orange-300' : 'text-gray-900 dark:text-white'
        }`}
      >
        {value}
      </p>
      {hint && <p className="mt-1 text-xs text-gray-400">{hint}</p>}
    </div>
  );
}

export default function AdminUsage({ token }: { token: string }) {
  const [days, setDays] = useState(7);
  const [customDays, setCustomDays] = useState('');
  const [data, setData] = useState<AdminUsage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getAdminUsage(token, days));
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, [token, days]);

  useEffect(() => {
    load();
  }, [load]);

  const applyCustom = () => {
    const n = Number(customDays);
    if (!Number.isFinite(n) || n < 1 || n > 90) {
      setError('请输入 1–90 之间的天数');
      return;
    }
    setError(null);
    setDays(Math.round(n));
  };

  const exportUsage = () => {
    if (!data) return;
    exportCsv(
      `cookhero-usage-${data.range_days}d-${new Date().toISOString().slice(0, 10)}.csv`,
      ['日期', '调用次数', 'Token', `成本(${data.currency})`],
      data.daily.map((d) => [d.date, d.calls, d.tokens, d.cost.toFixed(4)])
    );
  };

  const maxDaily = Math.max(1, ...(data?.daily.map((d) => d.tokens) ?? [0]));

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
          {RANGES.map((r) => (
            <button
              key={r}
              onClick={() => {
                setDays(r);
                setCustomDays('');
              }}
              className={`px-3 py-1.5 text-sm transition-colors ${
                days === r
                  ? 'bg-orange-500 text-white'
                  : 'text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800'
              }`}
            >
              最近 {r} 天
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1.5">
          <input
            value={customDays}
            onChange={(e) => setCustomDays(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && applyCustom()}
            placeholder="自定义天数"
            className="w-24 px-2.5 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-orange-500/30"
          />
          <button
            onClick={applyCustom}
            className="px-2.5 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
          >
            应用
          </button>
        </div>
        <button
          onClick={load}
          className="p-2 rounded-lg text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          title="刷新"
        >
          <RefreshCcw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
        <button
          onClick={exportUsage}
          disabled={!data}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-40"
        >
          <Download className="w-3.5 h-3.5" />
          导出 CSV
        </button>
        {data && (
          <span className="ml-auto text-xs text-gray-500 dark:text-gray-400">
            统计区间：最近 {data.range_days} 天
          </span>
        )}
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
      ) : data ? (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
            <StatCard
              icon={<Activity className="w-3.5 h-3.5" />}
              label="调用次数"
              value={data.totals.calls.toLocaleString()}
              hint={`最近 ${data.range_days} 天`}
            />
            <StatCard
              icon={<Zap className="w-3.5 h-3.5" />}
              label="Token 总量"
              value={data.totals.tokens.toLocaleString()}
              hint={`输入 ${compact(data.totals.input_tokens)} / 输出 ${compact(data.totals.output_tokens)}`}
            />
            <StatCard
              icon={<Timer className="w-3.5 h-3.5" />}
              label="平均耗时"
              value={`${data.totals.avg_duration_ms.toFixed(0)} ms`}
              hint="单次模型调用"
            />
            <StatCard
              icon={<BarChart3 className="w-3.5 h-3.5" />}
              label="单次均 Token"
              value={
                data.totals.calls > 0
                  ? Math.round(data.totals.tokens / data.totals.calls).toLocaleString()
                  : '0'
              }
              hint="总量 / 调用数"
            />
            <StatCard
              icon={<span className="text-[13px] leading-none">¥</span>}
              label="估算成本"
              value={formatMoney(data.totals.cost, data.currency)}
              hint="按 config.yml 单价估算"
              accent
            />
          </div>

          <section className="bg-white dark:bg-gray-900/60 border border-gray-200 dark:border-gray-800 rounded-2xl shadow-sm p-4">
            <h3 className="text-sm font-medium text-gray-700 dark:text-gray-200 mb-4">
              每日 Token 消耗
            </h3>
            {data.daily.length === 0 ? (
              <p className="text-sm text-gray-400 py-8 text-center">该时间段没有调用记录</p>
            ) : (
              <div className="flex items-end gap-1.5 h-40">
                {data.daily.map((d) => (
                  <div key={d.date} className="flex-1 flex flex-col items-center justify-end h-full group">
                    <span className="text-[10px] text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity mb-1 tabular-nums">
                      {compact(d.tokens)}
                    </span>
                    <div
                      className="w-full rounded-t bg-orange-400/80 group-hover:bg-orange-500 transition-colors min-h-[2px]"
                      style={{ height: `${Math.max(2, (d.tokens / maxDaily) * 100)}%` }}
                      title={`${d.date}：${d.calls} 次调用，${d.tokens.toLocaleString()} tokens，${formatMoney(d.cost, data.currency)}`}
                    />
                    <span className="mt-1.5 text-[10px] text-gray-400 truncate w-full text-center">
                      {d.date.slice(5)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </section>

          <div className="grid lg:grid-cols-2 gap-4">
            <section className="bg-white dark:bg-gray-900/60 border border-gray-200 dark:border-gray-800 rounded-2xl shadow-sm p-4">
              <h3 className="text-sm font-medium text-gray-700 dark:text-gray-200 mb-3">按模块</h3>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-gray-500 dark:text-gray-400">
                    <th className="text-left font-medium pb-2">模块</th>
                    <th className="text-right font-medium pb-2">调用</th>
                    <th className="text-right font-medium pb-2">Token</th>
                  </tr>
                </thead>
                <tbody>
                  {data.by_module.map((m) => (
                    <tr key={m.module} className="border-t border-gray-100 dark:border-gray-800">
                      <td className="py-2 text-gray-700 dark:text-gray-200">{m.module}</td>
                      <td className="py-2 text-right tabular-nums text-gray-600 dark:text-gray-300">{m.calls}</td>
                      <td className="py-2 text-right tabular-nums text-gray-600 dark:text-gray-300">
                        {m.tokens.toLocaleString()}
                      </td>
                    </tr>
                  ))}
                  {data.by_module.length === 0 && (
                    <tr>
                      <td colSpan={3} className="py-6 text-center text-gray-400 text-sm">
                        暂无数据
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </section>

            <section className="bg-white dark:bg-gray-900/60 border border-gray-200 dark:border-gray-800 rounded-2xl shadow-sm p-4">
              <h3 className="text-sm font-medium text-gray-700 dark:text-gray-200 mb-3">
                按模型与成本
              </h3>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-gray-500 dark:text-gray-400">
                    <th className="text-left font-medium pb-2">模型</th>
                    <th className="text-right font-medium pb-2">调用</th>
                    <th className="text-right font-medium pb-2">Token</th>
                    <th className="text-right font-medium pb-2">成本</th>
                  </tr>
                </thead>
                <tbody>
                  {data.by_model.map((m) => (
                    <tr key={m.model} className="border-t border-gray-100 dark:border-gray-800">
                      <td className="py-2 text-gray-700 dark:text-gray-200 truncate max-w-[160px]" title={m.model}>
                        {m.model}
                      </td>
                      <td className="py-2 text-right tabular-nums text-gray-600 dark:text-gray-300">{m.calls}</td>
                      <td className="py-2 text-right tabular-nums text-gray-600 dark:text-gray-300">
                        {m.tokens.toLocaleString()}
                      </td>
                      <td className="py-2 text-right tabular-nums text-orange-600 dark:text-orange-300">
                        {formatMoney(m.cost, data.currency)}
                      </td>
                    </tr>
                  ))}
                  {data.by_model.length === 0 && (
                    <tr>
                      <td colSpan={4} className="py-6 text-center text-gray-400 text-sm">
                        暂无数据
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </section>
          </div>

          <section className="bg-white dark:bg-gray-900/60 border border-gray-200 dark:border-gray-800 rounded-2xl shadow-sm p-4">
            <h3 className="text-sm font-medium text-gray-700 dark:text-gray-200 mb-3">
              Token 消耗 Top 10
            </h3>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-gray-500 dark:text-gray-400">
                  <th className="text-left font-medium pb-2 w-10">#</th>
                  <th className="text-left font-medium pb-2">用户</th>
                  <th className="text-right font-medium pb-2">调用</th>
                  <th className="text-right font-medium pb-2">Token</th>
                </tr>
              </thead>
              <tbody>
                {data.top_users.map((u, i) => (
                  <tr key={u.user_id} className="border-t border-gray-100 dark:border-gray-800">
                    <td className="py-2 text-gray-400 tabular-nums">{i + 1}</td>
                    <td className="py-2 text-gray-700 dark:text-gray-200">{u.username}</td>
                    <td className="py-2 text-right tabular-nums text-gray-600 dark:text-gray-300">{u.calls}</td>
                    <td className="py-2 text-right tabular-nums text-gray-600 dark:text-gray-300">
                      {u.tokens.toLocaleString()}
                    </td>
                  </tr>
                ))}
                {data.top_users.length === 0 && (
                  <tr>
                    <td colSpan={4} className="py-6 text-center text-gray-400 text-sm">
                      暂无数据
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </section>
        </>
      ) : null}
    </div>
  );
}
