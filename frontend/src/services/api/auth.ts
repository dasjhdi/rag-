/**
 * Authentication API services
 */

import { apiGet, apiPost } from './client';
import type { Credentials, AuthResponse } from '../../types';

/** 第二步：用密码阶段拿到的一次性挑战换取正式令牌 */
export interface TotpLoginRequest {
  challenge: string;
  code: string;
}

export interface TotpStatus {
  enabled: boolean;
  required: boolean;
  policy_enabled: boolean;
  confirmed_at: string | null;
  recovery_codes_left: number;
  issuer: string;
}

export interface TotpSetup {
  secret: string;
  otpauth_uri: string;
  issuer: string;
  digits: number;
  period: number;
}

export interface TotpConfirmResult {
  enabled: boolean;
  recovery_codes: string[];
  note: string;
}

export interface SessionIdentity {
  username: string;
  role: string;
  is_admin: boolean;
}

/**
 * User login
 */
export async function login(credentials: Credentials): Promise<AuthResponse> {
  return apiPost<AuthResponse>('/auth/login', credentials);
}

/**
 * User registration
 */
export async function register(credentials: Credentials): Promise<AuthResponse> {
  return apiPost<AuthResponse>('/auth/register', credentials);
}

/**
 * 用刷新令牌换取新的访问令牌（401 时由 client.ts 自动调用）
 */
export async function refreshToken(refreshTokenValue: string): Promise<AuthResponse> {
  return apiPost<AuthResponse>('/auth/refresh', { refresh_token: refreshTokenValue });
}

/**
 * 主动登出：服务端递增令牌版本、清除会话 Cookie，使该账号全部令牌失效。
 * 注意是「全端登出」，其他设备也会被踢下线。
 */
export async function logout(options: { revoke?: boolean } = {}): Promise<void> {
  const suffix = options.revoke === false ? '?revoke=false' : '';
  await apiPost<unknown, Record<string, never>>(`/auth/logout${suffix}`, {});
}

/** 读取当前 Cookie 会话对应的账号，用于刷新页面后恢复登录态。 */
export async function whoami(): Promise<SessionIdentity> {
  return apiGet<SessionIdentity>('/auth/whoami');
}

// ---------------------------------------------------------------------------
// 双因子（TOTP）
// ---------------------------------------------------------------------------
export async function loginTotp(payload: TotpLoginRequest): Promise<AuthResponse> {
  return apiPost<AuthResponse>('/auth/login/totp', payload);
}

export async function totpStatus(): Promise<TotpStatus> {
  return apiGet<TotpStatus>('/auth/totp/status');
}

export async function totpSetup(): Promise<TotpSetup> {
  return apiPost<TotpSetup, Record<string, never>>('/auth/totp/setup', {});
}

export async function totpConfirm(code: string): Promise<TotpConfirmResult> {
  return apiPost<TotpConfirmResult, { code: string }>('/auth/totp/confirm', { code });
}

export async function totpDisable(password: string, code: string): Promise<{ enabled: boolean }> {
  return apiPost<{ enabled: boolean }, { password: string; code: string }>(
    '/auth/totp/disable',
    { password, code },
  );
}
