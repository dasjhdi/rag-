/**
 * Admin console API (v1.1 – v1.3).
 *
 * 权限由服务端按能力（capability）判定，前端只按 whoami 返回的能力决定展示
 * 哪些入口与按钮，不作为安全边界。
 */

import { apiGet, apiPost } from './client';

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
  options: { page?: number; pageSize?: number } = {}
): Promise<AdminAuditList> {
  const { page = 1, pageSize = 20 } = options;
  return apiGet<AdminAuditList>(`/admin/audit?page=${page}&page_size=${pageSize}`, token);
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
