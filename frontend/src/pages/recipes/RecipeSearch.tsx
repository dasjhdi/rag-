import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Clock, Flame, Loader2, Search } from 'lucide-react';
import { useAuth } from '../../contexts';
import { searchRecipes } from '../../services/api/diet';
import type { Recipe } from '../../types/diet';

const DIET_TAGS = [
  { value: '', label: '全部饮食标签' },
  { value: 'vegetarian', label: '素食' },
  { value: 'vegan', label: '纯素' },
  { value: 'gluten_free', label: '无麸质' },
];

export default function RecipeSearchPage() {
  const { token } = useAuth();
  const [query, setQuery] = useState('');
  const [dietTag, setDietTag] = useState('');
  const [maxMinutes, setMaxMinutes] = useState('');
  const [excludeAllergens, setExcludeAllergens] = useState('');
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
        limit: 50,
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
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <Link
              to="/diet"
              className="inline-flex items-center gap-1 text-sm text-amber-600 dark:text-amber-300 hover:underline"
            >
              <ArrowLeft className="w-4 h-4" />
              返回饮食管理
            </Link>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mt-2">
              菜谱搜索
            </h1>
            <p className="text-sm text-gray-500 mt-1">
              按关键词、饮食标签、耗时和过敏原筛选结构化菜谱
            </p>
          </div>
          <Link
            to="/diet/profile"
            className="px-4 py-2 rounded-xl bg-amber-500 text-white text-sm hover:bg-amber-600"
          >
            饮食档案
          </Link>
        </div>

        <form
          onSubmit={event => {
            event.preventDefault();
            loadRecipes();
          }}
          className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-5 shadow-sm"
        >
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <label className="md:col-span-2 text-sm text-gray-600 dark:text-gray-300">
              关键词
              <div className="mt-1 flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-700 px-3 py-2">
                <Search className="w-4 h-4 text-gray-400" />
                <input
                  value={query}
                  onChange={event => setQuery(event.target.value)}
                  placeholder="例如：番茄、鸡胸肉"
                  className="w-full bg-transparent outline-none text-gray-900 dark:text-gray-100"
                />
              </div>
            </label>
            <label className="text-sm text-gray-600 dark:text-gray-300">
              饮食标签
              <select
                value={dietTag}
                onChange={event => setDietTag(event.target.value)}
                className="mt-1 w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-gray-900 dark:text-gray-100"
              >
                {DIET_TAGS.map(item => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm text-gray-600 dark:text-gray-300">
              最长耗时（分钟）
              <input
                type="number"
                min={1}
                value={maxMinutes}
                onChange={event => setMaxMinutes(event.target.value)}
                placeholder="不限"
                className="mt-1 w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-gray-900 dark:text-gray-100"
              />
            </label>
            <label className="md:col-span-3 text-sm text-gray-600 dark:text-gray-300">
              排除过敏原/食材（逗号分隔）
              <input
                value={excludeAllergens}
                onChange={event => setExcludeAllergens(event.target.value)}
                placeholder="例如：花生, 牛奶"
                className="mt-1 w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-gray-900 dark:text-gray-100"
              />
            </label>
            <div className="flex items-end">
              <button
                type="submit"
                className="w-full px-4 py-2 rounded-xl bg-amber-500 text-white text-sm hover:bg-amber-600"
              >
                搜索
              </button>
            </div>
          </div>
        </form>

        {error && (
          <div className="p-4 rounded-xl bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-300">
            {error}
          </div>
        )}

        {isLoading ? (
          <div className="flex justify-center py-16">
            <Loader2 className="w-8 h-8 animate-spin text-amber-500" />
          </div>
        ) : recipes.length === 0 ? (
          <div className="text-center py-16 text-gray-500">
            没有找到符合条件的菜谱
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {recipes.map(recipe => (
              <Link
                key={recipe.recipe_id}
                to={`/recipes/${recipe.recipe_id}`}
                className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-5 shadow-sm hover:shadow-md hover:-translate-y-0.5 transition-all"
              >
                <div className="flex items-start justify-between gap-3">
                  <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                    {recipe.title}
                  </h2>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-200">
                    {recipe.difficulty || '家常'}
                  </span>
                </div>
                <p className="text-sm text-gray-500 mt-1 line-clamp-2">
                  {recipe.description || recipe.category || '结构化菜谱'}
                </p>
                <div className="flex flex-wrap gap-3 mt-4 text-xs text-gray-500">
                  <span className="inline-flex items-center gap-1">
                    <Flame className="w-3.5 h-3.5" />
                    {Math.round(recipe.nutrition?.totals?.calories ?? 0)} kcal
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
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
