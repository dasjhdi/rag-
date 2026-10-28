/**
 * 落地页双语文案。
 *
 * 只服务公开首页，不引入全局 i18n 依赖——应用内的中文界面保持原样，
 * 避免为一次改版动到整个产品。
 */

export type Lang = 'zh' | 'en';

export interface Copy {
  nav: { product: string; scenes: string; workflow: string; gallery: string; cta: string; app: string };
  hero: {
    eyebrow: string;
    titleA: string;
    titleB: string;
    subtitle: string;
    primary: string;
    secondary: string;
    note: string;
    scroll: string;
  };
  marqueeCaption: string;
  capabilities: {
    eyebrow: string;
    title: string;
    subtitle: string;
    items: { title: string; desc: string; bullets: string[] }[];
  };
  scenes: {
    eyebrow: string;
    title: string;
    subtitle: string;
    tabs: { key: string; label: string; title: string; desc: string }[];
  };
  workflow: {
    eyebrow: string;
    title: string;
    subtitle: string;
    steps: { no: string; title: string; desc: string }[];
  };
  preview: {
    eyebrow: string;
    title: string;
    subtitle: string;
    windowTitle: string;
    online: string;
    userMsg: string;
    assistantMsg: string;
    thinking: string[];
    inputPlaceholder: string;
    cards: { name: string; time: string; kcal: string }[];
    planTitle: string;
    plan: { day: string; dish: string }[];
    views: { chat: string; plan: string; pantry: string };
    planView: {
      title: string;
      subtitle: string;
      days: { day: string; lunch: string; dinner: string; kcal: string }[];
      summary: string;
    };
    pantryView: {
      stockTitle: string;
      listTitle: string;
      columns: { name: string; qty: string; expiry: string };
      stock: { name: string; qty: string; expiry: string; warn?: boolean }[];
      shopping: { name: string; qty: string; done: boolean }[];
    };
  };
  gallery: { eyebrow: string; title: string; subtitle: string; cta: string };
  stats: { value: string; label: string }[];
  cta: { title: string; subtitle: string; button: string; hint: string };
  footer: { product: string; app: string; docs: string; stack: string; rights: string };
}

export const COPY: Record<Lang, Copy> = {
  zh: {
    nav: {
      product: '产品',
      scenes: '场景',
      workflow: '工作流',
      gallery: '菜谱库',
      cta: '进入厨房',
      app: '打开应用',
    },
    hero: {
      eyebrow: 'AI 烹饪助手',
      titleA: '灵感所至，',
      titleB: '好菜成席。',
      subtitle:
        '从「今晚吃什么」到一周菜单与采购清单——把菜谱检索、营养分析与库存管理收进同一个厨房工作台。',
      primary: '开始使用',
      secondary: '看看怎么用',
      note: '页面菜品图片来自项目内置的真实菜谱库',
      scroll: '向下浏览',
    },
    marqueeCaption: '373 道菜谱 · 435 张实拍配图',
    capabilities: {
      eyebrow: '核心能力',
      title: '一句话，做出一桌菜',
      subtitle: '不需要想清楚搜索词。说出食材、口味或时间限制，剩下的交给它。',
      items: [
        {
          title: '对话找菜',
          desc: '基于 RAG 的菜谱检索：理解「冰箱里只有鸡腿和土豆」这类模糊描述，给出可执行的方案而不是一堆链接。',
          bullets: ['语义检索', '多轮追问', '约束过滤'],
        },
        {
          title: '一周饮食计划',
          desc: '排餐时同时考虑热量目标、过敏原与烹饪时长；不满意的某一餐可以单独替换，其余不动。',
          bullets: ['营养配比', '忌口约束', '单餐替换'],
        },
        {
          title: '库存与采购',
          desc: '记录家里有什么，缺什么自动进采购清单；临期食材优先推荐，减少浪费。',
          bullets: ['库存台账', '自动清单', '临期优先'],
        },
      ],
    },
    scenes: {
      eyebrow: '使用场景',
      title: '不同的晚上，不同的做法',
      subtitle: '同一个入口，按你的处境调整答案。',
      tabs: [
        {
          key: 'weekday',
          label: '工作日晚餐',
          title: '30 分钟内上桌',
          desc: '优先推荐少步骤、少器具的做法；会主动避开需要长时间腌制或炖煮的菜。',
        },
        {
          key: 'family',
          label: '家庭聚餐',
          title: '一桌菜的搭配',
          desc: '按人数估算份量，兼顾荤素与口味差异，输出上菜顺序而不是零散菜谱。',
        },
        {
          key: 'lean',
          label: '减脂餐',
          title: '热量可控，不难吃',
          desc: '在热量缺口内挑选高蛋白组合，标注每餐估算值与偏差范围。',
        },
        {
          key: 'prep',
          label: '周末备菜',
          title: '一次备好一周',
          desc: '把可以提前处理的步骤合并，给出保鲜与复热建议，减少工作日决策成本。',
        },
      ],
    },
    workflow: {
      eyebrow: '工作流',
      title: '四步，从想法到餐桌',
      subtitle: '每一步都能看到它在做什么，而不是等一个黑盒结果。',
      steps: [
        { no: '01', title: '说一句', desc: '「两个人，冰箱有鸡腿和土豆，半小时内。」' },
        { no: '02', title: '拿到菜谱', desc: '检索、筛选、按你的约束重排，给出步骤与用量。' },
        { no: '03', title: '排进计划', desc: '选中的菜自动进入一周菜单，热量与忌口同步校验。' },
        { no: '04', title: '生成清单', desc: '缺什么补什么，按货架分区排序，照着买就行。' },
      ],
    },
    preview: {
      eyebrow: '产品界面',
      title: '看得见的工作台',
      subtitle: '不是一张聊天框。意图、检索、约束与结果都在同一屏里，随时可以打断和改写。',
      windowTitle: 'CookHero · 厨房工作台',
      online: '在线',
      userMsg: '两个人，冰箱里只有鸡腿和土豆，半小时内能吃上什么？',
      assistantMsg: '按 30 分钟上限筛出两道，都不需要额外买调料：',
      thinking: ['意图：菜谱检索', '约束：30 分钟 · 2 人份', '检索：18 条命中 → 重排'],
      inputPlaceholder: '继续追问，或直接说「换一道」…',
      cards: [
        { name: '可乐鸡翅', time: '25 分钟', kcal: '约 420 kcal' },
        { name: '咕噜肉', time: '30 分钟', kcal: '约 450 kcal' },
      ],
      planTitle: '本周计划',
      plan: [
        { day: '周一', dish: '可乐鸡翅' },
        { day: '周二', dish: '蒜蓉西兰花' },
        { day: '周三', dish: '番茄牛腩' },
        { day: '周四', dish: '清蒸鲈鱼' },
      ],
      views: { chat: '对话', plan: '计划', pantry: '库存' },
      planView: {
        title: '一周菜单',
        subtitle: '热量 1,860 / 2,100 kcal · 蛋白质达标 · 无过敏原冲突',
        days: [
          { day: '周一', lunch: '鸡翅饭', dinner: '西兰花炒虾仁', kcal: '1,820' },
          { day: '周二', lunch: '牛肉面', dinner: '清炒时蔬', kcal: '1,760' },
          { day: '周三', lunch: '番茄牛腩', dinner: '凉拌黄瓜', kcal: '1,940' },
          { day: '周四', lunch: '清蒸鲈鱼', dinner: '菌菇汤', kcal: '1,780' },
          { day: '周五', lunch: '咖喱鸡', dinner: '蒜蓉菠菜', kcal: '1,900' },
          { day: '周六', lunch: '肉蟹煲', dinner: '蔬菜沙拉', kcal: '2,050' },
          { day: '周日', lunch: '水煮鱼', dinner: '白粥小菜', kcal: '1,980' },
        ],
        summary: '周三晚餐可一键替换',
      },
      pantryView: {
        stockTitle: '家里有什么',
        listTitle: '还缺什么',
        columns: { name: '食材', qty: '数量', expiry: '到期' },
        stock: [
          { name: '鸡腿', qty: '500 g', expiry: '2 天', warn: true },
          { name: '土豆', qty: '3 个', expiry: '12 天' },
          { name: '西兰花', qty: '1 颗', expiry: '3 天', warn: true },
          { name: '鸡蛋', qty: '6 个', expiry: '18 天' },
          { name: '生抽', qty: '1 瓶', expiry: '—' },
        ],
        shopping: [
          { name: '鸡翅中', qty: '500 g', done: false },
          { name: '番茄', qty: '3 个', done: false },
          { name: '鲈鱼', qty: '1 条', done: false },
          { name: '生姜', qty: '1 块', done: true },
        ],
      },
    },
    gallery: {
      eyebrow: '菜谱库',
      title: '不是演示数据',
      subtitle: '373 道菜谱、真实配图与步骤，检索结果可直接下厨。',
      cta: '浏览全部菜谱',
    },
    stats: [
      { value: '373', label: '道菜谱' },
      { value: '1,944', label: '条向量索引' },
      { value: '5', label: '类 Agent 工具' },
      { value: '2', label: '档模型分层' },
    ],
    cta: {
      title: '今晚吃什么？',
      subtitle: '把这个问题交出去，留点时间给吃饭本身。',
      button: '进入 CookHero',
      hint: '已有账号可直接登录，没有则注册一个。',
    },
    footer: {
      product: '产品',
      app: '打开应用',
      docs: 'API 文档',
      stack: 'FastAPI · PostgreSQL · Milvus · React',
      rights: 'CookHero · 智能烹饪助手',
    },
  },
  en: {
    nav: {
      product: 'Product',
      scenes: 'Scenes',
      workflow: 'Workflow',
      gallery: 'Recipes',
      cta: 'Enter kitchen',
      app: 'Open app',
    },
    hero: {
      eyebrow: 'AI KITCHEN COMPANION',
      titleA: 'From a craving',
      titleB: 'to a plated dish.',
      subtitle:
        'From “what’s for dinner” to a weekly menu and a shopping list — recipe retrieval, nutrition analysis and pantry tracking in one workspace.',
      primary: 'Get started',
      secondary: 'See how it works',
      note: 'Dish photos come from the project’s real recipe library',
      scroll: 'Scroll',
    },
    marqueeCaption: '373 recipes · 435 real photos',
    capabilities: {
      eyebrow: 'CAPABILITIES',
      title: 'One sentence, one table',
      subtitle: 'No need to craft a search query. Say the ingredients, the mood, or the time you have.',
      items: [
        {
          title: 'Conversational search',
          desc: 'RAG-based retrieval that understands fuzzy requests like “I only have chicken thighs and potatoes”, and answers with a plan.',
          bullets: ['Semantic search', 'Follow-ups', 'Constraint filters'],
        },
        {
          title: 'Weekly meal plans',
          desc: 'Balance calories, allergens and cooking time; swap a single meal without rebuilding the whole week.',
          bullets: ['Macros', 'Allergens', 'Meal swap'],
        },
        {
          title: 'Pantry & shopping',
          desc: 'Track what you have, add what you lack to a shopping list, and use expiring ingredients first.',
          bullets: ['Inventory', 'Auto list', 'Expiry first'],
        },
      ],
    },
    scenes: {
      eyebrow: 'SCENES',
      title: 'Different nights, different answers',
      subtitle: 'One entry point, adjusted to your situation.',
      tabs: [
        {
          key: 'weekday',
          label: 'Weeknight',
          title: 'On the table in 30 minutes',
          desc: 'Prefers few steps and few pans, and skips anything that needs long marinating or braising.',
        },
        {
          key: 'family',
          label: 'Family dinner',
          title: 'A table that works together',
          desc: 'Scales portions to headcount, balances meat and vegetables, and returns a serving order.',
        },
        {
          key: 'lean',
          label: 'Lean meals',
          title: 'Controlled calories, still tasty',
          desc: 'High-protein combinations within your deficit, with estimated values and a tolerance range.',
        },
        {
          key: 'prep',
          label: 'Weekend prep',
          title: 'Prep once, eat all week',
          desc: 'Merges steps you can batch, then adds storage and reheating notes.',
        },
      ],
    },
    workflow: {
      eyebrow: 'WORKFLOW',
      title: 'Four steps, from idea to table',
      subtitle: 'You can see what it is doing at every step — not just wait for a black box.',
      steps: [
        { no: '01', title: 'Say it', desc: '“Two people, chicken thighs and potatoes, half an hour.”' },
        { no: '02', title: 'Get the recipe', desc: 'Retrieved, filtered and re-ranked against your constraints.' },
        { no: '03', title: 'Plan it', desc: 'Selected dishes enter the weekly plan with calories and allergens checked.' },
        { no: '04', title: 'Shop it', desc: 'Missing items become a list, sorted by store section.' },
      ],
    },
    preview: {
      eyebrow: 'THE WORKSPACE',
      title: 'A workspace you can see',
      subtitle:
        'Not just a chat box. Intent, retrieval, constraints and results share one screen you can interrupt and rewrite.',
      windowTitle: 'CookHero · Kitchen workspace',
      online: 'Online',
      userMsg: 'Two people, only chicken thighs and potatoes in the fridge. What can I cook in 30 minutes?',
      assistantMsg: 'Two options within your 30-minute limit, neither needs extra shopping:',
      thinking: ['Intent: recipe search', 'Constraints: 30 min · 2 servings', 'Retrieval: 18 hits → re-ranked'],
      inputPlaceholder: 'Ask a follow-up, or just say “swap this one”…',
      cards: [
        { name: 'Cola Chicken Wings', time: '25 min', kcal: '~420 kcal' },
        { name: 'Sweet & Sour Pork', time: '30 min', kcal: '~450 kcal' },
      ],
      planTitle: 'This week',
      plan: [
        { day: 'Mon', dish: 'Cola wings' },
        { day: 'Tue', dish: 'Garlic broccoli' },
        { day: 'Wed', dish: 'Beef stew' },
        { day: 'Thu', dish: 'Steamed fish' },
      ],
      views: { chat: 'Chat', plan: 'Plan', pantry: 'Pantry' },
      planView: {
        title: 'Weekly menu',
        subtitle: '1,860 / 2,100 kcal · protein on target · no allergen conflicts',
        days: [
          { day: 'Mon', lunch: 'Wings & rice', dinner: 'Shrimp broccoli', kcal: '1,820' },
          { day: 'Tue', lunch: 'Beef noodles', dinner: 'Greens', kcal: '1,760' },
          { day: 'Wed', lunch: 'Beef stew', dinner: 'Cucumber salad', kcal: '1,940' },
          { day: 'Thu', lunch: 'Steamed fish', dinner: 'Mushroom soup', kcal: '1,780' },
          { day: 'Fri', lunch: 'Curry chicken', dinner: 'Garlic spinach', kcal: '1,900' },
          { day: 'Sat', lunch: 'Crab pot', dinner: 'Garden salad', kcal: '2,050' },
          { day: 'Sun', lunch: 'Poached fish', dinner: 'Congee', kcal: '1,980' },
        ],
        summary: 'Swap Wednesday dinner in one tap',
      },
      pantryView: {
        stockTitle: 'In the pantry',
        listTitle: 'Still needed',
        columns: { name: 'Item', qty: 'Qty', expiry: 'Expires' },
        stock: [
          { name: 'Chicken thighs', qty: '500 g', expiry: '2 d', warn: true },
          { name: 'Potatoes', qty: '3 pcs', expiry: '12 d' },
          { name: 'Broccoli', qty: '1 head', expiry: '3 d', warn: true },
          { name: 'Eggs', qty: '6 pcs', expiry: '18 d' },
          { name: 'Soy sauce', qty: '1 bottle', expiry: '—' },
        ],
        shopping: [
          { name: 'Chicken wings', qty: '500 g', done: false },
          { name: 'Tomatoes', qty: '3 pcs', done: false },
          { name: 'Sea bass', qty: '1 pc', done: false },
          { name: 'Ginger', qty: '1 pc', done: true },
        ],
      },
    },
    gallery: {
      eyebrow: 'RECIPE LIBRARY',
      title: 'Not demo data',
      subtitle: '373 recipes with real photos and steps — results you can cook tonight.',
      cta: 'Browse all recipes',
    },
    stats: [
      { value: '373', label: 'recipes' },
      { value: '1,944', label: 'vector entries' },
      { value: '5', label: 'agent tool groups' },
      { value: '2', label: 'model tiers' },
    ],
    cta: {
      title: 'What’s for dinner?',
      subtitle: 'Hand the question over. Keep the time for eating.',
      button: 'Open CookHero',
      hint: 'Sign in if you already have an account, or create one.',
    },
    footer: {
      product: 'Product',
      app: 'Open app',
      docs: 'API docs',
      stack: 'FastAPI · PostgreSQL · Milvus · React',
      rights: 'CookHero · AI kitchen companion',
    },
  },
};
