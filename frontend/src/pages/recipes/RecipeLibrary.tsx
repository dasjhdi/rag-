import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Bookmark,
  Check,
  ChevronDown,
  ChevronUp,
  Clock,
  Flame,
  Heart,
  Loader2,
  Search,
  Sparkles,
  Utensils,
  X,
} from 'lucide-react';
import { useAuth } from '../../contexts';
import {
  listRecipeLibrary,
  toggleRecipeFeedback,
  type RecipeLibraryParams,
} from '../../services/api/diet';
import type {
  RecipeFacet,
  RecipeFeedbackFilter,
  RecipeLibraryItem,
  RecipeSortKey,
} from '../../types/diet';
import { cleanRecipeText } from '../../utils/recipeText';
import { BackButton, RecipeImage } from '../../components/common';

const PAGE_SIZE = 24;

const CATEGORY_EMOJI: Record<string, string> = {
  水产: '🐟',
  早餐: '🍳',
  甜品: '🍰',
  饮料: '🥤',
  饮品: '🥤',
  荤菜: '🍖',
  半成品: '🥫',
  主食: '🍚',
  素菜: '🥬',
  未分类: '🍽️',
};

const SORT_OPTIONS: { value: RecipeSortKey; label: string }[] = [
  { value: 'name', label: '按名称' },
  { value: 'minutes', label: '按耗时' },
  { value: 'calories', label: '按热量' },
  { value: 'ingredients', label: '按食材数' },
];

const FEEDBACK_FILTERS: { value: RecipeFeedbackFilter; label: string; icon: typeof Heart }[] = [
  { value: 'want', label: '想做', icon: Sparkles },
  { value: 'favorite', label: '收藏', icon: Heart },
  { value: 'cooked', label: '已做过', icon: Check },
];

function MiniBarChart({ facets, active, onSelect }: {
  facets: RecipeFacet[];
  active?: string;
  onSelect: (value: string | undefined) => void;
}) {
  const max = Math.max(1, ...facets.map(f => f.count));
  return (
    <div className="space-y-1.5">
      {facets.map(facet => (
        <button
          key={facet.value}
          onClick={() => onSelect(facet.value === active ? undefined : facet.value)}
          className={`w-full text-left group ${facet.value === active ? 'opacity-100' : 'opacity-90 hover:opacity-100'}`}
          title={`${facet.label} · ${facet.count} 道`}
        >
          <div className="flex items-center justify-between text-[11px] mb-0.5">
            <span className={facet.value === active ? 'text-ember-700 dark:text-ember-300 font-medium' : 'text-ink-500 dark:text-ink-300'}>
              {facet.label}
            </span>
            <span className="text-ink-400">{facet.count}</span>
          </div>
          <div className="h-1.5 rounded-full bg-cream-200/70 dark:bg-white/5 overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${facet.value === active ? 'bg-ember-500' : 'bg-ember-300/70 group-hover:bg-ember-400'}`}
              style={{ width: `${(facet.count / max) * 100}%` }}
            />
          </div>
        </button>
      ))}
    </div>
  );
}

function FeedbackButtons({ signals, onToggle }: {
  signals: string[];
  onToggle: (signal: RecipeFeedbackFilter, active: boolean) => void;
}) {
  const states: { signal: RecipeFeedbackFilter; icon: typeof Heart; label: string }[] = [
    { signal: 'want', icon: Sparkles, label: '想做' },
    { signal: 'favorite', icon: Heart, label: '收藏' },
    { signal: 'cooked', icon: Check, label: '已做' },
  ];
  return (
    <div className="flex items-center gap-0.5 mt-2" onClick={e => e.preventDefault()}>
      {states.map(({ signal, icon: Icon, label }) => {
        const active = signals.includes(signal);
        return (
          <button
            key={signal}
            onClick={() => onToggle(signal, !active)}
            title={label}
            className={`flex items-center gap-1 text-[10px] px-1.5 py-1 rounded-md transition-colors ${
              active
                ? signal === 'want'
                  ? 'bg-violet-100 text-violet-700 dark:bg-violet-500/20 dark:text-violet-200'
                  : signal === 'favorite'
                    ? 'bg-rose-100 text-rose-700 dark:bg-rose-500/20 dark:text-rose-200'
                    : 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-200'
                : 'text-ink-400 hover:bg-cream-100 dark:hover:bg-white/5'
            }`}
          >
            <Icon className="w-3 h-3" />
          </button>
        );
      })}
    </div>
  );
}

function RecipeCard({
  recipe,
  signals,
  onToggleFeedback,
}: {
  recipe: RecipeLibraryItem;
  signals: string[];
  onToggleFeedback: (signal: RecipeFeedbackFilter, active: boolean) => void;
}) {
  const [hovering, setHovering] = useState(false);
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleEnter = () => {
    hoverTimer.current = setTimeout(() => setHovering(true), 400);
  };
  const handleLeave = () => {
    if (hoverTimer.current) clearTimeout(hoverTimer.current);
    setHovering(false);
  };

  return (
    <Link
      to={`/recipes/${recipe.recipe_id}`}
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
      className="ch-card ch-card-hover group relative flex flex-col overflow-hidden !p-0"
    >
      <div className="relative">
        <RecipeImage
          src={recipe.image_url}
          title={recipe.title}
          alt={recipe.title}
          className="aspect-square"
          imageClassName="transition-transform duration-500 group-hover:scale-[1.04]"
          width={480}
        />
        {recipe.images_count > 1 && (
          <span className="absolute bottom-1.5 right-1.5 rounded-full bg-ink-900/65 px-1.5 py-0.5 text-[10px] font-medium text-white backdrop-blur-sm">
            {recipe.images_count} 图
          </span>
        )}
        {recipe.difficulty && (
          <span className="absolute top-1.5 left-1.5 rounded-full bg-white/85 dark:bg-ink-900/65 px-2 py-0.5 text-[10px] font-medium text-ink-700 dark:text-cream-100 backdrop-blur-sm">
            {recipe.difficulty}
          </span>
        )}
        {recipe.has_step_images && (
          <span className="absolute top-1.5 right-1.5 rounded-full bg-herb-500/85 px-1.5 py-0.5 text-[10px] font-medium text-white backdrop-blur-sm" title="含步骤图">
            图解
          </span>
        )}
      </div>
      <div className="flex flex-1 flex-col p-3">
        <h3 className="text-sm font-semibold text-ink-900 dark:text-cream-100 line-clamp-1">
          {cleanRecipeText(recipe.title)}
        </h3>
        {recipe.category && (
          <span className="text-[11px] text-ink-400 mt-0.5 line-clamp-1">{recipe.category}</span>
        )}
        <div className="flex flex-wrap gap-2 mt-2 text-[11px] text-ink-500 dark:text-ink-300">
          <span className="inline-flex items-center gap-0.5">
            <Flame className="w-3 h-3" />
            {recipe.calories ? `${recipe.calories} kcal` : '热量未知'}
          </span>
          <span className="inline-flex items-center gap-0.5">
            <Clock className="w-3 h-3" />
            {recipe.total_minutes ? `${recipe.total_minutes} 分` : '时间未知'}
          </span>
          <span>{recipe.ingredients_count} 食材</span>
        </div>
        <FeedbackButtons signals={signals} onToggle={onToggleFeedback} />
      </div>

      {hovering && (recipe.main_ingredients.length > 0 || recipe.description) && (
        <div className="absolute left-2 right-2 bottom-2 z-20 rounded-xl bg-white/95 dark:bg-ink-900/95 backdrop-blur border border-cream-200 dark:border-white/10 shadow-lg p-3 text-left">
          {recipe.main_ingredients.length > 0 && (
            <div className="flex flex-wrap gap-1 mb-1.5">
              {recipe.main_ingredients.slice(0, 6).map(name => (
                <span key={name} className="text-[10px] px-1.5 py-0.5 rounded bg-cream-100 dark:bg-white/5 text-ink-600 dark:text-ink-200">
                  {name}
                </span>
              ))}
            </div>
          )}
          {recipe.description && (
            <p className="text-[11px] text-ink-500 dark:text-ink-300 line-clamp-2">{cleanRecipeText(recipe.description)}</p>
          )}
          <div className="text-[10px] text-ember-600 dark:text-ember-300 mt-1.5 font-medium">点击查看完整菜谱 →</div>
        </div>
      )}
    </Link>
  );
}

function SkeletonCard() {
  return (
    <div className="ch-card overflow-hidden !p-0 animate-pulse">
      <div className="aspect-square bg-cream-200 dark:bg-white/5" />
      <div className="p-3 space-y-2">
        <div className="h-3.5 w-3/4 rounded bg-cream-200 dark:bg-white/5" />
        <div className="h-2.5 w-1/2 rounded bg-cream-100 dark:bg-white/5" />
        <div className="h-2.5 w-2/3 rounded bg-cream-100 dark:bg-white/5" />
      </div>
    </div>
  );
}

export default function RecipeLibraryPage() {
  const { token } = useAuth();
  const [category, setCategory] = useState<string | undefined>(undefined);
  const [difficulty, setDifficulty] = useState<string | undefined>(undefined);
  const [ingredient, setIngredient] = useState<string | undefined>(undefined);
  const [feedbackFilter, setFeedbackFilter] = useState<RecipeFeedbackFilter | undefined>(undefined);
  const [sort, setSort] = useState<RecipeSortKey>('name');
  const [hasStepImages, setHasStepImages] = useState<boolean | undefined>(undefined);
  const [query, setQuery] = useState('');
  const [committedQuery, setCommittedQuery] = useState('');
  const [ingredientsExpanded, setIngredientsExpanded] = useState(false);

  const [items, setItems] = useState<RecipeLibraryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [categories, setCategories] = useState<RecipeFacet[]>([]);
  const [difficulties, setDifficulties] = useState<RecipeFacet[]>([]);
  const [ingredients, setIngredients] = useState<RecipeFacet[]>([]);
  const [minutesBuckets, setMinutesBuckets] = useState<RecipeFacet[]>([]);
  const [offset, setOffset] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Optimistic feedback overrides: recipe_id -> string[]
  const [feedbackOverrides, setFeedbackOverrides] = useState<Record<string, string[]>>({});

  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const hasMore = items.length < total;

  const params: RecipeLibraryParams = useMemo(
    () => ({
      category,
      difficulty,
      ingredient,
      feedback: feedbackFilter,
      sort,
      has_step_images: hasStepImages,
      q: committedQuery.trim() || undefined,
      offset: 0,
      limit: PAGE_SIZE,
    }),
    [category, difficulty, ingredient, feedbackFilter, sort, hasStepImages, committedQuery]
  );

  const loadFirst = useCallback(async () => {
    if (!token) return;
    setIsLoading(true);
    setError(null);
    try {
      const res = await listRecipeLibrary(token, params);
      setItems(res.items);
      setTotal(res.total);
      setCategories(res.categories);
      setDifficulties(res.difficulties);
      setIngredients(res.ingredients);
      setMinutesBuckets(res.minutes_buckets);
      setOffset(res.items.length);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载菜谱失败');
    } finally {
      setIsLoading(false);
    }
  }, [token, params]);

  useEffect(() => {
    loadFirst();
  }, [loadFirst]);

  const loadMore = useCallback(async () => {
    if (!token || isLoadingMore || !hasMore) return;
    setIsLoadingMore(true);
    try {
      const res = await listRecipeLibrary(token, { ...params, offset, limit: PAGE_SIZE });
      setItems(prev => [...prev, ...res.items]);
      setOffset(prev => prev + res.items.length);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载更多失败');
    } finally {
      setIsLoadingMore(false);
    }
  }, [token, params, offset, isLoadingMore, hasMore]);

  useEffect(() => {
    const node = sentinelRef.current;
    if (!node || !hasMore) return;
    const observer = new IntersectionObserver(
      entries => {
        if (entries[0].isIntersecting) loadMore();
      },
      { rootMargin: '600px' }
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [loadMore, hasMore]);

  const activeFilterCount =
    (category ? 1 : 0) +
    (difficulty ? 1 : 0) +
    (ingredient ? 1 : 0) +
    (feedbackFilter ? 1 : 0) +
    (hasStepImages ? 1 : 0) +
    (committedQuery ? 1 : 0);

  const clearFilters = () => {
    setCategory(undefined);
    setDifficulty(undefined);
    setIngredient(undefined);
    setFeedbackFilter(undefined);
    setHasStepImages(undefined);
    setQuery('');
    setCommittedQuery('');
  };

  const handleToggleFeedback = useCallback(
    async (recipeId: string, signal: RecipeFeedbackFilter, active: boolean) => {
      if (!token) return;
      // Optimistic update
      setFeedbackOverrides(prev => {
        const current = prev[recipeId] ?? items.find(i => i.recipe_id === recipeId)?.feedback ?? [];
        const next = active
          ? Array.from(new Set([...current, signal]))
          : current.filter(s => s !== signal);
        return { ...prev, [recipeId]: next };
      });
      try {
        await toggleRecipeFeedback(token, recipeId, signal, active);
      } catch {
        // Revert on failure
        setFeedbackOverrides(prev => {
          const current = prev[recipeId] ?? [];
          const next = active
            ? current.filter(s => s !== signal)
            : Array.from(new Set([...current, signal]));
          return { ...prev, [recipeId]: next };
        });
      }
    },
    [token, items]
  );

  const signalsFor = (recipe: RecipeLibraryItem): string[] =>
    feedbackOverrides[recipe.recipe_id] ?? recipe.feedback;

  const visibleIngredients = ingredientsExpanded ? ingredients : ingredients.slice(0, 10);

  return (
    <div className="flex-1 overflow-auto p-4 md:p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        <div>
          <BackButton fallbackTo="/diet" label="返回上级" />
          <div className="ch-eyebrow mt-4">Recipe Library</div>
          <div className="flex flex-wrap items-end justify-between gap-4 mt-1">
            <div>
              <h1 className="ch-display text-[2rem] text-ink-900 dark:text-cream-50">菜谱图鉴</h1>
              <p className="text-sm text-ink-500 dark:text-ink-300 mt-1.5">
                浏览全部 {total} 道菜谱 · 按分类、食材、难度、状态筛选与排序
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Link to="/recipes" className="ch-btn ch-btn-secondary">
                <Search className="w-4 h-4" />
                条件搜索
              </Link>
              <Link to="/diet/profile" className="ch-btn ch-btn-secondary">
                饮食档案
              </Link>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[240px_1fr] gap-6">
          {/* Sidebar */}
          <aside className="space-y-4 lg:sticky lg:top-4 self-start max-h-[calc(100vh-2rem)] overflow-y-auto pr-1">
            <div className="ch-card p-4">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-semibold text-ink-900 dark:text-cream-100">筛选</h2>
                {activeFilterCount > 0 && (
                  <button
                    onClick={clearFilters}
                    className="text-[11px] text-ink-400 hover:text-ember-600 dark:hover:text-ember-300 flex items-center gap-1"
                  >
                    <X className="w-3 h-3" />
                    清除 ({activeFilterCount})
                  </button>
                )}
              </div>

              {/* Feedback state filters */}
              <div className="mb-4">
                <div className="text-[11px] uppercase tracking-wide text-ink-400 mb-1.5">我的标记</div>
                <div className="flex flex-wrap gap-1.5">
                  {FEEDBACK_FILTERS.map(({ value, label, icon: Icon }) => (
                    <button
                      key={value}
                      onClick={() => setFeedbackFilter(feedbackFilter === value ? undefined : value)}
                      className={`text-xs px-2.5 py-1 rounded-full inline-flex items-center gap-1 transition-colors ${
                        feedbackFilter === value
                          ? 'bg-ember-100 text-ember-700 dark:bg-ember-500/20 dark:text-ember-200'
                          : 'bg-cream-100 dark:bg-white/5 text-ink-500 dark:text-ink-300 hover:bg-cream-200 dark:hover:bg-white/10'
                      }`}
                    >
                      <Icon className="w-3 h-3" />
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Category list */}
              <div className="text-[11px] uppercase tracking-wide text-ink-400 mb-1.5">分类</div>
              <div className="space-y-0.5 mb-4">
                <button
                  onClick={() => setCategory(undefined)}
                  className={`w-full text-left px-2.5 py-1.5 rounded-lg text-sm transition-colors ${
                    !category
                      ? 'bg-ember-50 dark:bg-ember-500/15 text-ember-700 dark:text-ember-300 font-medium'
                      : 'text-ink-600 dark:text-ink-300 hover:bg-cream-100 dark:hover:bg-white/5'
                  }`}
                >
                  全部
                  <span className="float-right text-xs text-ink-400">{total}</span>
                </button>
                {categories.map(facet => (
                  <button
                    key={facet.value}
                    onClick={() => setCategory(facet.value === category ? undefined : facet.value)}
                    className={`w-full text-left px-2.5 py-1.5 rounded-lg text-sm transition-colors ${
                      facet.value === category
                        ? 'bg-ember-50 dark:bg-ember-500/15 text-ember-700 dark:text-ember-300 font-medium'
                        : 'text-ink-600 dark:text-ink-300 hover:bg-cream-100 dark:hover:bg-white/5'
                    }`}
                  >
                    <span className="mr-1.5">{CATEGORY_EMOJI[facet.label] ?? '🍽️'}</span>
                    {facet.label}
                    <span className="float-right text-xs text-ink-400">{facet.count}</span>
                  </button>
                ))}
              </div>

              {/* Minutes mini chart */}
              {minutesBuckets.length > 0 && (
                <div className="mb-4">
                  <div className="text-[11px] uppercase tracking-wide text-ink-400 mb-1.5">耗时分布</div>
                  <MiniBarChart facets={minutesBuckets} active={undefined} onSelect={() => {}} />
                </div>
              )}

              {/* Difficulty mini chart */}
              {difficulties.length > 0 && (
                <div className="mb-4">
                  <div className="text-[11px] uppercase tracking-wide text-ink-400 mb-1.5">难度分布</div>
                  <MiniBarChart
                    facets={difficulties}
                    active={difficulty}
                    onSelect={v => setDifficulty(v)}
                  />
                </div>
              )}

              {/* Ingredient facets */}
              {visibleIngredients.length > 0 && (
                <div>
                  <div className="text-[11px] uppercase tracking-wide text-ink-400 mb-1.5">常用食材</div>
                  <div className="flex flex-wrap gap-1">
                    {visibleIngredients.map(facet => (
                      <button
                        key={facet.value}
                        onClick={() => setIngredient(facet.value === ingredient ? undefined : facet.value)}
                        className={`text-[11px] px-2 py-0.5 rounded-full transition-colors ${
                          facet.value === ingredient
                            ? 'bg-ember-100 text-ember-700 dark:bg-ember-500/20 dark:text-ember-200'
                            : 'bg-cream-100 dark:bg-white/5 text-ink-500 dark:text-ink-300 hover:bg-cream-200 dark:hover:bg-white/10'
                        }`}
                        title={`${facet.label} · ${facet.count} 道`}
                      >
                        {facet.label} · {facet.count}
                      </button>
                    ))}
                  </div>
                  {ingredients.length > 10 && (
                    <button
                      onClick={() => setIngredientsExpanded(!ingredientsExpanded)}
                      className="mt-2 text-[11px] text-ember-600 dark:text-ember-300 inline-flex items-center gap-1"
                    >
                      {ingredientsExpanded ? <><ChevronUp className="w-3 h-3" />收起</> : <><ChevronDown className="w-3 h-3" />展开 ({ingredients.length - 10} 更多)</>}
                    </button>
                  )}
                </div>
              )}
            </div>
          </aside>

          {/* Main grid */}
          <div className="space-y-4 min-w-0">
            <form
              onSubmit={event => {
                event.preventDefault();
                setCommittedQuery(query);
              }}
              className="ch-card p-3 flex flex-wrap items-center gap-2"
            >
              <div className="ch-input flex items-center gap-2 !py-2 flex-1 min-w-[200px]">
                <Search className="w-4 h-4 text-ink-400" />
                <input
                  value={query}
                  onChange={event => setQuery(event.target.value)}
                  placeholder="搜索菜名或原料"
                  className="w-full bg-transparent outline-none text-ink-900 dark:text-cream-100 placeholder-ink-400"
                />
                {query && (
                  <button type="button" onClick={() => { setQuery(''); setCommittedQuery(''); }} className="text-ink-400 hover:text-ink-600">
                    <X className="w-4 h-4" />
                  </button>
                )}
              </div>
              <select
                value={sort}
                onChange={event => setSort(event.target.value as RecipeSortKey)}
                className="ch-input !py-2 text-sm"
              >
                {SORT_OPTIONS.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => setHasStepImages(hasStepImages ? undefined : true)}
                className={`ch-btn !py-2 text-sm ${hasStepImages ? 'ch-btn-primary' : 'ch-btn-secondary'}`}
                title="仅看有步骤图的菜谱"
              >
                <Bookmark className="w-4 h-4" />
                图解
              </button>
              <button type="submit" className="ch-btn ch-btn-primary !py-2.5">搜索</button>
            </form>

            {error && (
              <div className="p-4 rounded-2xl bg-red-50 dark:bg-red-900/25 text-red-700 dark:text-red-300 border border-red-200/70 dark:border-red-800/50">
                {error}
              </div>
            )}

            {isLoading ? (
              <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-3 md:gap-4">
                {Array.from({ length: 12 }).map((_, i) => <SkeletonCard key={i} />)}
              </div>
            ) : items.length === 0 ? (
              <div className="text-center py-16 text-ink-500">
                <Utensils className="w-8 h-8 mx-auto mb-2 text-ink-300" />
                没有符合条件的菜谱
              </div>
            ) : (
              <>
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-ink-500 dark:text-ink-300">
                  <span>
                    已显示 {items.length} / {total} 道
                    {category ? ` · ${category}` : ''}
                    {difficulty ? ` · ${difficulty}` : ''}
                    {ingredient ? ` · 含 ${ingredient}` : ''}
                    {hasStepImages ? ' · 有步骤图' : ''}
                    {feedbackFilter ? ` · ${FEEDBACK_FILTERS.find(f => f.value === feedbackFilter)?.label}` : ''}
                  </span>
                  {hasMore && (
                    <button onClick={loadMore} disabled={isLoadingMore} className="text-ember-600 dark:text-ember-300 hover:underline disabled:opacity-50">
                      {isLoadingMore ? '加载中…' : '加载更多'}
                    </button>
                  )}
                </div>
                <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-3 md:gap-4">
                  {items.map(recipe => (
                    <RecipeCard
                      key={recipe.recipe_id}
                      recipe={recipe}
                      signals={signalsFor(recipe)}
                      onToggleFeedback={(signal, active) => handleToggleFeedback(recipe.recipe_id, signal, active)}
                    />
                  ))}
                </div>
                {hasMore && (
                  <div ref={sentinelRef} className="flex justify-center py-6">
                    {isLoadingMore && <Loader2 className="w-6 h-6 animate-spin text-ember-500" />}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
