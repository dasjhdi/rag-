/**
 * Admin console shell.
 *
 * 页签按能力显示：用户（read）、用量（read）、会话（sessions）、审计（audit）。
 * 权限由服务端强制，前端只做展示层的裁剪。
 */

import { useCallback, useEffect, useState } from 'react';
import { BarChart3, Loader2, MessagesSquare, RefreshCcw, ScrollText, Users } from 'lucide-react';
import { useAuth } from '../../contexts';
import type { AdminOverview, AdminWhoami } from '../../services/api/admin';
import { getAdminOverview, getAdminWhoami } from '../../services/api/admin';
import { formatMoney } from './ui';
import AdminAudit from './AdminAudit';
import AdminSessions from './AdminSessions';
import AdminUsage from './AdminUsage';
import AdminUsers from './AdminUsers';

type Tab = 'users' | 'usage' | 'sessions' | 'audit';

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
  const [whoami, setWhoami] = useState<AdminWhoami | null>(null);
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [loading, setLoading] = useState(true);

  const loadOverview = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      setOverview(await getAdminOverview(token));
    } catch {
      setOverview(null);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    if (!token) return;
    getAdminWhoami(token)
      .then(setWhoami)
      .catch(() => setWhoami(null));
  }, [token]);

  useEffect(() => {
    loadOverview();
  }, [loadOverview]);

  if (!token) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-gray-500">请先登录</div>
    );
  }

  const capabilities = whoami?.capabilities ?? [];
  const tabs: { key: Tab; label: string; icon: React.ReactNode; show: boolean }[] = [
    { key: 'users', label: '用户列表', icon: <Users className="w-4 h-4" />, show: capabilities.includes('read') },
    { key: 'usage', label: '用量看板', icon: <BarChart3 className="w-4 h-4" />, show: capabilities.includes('read') },
    {
      key: 'sessions',
      label: '会话排障',
      icon: <MessagesSquare className="w-4 h-4" />,
      show: capabilities.includes('sessions'),
    },
    { key: 'audit', label: '审计日志', icon: <ScrollText className="w-4 h-4" />, show: capabilities.includes('audit') },
  ];
  const visibleTabs = tabs.filter((t) => t.show);
  const activeTab = visibleTabs.some((t) => t.key === tab) ? tab : visibleTabs[0]?.key ?? 'users';

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-7xl mx-auto p-4 md:p-6 space-y-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl md:text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
              管理后台
              {whoami && (
                <span className="text-[11px] font-medium px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400">
                  {whoami.role}
                </span>
              )}
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              账号、用量、会话与审计。所有写操作都会记录操作人与时间。
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
              hint={`${overview.llm.tokens_today.toLocaleString()} tokens`}
            />
            <Metric
              label="7 日成本"
              value={formatMoney(overview.llm.cost_7d, overview.llm.currency)}
              hint={`今日 ${formatMoney(overview.llm.cost_today, overview.llm.currency)}`}
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

        <div className="flex gap-1 border-b border-gray-200 dark:border-gray-800 overflow-x-auto">
          {visibleTabs.map((item) => (
            <button
              key={item.key}
              onClick={() => setTab(item.key)}
              className={`flex items-center gap-1.5 px-4 py-2.5 text-sm -mb-px border-b-2 transition-colors whitespace-nowrap ${
                activeTab === item.key
                  ? 'border-orange-500 text-orange-600 dark:text-orange-400 font-medium'
                  : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200'
              }`}
            >
              {item.icon}
              {item.label}
            </button>
          ))}
        </div>

        {activeTab === 'users' && <AdminUsers token={token} capabilities={capabilities} />}
        {activeTab === 'usage' && <AdminUsage token={token} />}
        {activeTab === 'sessions' && <AdminSessions token={token} />}
        {activeTab === 'audit' && <AdminAudit token={token} />}
      </div>
    </div>
  );
}
