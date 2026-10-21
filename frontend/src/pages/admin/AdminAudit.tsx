/**
 * Admin console · Audit tab
 *
 * 后台所有写操作的留痕：谁、何时、对谁、做了什么、改前改后、来源 IP。
 * 仅 super_admin 可见（capability: audit）。
 */

import { useCallback, useEffect, useState } from 'react';
import { Download, Loader2, RefreshCcw, ScrollText } from 'lucide-react';
import type { AdminAuditList } from '../../services/api/admin';
import { getAdminAudit } from '../../services/api/admin';
import { exportCsv, formatDate } from './ui';

const PAGE_SIZE = 20;

const ACTION_LABELS: Record<string, string> = {
  'user.disable': '禁用账号',
  'user.enable': '启用账号',
  'user.role': '修改角色',
  'user.reset_password': '重置密码',
};

export default function AdminAudit({ token }: { token: string }) {
  const [data, setData] = useState<AdminAuditList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getAdminAudit(token, { page, pageSize: PAGE_SIZE }));
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, [token, page]);

  useEffect(() => {
    load();
  }, [load]);

  const exportAudit = () => {
    if (!data) return;
    exportCsv(
      `cookhero-audit-${new Date().toISOString().slice(0, 10)}.csv`,
      ['时间', '操作人', '动作', '对象', '变更前', '变更后', 'IP'],
      data.items.map((r) => [
        formatDate(r.created_at),
        r.actor_username,
        ACTION_LABELS[r.action] ?? r.action,
        String((r.detail as Record<string, unknown> | null)?.username ?? r.target_id ?? ''),
        String((r.detail as Record<string, unknown> | null)?.before ?? ''),
        String((r.detail as Record<string, unknown> | null)?.after ?? ''),
        r.ip ?? '',
      ])
    );
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <button
          onClick={load}
          className="p-2 rounded-lg text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800"
          title="刷新"
        >
          <RefreshCcw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
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
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-800/60">
                  <th className="px-4 py-3 font-medium whitespace-nowrap">时间</th>
                  <th className="px-4 py-3 font-medium">操作人</th>
                  <th className="px-4 py-3 font-medium">动作</th>
                  <th className="px-4 py-3 font-medium">对象</th>
                  <th className="px-4 py-3 font-medium">变更</th>
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
                      <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                        {'before' in detail || 'after' in detail
                          ? `${String(detail.before ?? '—')} → ${String(detail.after ?? '—')}`
                          : '—'}
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
