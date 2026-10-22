/**
 * Authentication API services
 */

import { apiPost } from './client';
import type { Credentials, AuthResponse } from '../../types';

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
