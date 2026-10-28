/**
 * User-related type definitions
 */

export interface Credentials {
  username: string;
  password: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  username: string;
  /** 长有效期令牌，仅用于 /auth/refresh */
  refresh_token?: string;
  /** 访问令牌有效期（秒） */
  expires_in?: number;
  /** 需要第二步动态码：此时 access_token 为空 */
  requires_totp?: boolean;
  /** 密码阶段签发的短期挑战，用于 /auth/login/totp */
  totp_challenge?: string;
  /** 已登录但被策略要求绑定双因子 */
  totp_setup_required?: boolean;
}

export interface UserProfile {
  user_id: string;
  username: string;
  occupation?: string | null;
  bio?: string | null;
  profile?: string | null;
  user_instruction?: string | null;
}

export interface UserProfileUpdateRequest {
  username?: string;
  occupation?: string;
  bio?: string;
  profile?: string;
  user_instruction?: string;
}
