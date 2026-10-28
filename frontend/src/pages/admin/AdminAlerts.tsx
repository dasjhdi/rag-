/**
 * Admin console · Alerts tab
 *
 * 成本突增 / LLM 错误率 / 评测失败率三类告警的最近事件与当前阈值。
 * 「立即巡检」会真的按冷却窗口推送，用于验证 webhook 是否配通。
 */

import { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  BellRing,
  CheckCircle2,
  Loader2,
  RefreshCcw,
  Send,
  ShieldAlert,
} from 'lucide-react';
import type { AdminAlertResponse } from '../../services/api/admin';
import { getAdminAlerts, runAdminAlertCheck, sendAdminAlertTest } from '../../services/api/admin';
import { formatDate } from './ui';

const KIND_LABELS: Record<string, string> = {
  cost_spike: '成本异常',
  llm_error_rate: 'LLM 错误率',
  evaluation_failure: '评测失败率',
};

const THRESHOLD_LABELS: Record<string, string> = {
  cost_spike_ratio: '成本倍数阈值',
  cost_min_amount: '成本金额下限（元）',
  error_rate: '错误率阈值',
  error_min_samples: '错误率最小样本',
  eval_error_rate: '评测失败率阈值',
  eval_min_samples: '评测最小样本',
};

export default function AdminAlerts({
  token,
  canRun,
}: {
  token: string;
  canRun: boolean;
}) {
  const [data, setData] = useState<AdminAlertResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getAdminAlerts(token, 30));
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  const runCheck = async () => {
    setRunning(true);
    setError(null);
    setNotice(null);
    try {
      const res = await runAdminAlertCheck(token);
      setNotice(
        res.triggered > 0
          ? `本次触发 ${res.triggered} 条告警，已按冷却窗口处理推送。`
          : '本次巡检未触发任何告警。'
      );
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : '巡检失败');
    } finally {
      setRunning(false);
    }
  };

  const sendTest = async () => {
    setTesting(true);
    setError(null);
    setNotice(null);
    try {
      const res = await sendAdminAlertTest(token);
      setNotice(`测试消息已发送，渠道：${res.channel}。请到接收端确认。`);
    } catch (err) {
      setError(err instanceof Error ? err.message : '测试消息发送失败');
    } finally {
      setTesting(false);
    }
  };

  const thresholds = data?.config.thresholds ?? {};
  const formatThreshold = (key: string, value: number) => {
    if (key.endsWith('_rate') || key.endsWith('_ratio')) return `${(value * 100).toFixed(0)}%`;
    return String(value);
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={load}
          className="p-2 rounded-lg text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800"
          title="刷新"
        >
          <RefreshCcw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
        {canRun && (
          <>
            <button onClick={runCheck} disabled={running} className="adm-btn is-primary">
              {running ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Send className="w-3.5 h-3.5" />
              )}
              立即巡检
            </button>
            <button onClick={sendTest} disabled={testing} className="adm-btn">
              {testing ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <BellRing className="w-3.5 h-3.5" />
              )}
              测试通道
            </button>
          </>
        )}
        {data && (
          <span className="ml-auto flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
            {data.config.enabled ? (
              <CheckCircle2 className="w-3.5 h-3.5 text-green-500" />
            ) : (
              <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
            )}
            {data.config.enabled ? `每 ${data.config.interval_seconds}s 巡检` : '告警已关闭'}
            {' · '}
            {data.config.notify_ready
              ? `推送通道：${data.config.channel}`
              : '未配置推送通道（仅落库）'}
          </span>
        )}
      </div>

      {notice && (
        <div className="rounded-lg border border-emerald-200 dark:border-emerald-900/50 bg-emerald-50 dark:bg-emerald-900/20 px-4 py-2.5 text-sm text-emerald-700 dark:text-emerald-300">
          {notice}
        </div>
      )}

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
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900/60 p-4">
              <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
                <ShieldAlert className="w-3.5 h-3.5" />
                当前阈值
              </div>
              <div className="space-y-1.5 text-sm">
                {Object.entries(thresholds).map(([key, value]) => (
                  <div
                    key={key}
                    className="flex items-center justify-between border-b border-dashed border-gray-100 dark:border-gray-800 py-1 last:border-0"
                  >
                    <span className="text-gray-500 dark:text-gray-400">
                      {THRESHOLD_LABELS[key] ?? key}
                    </span>
                    <b className="font-medium text-gray-700 dark:text-gray-200">
                      {formatThreshold(key, value)}
                    </b>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900/60 p-4">
              <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
                <BellRing className="w-3.5 h-3.5" />
                巡检状态
              </div>
              <div className="space-y-1.5 text-sm">
                <div className="flex justify-between border-b border-dashed border-gray-100 dark:border-gray-800 py-1">
                  <span className="text-gray-500 dark:text-gray-400">上次巡检</span>
                  <b className="font-medium text-gray-700 dark:text-gray-200">
                    {data?.last_run_at ? formatDate(data.last_run_at) : '尚未执行'}
                  </b>
                </div>
                <div className="flex justify-between border-b border-dashed border-gray-100 dark:border-gray-800 py-1">
                  <span className="text-gray-500 dark:text-gray-400">冷却窗口</span>
                  <b className="font-medium text-gray-700 dark:text-gray-200">
                    {data?.config.cooldown_minutes ?? '—'} 分钟
                  </b>
                </div>
                <div className="flex justify-between py-1">
                  <span className="text-gray-500 dark:text-gray-400">最近错误</span>
                  <b className="max-w-[220px] truncate font-medium text-gray-700 dark:text-gray-200">
                    {data?.last_error ?? '无'}
                  </b>
                </div>
              </div>
            </div>
          </div>

          {!data || data.items.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-gray-400">
              <BellRing className="w-9 h-9 mb-2 text-gray-300" />
              <p className="text-sm">还没有触发过告警</p>
              <p className="mt-1 text-xs text-gray-400">
                阈值触发后会在这里留痕，即使 webhook 没配置成功也不会丢记录
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {data.items.map((item) => (
                <div
                  key={item.id}
                  className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900/60 p-4"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                        item.severity === 'critical'
                          ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'
                          : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'
                      }`}
                    >
                      {item.severity === 'critical' ? '严重' : '警告'}
                    </span>
                    <span className="text-sm font-medium text-gray-800 dark:text-gray-100">
                      {item.title}
                    </span>
                    <span className="text-xs text-gray-400">
                      {KIND_LABELS[item.kind] ?? item.kind}
                    </span>
                    <span className="ml-auto text-xs text-gray-400">
                      {formatDate(item.created_at)}
                    </span>
                  </div>
                  <p className="mt-1.5 text-sm text-gray-600 dark:text-gray-300">{item.message}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-gray-400">
                    <span className={item.notified ? 'text-emerald-500' : 'text-amber-500'}>
                      {item.notified ? '已推送' : '未推送'}
                    </span>
                    {item.channel && <span>渠道：{item.channel}</span>}
                    {item.notify_error && (
                      <span className="text-red-400">推送失败：{item.notify_error}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
