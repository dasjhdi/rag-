/**
 * Admin console · Users tab
 *
 * Read-only directory: who registered, whether they are active, when they last
 * logged in, and how much they have used the product. Write actions (disable,
 * reset password) are intentionally out of scope for P0.
 */

import { useCallback, useEffect, useState } from 'react';
import { Loader2, RefreshCcw, Search, ShieldAlert, Users } from 'lucide-react';
import type { AdminUserList } from '../../services/api/admin';
import { getAdminUsers } from '../../services/api/admin';

const PAGE_SIZE = 20;

function formatDate(value: string | null): string {
  if (!value) return '—';
  const d = new Date(value.endsWith('Z') ? value : `${value}Z`);
  if (Number.isNaN(d.getTime())) return '—';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const ROLE_LABELS: Record<string, string> = {
  super_admin: '超级管理员',
  ops: '运营',
  support: '客服',
  viewer: '只读',
  user: '普通用户',
};

const ROLE_CLASSES: Record<string, string> = {
  super_admin: 'bg-purple-100 text-purple-700 dark:bg-purple-500/15 dark:text-purple-300',
  ops: 'bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300',
  support: 'bg-teal-100 text-teal-700 dark:bg-teal-500/15 dark:text-teal-300',
  viewer: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300',
  user: 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400',
};

export default function AdminUsers({ token }: { token: string }) {
  const [data, setData] = useState<AdminUserList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [input, setInput] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getAdminUsers(token, { q: query, page, pageSize: PAGE_SIZE });
      setData(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, [token, query, page]);

  useEffect(() => {
    load();
  }, [load]);

  const submitSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    setQuery(input.trim());
  };

  const denied = !!error && /权限|403|forbidden/i.test(error);

  return (
    <div className="space-y-4">
      <form onSubmit={submitSearch} className="flex items-center gap-2">
        <div className="relative flex-1 max-w-sm">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="搜索用户名，回车确认"
            className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-orange-500/30"
          />
        </div>
        <button
          type="submit"
          className="px-3 py-2 text-sm rounded-lg bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
        >
          搜索
        </button>
        <button
          type="button"
          onClick={load}
          className="p-2 rounded-lg text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          title="刷新"
        >
          <RefreshCcw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
        {data && (
          <span className="ml-auto text-xs text-gray-500 dark:text-gray-400">
            共 {data.total} 个账号
          </span>
        )}
      </form>

      {denied ? (
        <div className="flex flex-col items-center justify-center py-16 text-gray-500 dark:text-gray-400">
          <ShieldAlert className="w-10 h-10 mb-3 text-amber-500" />
          <p className="text-sm">当前账号没有后台访问权限</p>
          <p className="text-xs mt-1 text-gray-400">请让管理员为账号设置 role 后再试</p>
        </div>
      ) : error ? (
        <div className="rounded-lg border border-red-200 dark:border-red-900/50 bg-red-50 dark:bg-red-900/20 px-4 py-3 text-sm text-red-600 dark:text-red-300">
          {error}
        </div>
      ) : loading && !data ? (
        <div className="flex items-center justify-center py-16 text-gray-500">
          <Loader2 className="w-5 h-5 animate-spin mr-2" />
          <span className="text-sm">加载中…</span>
        </div>
      ) : !data || data.items.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-gray-500 dark:text-gray-400">
          <Users className="w-10 h-10 mb-3 text-gray-300" />
          <p className="text-sm">没有匹配的账号</p>
        </div>
      ) : (
        <>
          <div className="overflow-x-auto rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900/60">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-800/60">
                  <th className="px-4 py-3 font-medium">用户名</th>
                  <th className="px-4 py-3 font-medium">角色</th>
                  <th className="px-4 py-3 font-medium">状态</th>
                  <th className="px-4 py-3 font-medium whitespace-nowrap">注册时间</th>
                  <th className="px-4 py-3 font-medium whitespace-nowrap">最后登录</th>
                  <th className="px-4 py-3 font-medium text-right">会话</th>
                  <th className="px-4 py-3 font-medium text-right">Agent</th>
                  <th className="px-4 py-3 font-medium text-right">记录</th>
                  <th className="px-4 py-3 font-medium text-right">Token</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((u) => (
                  <tr
                    key={u.id}
                    className="border-t border-gray-100 dark:border-gray-800 hover:bg-gray-50/70 dark:hover:bg-gray-800/40"
                  >
                    <td className="px-4 py-3 font-medium text-gray-900 dark:text-gray-100">
                      {u.username}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-block px-2 py-0.5 rounded-md text-xs ${ROLE_CLASSES[u.role] ?? ROLE_CLASSES.user}`}>
                        {ROLE_LABELS[u.role] ?? u.role}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {u.is_active ? (
                        <span className="inline-flex items-center gap-1.5 text-xs text-green-600 dark:text-green-400">
                          <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
                          正常
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 text-xs text-red-500">
                          <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
                          已禁用
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-500 dark:text-gray-400 whitespace-nowrap">
                      {formatDate(u.created_at)}
                    </td>
                    <td className="px-4 py-3 text-gray-500 dark:text-gray-400 whitespace-nowrap">
                      {formatDate(u.last_login_at)}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-gray-600 dark:text-gray-300">
                      {u.counts.conversations}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-gray-600 dark:text-gray-300">
                      {u.counts.agent_sessions}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-gray-600 dark:text-gray-300">
                      {u.counts.diet_log_items}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-gray-600 dark:text-gray-300">
                      {u.counts.tokens.toLocaleString()}
                    </td>
                  </tr>
                ))}
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
                className="px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 disabled:opacity-40 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
              >
                上一页
              </button>
              <button
                onClick={() => setPage((p) => (data.pages ? Math.min(data.pages, p + 1) : p))}
                disabled={data.page >= data.pages || loading}
                className="px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 disabled:opacity-40 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
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
