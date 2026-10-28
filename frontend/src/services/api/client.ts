/**
 * Base API client with common utilities
 */

import { API_BASE, COOKIE_SESSION_TOKEN, STORAGE_KEYS } from '../../constants';
import { capitalize } from '../../utils';

/**
 * 真实 Bearer 令牌才拼 Authorization；Cookie 会话模式下不带该头。
 */
function isBearerToken(token?: string): token is string {
  return Boolean(token) && token !== COOKIE_SESSION_TOKEN;
}

/**
 * Create authorization headers
 */
export function createAuthHeaders(token?: string): HeadersInit | undefined {
  return isBearerToken(token) ? { Authorization: `Bearer ${token}` } : undefined;
}

/**
 * Create headers with content-type and optional auth
 */
export function createJsonHeaders(token?: string): HeadersInit {
  return {
    'Content-Type': 'application/json',
    ...(isBearerToken(token) ? { Authorization: `Bearer ${token}` } : {}),
  };
}

/** 所有请求都带上 Cookie（同域部署下浏览器会自动附加会话）。 */
const CREDENTIALS: RequestCredentials = 'include';

/**
 * Custom error for 401 Unauthorized responses
 */
export class UnauthorizedError extends Error {
  constructor(message: string = 'Unauthorized') {
    super(message);
    this.name = 'UnauthorizedError';
  }
}

/**
 * Error carrying the HTTP status, so callers can tell "no permission" (403)
 * apart from "service unavailable" / network failures.
 */
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

/**
 * Parse typical FastAPI error responses (Pydantic validation errors or HTTPException)
 * and return a friendly message string.
 */
export async function parseErrorResponse(response: Response): Promise<string> {
  // Handle 401 Unauthorized - clear auth data
  if (response.status === 401) {
    localStorage.removeItem(STORAGE_KEYS.TOKEN);
    localStorage.removeItem(STORAGE_KEYS.REFRESH);
    localStorage.removeItem(STORAGE_KEYS.USERNAME);
    // Dispatch custom event to notify auth context
    window.dispatchEvent(new Event('auth-unauthorized'));
    throw new UnauthorizedError();
  }

  const contentType = response.headers.get('content-type') || '';
  
  try {
    if (contentType.includes('application/json')) {
      const body = await response.json();

      // Pydantic validation errors use `detail` as an array of error objects
      if (Array.isArray(body.detail)) {
        const parts = body.detail.map((err: { loc?: string[]; msg: string; ctx?: Record<string, unknown> }) => {
          const loc = Array.isArray(err.loc) ? err.loc.filter(Boolean) : [];
          const field = loc.length ? loc[loc.length - 1] : 'field';
          const msg = typeof err.msg === 'string' ? err.msg : JSON.stringify(err.msg);
          return `${capitalize(String(field))}: ${friendlyMessageFor(msg, err.ctx)}`.trim();
        });
        return parts.join('\n');
      }

      // If detail is a string, return it
      if (typeof body.detail === 'string') {
        return body.detail;
      }

      // Fallback to message or stringified body
      if (body.message) return String(body.message);
      return JSON.stringify(body);
    }
    
    // Not JSON; return raw text
    return await response.text();
  } catch (e) {
    return String(e instanceof Error ? e.message : 'Unknown error');
  }
}

/**
 * Convert error messages to user-friendly format
 */
function friendlyMessageFor(msg: string, ctx?: Record<string, unknown>): string {
  if (msg.includes('at least') && ctx && ctx.min_length) {
    return `Must be at least ${ctx.min_length} characters`;
  }
  if (msg.includes('field required') || msg === 'value_error.missing') {
    return 'This field is required';
  }
  return msg;
}

/**
 * 单飞（single-flight）刷新：并发 401 只触发一次 /auth/refresh。
 * 浏览器场景直接用 HttpOnly 刷新 Cookie；若本地仍存有旧令牌则兼容带上。
 */
let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const legacyRefresh = localStorage.getItem(STORAGE_KEYS.REFRESH);

  if (!refreshPromise) {
    refreshPromise = fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      credentials: CREDENTIALS,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(
        legacyRefresh ? { refresh_token: legacyRefresh } : {}
      ),
    })
      .then(async (res) => {
        if (!res.ok) return null;
        const data = await res.json();
        // Cookie 模式下服务端已写入新 Cookie，无需再保存任何东西
        localStorage.removeItem(STORAGE_KEYS.TOKEN);
        localStorage.removeItem(STORAGE_KEYS.REFRESH);
        window.dispatchEvent(new Event('auth:token-refreshed'));
        return (data?.access_token as string) || COOKIE_SESSION_TOKEN;
      })
      .catch(() => null)
      .finally(() => {
        refreshPromise = null;
      });
  }

  return refreshPromise;
}

/**
 * 发起请求；遇到 401 时先尝试刷新会话并重试一次。
 */
async function send(url: string, init: RequestInit): Promise<Response> {
  const withCredentials: RequestInit = { ...init, credentials: CREDENTIALS };
  let response = await fetch(url, withCredentials);

  if (response.status === 401) {
    const fresh = await refreshAccessToken();
    if (fresh) {
      // Cookie 已由刷新接口重写；若历史上拿到过 Bearer 令牌则一并带上
      const headers = new Headers(init.headers as HeadersInit | undefined);
      if (fresh !== COOKIE_SESSION_TOKEN) {
        headers.set('Authorization', `Bearer ${fresh}`);
      }
      response = await fetch(url, { ...init, headers, credentials: CREDENTIALS });
    }
  }

  return response;
}

/**
 * Make a GET request
 */
export async function apiGet<T>(endpoint: string, token?: string): Promise<T> {
  const response = await send(
    `${API_BASE}${endpoint}`,
    { headers: createAuthHeaders(token) },
  );

  if (!response.ok) {
    const msg = await parseErrorResponse(response);
    throw new ApiError(msg || `HTTP error! status: ${response.status}`, response.status);
  }

  return response.json();
}

/**
 * Make a POST request
 */
export async function apiPost<T, D = unknown>(
  endpoint: string,
  data: D,
  token?: string
): Promise<T> {
  const response = await send(
    `${API_BASE}${endpoint}`,
    {
      method: 'POST',
      headers: createJsonHeaders(token),
      body: JSON.stringify(data),
    },
  );

  if (!response.ok) {
    const msg = await parseErrorResponse(response);
    throw new ApiError(msg || `HTTP error! status: ${response.status}`, response.status);
  }

  return response.json();
}

/**
 * Make a PUT request
 */
export async function apiPut<T, D = unknown>(
  endpoint: string,
  data: D,
  token?: string
): Promise<T> {
  const response = await send(
    `${API_BASE}${endpoint}`,
    {
      method: 'PUT',
      headers: createJsonHeaders(token),
      body: JSON.stringify(data),
    },
  );

  if (!response.ok) {
    const msg = await parseErrorResponse(response);
    throw new ApiError(msg || `HTTP error! status: ${response.status}`, response.status);
  }

  return response.json();
}

/**
 * Make a PATCH request
 */
export async function apiPatch<T, D = unknown>(
  endpoint: string,
  data: D,
  token?: string
): Promise<T> {
  const response = await send(
    `${API_BASE}${endpoint}`,
    {
      method: 'PATCH',
      headers: createJsonHeaders(token),
      body: JSON.stringify(data),
    },
  );

  if (!response.ok) {
    const msg = await parseErrorResponse(response);
    throw new ApiError(msg || `HTTP error! status: ${response.status}`, response.status);
  }

  return response.json();
}

/**
 * Make a DELETE request
 */
export async function apiDelete<T>(endpoint: string, token?: string): Promise<T> {
  const response = await send(
    `${API_BASE}${endpoint}`,
    { method: 'DELETE', headers: createAuthHeaders(token) },
  );

  if (!response.ok) {
    const msg = await parseErrorResponse(response);
    throw new ApiError(msg || `HTTP error! status: ${response.status}`, response.status);
  }

  return response.json();
}
