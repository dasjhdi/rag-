/**
 * 双因子（TOTP）绑定与关闭面板。
 *
 * 两种用法：
 * - forced：超管被策略要求绑定，整个后台只显示这个面板；
 * - 普通：账号安全页里自行开启 / 关闭。
 *
 * 绑定成功会作废旧会话（后端递增 token_version），因此这里展示完恢复码后
 * 需要重新登录——这不是 bug，是让「已通过的会话」和「第二因素」对齐。
 */

import { useState } from 'react';
import { Check, Copy, KeyRound, Loader2, ShieldCheck, ShieldOff } from 'lucide-react';
import { totpConfirm, totpDisable, totpSetup } from '../../services/api/auth';
import type { TotpStatus } from '../../services/api/auth';

function CopyButton({ text, label }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* 剪贴板不可用时保持静默，用户仍可手动选中 */
    }
  };
  return (
    <button type="button" onClick={copy} className="adm-btn" title="复制">
      {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
      {label ?? (copied ? '已复制' : '复制')}
    </button>
  );
}

export default function AdminTotp({
  status,
  forced = false,
  onChanged,
  onRequireRelogin,
}: {
  status: TotpStatus | null;
  forced?: boolean;
  onChanged: () => void;
  onRequireRelogin: () => void;
}) {
  const [secret, setSecret] = useState<string | null>(null);
  const [otpauth, setOtpauth] = useState<string | null>(null);
  const [code, setCode] = useState('');
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [disableOpen, setDisableOpen] = useState(false);
  const [password, setPassword] = useState('');
  const [disableCode, setDisableCode] = useState('');

  const startSetup = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await totpSetup();
      setSecret(res.secret);
      setOtpauth(res.otpauth_uri);
    } catch (err) {
      setError(err instanceof Error ? err.message : '生成密钥失败');
    } finally {
      setBusy(false);
    }
  };

  const confirmSetup = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await totpConfirm(code.trim());
      setRecoveryCodes(res.recovery_codes);
      setSecret(null);
      setOtpauth(null);
      setCode('');
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : '验证码不正确');
    } finally {
      setBusy(false);
    }
  };

  const disable = async () => {
    setBusy(true);
    setError(null);
    try {
      await totpDisable(password, disableCode.trim());
      setDisableOpen(false);
      setPassword('');
      setDisableCode('');
      onChanged();
      onRequireRelogin();
    } catch (err) {
      setError(err instanceof Error ? err.message : '关闭失败');
    } finally {
      setBusy(false);
    }
  };

  // 绑定完成：只展示一次恢复码
  if (recoveryCodes) {
    return (
      <div className="adm-card" style={{ maxWidth: 620 }}>
        <div className="adm-card-label">
          <ShieldCheck size={12} /> 绑定成功
        </div>
        <p className="mt-3 text-sm text-gray-600 dark:text-gray-300">
          恢复码<strong>只显示这一次</strong>。请离线保存，手机丢失时用它登录；
          用完后需要重新绑定。
        </p>
        <div className="mt-3 grid grid-cols-2 gap-2 font-mono text-sm">
          {recoveryCodes.map((item) => (
            <span
              key={item}
              className="rounded-lg border border-gray-200 dark:border-gray-700 px-3 py-1.5 text-gray-700 dark:text-gray-200"
            >
              {item}
            </span>
          ))}
        </div>
        <div className="mt-4 flex items-center gap-2">
          <CopyButton text={recoveryCodes.join('\n')} label="复制全部" />
          <button className="adm-btn is-primary" onClick={onRequireRelogin}>
            我已保存，重新登录
          </button>
        </div>
      </div>
    );
  }

  // 绑定中：展示密钥与验证码输入
  if (secret) {
    return (
      <div className="adm-card" style={{ maxWidth: 620 }}>
        <div className="adm-card-label">
          <KeyRound size={12} /> 绑定验证器
        </div>
        <ol className="mt-3 space-y-3 text-sm text-gray-600 dark:text-gray-300">
          <li>
            1. 在手机验证器（Google Authenticator / 1Password / 微软验证器）中选择「手动输入密钥」。
          </li>
          <li>
            2. 账号填 <code className="font-mono">{status ? '当前账号' : '当前账号'}</code>，
            密钥填：
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <code className="rounded-lg border border-gray-200 dark:border-gray-700 px-3 py-1.5 font-mono text-sm tracking-wider text-gray-800 dark:text-gray-100">
                {secret}
              </code>
              <CopyButton text={secret} />
            </div>
            {otpauth && (
              <a
                className="mt-2 inline-block text-xs text-orange-600 dark:text-orange-300 underline break-all"
                href={otpauth}
              >
                或在本机打开 otpauth 链接
              </a>
            )}
          </li>
          <li>
            3. 输入验证器当前显示的 6 位码：
            <div className="mt-2 flex items-center gap-2">
              <input
                className="adm-input"
                style={{ width: 160, letterSpacing: '0.3em' }}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                placeholder="000000"
                inputMode="numeric"
                autoFocus
              />
              <button
                className="adm-btn is-primary"
                onClick={confirmSetup}
                disabled={busy || code.trim().length !== 6}
              >
                {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <ShieldCheck className="w-3.5 h-3.5" />}
                确认绑定
              </button>
            </div>
          </li>
        </ol>
        {error && <p className="mt-3 text-sm text-red-500">{error}</p>}
        <button
          className="adm-btn mt-4"
          onClick={() => {
            setSecret(null);
            setOtpauth(null);
            setError(null);
          }}
        >
          取消
        </button>
      </div>
    );
  }

  const enabled = Boolean(status?.enabled);

  return (
    <div className="adm-card" style={{ maxWidth: 620 }}>
      <div className="adm-card-label">
        <KeyRound size={12} /> 双因子认证（TOTP）
      </div>
      <p className="mt-3 text-sm text-gray-600 dark:text-gray-300">
        {enabled
          ? `已绑定，剩余恢复码 ${status?.recovery_codes_left ?? 0} 个。登录时需要输入验证器上的 6 位动态码。`
          : '未绑定。绑定后除密码外，还需输入验证器上的 6 位动态码才能登录。'}
        {forced && !enabled && (
          <span className="mt-1 block text-orange-600 dark:text-orange-300">
            当前策略要求超级管理员必须绑定双因子，绑定后才能访问后台数据。
          </span>
        )}
      </p>

      {error && <p className="mt-3 text-sm text-red-500">{error}</p>}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {!enabled && (
          <button className="adm-btn is-primary" onClick={startSetup} disabled={busy}>
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <ShieldCheck className="w-3.5 h-3.5" />}
            开始绑定
          </button>
        )}
        {enabled && !disableOpen && (
          <button className="adm-btn" onClick={() => setDisableOpen(true)}>
            <ShieldOff className="w-3.5 h-3.5" />
            关闭双因子
          </button>
        )}
      </div>

      {disableOpen && (
        <div className="mt-4 space-y-2 rounded-xl border border-red-200 dark:border-red-900/50 p-3">
          <p className="text-xs text-gray-500 dark:text-gray-400">
            关闭需要同时验证登录密码与当前动态码（或恢复码）。
          </p>
          <input
            className="adm-input"
            type="password"
            placeholder="登录密码"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <input
            className="adm-input"
            placeholder="6 位动态码或恢复码"
            value={disableCode}
            onChange={(e) => setDisableCode(e.target.value)}
          />
          <div className="flex items-center gap-2">
            <button
              className="adm-btn is-primary"
              onClick={disable}
              disabled={busy || !password || !disableCode}
            >
              {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <ShieldOff className="w-3.5 h-3.5" />}
              确认关闭
            </button>
            <button className="adm-btn" onClick={() => setDisableOpen(false)}>
              取消
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
