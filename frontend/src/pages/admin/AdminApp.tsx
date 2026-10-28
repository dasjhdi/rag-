/**
 * 独立后台外壳 —— "Mission Control"
 *
 * 与主应用完全分离：由 admin.html 独立挂载，不经过主应用的侧栏与聊天布局。
 * 左侧功能栏按能力逐项列出模块，右侧为内容区；总览页负责「讲清楚每个模块做什么」。
 *
 * 权限裁剪只影响展示层，真正的校验始终在服务端（admin.py 的 require_capability）。
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import type { CSSProperties, FormEvent } from 'react';
import {
  Activity,
  ArrowUpRight,
  BarChart3,
  BellRing,
  ChevronRight,
  Cpu,
  Home,
  LayoutDashboard,
  Loader2,
  Lock,
  LogOut,
  Menu,
  MessagesSquare,
  RefreshCcw,
  ScrollText,
  ShieldAlert,
  ShieldCheck,
  Users,
  X,
} from 'lucide-react';
import { useAuth } from '../../contexts';
import { ApiError, UnauthorizedError } from '../../services/api/client';
import type { AdminOverview, AdminWhoami } from '../../services/api/admin';
import { getAdminOverview, getAdminWhoami } from '../../services/api/admin';
import type { TotpStatus } from '../../services/api/auth';
import { totpStatus } from '../../services/api/auth';
import EvaluationPage from '../Evaluation';
import LLMStatsPage from '../LLMStats';
import AdminAlerts from './AdminAlerts';
import AdminAudit from './AdminAudit';
import AdminTotp from './AdminTotp';
import AdminSessions from './AdminSessions';
import AdminUsage from './AdminUsage';
import AdminUsers from './AdminUsers';
import { ROLE_LABELS, formatDate, formatMoney } from './ui';
import './admin.css';

type Section =
  | 'overview'
  | 'users'
  | 'usage'
  | 'quality'
  | 'calls'
  | 'sessions'
  | 'audit'
  | 'alerts'
  | 'security';

type NavItem = {
  key: Section;
  label: string;
  en: string;
  desc: string;
  icon: typeof Users;
  /** 需要的后台能力；overview 无需能力 */
  cap?: string;
  /** 侧栏分组 */
  group: '总览' | '运营' | '诊断' | '安全';
  /** 权限说明（总览卡片用） */
  need: string;
  /** 模块识别色（仅用于总览卡片图标） */
  accent?: string;
};

const NAV: NavItem[] = [
  {
    key: 'overview',
    label: '总览',
    en: 'COMMAND',
    desc: '全局指标、模块入口与权限边界',
    icon: LayoutDashboard,
    group: '总览',
    need: '任意后台角色',
  },
  {
    key: 'users',
    label: '用户与角色',
    en: 'IDENTITY',
    desc: '账号、角色、启停与凭证',
    icon: Users,
    cap: 'read',
    group: '运营',
    need: '只读即可进入，写操作按能力开放',
    accent: '#f2a87d',
  },
  {
    key: 'usage',
    label: '用量看板',
    en: 'CONSUMPTION',
    desc: '调用量、Token 与成本',
    icon: BarChart3,
    cap: 'read',
    group: '运营',
    need: '只读',
    accent: '#d3a04c',
  },
  {
    key: 'quality',
    label: '质量监控',
    en: 'QUALITY',
    desc: 'RAGAS 忠实度与答案相关性评分',
    icon: Activity,
    cap: 'read',
    group: '运营',
    need: '只读',
    accent: '#9cbd9c',
  },
  {
    key: 'calls',
    label: '模型调用',
    en: 'MODELS',
    desc: '分模型的时延、错误率与用量分布',
    icon: Cpu,
    cap: 'read',
    group: '运营',
    need: '只读',
    accent: '#c4838d',
  },
  {
    key: 'sessions',
    label: '会话排障',
    en: 'SESSIONS',
    desc: '回看对话与 Agent 轨迹',
    icon: MessagesSquare,
    cap: 'sessions',
    group: '诊断',
    need: '需要会话排查能力（客服及以上）',
    accent: '#e0b489',
  },
  {
    key: 'alerts',
    label: '告警',
    en: 'ALERTS',
    desc: '成本突增、错误率与评测失败的触发记录',
    icon: BellRing,
    cap: 'read',
    group: '诊断',
    need: '只读',
    accent: '#e38573',
  },
  {
    key: 'audit',
    label: '审计日志',
    en: 'AUDIT',
    desc: '后台写操作的操作人、目标与时间',
    icon: ScrollText,
    cap: 'audit',
    group: '安全',
    need: '仅超级管理员',
    accent: '#e38573',
  },
  {
    key: 'security',
    label: '账号安全',
    en: 'SECURITY',
    desc: '双因子绑定、恢复码与关闭验证',
    icon: ShieldCheck,
    group: '安全',
    need: '任意后台角色',
    accent: '#c4838d',
  },
];

const CAP_LABELS: Record<string, string> = {
  read: '只读数据',
  sessions: '会话排障',
  user_status: '启用 / 禁用',
  'user_password:self_tier': '重置下级密码',
  'user_password:all': '重置任意密码',
  user_role: '修改角色',
  user_delete: '删除账号',
  user_create: '创建账号',
  audit: '审计日志',
  alerts: '告警运维',
};

const GROUPS = ['总览', '运营', '诊断', '安全'] as const;

type Access = 'checking' | 'granted' | 'denied' | 'expired' | 'unavailable';

function readSectionFromUrl(): Section {
  const value = new URLSearchParams(window.location.search).get('tab');
  return NAV.some((item) => item.key === value) ? (value as Section) : 'overview';
}

export default function AdminApp() {
  const { token, username, login, loginWithTotp, logout, isReady } = useAuth();
  const [whoami, setWhoami] = useState<AdminWhoami | null>(null);
  const [access, setAccess] = useState<Access>('checking');
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [loadingOverview, setLoadingOverview] = useState(false);
  const [section, setSection] = useState<Section>(readSectionFromUrl);
  const [navOpen, setNavOpen] = useState(false);
  const [nonce, setNonce] = useState(0);
  const [loginName, setLoginName] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [loginError, setLoginError] = useState<string | null>(null);
  const [totpError, setTotpError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // 双因子：密码通过后进入第二步，或提示必须绑定
  const [totpStage, setTotpStage] = useState<'password' | 'totp'>('password');
  const [totpChallenge, setTotpChallenge] = useState('');
  const [totpCode, setTotpCode] = useState('');
  const [totpState, setTotpState] = useState<TotpStatus | null>(null);

  const authToken = token ?? '';

  const checkAccess = useCallback(async () => {
    if (!token) {
      setAccess('unavailable');
      return;
    }
    setAccess('checking');
    try {
      const res = await getAdminWhoami(token);
      setWhoami(res);
      if (res.is_admin) {
        // 刷新页面后同样要知道「是否必须先绑定双因子」
        try {
          setTotpState(await totpStatus());
        } catch {
          setTotpState(null);
        }
      }
      setAccess(res.is_admin ? 'granted' : 'denied');
    } catch (err) {
      setWhoami(null);
      if (err instanceof UnauthorizedError) {
        setAccess('expired');
      } else if (err instanceof ApiError && err.status === 403) {
        setAccess('denied');
      } else {
        setAccess('unavailable');
      }
    }
  }, [token]);

  const loadOverview = useCallback(async () => {
    if (!token) return;
    setLoadingOverview(true);
    try {
      setOverview(await getAdminOverview(token));
    } catch {
      setOverview(null);
    } finally {
      setLoadingOverview(false);
    }
  }, [token]);

  useEffect(() => {
    void checkAccess();
  }, [checkAccess]);

  const totpBlocked = Boolean(totpState?.required && !totpState.enabled);

  useEffect(() => {
    if (access === 'granted' && !totpBlocked) void loadOverview();
  }, [access, totpBlocked, loadOverview]);

  // 切换模块时同步地址栏，刷新后仍停在同一个模块
  useEffect(() => {
    const url = section === 'overview' ? window.location.pathname : `${window.location.pathname}?tab=${section}`;
    window.history.replaceState(null, '', url);
  }, [section]);

  const capabilities = useMemo(() => whoami?.capabilities ?? [], [whoami]);

  const visibleNav = useMemo(
    () => NAV.filter((item) => !item.cap || capabilities.includes(item.cap)),
    [capabilities]
  );

  const activeItem = useMemo(
    () => visibleNav.find((item) => item.key === section) ?? visibleNav[0] ?? NAV[0],
    [visibleNav, section]
  );

  const go = (next: Section) => {
    setSection(next);
    setNavOpen(false);
  };

  const refresh = () => {
    setNonce((n) => n + 1);
    void loadOverview();
  };

  const handleTotpLogin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submitting) return;
    if (totpCode.trim().length < 6) {
      setTotpError('请输入 6 位动态码或恢复码');
      return;
    }
    setSubmitting(true);
    setTotpError(null);
    setLoginError(null);
    try {
      await loginWithTotp(totpChallenge, totpCode.trim());
      await finishAdminLogin();
      setTotpStage('password');
      setTotpChallenge('');
      setTotpCode('');
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setTotpError('动态码不正确，或验证已过期（请重新输入密码）');
      } else {
        setTotpError(err instanceof Error ? err.message : '验证失败，请重试');
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleLogout = () => {
    logout();
    setLoginError(null);
    setLoginPassword('');
    setTotpStage('password');
    setTotpChallenge('');
    setTotpCode('');
    setTotpError(null);
    setTotpState(null);
  };

  /** 已登录但无后台权限时切换账号：退出当前会话，回到本页登录框。 */
  const switchAccount = (message?: string) => {
    // 同样是「仅退出本机」，避免普通用户因为点了一下切换账号被全端踢下线
    logout({ revoke: false });
    setLoginError(message ?? null);
    setLoginPassword('');
    setTotpStage('password');
    setTotpChallenge('');
    setTotpCode('');
    setTotpError(null);
    setTotpState(null);
  };

  /**
   * 后台专用登录：先验证凭据，再校验后台权限。
   * 普通用户即使密码正确也不放行，并立即吊销这次登录产生的会话。
   */
  /** 登录成功（含第二因素）后统一收尾：校验后台身份 + 拉取双因子状态。 */
  const finishAdminLogin = async () => {
    const me = await getAdminWhoami('');
    if (!me.is_admin) {
      // 只清掉本机的会话 Cookie，不吊销其他设备上的登录
      logout({ revoke: false });
      setLoginError('该账号权限不足，不能登录管理后台');
      setLoginPassword('');
      setAccess('unavailable');
      return;
    }
    let status: TotpStatus | null = null;
    try {
      status = await totpStatus();
    } catch {
      status = null;
    }
    setTotpState(status);
    setWhoami(me);
    setAccess('granted');
    setLoginPassword('');
  };

  const handleLogin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submitting) return;
    const name = loginName.trim();
    if (!name || !loginPassword) {
      setLoginError('请输入账号与密码');
      return;
    }
    setSubmitting(true);
    setLoginError(null);
    try {
      const outcome = await login({ username: name, password: loginPassword });
      if (outcome.requiresTotp && outcome.challenge) {
        setTotpChallenge(outcome.challenge);
        setTotpStage('totp');
        setTotpCode('');
        setTotpError(null);
        return;
      }
      await finishAdminLogin();
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        setLoginError('尝试过于频繁，请稍后再试');
      } else if (err instanceof UnauthorizedError) {
        setLoginError('账号或密码错误');
      } else if (err instanceof ApiError) {
        setLoginError(err.message || '登录失败，请稍后重试');
      } else {
        setLoginError('无法连接后台服务，请稍后重试');
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (!isReady) {
    return (
      <div className="adm-scope adm-gate">
        <div className="adm-loading">
          <Loader2 className="adm-spin" size={18} />
          正在确认会话…
        </div>
      </div>
    );
  }

  if (!token) {
    return (
      <AdminLogin
        username={loginName}
        password={loginPassword}
        error={loginError}
        submitting={submitting}
        onUsername={setLoginName}
        onPassword={setLoginPassword}
        onSubmit={handleLogin}
        stage={totpStage}
        totpCode={totpCode}
        totpError={totpError}
        onTotpCode={setTotpCode}
        onSubmitTotp={handleTotpLogin}
        onBackToPassword={() => {
          setTotpStage('password');
          setTotpChallenge('');
          setTotpCode('');
          setTotpError(null);
        }}
      />
    );
  }

  if (access === 'checking') {
    return (
      <div className="adm-scope adm-gate">
        <div className="adm-loading">
          <Loader2 className="adm-spin" size={18} />
          正在校验后台权限…
        </div>
      </div>
    );
  }

  if (access !== 'granted') {
    const copy =
      access === 'denied'
        ? {
            title: '权限不足',
            message: '该账号权限不足，不能登录管理后台。',
            meta: `当前账号：${username ?? '未知'}（普通用户）· 仅管理员与超级管理员可进入`,
          }
        : access === 'expired'
          ? {
              title: '登录状态已失效',
              message: '请重新登录后再访问管理控制台。',
              meta: '旧令牌已失效：可能是修改密码或主动登出。',
            }
          : {
              title: '后台暂不可用',
              message: '无法连接后台服务，请确认后端已启动后重试。',
              meta: '',
            };

    return (
      <Gate
        title={copy.title}
        message={copy.message}
        meta={copy.meta}
        action={
          access === 'denied'
            ? {
                label: '切换账号',
                onClick: () => switchAccount('该账号权限不足，不能登录管理后台'),
              }
            : { label: '返回应用', href: '/' }
        }
        secondary={
          access === 'denied'
            ? { label: '返回应用', href: '/' }
            : { label: '重试', onClick: () => void checkAccess() }
        }
      />
    );
  }

  const reloadTotp = async () => {
    try {
      setTotpState(await totpStatus());
    } catch {
      /* 状态刷新失败不阻断当前操作 */
    }
  };

  const requireRelogin = () => {
    logout({ revoke: false });
    setAccess('unavailable');
    setTotpState(null);
    setTotpStage('password');
    setTotpChallenge('');
    setTotpCode('');
  };

  // 策略要求超管必须绑定：后台只保留绑定页，不渲染任何业务数据
  if (access === 'granted' && totpBlocked) {
    return (
      <div className="adm-scope adm-gate">
        <div style={{ width: '100%', maxWidth: 720 }}>
          <div className="adm-gate-brand">
            <img src="/logo.svg" alt="" />
            CookHero <span>Control Deck · 安全设置</span>
          </div>
          <AdminTotp
            status={totpState}
            forced
            onChanged={reloadTotp}
            onRequireRelogin={requireRelogin}
          />
        </div>
      </div>
    );
  }

  const roleLabel = whoami ? (ROLE_LABELS[whoami.role] ?? whoami.role) : '后台';

  return (
    <div className="adm-scope adm-shell">
      <div className="adm-atmo" aria-hidden="true" />

      {navOpen && <div className="adm-scrim" onClick={() => setNavOpen(false)} aria-hidden="true" />}

      <aside className={`adm-sidebar ${navOpen ? 'is-open' : ''}`}>
        <div className="adm-brand">
          <img src="/logo.svg" alt="" />
          <div>
            <div className="adm-brand-name">CookHero</div>
            <div className="adm-brand-sub">Control Deck</div>
          </div>
          <button
            className="adm-sidebar-close"
            onClick={() => setNavOpen(false)}
            aria-label="收起功能栏"
          >
            <X size={15} />
          </button>
        </div>

        <div className="adm-operator">
          <div className="adm-operator-avatar">{roleLabel.charAt(0)}</div>
          <div style={{ minWidth: 0 }}>
            <div className="adm-operator-name">{whoami?.username ?? username}</div>
            <div className="adm-operator-role">
              <span data-dot />
              {roleLabel} · {capabilities.length} 项能力
            </div>
          </div>
        </div>

        <nav className="adm-nav-list" aria-label="后台功能">
          {GROUPS.map((group) => {
            const items = visibleNav.filter((item) => item.group === group);
            if (!items.length) return null;
            return (
              <div className="adm-nav-group" key={group}>
                <div className="adm-nav-group-label">{group}</div>
                {items.map((item) => {
                  const Icon = item.icon;
                  const active = activeItem.key === item.key;
                  return (
                    <button
                      key={item.key}
                      className={`adm-nav ${active ? 'is-active' : ''}`}
                      onClick={() => go(item.key)}
                      aria-current={active ? 'page' : undefined}
                    >
                      <span className="adm-nav-icon">
                        <Icon size={14} />
                      </span>
                      <span>
                        <span className="adm-nav-label">{item.label}</span>
                        <span className="adm-nav-desc">{item.desc}</span>
                      </span>
                      <ChevronRight className="adm-nav-chev" size={12} />
                    </button>
                  );
                })}
              </div>
            );
          })}
        </nav>

        <div className="adm-console-meta">
          <span className="adm-pulse" />
          Console v1.0 · Session active
        </div>

        <div className="adm-sidebar-foot">
          <a className="adm-foot-btn" href="/">
            <Home size={14} />
            返回主站
          </a>
          <button className="adm-foot-btn" onClick={handleLogout}>
            <LogOut size={14} />
            退出登录
          </button>
        </div>
      </aside>

      <main className="adm-main">
        <header className="adm-topbar">
          <button
            className="adm-icon-btn adm-menu-btn"
            onClick={() => setNavOpen(true)}
            aria-label="展开功能栏"
          >
            <Menu size={16} />
          </button>

          <div className="adm-topbar-head">
            <div className="adm-eyebrow">
              Admin Console <i>/</i> {activeItem.en}
            </div>
            <h1 className="adm-title">{activeItem.label}</h1>
            <p className="adm-subtitle">{activeItem.desc}</p>
          </div>

          <div className="adm-topbar-actions">
            <span className="adm-chip">
              <span className="adm-pulse" />
              {roleLabel}
            </span>
            <span className="adm-chip is-accent">{capabilities.length} 项权限</span>
            <button className="adm-icon-btn" onClick={refresh} title="刷新当前模块">
              <RefreshCcw size={14} className={loadingOverview ? 'adm-spin' : undefined} />
            </button>
            <a className="adm-btn" href="/">
              返回应用
            </a>
          </div>
        </header>

        <div className="adm-content">
          <div className="adm-inner">
            {activeItem.key === 'overview' ? (
              <Overview
                overview={overview}
                loading={loadingOverview}
                whoami={whoami}
                capabilities={capabilities}
                modules={visibleNav.filter((item) => item.key !== 'overview')}
                onOpen={go}
              />
            ) : (
              <div className="adm-panel" key={`${activeItem.key}-${nonce}`}>
                {activeItem.key === 'users' && (
                  <AdminUsers token={authToken} capabilities={capabilities} myRole={whoami?.role} />
                )}
                {activeItem.key === 'usage' && <AdminUsage token={authToken} />}
                {activeItem.key === 'quality' && <EvaluationPage embedded />}
                {activeItem.key === 'calls' && <LLMStatsPage embedded />}
                {activeItem.key === 'sessions' && <AdminSessions token={authToken} />}
                {activeItem.key === 'audit' && <AdminAudit token={authToken} />}
                {activeItem.key === 'alerts' && (
                  <AdminAlerts token={authToken} canRun={capabilities.includes('alerts')} />
                )}
                {activeItem.key === 'security' && (
                  <AdminTotp
                    status={totpState}
                    onChanged={reloadTotp}
                    onRequireRelogin={requireRelogin}
                  />
                )}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

/**
 * 后台专用登录：留在本页完成，不跳主应用登录页。
 * 凭据正确但账号不是 admin / super_admin 时，会立刻吊销这次会话并提示权限不足。
 */
function AdminLogin({
  username,
  password,
  error,
  submitting,
  onUsername,
  onPassword,
  onSubmit,
  stage,
  totpCode,
  totpError,
  onTotpCode,
  onSubmitTotp,
  onBackToPassword,
}: {
  username: string;
  password: string;
  error: string | null;
  submitting: boolean;
  onUsername: (value: string) => void;
  onPassword: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  stage: 'password' | 'totp';
  totpCode: string;
  totpError: string | null;
  onTotpCode: (value: string) => void;
  onSubmitTotp: (event: FormEvent<HTMLFormElement>) => void;
  onBackToPassword: () => void;
}) {
  return (
    <div className="adm-scope adm-gate">
      <div className="adm-gate-card adm-login-card">
        <div className="adm-gate-brand">
          <img src="/logo.svg" alt="" />
          CookHero <span>Control Deck</span>
        </div>
        <div className="adm-gate-icon">
          <ShieldCheck size={20} />
        </div>
        <h1 className="adm-gate-title">
          {stage === 'totp' ? '输入动态验证码' : '登录管理控制台'}
        </h1>
        <p className="adm-gate-text">
          {stage === 'totp'
            ? `账号 ${username} 已启用双因子，请输入验证器上的 6 位码（或用恢复码）`
            : '仅管理员与超级管理员可进入'}
        </p>

        {stage === 'totp' ? (
          <form className="adm-login-form" onSubmit={onSubmitTotp}>
            <label className="adm-field">
              <span>动态验证码</span>
              <input
                className="adm-input"
                value={totpCode}
                onChange={(e) => onTotpCode(e.target.value.replace(/\s/g, '').slice(0, 20))}
                placeholder="000000 或 xxxxx-xxxxx"
                inputMode="numeric"
                autoComplete="one-time-code"
                autoFocus
              />
            </label>

            {totpError && (
              <p className="adm-login-error" role="alert">
                <ShieldAlert size={13} />
                {totpError}
              </p>
            )}

            <button
              type="submit"
              className="adm-btn is-primary adm-login-submit"
              disabled={submitting || totpCode.trim().length < 6}
            >
              {submitting ? (
                <>
                  <Loader2 className="adm-spin" size={13} />
                  正在验证…
                </>
              ) : (
                '验证并登录'
              )}
            </button>

            <button
              type="button"
              className="adm-btn adm-login-submit"
              onClick={onBackToPassword}
              disabled={submitting}
            >
              返回重新输入密码
            </button>
          </form>
        ) : (
        <form className="adm-login-form" onSubmit={onSubmit}>
          <label className="adm-field">
            <span>账号</span>
            <input
              className="adm-input"
              value={username}
              onChange={(e) => onUsername(e.target.value)}
              autoComplete="username"
              placeholder="输入账号"
              autoFocus
            />
          </label>
          <label className="adm-field">
            <span>密码</span>
            <input
              className="adm-input"
              type="password"
              value={password}
              onChange={(e) => onPassword(e.target.value)}
              autoComplete="current-password"
              placeholder="输入密码"
            />
          </label>

          {error && (
            <p className="adm-login-error" role="alert">
              <ShieldAlert size={13} />
              {error}
            </p>
          )}

          <button
            type="submit"
            className="adm-btn is-primary adm-login-submit"
            disabled={submitting || !username.trim() || !password}
          >
            {submitting ? (
              <>
                <Loader2 className="adm-spin" size={13} />
                正在验证…
              </>
            ) : (
              '登录'
            )}
          </button>
        </form>
        )}

        <a className="adm-login-back" href="/">
          返回主站
        </a>
      </div>
    </div>
  );
}

/** 权限门 / 异常态的统一卡片。 */
function Gate({
  title,
  message,
  meta,
  action,
  secondary,
}: {
  title: string;
  message: string;
  meta?: string;
  action: { label: string; href?: string; onClick?: () => void };
  secondary?: { label: string; href?: string; onClick?: () => void };
}) {
  const renderButton = (
    item: { label: string; href?: string; onClick?: () => void },
    primary: boolean
  ) =>
    item.href ? (
      <a className={`adm-btn ${primary ? 'is-primary' : ''}`} href={item.href}>
        {item.label}
      </a>
    ) : (
      <button className={`adm-btn ${primary ? 'is-primary' : ''}`} onClick={item.onClick}>
        {item.label}
      </button>
    );

  return (
    <div className="adm-scope adm-gate">
      <div className="adm-gate-card">
        <div className="adm-gate-brand">
          <img src="/logo.svg" alt="" />
          CookHero <span>Control Deck</span>
        </div>
        <div className="adm-gate-icon">
          <ShieldAlert size={20} />
        </div>
        <h1 className="adm-gate-title">{title}</h1>
        <p className="adm-gate-text">{message}</p>
        {meta && <p className="adm-gate-meta">{meta}</p>}
        <div className="adm-gate-actions">
          {renderButton(action, true)}
          {secondary && renderButton(secondary, false)}
        </div>
      </div>
    </div>
  );
}

function Stat({
  index,
  label,
  value,
  hint,
}: {
  index: string;
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <div className="adm-stat">
      <div className="adm-stat-label" style={{ justifyContent: 'space-between' }}>
        <span>{label}</span>
        <span style={{ fontFamily: 'ui-monospace, monospace', letterSpacing: '0.12em', color: '#6b5e52' }}>
          {index}
        </span>
      </div>
      <div className="adm-stat-value">{value}</div>
      <div className="adm-stat-hint">{hint}</div>
    </div>
  );
}

/** 总览：指标 + 模块说明 + 操作员权限。 */
function Overview({
  overview,
  loading,
  whoami,
  capabilities,
  modules,
  onOpen,
}: {
  overview: AdminOverview | null;
  loading: boolean;
  whoami: AdminWhoami | null;
  capabilities: string[];
  modules: NavItem[];
  onOpen: (section: Section) => void;
}) {
  const money = (value: number) => formatMoney(value, overview?.llm.currency ?? 'CNY');

  const stats = overview
    ? [
        {
          label: '账号总数',
          value: String(overview.users.total),
          hint: `活跃 ${overview.users.active} · 7 日新增 ${overview.users.new_7d}`,
        },
        {
          label: '7 日登录',
          value: String(overview.users.logged_in_7d),
          hint: `其中管理员 ${overview.users.admins}`,
        },
        {
          label: '今日调用',
          value: overview.llm.calls_today.toLocaleString('en-US'),
          hint: `${overview.llm.tokens_today.toLocaleString('en-US')} tokens`,
        },
        {
          label: '7 日成本',
          value: money(overview.llm.cost_7d),
          hint: `今日 ${money(overview.llm.cost_today)}`,
        },
        {
          label: '内容 / 会话',
          value: `${overview.content.global_documents} / ${overview.activity.conversations}`,
          hint: `Agent 会话 ${overview.activity.agent_sessions} 个`,
        },
      ]
    : [];

  return (
    <>
      <div className="adm-section-head" style={{ marginTop: 0 }}>
        <div>
          <div className="adm-section-title">运行指标</div>
          <div className="adm-section-desc">
            {overview
              ? `数据快照 · ${formatDate(overview.generated_at)}`
              : loading
                ? '正在读取概览…'
                : '概览暂不可用，可切换到具体模块查看'}
          </div>
        </div>
        <span className="adm-chip">实时来自后台接口</span>
      </div>

      {overview ? (
        <div className="adm-stat-grid">
          {stats.map((stat, i) => (
            <Stat
              key={stat.label}
              index={String(i + 1).padStart(2, '0')}
              label={stat.label}
              value={stat.value}
              hint={stat.hint}
            />
          ))}
        </div>
      ) : (
        <div className="adm-card" style={{ color: '#a99a8b', fontSize: 12.5 }}>
          {loading ? '正在加载概览…' : '概览不可用（可能没有 read 权限，或后端未启动）。'}
        </div>
      )}

      <div className="adm-overview-grid">
        <div>
          <div className="adm-section-head" style={{ marginTop: 4 }}>
            <div>
              <div className="adm-section-title">可用模块</div>
              <div className="adm-section-desc">
                左侧功能栏与下方一一对应；只显示当前账号有权限的模块。
              </div>
            </div>
            <span className="adm-chip">{modules.length} 个</span>
          </div>

          <div className="adm-mod-grid">
            {modules.map((item, i) => {
              const Icon = item.icon;
              return (
                <button key={item.key} className="adm-mod" onClick={() => onOpen(item.key)}>
                  <span className="adm-mod-top">
                    <span className="adm-mod-index">{String(i + 1).padStart(2, '0')}</span>
                    <span
                      className="adm-mod-icon"
                      style={{ '--mod-accent': item.accent } as CSSProperties}
                    >
                      <Icon size={15} />
                    </span>
                    <ArrowUpRight className="adm-mod-arrow" size={14} />
                  </span>
                  <span className="adm-mod-title">{item.label}</span>
                  <span className="adm-mod-desc">{item.desc}</span>
                  <span className="adm-mod-need">
                    <Lock size={10} />
                    {item.need}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <aside>
          <div className="adm-card">
            <div className="adm-card-label">Operator</div>
            <div className="adm-kv" style={{ marginTop: 10 }}>
              <span>账号</span>
              <b>{whoami?.username ?? '—'}</b>
            </div>
            <div className="adm-kv">
              <span>角色</span>
              <b>{whoami ? (ROLE_LABELS[whoami.role] ?? whoami.role) : '—'}</b>
            </div>
            <div className="adm-kv">
              <span>会话方式</span>
              <b>HttpOnly Cookie</b>
            </div>
            <div className="adm-cap-list">
              {capabilities.map((cap) => (
                <span className="adm-cap" key={cap}>
                  {CAP_LABELS[cap] ?? cap}
                </span>
              ))}
            </div>
          </div>

          <div className="adm-card">
            <div className="adm-card-label">Boundaries</div>
            <div className="adm-kv" style={{ marginTop: 10 }}>
              <span>创建 / 删除账号</span>
              <b>仅超级管理员</b>
            </div>
            <div className="adm-kv">
              <span>修改角色 / 看审计</span>
              <b>仅超级管理员</b>
            </div>
            <div className="adm-kv">
              <span>改密 / 启停账号</span>
              <b>按级别向下</b>
            </div>
            <p style={{ marginTop: 12, fontSize: 10.5, lineHeight: 1.6, color: '#857568' }}>
              所有写操作都会在服务端二次校验并写入审计；前端隐藏按钮只是展示层裁剪。
            </p>
          </div>
        </aside>
      </div>

      {overview && (
        <>
          <div className="adm-section-head">
            <div>
              <div className="adm-section-title">数据体量</div>
              <div className="adm-section-desc">与「运行指标」同一份快照，便于判断系统规模。</div>
            </div>
            <span className="adm-chip">DATA VOLUME</span>
          </div>
          <div className="adm-volume">
            {[
              { label: '公共菜谱文档', value: overview.content.global_documents },
              { label: '个人知识库', value: overview.content.personal_documents },
              { label: '对话会话', value: overview.activity.conversations },
              { label: 'Agent 会话', value: overview.activity.agent_sessions },
              { label: '饮食记录', value: overview.activity.diet_log_items },
              { label: '库存条目', value: overview.activity.pantry_items },
            ].map((item) => (
              <div className="adm-volume-item" key={item.label}>
                <div className="adm-volume-value">{item.value.toLocaleString('en-US')}</div>
                <div className="adm-volume-label">{item.label}</div>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}
