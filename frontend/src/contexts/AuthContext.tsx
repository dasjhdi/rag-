/**
 * Authentication Context
 *
 * 会话凭据由服务端下发的 HttpOnly Cookie 承载，JS 不接触令牌。
 * 页面刷新后通过 /auth/whoami 恢复登录态；`token` 字段保留为哨兵值，
 * 供既有组件（`if (!token)` 判据、API 入参）继续使用。
 */

import { createContext, useContext, useEffect, useMemo, useState, useCallback } from 'react';
import type { ReactNode } from 'react';
import {
  loginUser,
  loginTotp,
  registerUser,
  updateProfile as updateUserProfile,
  logout as revokeSession,
  whoami,
} from '../services/api';
import { COOKIE_SESSION_TOKEN, STORAGE_KEYS } from '../constants';
import type { AuthResponse, Credentials, UserProfileUpdateRequest } from '../types';

export interface LoginOutcome {
  /** 密码正确但还差动态码，调用 loginWithTotp 完成登录 */
  requiresTotp: boolean;
  challenge?: string;
}

export interface AuthContextValue {
  token: string | null;
  username: string | null;
  isAuthenticated: boolean;
  /** 启动时是否已完成会话探测，false 时不应据此重定向 */
  isReady: boolean;
  login: (credentials: Credentials) => Promise<LoginOutcome>;
  /** 第二步：用挑战 + 动态码完成登录 */
  loginWithTotp: (challenge: string, code: string) => Promise<void>;
  register: (credentials: Credentials) => Promise<void>;
  /** 默认全端登出；传 { revoke: false } 只清当前浏览器的 Cookie */
  logout: (options?: { revoke?: boolean }) => void;
  updateProfile: (data: UserProfileUpdateRequest) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

/** 清掉改造前遗留的明文令牌，避免旧数据继续留在浏览器里。 */
function purgeLegacyStorage(): void {
  localStorage.removeItem(STORAGE_KEYS.TOKEN);
  localStorage.removeItem(STORAGE_KEYS.REFRESH);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [username, setUsername] = useState<string | null>(null);
  const [isReady, setIsReady] = useState(false);

  // 启动时用 Cookie 会话探测身份（不依赖任何本地存储）
  useEffect(() => {
    let cancelled = false;
    purgeLegacyStorage();

    whoami()
      .then((me) => {
        if (cancelled) return;
        setToken(COOKIE_SESSION_TOKEN);
        setUsername(me.username);
        localStorage.setItem(STORAGE_KEYS.USERNAME, me.username);
      })
      .catch(() => {
        if (cancelled) return;
        setToken(null);
        setUsername(null);
      })
      .finally(() => {
        if (!cancelled) setIsReady(true);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  // 请求层静默续期成功后刷新登录态；彻底失效时回到未登录。
  useEffect(() => {
    const onRefreshed = () => setToken(COOKIE_SESSION_TOKEN);
    const onUnauthorized = () => {
      setToken(null);
      setUsername(null);
    };
    window.addEventListener('auth:token-refreshed', onRefreshed);
    window.addEventListener('auth-unauthorized', onUnauthorized);
    return () => {
      window.removeEventListener('auth:token-refreshed', onRefreshed);
      window.removeEventListener('auth-unauthorized', onUnauthorized);
    };
  }, []);

  const handleAuthSuccess = useCallback((data: AuthResponse) => {
    setToken(COOKIE_SESSION_TOKEN);
    setUsername(data.username);
    localStorage.setItem(STORAGE_KEYS.USERNAME, data.username);
    purgeLegacyStorage();
  }, []);

  const login = useCallback(async (credentials: Credentials): Promise<LoginOutcome> => {
    const res = await loginUser(credentials);
    if (res.requires_totp) {
      return { requiresTotp: true, challenge: res.totp_challenge };
    }
    handleAuthSuccess(res);
    return { requiresTotp: false };
  }, [handleAuthSuccess]);

  const loginWithTotp = useCallback(async (challenge: string, code: string) => {
    const res = await loginTotp({ challenge, code });
    handleAuthSuccess(res);
  }, [handleAuthSuccess]);

  const register = useCallback(async (credentials: Credentials) => {
    const res = await registerUser(credentials);
    handleAuthSuccess(res);
  }, [handleAuthSuccess]);

  const logout = useCallback((options?: { revoke?: boolean }) => {
    // 先清本地状态让界面立即响应，再通知服务端清 Cookie（默认同时吊销令牌）
    setToken(null);
    setUsername(null);
    localStorage.removeItem(STORAGE_KEYS.USERNAME);
    void revokeSession(options).catch(() => {
      /* 网络异常时 Cookie 仍会在过期后失效，不打扰用户 */
    });
  }, []);

  const updateProfile = useCallback(async (data: UserProfileUpdateRequest) => {
    if (!token) throw new Error('Not authenticated');
    const res = await updateUserProfile(data, token);
    if (res.username) {
      setUsername(res.username);
      localStorage.setItem(STORAGE_KEYS.USERNAME, res.username);
    }
  }, [token]);

  const value = useMemo<AuthContextValue>(() => ({
    token,
    username,
    isAuthenticated: Boolean(token),
    isReady,
    login,
    loginWithTotp,
    register,
    logout,
    updateProfile,
  }), [token, username, isReady, login, loginWithTotp, register, logout, updateProfile]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/**
 * Hook to access authentication context
 */
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return ctx;
}
