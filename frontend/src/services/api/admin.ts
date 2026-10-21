/**
 * Admin console API (P0: read-only).
 *
 * Endpoints live under `/api/v1/admin/*` and require an admin role; a normal
 * account receives 403, which the UI surfaces as a "no permission" state.
 */

import { apiGet } from './client';

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

export interface AdminUsageBucket {
  calls: number;
  tokens: number;
}

export interface AdminUsage {
  range_days: number;
  since: string;
  totals: {
    calls: number;
    input_tokens: number;
    output_tokens: number;
    tokens: number;
    avg_duration_ms: number;
  };
  daily: { date: string; calls: number; tokens: number }[];
  by_module: { module: string; calls: number; tokens: number }[];
  by_model: { model: string; calls: number; tokens: number }[];
  top_users: { user_id: string; username: string; calls: number; tokens: number }[];
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
