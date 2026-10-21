/**
 * Admin console · Users tab
 *
 * 用户目录 + 账号管理。写操作按能力显示：
 * user_status（启停）、user_password（重置密码）、user_role（改角色）。
 * 每次写操作成功后刷新列表，并给出提示。
 */

import { useCallback, useEffect, useState } from 'react';
import { Download, Loader2, RefreshCcw, Search, ShieldAlert, Users } from 'lucide-react';
import type { AdminUserList, AdminUserRow } from '../../services/api/admin';
import {
  getAdminUsers,
  resetAdminUserPassword,
  setAdminUserRole,
  setAdminUserStatus,
} from '../../services/api/admin';
import { Modal, ROLE_CLASSES, ROLE_LABELS, exportCsv, formatDate } from './ui';

const PAGE_SIZE = 20;
const ROLE_OPTIONS = ['user', 'viewer', 'support', 'ops', 'super_admin'];

export default function AdminUsers({
  token,
  capabilities,
}: {
  token: string;
  capabilities: string[];
}) {
  const can = (c: string) => capabilities.includes(c);

  const [data, setData] = useState<AdminUserList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [input, setInput] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [notice, setNotice] = useState<string | null>(null);

  const [resetTarget, setResetTarget] = useState<AdminUserRow | null>(null);
  const [password, setPassword] = useState('');
  const [roleTarget, setRoleTarget] = useState<AdminUserRow | null>(null);
  const [role, setRole] = useState('user');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getAdminUsers(token, { q: query, page, pageSize: PAGE_SIZE }));
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, [token, query, page]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 3000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const submitSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    setQuery(input.trim());
  };

  const toggleStatus = async (user: AdminUserRow) => {
    setBusy(true);
    try {
      await setAdminUserStatus(token, user.id, !user.is_active);
      setNotice(`${user.username} 已${user.is_active ? '禁用' : '启用'}`);
      await load();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '操作失败');
    } finally {
      setBusy(false);
    }
  };

  const submitPassword = async () => {
    if (!resetTarget) return;
    if (password.length < 8) {
      setNotice('密码至少 8 位');
      return;
    }
    setBusy(true);
    try {
      await resetAdminUserPassword(token, resetTarget.id, password);
      setNotice(`${resetTarget.username} 的密码已重置`);
      setResetTarget(null);
      setPassword('');
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '重置失败');
    } finally {
      setBusy(false);
    }
  };

  const submitRole = async () => {
    if (!roleTarget) return;
    setBusy(true);
    try {
      await setAdminUserRole(token, roleTarget.id, role);
      setNotice(`${roleTarget.username} 的角色已改为${ROLE_LABELS[role] ?? role}`);
      setRoleTarget(null);
      await load();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '修改失败');
    } finally {
      setBusy(false);
    }
  };

  const exportList = () => {
    if (!data) return;
    exportCsv(
      `cookhero-users-${new Date().toISOString().slice(0, 10)}.csv`,
      ['用户名', '角色', '状态', '注册时间', '最后登录', '会话', 'Agent 会话', '饮食记录', 'Token'],
      data.items.map((u) => [
        u.username,
        ROLE_LABELS[u.role] ?? u.role,
        u.is_active ? '正常' : '已禁用',
        formatDate(u.created_at),
        formatDate(u.last_login_at),
        u.counts.conversations,
        u.counts.agent_sessions,
        u.counts.diet_log_items,
        u.counts.tokens,
      ])
    );
  };

  const denied = !!error && /权限|403|forbidden/i.test(error);
  const hasActions = can('user_status') || can('user_password') || can('user_role');

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <form onSubmit={submitSearch} className="flex items-center gap-2">
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="搜索用户名，回车确认"
              className="w-56 pl-9 pr-3 py-2 text-sm rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-orange-500/30"
            />
          </div>
          <button
            type="submit"
            className="px-3 py-2 text-sm rounded-lg bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
          >
            搜索
          </button>
        </form>
        <button
          onClick={load}
          className="p-2 rounded-lg text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          title="刷新"
        >
          <RefreshCcw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
        <button
          onClick={exportList}
          disabled={!data}
          className="flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-40 transition-colors"
        >
          <Download className="w-3.5 h-3.5" />
          导出 CSV
        </button>
        {data && (
          <span className="ml-auto text-xs text-gray-500 dark:text-gray-400">
            共 {data.total} 个账号
          </span>
        )}
      </div>

      {notice && (
        <div className="rounded-lg border border-orange-200 dark:border-orange-900/50 bg-orange-50 dark:bg-orange-900/20 px-4 py-2.5 text-sm text-orange-700 dark:text-orange-300">
          {notice}
        </div>
      )}

      {denied ? (
        <div className="flex flex-col items-center justify-center py-16 text-gray-500 dark:text-gray-400">
          <ShieldAlert className="w-10 h-10 mb-3 text-amber-500" />
          <p className="text-sm">当前账号没有后台访问权限</p>
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
                  {hasActions && <th className="px-4 py-3 font-medium text-right">操作</th>}
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
                      <span
                        className={`inline-block px-2 py-0.5 rounded-md text-xs ${ROLE_CLASSES[u.role] ?? ROLE_CLASSES.user}`}
                      >
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
                    {hasActions && (
                      <td className="px-4 py-3 text-right whitespace-nowrap">
                        <div className="inline-flex gap-1">
                          {can('user_status') && (
                            <button
                              onClick={() => toggleStatus(u)}
                              disabled={busy}
                              className="px-2 py-1 text-xs rounded border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-40"
                            >
                              {u.is_active ? '禁用' : '启用'}
                            </button>
                          )}
                          {can('user_password') && (
                            <button
                              onClick={() => {
                                setResetTarget(u);
                                setPassword('');
                              }}
                              disabled={busy}
                              className="px-2 py-1 text-xs rounded border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-40"
                            >
                              重置密码
                            </button>
                          )}
                          {can('user_role') && (
                            <button
                              onClick={() => {
                                setRoleTarget(u);
                                setRole(u.role);
                              }}
                              disabled={busy}
                              className="px-2 py-1 text-xs rounded border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-40"
                            >
                              改角色
                            </button>
                          )}
                        </div>
                      </td>
                    )}
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

      {resetTarget && (
        <Modal title={`重置密码 · ${resetTarget.username}`} onClose={() => setResetTarget(null)}>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
            该用户已签发的令牌在过期前仍有效，必要时请同时禁用账号。
          </p>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="新密码（至少 8 位）"
            className="w-full px-3 py-2 text-sm rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-orange-500/30"
          />
          <div className="flex justify-end gap-2 mt-4">
            <button
              onClick={() => setResetTarget(null)}
              className="px-3 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300"
            >
              取消
            </button>
            <button
              onClick={submitPassword}
              disabled={busy}
              className="px-3 py-1.5 text-sm rounded-lg bg-orange-500 text-white hover:bg-orange-600 disabled:opacity-50"
            >
              确认重置
            </button>
          </div>
        </Modal>
      )}

      {roleTarget && (
        <Modal title={`修改角色 · ${roleTarget.username}`} onClose={() => setRoleTarget(null)}>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
            角色决定可执行的后台操作，修改会立即生效（无需对方重新登录）。
          </p>
          <select
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="w-full px-3 py-2 text-sm rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
          >
            {ROLE_OPTIONS.map((r) => (
              <option key={r} value={r}>
                {ROLE_LABELS[r] ?? r}
              </option>
            ))}
          </select>
          <div className="flex justify-end gap-2 mt-4">
            <button
              onClick={() => setRoleTarget(null)}
              className="px-3 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300"
            >
              取消
            </button>
            <button
              onClick={submitRole}
              disabled={busy}
              className="px-3 py-1.5 text-sm rounded-lg bg-orange-500 text-white hover:bg-orange-600 disabled:opacity-50"
            >
              保存
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
