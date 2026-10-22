/**
 * 前端 401 静默续期逻辑的回归测试（Node 环境，无需浏览器）。
 *
 * 做法：用 esbuild 把真实的 `src/services/api/client.ts` 打成 ESM，
 * 桩掉 fetch / localStorage / window，在 Node 里验证三条关键行为：
 *   1. 401 → 调 /auth/refresh → 用新令牌重试成功
 *   2. 没有刷新令牌 → 401 原样抛出并清空登录态
 *   3. 并发 401 → 只触发一次刷新（single-flight）
 *
 * 运行：cd frontend && npm run test:client
 */

import { build } from 'esbuild';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const dir = await mkdtemp(join(tmpdir(), 'cookhero-client-'));
const outfile = join(dir, 'client.mjs');

await build({
  entryPoints: ['src/services/api/client.ts'],
  bundle: true,
  format: 'esm',
  platform: 'node',
  outfile,
  define: { 'import.meta.env': '{}' },
  logLevel: 'error',
});

const store = new Map();
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
};

const events = [];
globalThis.window = {
  addEventListener: () => {},
  removeEventListener: () => {},
  dispatchEvent: (e) => {
    events.push(e.type);
    return true;
  },
};
globalThis.CustomEvent = class CustomEvent {
  constructor(type, init) {
    this.type = type;
    this.detail = init?.detail;
  }
};

const { apiGet, UnauthorizedError } = await import(pathToFileURL(outfile).href);

const response = (status, body) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });

let pass = 0;
let fail = 0;
const check = (name, ok, extra = '') => {
  if (ok) {
    pass += 1;
    console.log(`  ✅ ${name}`);
  } else {
    fail += 1;
    console.log(`  ❌ ${name} ${extra}`);
  }
};

console.log('场景 1：401 → 刷新 → 重试成功');
{
  store.clear();
  store.set('cookhero_token', 'old-access');
  store.set('cookhero_refresh_token', 'refresh-abc');

  let refreshCalls = 0;
  let businessCalls = 0;
  globalThis.fetch = async (url, init) => {
    if (String(url).includes('/auth/refresh')) {
      refreshCalls += 1;
      const body = JSON.parse(init.body);
      if (body.refresh_token !== 'refresh-abc') return response(400, { detail: 'bad' });
      return response(200, {
        access_token: 'new-access',
        refresh_token: 'refresh-new',
        username: 'demo',
      });
    }
    businessCalls += 1;
    const auth = new Headers(init.headers || {}).get('Authorization');
    if (auth === 'Bearer old-access') return response(401, { detail: 'expired' });
    if (auth === 'Bearer new-access') return response(200, { ok: true });
    return response(403, { detail: `forbidden:${auth}` });
  };

  const result = await apiGet('/admin/whoami', 'old-access');
  check('返回业务数据', result.ok === true);
  check('刷新只调用一次', refreshCalls === 1, `实际 ${refreshCalls}`);
  check('业务请求调用了两次（401 + 重试）', businessCalls === 2, `实际 ${businessCalls}`);
  check('新令牌已写入 localStorage', store.get('cookhero_token') === 'new-access');
  check('刷新令牌被轮换', store.get('cookhero_refresh_token') === 'refresh-new');
  check('广播了续期事件', events.includes('auth:token-refreshed'));
}

console.log('场景 2：没有刷新令牌 → 直接判失败');
{
  store.clear();
  store.set('cookhero_token', 'expired-access');
  let refreshCalls = 0;
  globalThis.fetch = async (url) => {
    if (String(url).includes('/auth/refresh')) {
      refreshCalls += 1;
      return response(200, { access_token: 'x' });
    }
    return response(401, { detail: 'expired' });
  };

  let caught = null;
  try {
    await apiGet('/admin/overview', 'expired-access');
  } catch (err) {
    caught = err;
  }
  check('抛出 UnauthorizedError', caught instanceof UnauthorizedError, String(caught));
  check('没有发起刷新请求', refreshCalls === 0);
  check(
    '登录态已清空（访问令牌与刷新令牌）',
    !store.has('cookhero_token') && !store.has('cookhero_refresh_token')
  );
  check('广播了未授权事件', events.includes('auth-unauthorized'));
}

console.log('场景 3：并发 401 只刷新一次');
{
  store.clear();
  store.set('cookhero_token', 'old-access');
  store.set('cookhero_refresh_token', 'refresh-abc');

  let refreshCalls = 0;
  globalThis.fetch = async (url, init) => {
    if (String(url).includes('/auth/refresh')) {
      refreshCalls += 1;
      await new Promise((r) => setTimeout(r, 30));
      return response(200, { access_token: 'new-access', username: 'demo' });
    }
    const auth = new Headers(init.headers || {}).get('Authorization');
    if (auth === 'Bearer old-access') return response(401, { detail: 'expired' });
    if (auth === 'Bearer new-access') return response(200, { ok: true });
    return response(403, { detail: `forbidden:${auth}` });
  };

  const [a, b, c] = await Promise.all([
    apiGet('/admin/users', 'old-access'),
    apiGet('/admin/usage', 'old-access'),
    apiGet('/admin/sessions', 'old-access'),
  ]);
  check('三个请求都成功', a.ok && b.ok && c.ok);
  check('刷新只调用一次', refreshCalls === 1, `实际 ${refreshCalls}`);
}

await rm(dir, { recursive: true, force: true });

console.log(`\n结果：${pass} 通过 / ${fail} 失败`);
process.exit(fail === 0 ? 0 : 1);
