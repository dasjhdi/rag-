import { ChefHat, Sparkles, UtensilsCrossed, CalendarHeart, Package } from 'lucide-react';

/**
 * 登录 / 注册页左侧品牌视觉区
 */
export function AuthBrandPanel({ variant = 'login' }: { variant?: 'login' | 'register' }) {
  const isRegister = variant === 'register';

  return (
    <aside className="relative hidden lg:flex flex-col justify-between overflow-hidden bg-[#17120e] p-12 xl:p-16 text-cream-100">
      <div className="absolute -top-40 -right-24 w-[32rem] h-[32rem] rounded-full bg-ember-500/30 blur-[110px] animate-glow" />
      <div className="absolute -bottom-48 -left-24 w-[28rem] h-[28rem] rounded-full bg-herb-500/25 blur-[110px]" />
      <div
        className="absolute inset-0 opacity-[0.07]"
        style={{
          backgroundImage: 'radial-gradient(circle at 1px 1px, #fff 1px, transparent 0)',
          backgroundSize: '26px 26px',
        }}
      />

      <div className="relative">
        <div className="flex items-center gap-3">
          <img
            src="/logo.svg"
            alt="CookHero"
            className="w-12 h-12 drop-shadow-[0_12px_24px_rgba(226,96,44,0.55)]"
          />
          <div>
            <div className="ch-wordmark text-xl text-cream-100">CookHero</div>
            <div className="text-[10px] tracking-[0.22em] uppercase text-cream-100/40">
              AI Kitchen Companion
            </div>
          </div>
        </div>
      </div>

      <div className="relative max-w-lg animate-fade-up">
        <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-[11px] tracking-wide text-cream-100/70 mb-7">
          <Sparkles className="w-3.5 h-3.5 text-ember-300" />
          {isRegister ? '三个月后，你会感谢今天的自己' : '从灵感到餐桌，只差一句对话'}
        </div>
        {isRegister ? (
          <h1 className="ch-display text-[2.9rem] xl:text-[3.4rem] leading-[1.08] text-cream-50">
            你的厨房,
            <br />
            从此多一位
            <span className="bg-gradient-to-r from-ember-300 to-honey-300 bg-clip-text text-transparent">
              搭档
            </span>
            。
          </h1>
        ) : (
          <h1 className="ch-display text-[2.9rem] xl:text-[3.4rem] leading-[1.08] text-cream-50">
            把每一顿饭,
            <br />
            做成一件
            <span className="bg-gradient-to-r from-ember-300 to-honey-300 bg-clip-text text-transparent">
              作品
            </span>
            。
          </h1>
        )}
        <p className="mt-6 text-[15px] leading-relaxed text-cream-100/60 max-w-md">
          {isRegister
            ? '一个账号，收好你的口味偏好、家庭档案与一周菜单。下次打开，它已经懂你。'
            : 'CookHero 把菜谱检索、营养分析与一周计划收进同一个厨房工作台，让“今天吃什么”不再是一个难题。'}
        </p>

        <div className="mt-9 space-y-3.5">
          {[
            { icon: <UtensilsCrossed className="w-4 h-4" />, text: '按食材、口味与时间，找到今晚那道菜' },
            { icon: <CalendarHeart className="w-4 h-4" />, text: '一周饮食计划，自动照顾营养与过敏约束' },
            { icon: <Package className="w-4 h-4" />, text: '库存、采购与家庭档案，一处打理' },
          ].map((item) => (
            <div key={item.text} className="flex items-center gap-3 text-sm text-cream-100/75">
              <span className="w-8 h-8 rounded-xl bg-ember-400/10 border border-ember-300/20 flex items-center justify-center text-ember-200 shrink-0">
                {item.icon}
              </span>
              {item.text}
            </div>
          ))}
        </div>
      </div>

      <div className="relative flex items-center justify-between text-[11px] text-cream-100/35">
        <span>© {new Date().getFullYear()} CookHero</span>
        <span className="flex items-center gap-1.5">
          <ChefHat className="w-3.5 h-3.5" />
          Made for home cooks
        </span>
      </div>
    </aside>
  );
}
