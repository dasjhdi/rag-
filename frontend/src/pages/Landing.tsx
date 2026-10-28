/**
 * 公开落地页（门面）
 *
 * 设计基调：深色、影像驱动，结构参考产品官网：
 * Hero（沉浸影像）→ 作品滚动带 → 核心能力 → 场景切换 → 工作流 → 菜谱墙 → 数据 → CTA
 *
 * 与应用的边界：本页不依赖登录，`/` 公开可访问；
 * 所有 CTA 按登录态分流到 /agent 或 /login。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  BookOpen,
  CalendarDays,
  ChefHat,
  Languages,
  MessageSquare,
  Package,
  Send,
  Sparkles,
} from 'lucide-react';

import { useAuth } from '../contexts';
import { DISHES, HERO_SLIDES, SCENE_SHOTS, dishSrc } from './landing/assets';
import { COPY } from './landing/copy';
import type { Copy, Lang } from './landing/copy';

const LANG_KEY = 'cookhero_landing_lang';

/** 读取首选语言：显式选择优先，其次浏览器语言。 */
function initialLang(): Lang {
  const saved = localStorage.getItem(LANG_KEY);
  if (saved === 'zh' || saved === 'en') return saved;
  const nav = (navigator.language || 'zh').toLowerCase();
  return nav.startsWith('zh') ? 'zh' : 'en';
}

/** 滚动进入视口时触发的轻量显现动画。 */
function useReveal<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    // 老浏览器兜底：不做动画，直接显示
    if (typeof IntersectionObserver === 'undefined') {
      node.querySelectorAll('.ch-reveal').forEach((el) => el.classList.add('is-visible'));
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible');
            observer.unobserve(entry.target);
          }
        });
      },
      { rootMargin: '0px 0px -12% 0px', threshold: 0.08 }
    );
    node.querySelectorAll('.ch-reveal').forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, []);
  return ref;
}

/** 是否偏好减少动效（尊重系统设置）。 */
function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReduced(mq.matches);
    update();
    mq.addEventListener?.('change', update);
    return () => mq.removeEventListener?.('change', update);
  }, []);

  return reduced;
}

/** 三层遮罩：压暗、左侧渐深保证文字可读、底部融进下一段。 */
function HeroShade() {
  return (
    <>
      <div className="absolute inset-0 bg-black/60" />
      <div className="absolute inset-0 bg-gradient-to-r from-black via-black/75 to-transparent" />
      <div className="absolute inset-x-0 bottom-0 h-44 bg-gradient-to-t from-[#08090a] to-transparent" />
    </>
  );
}

/** 降级方案：多张实拍图交叉淡入 + 缓慢推进。 */
function HeroBackdrop({ lang }: { lang: Lang }) {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setIndex((prev) => (prev + 1) % HERO_SLIDES.length);
    }, 6500);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <div className="absolute inset-0 overflow-hidden">
      {HERO_SLIDES.map((dish, i) => (
        <div
          key={dish.file}
          className="absolute inset-0 transition-opacity duration-[1400ms] ease-out"
          style={{ opacity: i === index ? 1 : 0 }}
          aria-hidden={i !== index}
        >
          <img
            src={dishSrc(dish.file, 1600)}
            alt={lang === 'zh' ? dish.name : dish.en}
            className={`h-full w-full object-cover ${i === index ? 'ch-kenburns' : ''}`}
            loading={i === 0 ? 'eager' : 'lazy'}
            decoding="async"
          />
        </div>
      ))}
      <HeroShade />
    </div>
  );
}

/**
 * Hero 影像：真实烹饪短片（Mixkit 免费素材，已转码至 720p/2.3MB）。
 * 用户偏好减少动效或视频加载失败时，回落到图片轮播。
 */
function HeroMedia({ lang }: { lang: Lang }) {
  const reduced = usePrefersReducedMotion();
  const [videoFailed, setVideoFailed] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  // 离开视口时暂停，避免后台持续解码耗电
  useEffect(() => {
    const video = videoRef.current;
    if (!video || reduced || videoFailed) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          void video.play().catch(() => {
            /* 自动播放被拦截时保持封面图 */
          });
        } else {
          video.pause();
        }
      },
      { threshold: 0.15 }
    );
    observer.observe(video);
    return () => observer.disconnect();
  }, [reduced, videoFailed]);

  if (reduced || videoFailed) {
    return <HeroBackdrop lang={lang} />;
  }

  return (
    <div className="absolute inset-0 overflow-hidden">
      <video
        ref={videoRef}
        className="h-full w-full object-cover"
        autoPlay
        muted
        loop
        playsInline
        preload="metadata"
        poster="/videos/hero-poster.jpg"
        aria-hidden="true"
        onError={() => setVideoFailed(true)}
      >
        <source src="/videos/hero.mp4" type="video/mp4" />
      </video>
      <HeroShade />
    </div>
  );
}

/** 数字滚动：进入视口后从 0 递增到目标值；减少动效时直接落位。 */
function CountUp({ value, label }: { value: string; label: string }) {
  const target = Number(value.replace(/[^0-9]/g, '')) || 0;
  const grouped = value.includes(',');
  const reduced = usePrefersReducedMotion();
  const shouldAnimate = !reduced && typeof IntersectionObserver !== 'undefined';
  const [animated, setAnimated] = useState<number | null>(null);
  const ref = useRef<HTMLDivElement | null>(null);

  // 不可动画时直接用最终值，避免在 effect 里同步 setState
  const display = shouldAnimate ? (animated ?? 0) : target;

  useEffect(() => {
    if (!shouldAnimate) return;
    const node = ref.current;
    if (!node) return;

    let frame = 0;
    let started = false;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting || started) return;
        started = true;
        const startedAt = performance.now();
        const duration = 1100;
        const tick = (now: number) => {
          const progress = Math.min(1, (now - startedAt) / duration);
          const eased = 1 - Math.pow(1 - progress, 3);
          setAnimated(Math.round(target * eased));
          if (progress < 1) frame = requestAnimationFrame(tick);
        };
        frame = requestAnimationFrame(tick);
      },
      { threshold: 0.4 }
    );
    observer.observe(node);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
    };
  }, [target, shouldAnimate]);

  return (
    <div ref={ref} className="ch-reveal">
      <div className="ch-display text-[2.2rem] tabular-nums sm:text-[2.6rem]">
        {grouped ? display.toLocaleString('en-US') : display}
      </div>
      <div className="mt-1 text-[12px] uppercase tracking-[0.15em] text-white/35">{label}</div>
    </div>
  );
}

function Marquee({ reverse = false, width = 300 }: { reverse?: boolean; width?: number }) {
  const items = useMemo(() => [...DISHES, ...DISHES], []);
  return (
    <div className="ch-marquee-mask relative overflow-hidden">
      <div
        className={`flex w-max gap-4 ${reverse ? 'ch-marquee-right' : 'ch-marquee-left'} hover:[animation-play-state:paused]`}
      >
        {items.map((dish, i) => (
          <figure
            key={`${dish.file}-${i}`}
            className="relative overflow-hidden rounded-2xl border border-white/10"
            style={{ width }}
          >
            <img
              src={dishSrc(dish.file, 600)}
              alt={dish.name}
              className="h-[190px] w-full object-cover opacity-90 transition-transform duration-700 hover:scale-105"
              loading="lazy"
              decoding="async"
            />
            <figcaption className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 to-transparent px-3 pb-2 pt-6 text-[11px] text-white/80">
              {dish.name}
            </figcaption>
          </figure>
        ))}
      </div>
    </div>
  );
}

/**
 * 产品界面示意：用真实 UI 语言拼出的静态界面，可在「对话 / 计划 / 库存」间切换。
 * 比截图更可控——文案随语言切换、图片用真实菜谱、任何分辨率下都清晰。
 */
type PreviewView = 'chat' | 'plan' | 'pantry';

function ProductPreview({ lang }: { lang: Lang }) {
  const copy = COPY[lang].preview;
  const [view, setView] = useState<PreviewView>('chat');
  const shots = [dishSrc('dc0557174a72.jpg', 420), dishSrc('c49722c10ac8.jpg', 420)];

  const tabs: { key: PreviewView; label: string; icon: typeof MessageSquare }[] = [
    { key: 'chat', label: copy.views.chat, icon: MessageSquare },
    { key: 'plan', label: copy.views.plan, icon: CalendarDays },
    { key: 'pantry', label: copy.views.pantry, icon: Package },
  ];

  const navItems = [
    { icon: MessageSquare, label: lang === 'zh' ? '对话厨房' : 'Kitchen chat', active: view === 'chat' },
    { icon: BookOpen, label: lang === 'zh' ? '菜谱库' : 'Recipes', active: false },
    { icon: CalendarDays, label: lang === 'zh' ? '一周计划' : 'Meal plan', active: view === 'plan' },
    { icon: Package, label: lang === 'zh' ? '库存采购' : 'Pantry', active: view === 'pantry' },
  ];

  return (
    <section id="preview" className="relative scroll-mt-20 overflow-hidden py-24">
      <div
        className="pointer-events-none absolute inset-0 opacity-80"
        style={{
          background:
            'radial-gradient(48rem 26rem at 50% 8%, rgba(226,96,44,0.18), transparent 66%)',
        }}
      />

      <div className="relative mx-auto max-w-7xl px-5 sm:px-8">
        <div className="ch-reveal max-w-2xl">
          <div className="mb-3 text-[11px] uppercase tracking-[0.22em] text-[#f2a87d]">
            {copy.eyebrow}
          </div>
          <h2 className="ch-display text-[2rem] sm:text-[2.8rem]">{copy.title}</h2>
          <p className="mt-4 text-[15px] leading-relaxed text-white/55">{copy.subtitle}</p>
        </div>

        {/* 视图切换 */}
        <div className="ch-reveal mt-8 inline-flex rounded-full border border-white/12 bg-white/[0.03] p-1">
          {tabs.map((tab) => {
            const active = view === tab.key;
            return (
              <button
                key={tab.key}
                type="button"
                onClick={() => setView(tab.key)}
                aria-pressed={active}
                className={`flex items-center gap-1.5 rounded-full px-4 py-2 text-[12.5px] transition-colors ${
                  active ? 'bg-white text-black' : 'text-white/60 hover:text-white'
                }`}
              >
                <tab.icon className="h-3.5 w-3.5" />
                {tab.label}
              </button>
            );
          })}
        </div>

        <div className="ch-reveal relative mt-6">
          <div className="overflow-hidden rounded-[1.6rem] border border-white/12 bg-[#0f1113] p-1.5 shadow-[0_40px_100px_-40px_rgba(0,0,0,0.9)]">
            <div className="overflow-hidden rounded-[1.2rem] bg-cream-50 text-ink-900">
              {/* 窗口标题栏 */}
              <div className="flex items-center gap-2 border-b border-cream-300/70 px-4 py-2.5">
                <span className="h-2.5 w-2.5 rounded-full bg-[#e2602c]/70" />
                <span className="h-2.5 w-2.5 rounded-full bg-[#d3a04c]/60" />
                <span className="h-2.5 w-2.5 rounded-full bg-[#52795c]/50" />
                <span className="ml-3 text-[11px] text-ink-500">{copy.windowTitle}</span>
                <span className="ml-auto flex items-center gap-1.5 rounded-full bg-[#52795c]/10 px-2 py-0.5 text-[10px] text-[#3f6249]">
                  <span className="h-1.5 w-1.5 rounded-full bg-[#52795c]" />
                  {copy.online}
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-[168px_1fr]">
                {/* 侧栏 */}
                <aside className="hidden border-r border-cream-300/60 bg-[#faf6ef] px-3 py-4 sm:block">
                  <div className="mb-4 flex items-center gap-2 px-1">
                    <img src="/logo.svg" alt="" className="h-7 w-7" />
                    <span className="ch-wordmark text-[13px]">CookHero</span>
                  </div>
                  {navItems.map((item) => (
                    <div
                      key={item.label}
                      className={`mb-1 flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-[12px] ${
                        item.active ? 'bg-white text-ink-900 shadow-sm' : 'text-ink-500'
                      }`}
                    >
                      <item.icon className="h-3.5 w-3.5" />
                      {item.label}
                    </div>
                  ))}
                </aside>

                {/* 内容区 */}
                <div className="px-4 py-5 sm:px-6 sm:py-6">
                  {view === 'chat' && <ChatView copy={copy} shots={shots} />}
                  {view === 'plan' && <PlanView copy={copy} />}
                  {view === 'pantry' && <PantryView copy={copy} />}
                </div>
              </div>
            </div>
          </div>

          {/* 浮动计划卡：仅在对话视图出现，避免与计划视图重复 */}
          {view === 'chat' && (
            <div className="absolute -bottom-6 right-4 hidden w-56 rounded-2xl border border-white/12 bg-[#0f1113]/95 p-3 shadow-[0_24px_60px_-24px_rgba(0,0,0,0.9)] backdrop-blur lg:block">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-[11px] text-white/70">{copy.planTitle}</span>
                <CalendarDays className="h-3.5 w-3.5 text-[#f2a87d]" />
              </div>
              <div className="space-y-1.5">
                {copy.plan.map((slot) => (
                  <div key={slot.day} className="flex items-center gap-2 text-[11px]">
                    <span className="w-8 shrink-0 text-white/35">{slot.day}</span>
                    <span className="truncate rounded-md bg-white/[0.06] px-2 py-1 text-white/70">
                      {slot.dish}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

/** 视图一：对话 */
function ChatView({ copy, shots }: { copy: Copy['preview']; shots: string[] }) {
  return (
    <>
      <div className="flex justify-end">
        <div className="max-w-[86%] rounded-2xl rounded-br-md bg-gradient-to-br from-[#ef8654] to-[#c74e1f] px-3.5 py-2.5 text-[12.5px] leading-relaxed text-white shadow-sm">
          {copy.userMsg}
        </div>
      </div>

      <div className="mt-4 flex gap-2.5">
        <img src="/logo.svg" alt="" className="mt-0.5 h-7 w-7 shrink-0" />
        <div className="min-w-0 flex-1">
          <div className="rounded-2xl rounded-tl-md border border-cream-300/60 bg-white px-3.5 py-2.5 shadow-sm">
            <p className="text-[12.5px] leading-relaxed text-ink-700">{copy.assistantMsg}</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {copy.thinking.map((step) => (
                <span
                  key={step}
                  className="rounded-full bg-[#f0e7d8]/70 px-2 py-0.5 text-[10px] text-ink-500"
                >
                  {step}
                </span>
              ))}
            </div>
          </div>

          <div className="mt-2.5 grid grid-cols-2 gap-2.5">
            {copy.cards.map((card, i) => (
              <div
                key={card.name}
                className="overflow-hidden rounded-xl border border-cream-300/60 bg-white shadow-sm"
              >
                <img
                  src={shots[i]}
                  alt={card.name}
                  className="h-20 w-full object-cover sm:h-24"
                  loading="lazy"
                  decoding="async"
                />
                <div className="px-2.5 py-2">
                  <div className="truncate text-[12px] font-medium text-ink-900">{card.name}</div>
                  <div className="mt-0.5 flex items-center gap-1.5 text-[10px] text-ink-400">
                    <span>{card.time}</span>
                    <span className="text-ink-200">·</span>
                    <span>{card.kcal}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-4 flex items-center gap-2 rounded-xl border border-cream-300/70 bg-white px-3 py-2">
        <span className="flex-1 truncate text-[11.5px] text-ink-400">{copy.inputPlaceholder}</span>
        <span className="grid h-6 w-6 place-items-center rounded-lg bg-[#e2602c] text-white">
          <Send className="h-3 w-3" />
        </span>
      </div>
    </>
  );
}

/** 视图二：一周计划 */
function PlanView({ copy }: { copy: Copy['preview'] }) {
  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <div className="text-[13px] font-semibold text-ink-900">{copy.planView.title}</div>
          <div className="mt-0.5 text-[10.5px] text-ink-400">{copy.planView.subtitle}</div>
        </div>
        <span className="rounded-full bg-[#52795c]/10 px-2 py-0.5 text-[10px] text-[#3f6249]">
          {copy.planView.summary}
        </span>
      </div>

      <div className="mt-3 grid grid-cols-4 gap-2 sm:grid-cols-7">
        {copy.planView.days.map((day) => (
          <div
            key={day.day}
            className="rounded-xl border border-cream-300/60 bg-white p-2 shadow-sm"
          >
            <div className="text-[10px] font-medium text-ink-400">{day.day}</div>
            <div className="mt-1.5 space-y-1">
              <div className="truncate rounded-md bg-[#f8f3ea] px-1.5 py-1 text-[10px] text-ink-700">
                {day.lunch}
              </div>
              <div className="truncate rounded-md bg-[#f8f3ea] px-1.5 py-1 text-[10px] text-ink-700">
                {day.dinner}
              </div>
            </div>
            <div className="mt-1.5 text-[9.5px] text-ink-400">{day.kcal} kcal</div>
          </div>
        ))}
      </div>

      <div className="mt-3 flex items-center gap-2 rounded-lg bg-[#f8f3ea] px-3 py-2 text-[10.5px] text-ink-500">
        <Sparkles className="h-3 w-3 text-[#c74e1f]" />
        {copy.planView.subtitle}
      </div>
    </>
  );
}

/** 视图三：库存与采购 */
function PantryView({ copy }: { copy: Copy['preview'] }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div>
        <div className="mb-2 flex items-center gap-1.5 text-[12px] font-semibold text-ink-900">
          <Package className="h-3.5 w-3.5 text-[#52795c]" />
          {copy.pantryView.stockTitle}
        </div>
        <div className="overflow-hidden rounded-xl border border-cream-300/60 bg-white">
          <div className="grid grid-cols-[1fr_auto_auto] gap-2 border-b border-cream-200/80 px-2.5 py-1.5 text-[9.5px] uppercase tracking-wide text-ink-400">
            <span>{copy.pantryView.columns.name}</span>
            <span>{copy.pantryView.columns.qty}</span>
            <span>{copy.pantryView.columns.expiry}</span>
          </div>
          {copy.pantryView.stock.map((item) => (
            <div
              key={item.name}
              className="grid grid-cols-[1fr_auto_auto] items-center gap-2 border-b border-cream-200/60 px-2.5 py-1.5 text-[10.5px] last:border-0"
            >
              <span className="flex items-center gap-1.5 truncate text-ink-700">
                {item.warn && <span className="h-1.5 w-1.5 rounded-full bg-[#e2602c]" />}
                {item.name}
              </span>
              <span className="text-ink-400">{item.qty}</span>
              <span className={item.warn ? 'text-[#c74e1f]' : 'text-ink-400'}>{item.expiry}</span>
            </div>
          ))}
        </div>
      </div>

      <div>
        <div className="mb-2 flex items-center gap-1.5 text-[12px] font-semibold text-ink-900">
          <BookOpen className="h-3.5 w-3.5 text-[#c74e1f]" />
          {copy.pantryView.listTitle}
        </div>
        <div className="rounded-xl border border-cream-300/60 bg-white p-1.5">
          {copy.pantryView.shopping.map((item) => (
            <div
              key={item.name}
              className="flex items-center gap-2 rounded-lg px-1.5 py-1.5 text-[10.5px] hover:bg-[#f8f3ea]"
            >
              <span
                className={`grid h-3.5 w-3.5 place-items-center rounded border ${
                  item.done
                    ? 'border-[#52795c] bg-[#52795c] text-white'
                    : 'border-cream-300'
                }`}
              >
                {item.done && <span className="text-[8px] leading-none">✓</span>}
              </span>
              <span className={item.done ? 'text-ink-300 line-through' : 'text-ink-700'}>
                {item.name}
              </span>
              <span className="ml-auto text-ink-400">{item.qty}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function Landing() {
  const [lang, setLang] = useState<Lang>(initialLang);
  const [scene, setScene] = useState(0);
  const [openStep, setOpenStep] = useState(0);
  const { isAuthenticated } = useAuth();
  const t = COPY[lang];
  const appHref = isAuthenticated ? '/agent' : '/login';

  const revealRef = useReveal<HTMLDivElement>();

  useEffect(() => {
    localStorage.setItem(LANG_KEY, lang);
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
    const previous = document.title;
    document.title =
      lang === 'zh'
        ? 'CookHero · AI 烹饪助手，从一句话到一桌菜'
        : 'CookHero · AI kitchen companion, from a sentence to a table';
    return () => {
      document.title = previous;
    };
  }, [lang]);

  const toggleLang = useCallback(() => {
    setLang((prev) => (prev === 'zh' ? 'en' : 'zh'));
  }, []);

  return (
    <div ref={revealRef} className="min-h-screen bg-[#08090a] text-white antialiased">
      {/* ---------------- 导航 ---------------- */}
      <header className="fixed inset-x-0 top-0 z-40 border-b border-white/[0.07] bg-[#08090a]/70 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-7xl items-center gap-3 px-5 sm:px-8">
          <Link to="/" className="flex items-center gap-2.5">
            <img src="/logo.svg" alt="CookHero" className="h-8 w-8" />
            <span className="ch-wordmark text-[15px] tracking-tight">CookHero</span>
          </Link>

          <nav className="mx-auto hidden items-center gap-1 text-[13px] font-medium text-white/55 md:flex">
            {[
              { href: '#capabilities', label: t.nav.product },
              { href: '#scenes', label: t.nav.scenes },
              { href: '#workflow', label: t.nav.workflow },
              { href: '#gallery', label: t.nav.gallery },
            ].map((item) => (
              <a
                key={item.href}
                href={item.href}
                className="rounded-full px-3.5 py-1.5 transition-colors hover:bg-white/[0.07] hover:text-white"
              >
                {item.label}
              </a>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-2">
            <button
              type="button"
              onClick={toggleLang}
              aria-label={lang === 'zh' ? 'Switch to English' : '切换到中文'}
              className="flex h-9 items-center gap-1.5 rounded-full border border-white/15 px-3 text-[12px] text-white/70 transition-colors hover:border-white/30 hover:text-white"
            >
              <Languages className="h-3.5 w-3.5" />
              {lang === 'zh' ? 'EN' : '中文'}
            </button>
            <Link
              to={appHref}
              className="inline-flex h-9 items-center gap-1.5 rounded-full bg-white px-3.5 text-[13px] font-semibold text-black transition-colors hover:bg-white/90 sm:px-4"
            >
              {t.nav.app}
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </div>
      </header>

      {/* ---------------- Hero ---------------- */}
      <section className="relative flex min-h-[92vh] items-end overflow-hidden pt-16">
        <HeroMedia lang={lang} />

        <div className="relative mx-auto w-full max-w-7xl px-5 pb-16 pt-24 sm:px-8 sm:pb-24">
          <div className="max-w-2xl">
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/[0.04] px-3 py-1.5 text-[11px] tracking-[0.16em] text-white/70">
              <Sparkles className="h-3.5 w-3.5 text-[#f2a87d]" />
              {t.hero.eyebrow}
            </div>

            <h1 className="ch-display text-[2.6rem] leading-[1.06] sm:text-[4rem] lg:text-[4.6rem]">
              {t.hero.titleA}
              <br />
              <span className="bg-gradient-to-r from-[#f2a87d] via-[#e2602c] to-[#d3a04c] bg-clip-text text-transparent">
                {t.hero.titleB}
              </span>
            </h1>

            <p className="mt-6 max-w-xl text-[15px] leading-relaxed text-white/65 sm:text-base">
              {t.hero.subtitle}
            </p>

            <div className="mt-9 flex flex-wrap items-center gap-3">
              <Link
                to={appHref}
                className="inline-flex h-11 items-center gap-2 rounded-full bg-white px-6 text-sm font-semibold text-black transition-transform hover:-translate-y-0.5"
              >
                {t.hero.primary}
                <ArrowRight className="h-4 w-4" />
              </Link>
              <a
                href="#preview"
                className="inline-flex h-11 items-center gap-2 rounded-full border border-white/20 px-6 text-sm text-white/80 transition-colors hover:border-white/40 hover:text-white"
              >
                {t.hero.secondary}
              </a>
            </div>

            <p className="mt-6 text-[11px] text-white/35">{t.hero.note}</p>
          </div>
        </div>

        <div className="pointer-events-none absolute bottom-6 left-1/2 hidden -translate-x-1/2 flex-col items-center gap-2 text-[10px] uppercase tracking-[0.24em] text-white/30 sm:flex">
          {t.hero.scroll}
          <span className="h-8 w-px bg-gradient-to-b from-white/40 to-transparent" />
        </div>
      </section>

      {/* ---------------- 作品滚动带 ---------------- */}
      <section className="border-y border-white/[0.06] bg-[#0a0b0d] py-10">
        <div className="mb-6 flex items-center justify-between px-5 sm:px-8">
          <span className="text-[11px] uppercase tracking-[0.22em] text-white/35">
            {t.marqueeCaption}
          </span>
        </div>
        <div className="space-y-4">
          <Marquee />
          <Marquee reverse width={240} />
        </div>
      </section>

      {/* ---------------- 核心能力 ---------------- */}
      <section id="capabilities" className="mx-auto scroll-mt-20 max-w-7xl px-5 py-24 sm:px-8">
        <div className="ch-reveal max-w-2xl">
          <div className="mb-3 text-[11px] uppercase tracking-[0.22em] text-[#f2a87d]">
            {t.capabilities.eyebrow}
          </div>
          <h2 className="ch-display text-[2rem] sm:text-[2.8rem]">{t.capabilities.title}</h2>
          <p className="mt-4 text-[15px] leading-relaxed text-white/55">{t.capabilities.subtitle}</p>
        </div>

        <div className="mt-16 space-y-20">
          {t.capabilities.items.map((item, i) => {
            const icons = [MessageSquare, CalendarDays, Package];
            const Icon = icons[i] ?? MessageSquare;
            const dish = DISHES[(i * 3) % DISHES.length];
            const inset = DISHES[(i * 3 + 1) % DISHES.length];
            return (
              <div
                key={item.title}
                className={`ch-reveal relative grid items-center gap-10 md:grid-cols-2 ${
                  i % 2 === 1 ? 'md:[&>figure]:order-2' : ''
                }`}
              >
                <figure className="relative overflow-hidden rounded-[1.75rem] border border-white/10">
                  <img
                    src={dishSrc(dish.file, 1100)}
                    alt={lang === 'zh' ? dish.name : dish.en}
                    className="h-[300px] w-full object-cover sm:h-[380px]"
                    loading="lazy"
                    decoding="async"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent" />
                </figure>

                {/* 叠放小图：同一能力的补充画面 */}
                <figure
                  className={`absolute bottom-5 hidden w-32 overflow-hidden rounded-2xl border border-white/20 shadow-[0_18px_40px_-16px_rgba(0,0,0,0.9)] md:block ${
                    i % 2 === 1 ? 'md:-right-4' : 'md:-left-4'
                  }`}
                >
                  <img
                    src={dishSrc(inset.file, 320)}
                    alt={lang === 'zh' ? inset.name : inset.en}
                    className="h-24 w-full object-cover"
                    loading="lazy"
                    decoding="async"
                  />
                </figure>

                <div>
                  <div className="mb-4 inline-flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-white/[0.04] text-[#f2a87d]">
                    <Icon className="h-4.5 w-4.5" />
                  </div>
                  <h3 className="ch-display text-[1.6rem] sm:text-[2rem]">{item.title}</h3>
                  <p className="mt-4 max-w-md text-[15px] leading-relaxed text-white/55">
                    {item.desc}
                  </p>
                  <div className="mt-6 flex flex-wrap gap-2">
                    {item.bullets.map((bullet) => (
                      <span
                        key={bullet}
                        className="rounded-full border border-white/12 px-3 py-1 text-[11px] text-white/55"
                      >
                        {bullet}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* ---------------- 产品界面 ---------------- */}
      <ProductPreview lang={lang} />

      {/* ---------------- 场景切换 ---------------- */}
      <section id="scenes" className="scroll-mt-20 border-t border-white/[0.06] bg-[#0a0b0d]">
        <div className="mx-auto max-w-7xl px-5 py-24 sm:px-8">
          <div className="ch-reveal">
            <div className="mb-3 text-[11px] uppercase tracking-[0.22em] text-[#f2a87d]">
              {t.scenes.eyebrow}
            </div>
            <h2 className="ch-display text-[2rem] sm:text-[2.8rem]">{t.scenes.title}</h2>
            <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-white/55">
              {t.scenes.subtitle}
            </p>
          </div>

          <div className="ch-reveal mt-10 flex flex-wrap gap-2">
            {t.scenes.tabs.map((tab, i) => (
              <button
                key={tab.key}
                type="button"
                onClick={() => setScene(i)}
                aria-pressed={scene === i}
                className={`rounded-full border px-4 py-2 text-[13px] transition-colors ${
                  scene === i
                    ? 'border-white bg-white text-black'
                    : 'border-white/15 text-white/60 hover:border-white/35 hover:text-white'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div className="ch-reveal mt-8 grid gap-8 overflow-hidden rounded-[1.75rem] border border-white/10 bg-white/[0.02] p-6 sm:p-10 md:grid-cols-[1.1fr_0.9fr]">
            <div className="flex flex-col justify-center">
              <h3 className="ch-display text-[1.6rem] sm:text-[2rem]">
                {t.scenes.tabs[scene].title}
              </h3>
              <p className="mt-4 max-w-lg text-[15px] leading-relaxed text-white/55">
                {t.scenes.tabs[scene].desc}
              </p>
              <Link
                to={appHref}
                className="mt-7 inline-flex w-fit items-center gap-2 text-sm text-[#f2a87d] transition-colors hover:text-white"
              >
                {t.hero.primary}
                <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {SCENE_SHOTS[scene].map((file) => {
                const dish = DISHES.find((item) => item.file === file);
                return (
                  <figure
                    key={file}
                    className="overflow-hidden rounded-2xl border border-white/10"
                  >
                    <img
                      src={dishSrc(file, 600)}
                      alt={dish ? (lang === 'zh' ? dish.name : dish.en) : ''}
                      className="h-full w-full object-cover"
                      loading="lazy"
                      decoding="async"
                    />
                  </figure>
                );
              })}
            </div>
          </div>
        </div>
      </section>

      {/* ---------------- 工作流 ---------------- */}
      <section id="workflow" className="mx-auto scroll-mt-20 max-w-7xl px-5 py-24 sm:px-8">
        <div className="ch-reveal max-w-2xl">
          <div className="mb-3 text-[11px] uppercase tracking-[0.22em] text-[#f2a87d]">
            {t.workflow.eyebrow}
          </div>
          <h2 className="ch-display text-[2rem] sm:text-[2.8rem]">{t.workflow.title}</h2>
          <p className="mt-4 text-[15px] leading-relaxed text-white/55">{t.workflow.subtitle}</p>
        </div>

        <div className="ch-reveal mt-12 grid gap-3 md:grid-cols-4">
          {t.workflow.steps.map((step, i) => {
            const active = openStep === i;
            return (
              <button
                key={step.no}
                type="button"
                onClick={() => setOpenStep(i)}
                className={`rounded-2xl border p-5 text-left transition-all ${
                  active
                    ? 'border-white/25 bg-white/[0.06]'
                    : 'border-white/10 bg-transparent hover:border-white/20'
                }`}
              >
                <span
                  className={`text-[11px] tracking-[0.18em] ${
                    active ? 'text-[#f2a87d]' : 'text-white/35'
                  }`}
                >
                  {step.no}
                </span>
                <div className="ch-display mt-3 text-[1.15rem]">{step.title}</div>
                <p
                  className={`mt-2 text-[13px] leading-relaxed transition-colors ${
                    active ? 'text-white/60' : 'text-white/35'
                  }`}
                >
                  {step.desc}
                </p>
              </button>
            );
          })}
        </div>
      </section>

      {/* ---------------- 菜谱墙 ---------------- */}
      <section id="gallery" className="scroll-mt-20 border-t border-white/[0.06] bg-[#0a0b0d]">
        <div className="mx-auto max-w-7xl px-5 py-24 sm:px-8">
          <div className="ch-reveal flex flex-wrap items-end justify-between gap-6">
            <div className="max-w-xl">
              <div className="mb-3 text-[11px] uppercase tracking-[0.22em] text-[#f2a87d]">
                {t.gallery.eyebrow}
              </div>
              <h2 className="ch-display text-[2rem] sm:text-[2.8rem]">{t.gallery.title}</h2>
              <p className="mt-4 text-[15px] leading-relaxed text-white/55">{t.gallery.subtitle}</p>
            </div>
            <Link
              to={appHref}
              className="inline-flex items-center gap-2 rounded-full border border-white/20 px-5 py-2.5 text-sm text-white/75 transition-colors hover:border-white/40 hover:text-white"
            >
              {t.gallery.cta}
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>

          <div className="ch-reveal mt-12 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {DISHES.slice(0, 12).map((dish, i) => (
              <figure
                key={dish.file}
                className={`group relative overflow-hidden rounded-2xl border border-white/10 ${
                  i === 0 || i === 7 ? 'sm:row-span-2 sm:h-full' : ''
                }`}
              >
                <img
                  src={dishSrc(dish.file, 700)}
                  alt={lang === 'zh' ? dish.name : dish.en}
                  className={`w-full object-cover transition-transform duration-700 group-hover:scale-105 ${
                    i === 0 || i === 7 ? 'h-56 sm:h-full' : 'h-56'
                  }`}
                  loading="lazy"
                  decoding="async"
                />
                <figcaption className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 via-black/30 to-transparent px-3 pb-2.5 pt-8 text-[12px]">
                  {lang === 'zh' ? dish.name : dish.en}
                </figcaption>
              </figure>
            ))}
          </div>
        </div>
      </section>

      {/* ---------------- 数据 ---------------- */}
      <section className="border-t border-white/[0.06]">
        <div className="mx-auto grid max-w-7xl grid-cols-2 gap-8 px-5 py-14 sm:px-8 md:grid-cols-4">
          {t.stats.map((stat) => (
            <CountUp key={stat.label} value={stat.value} label={stat.label} />
          ))}
        </div>
      </section>

      {/* ---------------- 收尾 CTA ---------------- */}
      <section className="relative overflow-hidden border-t border-white/[0.06] py-28">
        <div
          className="pointer-events-none absolute inset-0 opacity-70"
          style={{
            background:
              'radial-gradient(38rem 20rem at 50% 0%, rgba(226,96,44,0.32), transparent 65%)',
          }}
        />
        <div className="ch-reveal relative mx-auto max-w-3xl px-5 text-center">
          <ChefHat className="mx-auto h-9 w-9 text-[#f2a87d]" />
          <h2 className="ch-display mt-6 text-[2.2rem] sm:text-[3.2rem]">{t.cta.title}</h2>
          <p className="mx-auto mt-4 max-w-lg text-[15px] leading-relaxed text-white/55">
            {t.cta.subtitle}
          </p>
          <Link
            to={appHref}
            className="mt-9 inline-flex h-12 items-center gap-2 rounded-full bg-white px-7 text-sm font-semibold text-black transition-transform hover:-translate-y-0.5"
          >
            {t.cta.button}
            <ArrowRight className="h-4 w-4" />
          </Link>
          <p className="mt-4 text-[11px] text-white/35">{t.cta.hint}</p>
        </div>
      </section>

      {/* ---------------- 页脚 ---------------- */}
      <footer className="border-t border-white/[0.06] bg-[#050607]">
        <div className="mx-auto flex max-w-7xl flex-col gap-6 px-5 py-10 sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <div className="flex items-center gap-2.5">
            <img src="/logo.svg" alt="CookHero" className="h-7 w-7" />
            <span className="ch-wordmark text-sm">CookHero</span>
          </div>
          <div className="flex flex-wrap items-center gap-5 text-[12px] text-white/45">
            <Link to={appHref} className="transition-colors hover:text-white">
              {t.footer.app}
            </Link>
            <a
              href="/docs"
              target="_blank"
              rel="noreferrer"
              className="transition-colors hover:text-white"
            >
              {t.footer.docs}
            </a>
            <span className="text-white/25">{t.footer.stack}</span>
          </div>
          <div className="text-[11px] text-white/25">
            © {new Date().getFullYear()} {t.footer.rights}
          </div>
        </div>
      </footer>
    </div>
  );
}
