/**
 * Admin console · LLM usage tab
 *
 * Aggregations come from `/admin/usage`, which pushes GROUP BY into SQL.
 * The daily chart is drawn with plain divs on purpose: adding a chart library
 * to this page would grow the bundle without adding information.
 */

import { useCallback, useEffect, useState } from 'react';
import { Activity, BarChart3, Loader2, RefreshCcw, Timer, Zap } from 'lucide-react';
import type { AdminUsage } from '../../services/api/admin';
import { getAdminUsage } from '../../services/api/admin';

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
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="bg-white dark:bg-gray-900/60 border border-gray-200 dark:border-gray-800 rounded-2xl shadow-sm p-4">
      <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400 text-xs">
        {icon}
        <span>{label}</span>
      </div>
      <p className="mt-2 text-2xl font-bold text-gray-900 dark:text-white tabular-nums">{value}</p>
      {hint && <p className="mt-1 text-xs text-gray-400">{hint}</p>}
    </div>
  );
}

export default function AdminUsage({ token }: { token: string }) {
  const [days, setDays] = useState(7);
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

  const maxDaily = Math.max(1, ...(data?.daily.map((d) => d.tokens) ?? [0]));

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2">
        <div className="flex rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
          {RANGES.map((r) => (
            <button
              key={r}
              onClick={() => setDays(r)}
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
        <button
          onClick={load}
          className="p-2 rounded-lg text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          title="刷新"
        >
          <RefreshCcw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
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
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
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
                      title={`${d.date}：${d.calls} 次调用，${d.tokens.toLocaleString()} tokens`}
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
              <h3 className="text-sm font-medium text-gray-700 dark:text-gray-200 mb-3">按模型</h3>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-gray-500 dark:text-gray-400">
                    <th className="text-left font-medium pb-2">模型</th>
                    <th className="text-right font-medium pb-2">调用</th>
                    <th className="text-right font-medium pb-2">Token</th>
                  </tr>
                </thead>
                <tbody>
                  {data.by_model.map((m) => (
                    <tr key={m.model} className="border-t border-gray-100 dark:border-gray-800">
                      <td className="py-2 text-gray-700 dark:text-gray-200 truncate max-w-[180px]" title={m.model}>
                        {m.model}
                      </td>
                      <td className="py-2 text-right tabular-nums text-gray-600 dark:text-gray-300">{m.calls}</td>
                      <td className="py-2 text-right tabular-nums text-gray-600 dark:text-gray-300">
                        {m.tokens.toLocaleString()}
                      </td>
                    </tr>
                  ))}
                  {data.by_model.length === 0 && (
                    <tr>
                      <td colSpan={3} className="py-6 text-center text-gray-400 text-sm">
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
