/**
 * Admin console API (v1.1 – v1.3).
 *
 * 权限由服务端按能力（capability）判定，前端只按 whoami 返回的能力决定展示
 * 哪些入口与按钮，不作为安全边界。
 */

import { apiDelete, apiGet, apiPost } from './client';

export interface AdminWhoami {
  username: string;
  role: string;
  is_admin: boolean;
  capabilities: string[];
}

export interface AdminOverview {
  generated_at: string;
  users: {
    total: number;
    active: number;
    admins: number;
    new_7d: number;
    logged_in_7d: number;
  };
  content: {
    global_documents: number;
    personal_documents: number;
  };
  activity: {
    conversations: number;
    agent_sessions: number;
    diet_log_items: number;
    pantry_items: number;
    recipe_feedback: number;
  };
  llm: {
    calls_today: number;
    tokens_today: number;
    calls_7d: number;
    tokens_7d: number;
    cost_today: number;
    cost_7d: number;
    currency: string;
  };
}

export interface AdminUserCounts {
  conversations: number;
  agent_sessions: number;
  diet_log_items: number;
  pantry_items: number;
  llm_calls: number;
  tokens: number;
}

export interface AdminUserRow {
  id: string;
  username: string;
  role: string;
  is_active: boolean;
  created_at: string | null;
  last_login_at: string | null;
  occupation: string | null;
  counts: AdminUserCounts;
}

export interface AdminUserList {
  items: AdminUserRow[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface AdminUsageModelRow {
  model: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  tokens: number;
  cost: number;
}

export interface AdminUsage {
  range_days: number;
  since: string;
  currency: string;
  totals: {
    calls: number;
    input_tokens: number;
    output_tokens: number;
    tokens: number;
    avg_duration_ms: number;
    cost: number;
  };
  daily: { date: string; calls: number; tokens: number; cost: number }[];
  by_module: { module: string; calls: number; tokens: number }[];
  by_model: AdminUsageModelRow[];
  top_users: { user_id: string; username: string; calls: number; tokens: number }[];
}

export interface AdminSessionRow {
  id: string;
  user_id: string;
  username: string;
  title: string;
  created_at: string | null;
  updated_at: string | null;
  message_count: number;
  compressed: boolean;
}

export interface AdminSessionList {
  items: AdminSessionRow[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface AdminSessionMessage {
  id: string;
  role: string;
  content: string;
  tool_name: string | null;
  tool_calls: unknown;
  trace: unknown;
  thinking_ms: number | null;
  answer_ms: number | null;
  created_at: string | null;
}

export interface AdminSessionDetail {
  id: string;
  username: string;
  user_id: string;
  title: string;
  created_at: string | null;
  updated_at: string | null;
  messages: AdminSessionMessage[];
}

export interface AdminAuditRow {
  id: string;
  actor_username: string;
  action: string;
  target_type: string;
  target_id: string | null;
  detail: Record<string, unknown> | null;
  /** 失败记录也会入库：success=false + error 说明被什么规则拦下 */
  success: boolean;
  error: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  request_id: string | null;
  user_agent: string | null;
  ip: string | null;
  created_at: string | null;
}

export interface AdminAuditList {
  items: AdminAuditRow[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export function getAdminWhoami(token: string): Promise<AdminWhoami> {
  return apiGet<AdminWhoami>('/admin/whoami', token);
}

export function getAdminOverview(token: string): Promise<AdminOverview> {
  return apiGet<AdminOverview>('/admin/overview', token);
}

export function getAdminUsers(
  token: string,
  options: { q?: string; page?: number; pageSize?: number } = {}
): Promise<AdminUserList> {
  const { q, page = 1, pageSize = 20 } = options;
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (q && q.trim()) params.set('q', q.trim());
  return apiGet<AdminUserList>(`/admin/users?${params.toString()}`, token);
}

export function getAdminUsage(token: string, days = 7): Promise<AdminUsage> {
  return apiGet<AdminUsage>(`/admin/usage?days=${days}`, token);
}

export function getAdminSessions(
  token: string,
  options: { q?: string; days?: number; page?: number; pageSize?: number } = {}
): Promise<AdminSessionList> {
  const { q, days = 30, page = 1, pageSize = 20 } = options;
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
    days: String(days),
  });
  if (q && q.trim()) params.set('q', q.trim());
  return apiGet<AdminSessionList>(`/admin/sessions?${params.toString()}`, token);
}

export function getAdminSessionDetail(token: string, id: string): Promise<AdminSessionDetail> {
  return apiGet<AdminSessionDetail>(`/admin/sessions/${id}`, token);
}

export function getAdminAudit(
  token: string,
  options: { page?: number; pageSize?: number; success?: boolean; action?: string } = {}
): Promise<AdminAuditList> {
  const { page = 1, pageSize = 20, success, action } = options;
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (success !== undefined) params.set('success', String(success));
  if (action) params.set('action', action);
  return apiGet<AdminAuditList>(`/admin/audit?${params.toString()}`, token);
}

export function setAdminUserStatus(
  token: string,
  userId: string,
  isActive: boolean
): Promise<{ id: string; is_active: boolean }> {
  return apiPost<{ id: string; is_active: boolean }, { is_active: boolean }>(
    `/admin/users/${userId}/status`,
    { is_active: isActive },
    token
  );
}

export function setAdminUserRole(
  token: string,
  userId: string,
  role: string
): Promise<{ id: string; role: string }> {
  return apiPost<{ id: string; role: string }, { role: string }>(
    `/admin/users/${userId}/role`,
    { role },
    token
  );
}

export function resetAdminUserPassword(
  token: string,
  userId: string,
  newPassword: string
): Promise<{ id: string; reset: boolean }> {
  return apiPost<{ id: string; reset: boolean }, { new_password: string }>(
    `/admin/users/${userId}/reset-password`,
    { new_password: newPassword },
    token
  );
}

export interface DeleteUserResult {
  id: string;
  deleted: boolean;
  counts: Record<string, number>;
}

/**
 * 删除账号。
 * force=false 时若名下有数据会返回 409（错误文案里带数据摘要）；
 * 确认要连同数据一起删除时传 force=true。
 */
export function deleteAdminUser(
  token: string,
  userId: string,
  force = false
): Promise<DeleteUserResult> {
  const suffix = force ? '?force=true' : '';
  return apiDelete<DeleteUserResult>(`/admin/users/${userId}${suffix}`, token);
}

export interface CreateUserInput {
  username: string;
  password: string;
  role: string;
}

export interface CreatedUser {
  id: string;
  username: string;
  role: string;
  is_active: boolean;
}

/** 超管直接创建账号（可指定初始角色），仅 user_create 能力可调用。 */
export function createAdminUser(
  token: string,
  payload: CreateUserInput
): Promise<CreatedUser> {
  return apiPost<CreatedUser, CreateUserInput>('/admin/users', payload, token);
}

// ---------------------------------------------------------------------------
// 告警
// ---------------------------------------------------------------------------
export interface AdminAlertEvent {
  id: string;
  kind: string;
  severity: string;
  title: string;
  message: string;
  metrics: Record<string, unknown> | null;
  channel: string | null;
  notified: boolean;
  notify_error: string | null;
  created_at: string | null;
}

export interface AdminAlertResponse {
  items: AdminAlertEvent[];
  config: {
    enabled: boolean;
    channel: string;
    notify_ready: boolean;
    interval_seconds: number;
    cooldown_minutes: number;
    thresholds: Record<string, number>;
  };
  last_run_at: string | null;
  last_error: string | null;
}

export function getAdminAlerts(token: string, limit = 20): Promise<AdminAlertResponse> {
  return apiGet<AdminAlertResponse>(`/admin/alerts?limit=${limit}`, token);
}

export function runAdminAlertCheck(
  token: string
): Promise<{ triggered: number; items: AdminAlertEvent[] }> {
  return apiPost(`/admin/alerts/check`, {}, token);
}

export function sendAdminAlertTest(
  token: string
): Promise<{ notified: boolean; channel: string }> {
  return apiPost<{ notified: boolean; channel: string }>('/admin/alerts/test', {}, token);
}
