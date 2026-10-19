import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  ChefHat,
  Clock,
  Flame,
  Heart,
  Loader2,
  ThumbsDown,
  ThumbsUp,
  Users,
} from 'lucide-react';
import { useAuth } from '../../contexts';
import {
  addRecipeFeedback,
  deleteRecipeReview,
  getRecipe,
  getRecipeReviews,
  getSimilarRecipes,
  upsertRecipeReview,
} from '../../services/api/diet';
import type { Recipe, RecipeLibraryItem, RecipeReviewSummary } from '../../types/diet';
import { cleanRecipeText } from '../../utils/recipeText';
import { resolveMediaUrl } from '../../utils';
import { BackButton, RecipeImage } from '../../components/common';

export default function RecipeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { token } = useAuth();
  const [recipe, setRecipe] = useState<Recipe | null>(null);
  const [servings, setServings] = useState(2);
  const [unitSystem, setUnitSystem] = useState<'metric' | 'imperial'>('metric');
  const [reviews, setReviews] = useState<RecipeReviewSummary | null>(null);
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [activeImage, setActiveImage] = useState<string | undefined>();
  const [similar, setSimilar] = useState<RecipeLibraryItem[]>([]);

  const loadRecipe = useCallback(async () => {
    if (!token || !id) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await getRecipe(token, id, {
        servings,
        unit_system: unitSystem,
      });
      setRecipe(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载菜谱失败');
    } finally {
      setIsLoading(false);
    }
  }, [token, id, servings, unitSystem]);

  const loadReviews = useCallback(async () => {
    if (!token || !id) return;
    try {
      setReviews(await getRecipeReviews(token, id));
    } catch {
      setReviews(null);
    }
  }, [token, id]);

  const loadSimilar = useCallback(async () => {
    if (!token || !id) return;
    try {
      const res = await getSimilarRecipes(token, id, 8);
      setSimilar(res.items);
    } catch {
      setSimilar([]);
    }
  }, [token, id]);

  useEffect(() => {
    loadRecipe();
  }, [loadRecipe]);

  useEffect(() => {
    loadReviews();
  }, [loadReviews]);

  useEffect(() => {
    loadSimilar();
  }, [loadSimilar]);

  useEffect(() => {
    setActiveImage(recipe?.image_url || undefined);
  }, [recipe?.recipe_id, recipe?.image_url]);

  const sendFeedback = async (signal: string) => {
    if (!token || !id) return;
    try {
      await addRecipeFeedback(token, id, { signal });
      setMessage('反馈已记录，会影响后续推荐排序');
    } catch (err) {
      setError(err instanceof Error ? err.message : '提交反馈失败');
    }
  };

  const submitReview = async () => {
    if (!token || !id) return;
    try {
      await upsertRecipeReview(token, id, { rating, comment: comment.trim() || undefined });
      setComment('');
      setMessage('评价已保存');
      await loadReviews();
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存评价失败');
    }
  };

  const removeReview = async () => {
    if (!token || !id) return;
    try {
      await deleteRecipeReview(token, id);
      setMessage('评价已删除');
      await loadReviews();
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除评价失败');
    }
  };

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-ember-500" />
      </div>
    );
  }

  if (error && !recipe) {
    return (
      <div className="flex-1 p-6">
        <div className="max-w-3xl mx-auto rounded-2xl bg-red-50 dark:bg-red-900/30 p-5 text-red-600 dark:text-red-300">
          {error}
        </div>
      </div>
    );
  }

  if (!recipe) {
    return null;
  }

  const gallery =
    recipe.images && recipe.images.length > 0
      ? recipe.images
      : recipe.image_url
        ? [{ url: recipe.image_url, alt: recipe.title }]
        : [];

  return (
    <div className="flex-1 overflow-auto p-4 md:p-6">
      <div className="max-w-5xl mx-auto space-y-6">
        <div>
          <BackButton fallbackTo="/recipes" label="返回菜谱" />
          <div className="flex flex-wrap items-start justify-between gap-4 mt-3">
            <div className="min-w-0 flex-1">
              <h1 className="ch-display text-[2.2rem] text-ink-900 dark:text-cream-50">
                {cleanRecipeText(recipe.title)}
              </h1>
              {cleanRecipeText(recipe.description || recipe.category) && (
                <p className="text-sm text-ink-500 dark:text-ink-300 mt-1">
                  {cleanRecipeText(recipe.description || recipe.category)}
                </p>
              )}
            </div>
            <Link
              to={`/recipes/${recipe.recipe_id}/cook?servings=${servings}`}
              className="ch-btn ch-btn-primary !py-2.5"
            >
              <ChefHat className="w-5 h-5" />
              开始烹饪
            </Link>
          </div>
        </div>

        <div className="space-y-3">
          <RecipeImage
            src={activeImage || recipe.image_url}
            title={recipe.title}
            alt={recipe.title}
            className="aspect-[16/7] rounded-3xl border border-cream-300/60 dark:border-white/10"
            loading="eager"
            width={1200}
          />
          {gallery.length > 1 && (
            <div className="scrollbar-hide flex gap-2 overflow-x-auto pb-1">
              {gallery.map(image => {
                const src = resolveMediaUrl(image.url, 240);
                const selected = (activeImage || recipe.image_url) === image.url;
                return (
                  <button
                    key={image.url}
                    type="button"
                    onClick={() => setActiveImage(image.url)}
                    className={`relative h-16 w-24 flex-none overflow-hidden rounded-xl border-2 transition-all ${
                      selected
                        ? 'border-ember-500 opacity-100'
                        : 'border-transparent opacity-65 hover:opacity-100'
                    }`}
                    title={image.alt || recipe.title}
                  >
                    {src ? (
                      <img
                        src={src}
                        alt={image.alt || recipe.title}
                        loading="lazy"
                        className="h-full w-full object-cover"
                      />
                    ) : null}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {message && (
          <div className="p-3 rounded-xl bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-300 text-sm">
            {message}
          </div>
        )}
        {error && (
          <div className="p-3 rounded-xl bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-300 text-sm">
            {error}
          </div>
        )}

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="ch-card p-4">
            <div className="flex items-center gap-2 text-gray-500 text-xs">
              <Users className="w-4 h-4" /> 份量
            </div>
            <div className="mt-2 flex items-center gap-2">
              <button
                onClick={() => setServings(value => Math.max(1, value - 1))}
                className="w-7 h-7 rounded-lg bg-gray-100 dark:bg-gray-800"
              >
                -
              </button>
              <span className="font-semibold text-gray-900 dark:text-gray-100">
                {servings} 人份
              </span>
              <button
                onClick={() => setServings(value => value + 1)}
                className="w-7 h-7 rounded-lg bg-gray-100 dark:bg-gray-800"
              >
                +
              </button>
            </div>
          </div>
          <div className="ch-card p-4">
            <div className="flex items-center gap-2 text-gray-500 text-xs">
              <Clock className="w-4 h-4" /> 耗时
            </div>
            <div className="mt-2 font-semibold text-gray-900 dark:text-gray-100">
              {recipe.total_minutes ? `${recipe.total_minutes} 分钟` : '未标注'}
            </div>
          </div>
          <div className="ch-card p-4">
            <div className="flex items-center gap-2 text-gray-500 text-xs">
              <Flame className="w-4 h-4" /> 热量
            </div>
            <div className="mt-2 font-semibold text-gray-900 dark:text-gray-100">
              {(recipe.nutrition?.totals?.calories ?? 0) > 0
                ? `${Math.round(recipe.nutrition?.totals?.calories ?? 0)} kcal`
                : '热量未知'}
            </div>
          </div>
          <div className="ch-card p-4">
            <div className="text-gray-500 text-xs">单位制</div>
            <select
              value={unitSystem}
              onChange={event =>
                setUnitSystem(event.target.value === 'imperial' ? 'imperial' : 'metric')
              }
              className="mt-2 w-full bg-transparent font-semibold text-gray-900 dark:text-gray-100 outline-none"
            >
              <option value="metric">公制</option>
              <option value="imperial">英制</option>
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <section className="lg:col-span-1 rounded-2xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 p-5">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">食材</h2>
            <ul className="mt-3 space-y-2">
              {recipe.ingredients.map((ingredient, index) => (
                <li
                  key={`${ingredient.name}-${index}`}
                  className="flex items-center justify-between gap-3 text-sm border-b border-gray-100 dark:border-gray-800 pb-2 last:border-0"
                >
                  <span className="text-gray-700 dark:text-gray-200">{ingredient.name}</span>
                  <span className="text-gray-500">
                    {ingredient.display || ingredient.unit || '适量'}
                  </span>
                </li>
              ))}
            </ul>
            {recipe.allergens.length > 0 && (
              <div className="mt-5">
                <h3 className="text-xs font-semibold text-red-600 dark:text-red-300">过敏原</h3>
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {recipe.allergens.map(allergen => (
                    <span
                      key={allergen}
                      className="text-xs px-2 py-0.5 rounded-full bg-red-50 text-red-600 dark:bg-red-900/30 dark:text-red-300"
                    >
                      {allergen}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {recipe.diet_tags.length > 0 && (
              <div className="mt-4">
                <h3 className="text-xs font-semibold text-green-600 dark:text-green-300">饮食标签</h3>
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {recipe.diet_tags.map(tag => (
                    <span
                      key={tag}
                      className="text-xs px-2 py-0.5 rounded-full bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-300"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            )}
            <div className="mt-5 text-xs text-gray-500">
              营养置信度：{recipe.nutrition?.confidence || 'low'} · 覆盖率{' '}
              {Math.round((recipe.nutrition?.coverage ?? 0) * 100)}%
            </div>
          </section>

          <section className="lg:col-span-2 rounded-2xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 p-5">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">步骤</h2>
            <ol className="mt-3 space-y-4">
              {recipe.steps.map(step => (
                <li key={step.index} className="flex gap-3">
                  <span className="flex-none w-7 h-7 rounded-full bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-200 text-sm font-semibold flex items-center justify-center">
                    {step.index}
                  </span>
                  <div>
                    <p className="text-sm text-gray-700 dark:text-gray-200 leading-relaxed">
                      {step.text}
                    </p>
                    {step.timer_seconds && (
                      <span className="inline-flex items-center gap-1 mt-1 text-xs text-amber-600 dark:text-amber-300">
                        <Clock className="w-3 h-3" />
                        {Math.round(step.timer_seconds / 60)} 分钟
                      </span>
                    )}
                    {step.image_url && (
                      <RecipeImage
                        src={step.image_url}
                        alt={`步骤 ${step.index}`}
                        className="mt-3 aspect-[16/9] max-h-56 w-full rounded-xl"
                        width={800}
                      />
                    )}
                  </div>
                </li>
              ))}
            </ol>
            {recipe.warnings.length > 0 && (
              <div className="mt-5 p-3 rounded-xl bg-amber-50 dark:bg-amber-900/20 text-xs text-amber-700 dark:text-amber-200 space-y-1">
                {recipe.warnings.map(warning => (
                  <div key={warning}>{warning}</div>
                ))}
              </div>
            )}
          </section>
        </div>

        {similar.length > 0 && (
          <section className="rounded-2xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 p-5">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">相似菜谱</h2>
              <span className="text-xs text-gray-400">基于食材重合度推荐</span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
              {similar.map(item => (
                <Link
                  key={item.recipe_id}
                  to={`/recipes/${item.recipe_id}`}
                  className="group flex flex-col overflow-hidden rounded-xl border border-gray-100 dark:border-gray-800 hover:border-ember-300 dark:hover:border-ember-700 transition-colors"
                >
                  <RecipeImage
                    src={item.image_url}
                    title={item.title}
                    alt={item.title}
                    className="aspect-[4/3]"
                    imageClassName="group-hover:scale-[1.04] transition-transform duration-500"
                    width={400}
                  />
                  <div className="p-2.5">
                    <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 line-clamp-1">
                      {cleanRecipeText(item.title)}
                    </h3>
                    <div className="flex items-center gap-2 mt-1 text-[11px] text-gray-500">
                      <span className="inline-flex items-center gap-0.5">
                        <Flame className="w-3 h-3" />
                        {item.calories ? `${item.calories} kcal` : '热量未知'}
                      </span>
                      <span className="inline-flex items-center gap-0.5">
                        <Clock className="w-3 h-3" />
                        {item.total_minutes ? `${item.total_minutes} 分` : '时间未知'}
                      </span>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          </section>
        )}

        <section className="rounded-2xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">反馈与评价</h2>
            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => sendFeedback('favorite')}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-pink-50 text-pink-600 dark:bg-pink-900/30 dark:text-pink-300 text-sm"
              >
                <Heart className="w-4 h-4" /> 收藏
              </button>
              <button
                onClick={() => sendFeedback('like')}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-300 text-sm"
              >
                <ThumbsUp className="w-4 h-4" /> 喜欢
              </button>
              <button
                onClick={() => sendFeedback('dislike')}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-red-50 text-red-600 dark:bg-red-900/30 dark:text-red-300 text-sm"
              >
                <ThumbsDown className="w-4 h-4" /> 不喜欢
              </button>
              <button
                onClick={() => sendFeedback('cooked')}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300 text-sm"
              >
                <ChefHat className="w-4 h-4" /> 做过了
              </button>
            </div>
          </div>

          <div className="mt-5 grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div>
              <div className="text-sm text-gray-500">
                平均评分 {reviews?.average_rating ?? 0} / 5 · {reviews?.review_count ?? 0} 条评价
              </div>
              <div className="mt-3 space-y-2">
                {reviews?.reviews?.length ? (
                  reviews.reviews.map(review => (
                    <div
                      key={review.id}
                      className="rounded-xl border border-gray-100 dark:border-gray-800 p-3 text-sm"
                    >
                      <div className="flex items-center justify-between text-xs text-gray-500">
                        <span>{'★'.repeat(review.rating)}{'☆'.repeat(5 - review.rating)}</span>
                        <span>{new Date(review.updated_at).toLocaleDateString('zh-CN')}</span>
                      </div>
                      {review.comment && (
                        <p className="mt-1 text-gray-700 dark:text-gray-200">{review.comment}</p>
                      )}
                    </div>
                  ))
                ) : (
                  <div className="text-sm text-gray-400">还没有评价，来写第一条吧。</div>
                )}
              </div>
            </div>
            <div className="rounded-xl bg-gray-50 dark:bg-gray-800/50 p-4">
              <label className="text-sm text-gray-600 dark:text-gray-300">
                评分
                <select
                  value={rating}
                  onChange={event => setRating(Number(event.target.value))}
                  className="mt-1 w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2"
                >
                  {[5, 4, 3, 2, 1].map(value => (
                    <option key={value} value={value}>
                      {value} 星
                    </option>
                  ))}
                </select>
              </label>
              <label className="block mt-3 text-sm text-gray-600 dark:text-gray-300">
                评论
                <textarea
                  value={comment}
                  onChange={event => setComment(event.target.value)}
                  rows={3}
                  maxLength={2000}
                  className="mt-1 w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2"
                  placeholder="这道菜做起来怎么样？"
                />
              </label>
              <div className="flex gap-2 mt-3">
                <button
                  onClick={submitReview}
                  className="px-4 py-2 rounded-lg bg-amber-500 text-white text-sm hover:bg-amber-600"
                >
                  保存评价
                </button>
                <button
                  onClick={removeReview}
                  className="px-4 py-2 rounded-lg border border-gray-200 dark:border-gray-700 text-sm text-gray-600 dark:text-gray-300"
                >
                  删除我的评价
                </button>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
