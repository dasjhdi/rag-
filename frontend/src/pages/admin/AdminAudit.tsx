/**
 * Admin console · Audit tab
 *
 * 后台所有写操作的留痕：谁、何时、对谁、做了什么、成功还是被拦截、
 * 改前改后、请求号与来源。失败记录由中间件独立事务写入，不会随业务回滚丢失。
 * 仅 super_admin 可见（capability: audit）。
 */

import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, Download, Loader2, RefreshCcw, ScrollText } from 'lucide-react';
import type { AdminAuditList, AdminAuditRow } from '../../services/api/admin';
import { getAdminAudit } from '../../services/api/admin';
import { exportCsv, formatDate } from './ui';

const PAGE_SIZE = 20;

const ACTION_LABELS: Record<string, string> = {
  'user.disable': '禁用账号',
  'user.enable': '启用账号',
  'user.role': '修改角色',
  'user.reset_password': '重置密码',
  'user.create': '创建账号',
  'user.delete': '删除账号',
  'user.status': '启停账号（失败）',
  'alert.check': '手动巡检告警',
};

type ResultFilter = 'all' | 'success' | 'failure';

/** 把 {a:1} 这类前后值压成一行，表格里不炸行高。 */
function compactDiff(row: AdminAuditRow): string {
  const before = row.before ?? (row.detail?.before as Record<string, unknown> | undefined);
  const after = row.after ?? (row.detail?.after as Record<string, unknown> | undefined);
  if (!before && !after) return '—';
  const flatten = (value: unknown) =>
    value && typeof value === 'object'
      ? Object.entries(value as Record<string, unknown>)
          .map(([key, val]) => `${key}=${String(val)}`)
          .join(', ')
      : String(value);
  if (before && after) return `${flatten(before)} → ${flatten(after)}`;
  return before ? `删除前：${flatten(before)}` : `新增：${flatten(after)}`;
}

export default function AdminAudit({ token }: { token: string }) {
  const [data, setData] = useState<AdminAuditList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<ResultFilter>('all');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(
        await getAdminAudit(token, {
          page,
          pageSize: PAGE_SIZE,
          success: result === 'all' ? undefined : result === 'success',
        })
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, [token, page, result]);

  useEffect(() => {
    load();
  }, [load]);

  const exportAudit = () => {
    if (!data) return;
    exportCsv(
      `cookhero-audit-${new Date().toISOString().slice(0, 10)}.csv`,
      ['时间', '操作人', '动作', '对象', '结果', '错误', '变更', '请求号', 'IP', 'User-Agent'],
      data.items.map((r) => [
        formatDate(r.created_at),
        r.actor_username,
        ACTION_LABELS[r.action] ?? r.action,
        String((r.detail as Record<string, unknown> | null)?.username ?? r.target_id ?? ''),
        r.success ? '成功' : '失败',
        r.error ?? '',
        compactDiff(r),
        r.request_id ?? '',
        r.ip ?? '',
        r.user_agent ?? '',
      ])
    );
  };

  const filterButton = (key: ResultFilter, label: string) => (
    <button
      key={key}
      onClick={() => {
        setResult(key);
        setPage(1);
      }}
      className={`px-3 py-1.5 text-xs rounded-full border transition-colors ${
        result === key
          ? 'bg-orange-500/15 border-orange-500/40 text-orange-300'
          : 'border-gray-200 dark:border-gray-700 text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200'
      }`}
    >
      {label}
    </button>
  );

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
        <div className="flex items-center gap-1.5">
          {filterButton('all', '全部')}
          {filterButton('success', '成功')}
          {filterButton('failure', '失败')}
        </div>
        <button
          onClick={exportAudit}
          disabled={!data}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-40"
        >
          <Download className="w-3.5 h-3.5" />
          导出 CSV
        </button>
        {data && (
          <span className="ml-auto text-xs text-gray-500 dark:text-gray-400">
            共 {data.total} 条记录
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
      ) : !data || data.items.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-gray-400">
          <ScrollText className="w-9 h-9 mb-2 text-gray-300" />
          <p className="text-sm">还没有后台操作记录</p>
        </div>
      ) : (
        <>
          <div className="overflow-x-auto rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900/60">
            <table className="adm-table adm-table--wide w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-800/60">
                  <th className="px-4 py-3 font-medium whitespace-nowrap">时间</th>
                  <th className="px-4 py-3 font-medium">操作人</th>
                  <th className="px-4 py-3 font-medium">动作</th>
                  <th className="px-4 py-3 font-medium">对象</th>
                  <th className="px-4 py-3 font-medium">结果</th>
                  <th className="px-4 py-3 font-medium">变更</th>
                  <th className="px-4 py-3 font-medium">请求号</th>
                  <th className="px-4 py-3 font-medium">IP</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((r) => {
                  const detail = (r.detail ?? {}) as Record<string, unknown>;
                  return (
                    <tr
                      key={r.id}
                      className="border-t border-gray-100 dark:border-gray-800 hover:bg-gray-50/70 dark:hover:bg-gray-800/40"
                    >
                      <td className="px-4 py-3 text-gray-500 dark:text-gray-400 whitespace-nowrap">
                        {formatDate(r.created_at)}
                      </td>
                      <td className="px-4 py-3 text-gray-800 dark:text-gray-100">
                        {r.actor_username}
                      </td>
                      <td className="px-4 py-3 text-gray-700 dark:text-gray-200">
                        {ACTION_LABELS[r.action] ?? r.action}
                      </td>
                      <td className="px-4 py-3 text-gray-600 dark:text-gray-300">
                        {String(detail.username ?? r.target_id ?? '—')}
                      </td>
                      <td className="px-4 py-3">
                        {r.success ? (
                          <span className="inline-flex items-center gap-1 text-green-600 dark:text-green-400">
                            <CheckCircle2 className="w-3.5 h-3.5" />
                            成功
                          </span>
                        ) : (
                          <span
                            className="inline-flex items-center gap-1 text-red-600 dark:text-red-400"
                            title={r.error ?? ''}
                          >
                            <AlertTriangle className="w-3.5 h-3.5" />
                            失败
                          </span>
                        )}
                        {!r.success && r.error && (
                          <div className="mt-1 max-w-[240px] truncate text-[11px] text-gray-500 dark:text-gray-400">
                            {r.error}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                        <span className="block max-w-[280px] truncate" title={compactDiff(r)}>
                          {compactDiff(r)}
                        </span>
                      </td>
                      <td className="px-4 py-3 font-mono text-[11px] text-gray-400">
                        {r.request_id ?? '—'}
                      </td>
                      <td className="px-4 py-3 text-gray-400 whitespace-nowrap">{r.ip ?? '—'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-500 dark:text-gray-400">
              第 {data.page} / {Math.max(data.pages, 1)} 页
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={data.page <= 1 || loading}
                className="px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 disabled:opacity-40"
              >
                上一页
              </button>
              <button
                onClick={() => setPage((p) => (data.pages ? Math.min(data.pages, p + 1) : p))}
                disabled={data.page >= data.pages || loading}
                className="px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 disabled:opacity-40"
              >
                下一页
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
