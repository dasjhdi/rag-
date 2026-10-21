/**
 * Admin console shell (P0).
 *
 * Two tabs today: user directory and LLM usage. Everything is read-only, and
 * permission is enforced server-side — a non-admin account gets a 403 which the
 * child views render as a "no permission" panel.
 */

import { useCallback, useEffect, useState } from 'react';
import { BarChart3, Loader2, RefreshCcw, Users } from 'lucide-react';
import { useAuth } from '../../contexts';
import type { AdminOverview } from '../../services/api/admin';
import { getAdminOverview } from '../../services/api/admin';
import AdminUsers from './AdminUsers';
import AdminUsage from './AdminUsage';

type Tab = 'users' | 'usage';

function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="bg-white dark:bg-gray-900/60 border border-gray-200 dark:border-gray-800 rounded-2xl shadow-sm px-4 py-3">
      <div className="text-xs text-gray-500 dark:text-gray-400">{label}</div>
      <div className="mt-1 text-xl font-bold text-gray-900 dark:text-white tabular-nums">{value}</div>
      {hint && <div className="text-[11px] text-gray-400 mt-0.5">{hint}</div>}
    </div>
  );
}

export default function AdminConsole() {
  const { token } = useAuth();
  const [tab, setTab] = useState<Tab>('users');
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [loading, setLoading] = useState(true);

  const loadOverview = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      setOverview(await getAdminOverview(token));
    } catch {
      // Child views surface permission errors; the header just stays empty.
      setOverview(null);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    loadOverview();
  }, [loadOverview]);

  if (!token) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-gray-500">
        请先登录
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-7xl mx-auto p-4 md:p-6 space-y-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl md:text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
              管理后台
              <span className="text-[11px] font-medium px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400">
                P0 · 只读
              </span>
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              账号与用量总览。当前版本不提供任何写操作。
            </p>
          </div>
          <button
            onClick={loadOverview}
            className="p-2 rounded-lg text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            title="刷新概览"
          >
            <RefreshCcw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {overview ? (
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
            <Metric
              label="账号总数"
              value={String(overview.users.total)}
              hint={`7 日新增 ${overview.users.new_7d} · 禁用 ${overview.users.total - overview.users.active}`}
            />
            <Metric
              label="7 日登录"
              value={String(overview.users.logged_in_7d)}
              hint={`管理员 ${overview.users.admins}`}
            />
            <Metric
              label="今日调用"
              value={overview.llm.calls_today.toLocaleString()}
              hint={`今日 ${overview.llm.tokens_today.toLocaleString()} tokens`}
            />
            <Metric
              label="7 日 Token"
              value={overview.llm.tokens_7d.toLocaleString()}
              hint={`${overview.llm.calls_7d.toLocaleString()} 次调用`}
            />
            <Metric
              label="内容 / 会话"
              value={`${overview.content.global_documents} / ${overview.activity.conversations}`}
              hint={`Agent 会话 ${overview.activity.agent_sessions} 个`}
            />
          </div>
        ) : (
          <div className="flex items-center gap-2 text-sm text-gray-400 h-16">
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                正在加载概览…
              </>
            ) : (
              '概览不可用（可能没有后台权限）'
            )}
          </div>
        )}

        <div className="flex gap-1 border-b border-gray-200 dark:border-gray-800">
          {(
            [
              { key: 'users', label: '用户列表', icon: <Users className="w-4 h-4" /> },
              { key: 'usage', label: '用量看板', icon: <BarChart3 className="w-4 h-4" /> },
            ] as const
          ).map((item) => (
            <button
              key={item.key}
              onClick={() => setTab(item.key)}
              className={`flex items-center gap-1.5 px-4 py-2.5 text-sm -mb-px border-b-2 transition-colors ${
                tab === item.key
                  ? 'border-orange-500 text-orange-600 dark:text-orange-400 font-medium'
                  : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200'
              }`}
            >
              {item.icon}
              {item.label}
            </button>
          ))}
        </div>

        {tab === 'users' ? <AdminUsers token={token} /> : <AdminUsage token={token} />}
      </div>
    </div>
  );
}
