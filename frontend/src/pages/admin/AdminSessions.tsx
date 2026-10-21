/**
 * Admin console · Sessions tab（排障）
 *
 * 左侧会话列表、右侧消息流与工具轨迹。数据来自 agent_sessions /
 * agent_messages：trace 里记录了每一轮的工具名、参数与结果，是回答
 * "它为什么答错" 的主要依据。
 */

import { useCallback, useEffect, useState } from 'react';
import { ChevronRight, Loader2, RefreshCcw, Search, X } from 'lucide-react';
import type { AdminSessionDetail, AdminSessionList, AdminSessionMessage } from '../../services/api/admin';
import { getAdminSessionDetail, getAdminSessions } from '../../services/api/admin';
import { formatDate } from './ui';

const PAGE_SIZE = 20;
const DAY_OPTIONS = [7, 30, 90];

interface TraceStep {
  action?: string;
  iteration?: number;
  tool_calls?: { name?: string; arguments?: unknown }[];
  content?: unknown;
  error?: string | null;
}

function pretty(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function MessageItem({ message }: { message: AdminSessionMessage }) {
  const steps = Array.isArray(message.trace) ? (message.trace as TraceStep[]) : [];
  const roleLabel: Record<string, string> = {
    user: '用户',
    assistant: '助手',
    tool: '工具',
    system: '系统',
  };
  const roleColor: Record<string, string> = {
    user: 'bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300',
    assistant: 'bg-orange-100 text-orange-700 dark:bg-orange-500/15 dark:text-orange-300',
    tool: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300',
    system: 'bg-purple-100 text-purple-700 dark:bg-purple-500/15 dark:text-purple-300',
  };

  return (
    <div className="border border-gray-100 dark:border-gray-800 rounded-lg p-3">
      <div className="flex items-center gap-2 mb-1.5">
        <span className={`px-1.5 py-0.5 rounded text-[11px] ${roleColor[message.role] ?? roleColor.tool}`}>
          {roleLabel[message.role] ?? message.role}
        </span>
        {message.tool_name && (
          <span className="text-[11px] text-gray-500 dark:text-gray-400">{message.tool_name}</span>
        )}
        <span className="text-[11px] text-gray-400 ml-auto">{formatDate(message.created_at)}</span>
      </div>

      {message.content && (
        <pre className="text-xs text-gray-700 dark:text-gray-300 whitespace-pre-wrap break-words max-h-56 overflow-y-auto">
          {message.content}
        </pre>
      )}

      {steps.length > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer text-[11px] text-orange-600 dark:text-orange-300 select-none">
            执行轨迹（{steps.length} 步）
          </summary>
          <ol className="mt-2 space-y-1.5">
            {steps.map((step, i) => (
              <li key={i} className="text-[11px] text-gray-600 dark:text-gray-400">
                <span className="font-medium text-gray-700 dark:text-gray-200">
                  #{step.iteration ?? i} {step.action ?? 'step'}
                </span>
                {step.tool_calls?.length ? (
                  <span className="ml-1">
                    → {step.tool_calls.map((t) => t.name || 'unknown').join(', ')}
                  </span>
                ) : null}
                {step.error ? (
                  <span className="ml-1 text-red-500">错误：{step.error}</span>
                ) : null}
                {step.tool_calls?.length ? (
                  <pre className="mt-1 ml-3 p-1.5 rounded bg-gray-50 dark:bg-gray-800/60 whitespace-pre-wrap break-words max-h-32 overflow-y-auto">
                    {pretty(step.tool_calls.map((t) => t.arguments))}
                  </pre>
                ) : null}
              </li>
            ))}
          </ol>
        </details>
      )}
    </div>
  );
}

export default function AdminSessions({ token }: { token: string }) {
  const [data, setData] = useState<AdminSessionList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [input, setInput] = useState('');
  const [query, setQuery] = useState('');
  const [days, setDays] = useState(30);
  const [page, setPage] = useState(1);

  const [detail, setDetail] = useState<AdminSessionDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getAdminSessions(token, { q: query, days, page, pageSize: PAGE_SIZE }));
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, [token, query, days, page]);

  useEffect(() => {
    load();
  }, [load]);

  const openDetail = async (id: string) => {
    setDetailLoading(true);
    try {
      setDetail(await getAdminSessionDetail(token, id));
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载会话失败');
    } finally {
      setDetailLoading(false);
    }
  };

  const submitSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    setQuery(input.trim());
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <form onSubmit={submitSearch} className="flex items-center gap-2">
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="按会话标题搜索"
              className="w-52 pl-9 pr-3 py-2 text-sm rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-orange-500/30"
            />
          </div>
          <button
            type="submit"
            className="px-3 py-2 text-sm rounded-lg bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-700"
          >
            搜索
          </button>
        </form>

        <div className="flex rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
          {DAY_OPTIONS.map((d) => (
            <button
              key={d}
              onClick={() => {
                setDays(d);
                setPage(1);
              }}
              className={`px-3 py-1.5 text-sm ${
                days === d
                  ? 'bg-orange-500 text-white'
                  : 'text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800'
              }`}
            >
              {d} 天
            </button>
          ))}
        </div>

        <button
          onClick={load}
          className="p-2 rounded-lg text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800"
          title="刷新"
        >
          <RefreshCcw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
        {data && (
          <span className="ml-auto text-xs text-gray-500 dark:text-gray-400">
            共 {data.total} 个会话
          </span>
        )}
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 dark:border-red-900/50 bg-red-50 dark:bg-red-900/20 px-4 py-3 text-sm text-red-600 dark:text-red-300">
          {error}
        </div>
      )}

      <div className="grid lg:grid-cols-[minmax(320px,420px)_1fr] gap-4">
        <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900/60 overflow-hidden">
          {loading && !data ? (
            <div className="flex items-center justify-center py-16 text-gray-500">
              <Loader2 className="w-5 h-5 animate-spin mr-2" />
              <span className="text-sm">加载中…</span>
            </div>
          ) : !data || data.items.length === 0 ? (
            <p className="py-16 text-center text-sm text-gray-400">该时间段没有会话</p>
          ) : (
            <ul className="divide-y divide-gray-100 dark:divide-gray-800 max-h-[560px] overflow-y-auto">
              {data.items.map((s) => (
                <li key={s.id}>
                  <button
                    onClick={() => openDetail(s.id)}
                    className={`w-full text-left px-3 py-2.5 hover:bg-gray-50 dark:hover:bg-gray-800/60 transition-colors ${
                      detail?.id === s.id ? 'bg-orange-50 dark:bg-orange-500/10' : ''
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-gray-800 dark:text-gray-100 truncate">
                        {s.title}
                      </span>
                      <ChevronRight className="w-3.5 h-3.5 text-gray-300 ml-auto shrink-0" />
                    </div>
                    <div className="mt-1 flex items-center gap-2 text-[11px] text-gray-500 dark:text-gray-400">
                      <span>{s.username}</span>
                      <span>·</span>
                      <span>{s.message_count} 条消息</span>
                      <span>·</span>
                      <span>{formatDate(s.updated_at)}</span>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}

          {data && data.pages > 1 && (
            <div className="flex items-center justify-between px-3 py-2 border-t border-gray-100 dark:border-gray-800 text-xs">
              <span className="text-gray-500 dark:text-gray-400">
                第 {data.page} / {data.pages} 页
              </span>
              <div className="flex gap-1.5">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={data.page <= 1}
                  className="px-2 py-1 rounded border border-gray-200 dark:border-gray-700 disabled:opacity-40"
                >
                  上一页
                </button>
                <button
                  onClick={() => setPage((p) => Math.min(data.pages, p + 1))}
                  disabled={data.page >= data.pages}
                  className="px-2 py-1 rounded border border-gray-200 dark:border-gray-700 disabled:opacity-40"
                >
                  下一页
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900/60 p-4 min-h-[240px]">
          {detailLoading ? (
            <div className="flex items-center justify-center py-16 text-gray-500">
              <Loader2 className="w-5 h-5 animate-spin mr-2" />
              <span className="text-sm">加载会话…</span>
            </div>
          ) : !detail ? (
            <div className="flex flex-col items-center justify-center py-16 text-gray-400">
              <Search className="w-8 h-8 mb-2 text-gray-300" />
              <p className="text-sm">从左侧选择一个会话查看消息与工具轨迹</p>
            </div>
          ) : (
            <div>
              <div className="flex items-start gap-2 mb-3">
                <div className="min-w-0">
                  <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-100 truncate">
                    {detail.title}
                  </h3>
                  <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5">
                    {detail.username} · {detail.messages.length} 条消息 · 创建于{' '}
                    {formatDate(detail.created_at)}
                  </p>
                </div>
                <button
                  onClick={() => setDetail(null)}
                  className="ml-auto p-1 rounded text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
                  aria-label="关闭"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
              <div className="space-y-2 max-h-[520px] overflow-y-auto pr-1">
                {detail.messages.map((m) => (
                  <MessageItem key={m.id} message={m} />
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
