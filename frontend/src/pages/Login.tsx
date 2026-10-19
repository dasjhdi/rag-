import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import type { Location } from 'react-router-dom';
import { ArrowRight, Loader2 } from 'lucide-react';
import { useAuth } from '../contexts';
import { AuthBrandPanel } from '../components/common/AuthBrandPanel';

function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: Location })?.from?.pathname || '/agent';

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | string[] | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) {
      setError('请输入用户名和密码。');
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      await login({ username: username.trim(), password });
      navigate(from, { replace: true });
    } catch (err) {
      const msg = err instanceof Error ? err.message : '登录失败，请稍后重试';
      setError(msg.includes('\n') ? msg.split('\n').map(s => s.trim()).filter(Boolean) : msg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-[1.02fr_1fr] bg-cream-50 dark:bg-[#12100c]">
      <AuthBrandPanel variant="login" />

      <main className="relative flex items-center justify-center px-5 py-12 sm:px-8">
        <div className="absolute inset-0 lg:hidden -z-0">
          <div className="absolute -top-24 right-0 w-72 h-72 rounded-full bg-ember-200/40 blur-[90px]" />
          <div className="absolute bottom-0 -left-16 w-64 h-64 rounded-full bg-herb-200/30 blur-[90px]" />
        </div>

        <div className="relative w-full max-w-[420px]">
          <div className="lg:hidden flex items-center gap-2.5 mb-9">
            <div className="w-10 h-10 rounded-2xl bg-white border border-cream-300/70 p-1.5 shadow-sm">
              <img src="/logo1.png" alt="CookHero" className="w-full h-full object-contain" />
            </div>
            <div>
              <div className="ch-wordmark text-lg text-ink-900">CookHero</div>
              <div className="text-[9px] tracking-[0.2em] uppercase text-ink-400">
                AI Kitchen Companion
              </div>
            </div>
          </div>

          <div className="ch-card !rounded-3xl p-7 sm:p-9 animate-fade-up">
            <div className="ch-eyebrow mb-3">Welcome back</div>
            <h2 className="text-[1.7rem] font-bold tracking-tight text-ink-900 dark:text-cream-50">
              欢迎回来
            </h2>
            <p className="mt-2 text-sm text-ink-500 dark:text-ink-200">登录后继续你的厨房探索。</p>

            <form className="mt-7 space-y-4" onSubmit={handleSubmit}>
              <div>
                <label htmlFor="login-username" className="ch-label">用户名</label>
                <input
                  id="login-username"
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="ch-input"
                  placeholder="chef_annie"
                  autoComplete="username"
                />
              </div>
              <div>
                <label htmlFor="login-password" className="ch-label">密码</label>
                <input
                  id="login-password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="ch-input"
                  placeholder="••••••••"
                  autoComplete="current-password"
                />
              </div>
              {error && (
                <div className="text-sm text-red-700 dark:text-red-300 bg-red-50/80 dark:bg-red-900/25 border border-red-200/80 dark:border-red-800/60 rounded-xl px-3.5 py-2.5">
                  {Array.isArray(error) ? (
                    <ul className="list-disc ml-5 space-y-0.5">
                      {error.map((e, i) => (
                        <li key={i}>{e}</li>
                      ))}
                    </ul>
                  ) : (
                    <div>{error}</div>
                  )}
                </div>
              )}
              <button
                type="submit"
                disabled={isLoading}
                className="ch-btn ch-btn-primary w-full !py-3 !rounded-xl group"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    正在登录…
                  </>
                ) : (
                  <>
                    登录
                    <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5" />
                  </>
                )}
              </button>
            </form>

            <div className="mt-6 pt-5 border-t border-cream-200/80 dark:border-white/5 text-sm text-ink-500 dark:text-ink-200 text-center">
              还没有账号？{' '}
              <Link
                to="/register"
                className="font-semibold text-ember-600 dark:text-ember-300 hover:text-ember-700 dark:hover:text-ember-200 transition-colors"
              >
                创建一个
              </Link>
            </div>
          </div>

          <p className="mt-5 text-center text-[11px] text-ink-400">
            登录即表示你同意 CookHero 的使用条款与隐私政策
          </p>
        </div>
      </main>
    </div>
  );
}

export default LoginPage;
