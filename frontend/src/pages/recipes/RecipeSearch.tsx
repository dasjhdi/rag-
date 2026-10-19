import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Clock, Flame, Library, Loader2, Plus, Search } from 'lucide-react';
import { useAuth } from '../../contexts';
import { searchRecipes } from '../../services/api/diet';
import type { Recipe } from '../../types/diet';
import { cleanRecipeText } from '../../utils/recipeText';
import { BackButton, RecipeImage } from '../../components/common';
import { ImportRecipeModal } from '../../components/recipes/ImportRecipeModal';

const DIET_TAGS = [
  { value: '', label: '全部饮食标签' },
  { value: 'vegetarian', label: '素食' },
  { value: 'vegan', label: '纯素' },
  { value: 'gluten_free', label: '无麸质' },
];

export default function RecipeSearchPage() {
  const { token } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [query, setQuery] = useState('');
  const [dietTag, setDietTag] = useState('');
  const [maxMinutes, setMaxMinutes] = useState('');
  const [excludeAllergens, setExcludeAllergens] = useState('');
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isImportOpen, setIsImportOpen] = useState(false);

  useEffect(() => {
    if (searchParams.get('import') === '1') {
      setIsImportOpen(true);
      const next = new URLSearchParams(searchParams);
      next.delete('import');
      setSearchParams(next, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  const loadRecipes = useCallback(async () => {
    if (!token) return;
    setIsLoading(true);
    setError(null);
    try {
      const result = await searchRecipes(token, {
        q: query.trim() || undefined,
        diet_tag: dietTag || undefined,
        max_minutes: maxMinutes ? Number(maxMinutes) : undefined,
        exclude_allergens: excludeAllergens
          .split(',')
          .map(item => item.trim())
          .filter(Boolean),
        limit: 100,
      });
      setRecipes(result.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载菜谱失败');
    } finally {
      setIsLoading(false);
    }
  }, [token, query, dietTag, maxMinutes, excludeAllergens]);

  useEffect(() => {
    loadRecipes();
  }, [loadRecipes]);

  return (
    <div className="flex-1 overflow-auto p-4 md:p-6">
      <div className="max-w-6xl mx-auto space-y-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <BackButton fallbackTo="/diet" label="返回上级" />
            <div className="ch-eyebrow mt-4">Recipe Library</div>
            <h1 className="ch-display text-[2rem] text-ink-900 dark:text-cream-50 mt-1">
              菜谱搜索
            </h1>
            <p className="text-sm text-ink-500 dark:text-ink-300 mt-1.5">
              按关键词、饮食标签、耗时和过敏原筛选结构化菜谱
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Link to="/recipes/library" className="ch-btn ch-btn-secondary">
              <Library className="w-4 h-4" />
              菜谱图鉴
            </Link>
            <button
              type="button"
              onClick={() => setIsImportOpen(true)}
              className="ch-btn ch-btn-primary"
            >
              <Plus className="w-4 h-4" />
              导入菜谱
            </button>
            <Link to="/diet/profile" className="ch-btn ch-btn-secondary">
              饮食档案
            </Link>
          </div>
        </div>

        <form
          onSubmit={event => {
            event.preventDefault();
            loadRecipes();
          }}
          className="ch-card p-5"
        >
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <label className="md:col-span-2 block">
              <span className="ch-label">关键词</span>
              <div className="ch-input flex items-center gap-2 !py-2.5">
                <Search className="w-4 h-4 text-ink-400" />
                <input
                  value={query}
                  onChange={event => setQuery(event.target.value)}
                  placeholder="例如：番茄、鸡胸肉"
                  className="w-full bg-transparent outline-none text-ink-900 dark:text-cream-100 placeholder-ink-400"
                />
              </div>
            </label>
            <label className="block">
              <span className="ch-label">饮食标签</span>
              <select
                value={dietTag}
                onChange={event => setDietTag(event.target.value)}
                className="ch-input !py-2.5"
              >
                {DIET_TAGS.map(item => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="ch-label">最长耗时（分钟）</span>
              <input
                type="number"
                min={1}
                value={maxMinutes}
                onChange={event => setMaxMinutes(event.target.value)}
                placeholder="不限"
                className="ch-input !py-2.5"
              />
            </label>
            <label className="md:col-span-3 block">
              <span className="ch-label">排除过敏原 / 食材（逗号分隔）</span>
              <input
                value={excludeAllergens}
                onChange={event => setExcludeAllergens(event.target.value)}
                placeholder="例如：花生, 牛奶"
                className="ch-input !py-2.5"
              />
            </label>
            <div className="flex items-end">
              <button type="submit" className="ch-btn ch-btn-primary w-full !py-2.5">
                搜索
              </button>
            </div>
          </div>
        </form>

        {error && (
          <div className="p-4 rounded-2xl bg-red-50 dark:bg-red-900/25 text-red-700 dark:text-red-300 border border-red-200/70 dark:border-red-800/50">
            {error}
          </div>
        )}

        {isLoading ? (
          <div className="flex justify-center py-16">
            <Loader2 className="w-7 h-7 animate-spin text-ember-500" />
          </div>
        ) : recipes.length === 0 ? (
          <div className="text-center py-16 text-ink-500">
            没有找到符合条件的菜谱
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {recipes.map(recipe => (
              <Link
                key={recipe.recipe_id}
                to={`/recipes/${recipe.recipe_id}`}
                className="ch-card ch-card-hover group flex flex-col overflow-hidden !p-0"
              >
                <div className="relative">
                  <RecipeImage
                    src={recipe.image_url}
                    title={recipe.title}
                    alt={recipe.title}
                    className="aspect-[16/10]"
                    imageClassName="transition-transform duration-500 group-hover:scale-[1.03]"
                    width={640}
                  />
                  {recipe.images && recipe.images.length > 1 ? (
                    <span className="absolute bottom-2 right-2 rounded-full bg-ink-900/65 px-2 py-0.5 text-[10px] font-medium text-white backdrop-blur-sm">
                      {recipe.images.length} 张
                    </span>
                  ) : null}
                </div>
                <div className="flex flex-1 flex-col p-5">
                  <div className="flex items-start justify-between gap-3">
                    <h2 className="text-lg font-semibold text-ink-900 dark:text-cream-100">
                      {cleanRecipeText(recipe.title)}
                    </h2>
                    <span className="text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-200">
                      {recipe.difficulty || '家常'}
                    </span>
                  </div>
                  {cleanRecipeText(recipe.description || recipe.category) && (
                    <p className="text-sm text-ink-500 dark:text-ink-300 mt-1 line-clamp-2">
                      {cleanRecipeText(recipe.description || recipe.category)}
                    </p>
                  )}
                  <div className="flex flex-wrap gap-3 mt-4 text-xs text-ink-500 dark:text-ink-300">
                    <span className="inline-flex items-center gap-1">
                      <Flame className="w-3.5 h-3.5" />
                      {(recipe.nutrition?.totals?.calories ?? 0) > 0
                        ? `${Math.round(recipe.nutrition?.totals?.calories ?? 0)} kcal`
                        : '热量未知'}
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <Clock className="w-3.5 h-3.5" />
                      {recipe.total_minutes ? `${recipe.total_minutes} 分钟` : '时间未知'}
                    </span>
                    <span>{recipe.ingredients.length} 种食材</span>
                  </div>
                  <div className="flex flex-wrap gap-1.5 mt-3">
                    {recipe.diet_tags.slice(0, 4).map(tag => (
                      <span
                        key={tag}
                        className="text-[11px] px-2 py-0.5 rounded-full bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-300"
                      >
                        {tag}
                      </span>
                    ))}
                    {recipe.allergens.map(allergen => (
                      <span
                        key={allergen}
                        className="text-[11px] px-2 py-0.5 rounded-full bg-red-50 text-red-600 dark:bg-red-900/30 dark:text-red-300"
                      >
                        含 {allergen}
                      </span>
                    ))}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>

      <ImportRecipeModal
        open={isImportOpen}
        onClose={() => setIsImportOpen(false)}
        onOpenRecipe={recipeId => {
          setIsImportOpen(false);
          navigate(`/recipes/${recipeId}`);
        }}
        onImported={() => {
          void loadRecipes();
        }}
      />
    </div>
  );
}
