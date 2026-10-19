/**
 * Diet API service
 */

import { apiGet, apiPost, apiPut, apiPatch, apiDelete } from './client';
import { API_BASE } from '../../constants';
import type {
  DietPlan,
  DietPlanMeal,
  DietLog,
  DailySummary,
  WeeklySummary,
  DeviationAnalysis,
  UserFoodPreference,
  AddMealRequest,
  UpdateMealRequest,
  CreateLogRequest,
  LogFromTextRequest,
  MarkMealEatenRequest,
  UpdateLogRequest,
  UpdatePreferenceRequest,
  Recipe,
  RecipeReview,
  RecipeReviewSummary,
  PantryItem,
  ShoppingListItem,
  FamilyMember,
  FamilyMergedContext,
  TodayView,
  AdherenceSummary,
  NutritionEstimate,
  UnitConversion,
  FoodRecord,
  CookableRecipe,
  GeneratePlanResponse,
} from '../../types/diet';

const DIET_BASE = '/diet';

// ==================== Plan APIs ====================

/**
 * Get plan meals by week start date
 */
export async function getPlanByWeek(
  token: string,
  weekStartDate: string
): Promise<{ plan: DietPlan | null }> {
  const query = new URLSearchParams({ week_start_date: weekStartDate });
  return apiGet(`${DIET_BASE}/plans/by-week?${query.toString()}`, token);
}

// ==================== Meal APIs ====================

/**
 * Add meal to plan
 */
export async function addMealToPlan(
  token: string,
  data: AddMealRequest
): Promise<void> {
  await apiPost(`${DIET_BASE}/plans/meals`, data, token);
}

/**
 * Update meal
 */
export async function updateMeal(
  token: string,
  mealId: string,
  data: UpdateMealRequest
): Promise<void> {
  const response = await fetch(`${API_BASE}${DIET_BASE}/meals/${mealId}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    throw new Error('Failed to update meal');
  }
}

/**
 * Delete meal
 */
export async function deleteMeal(token: string, mealId: string): Promise<void> {
  await apiDelete(`${DIET_BASE}/meals/${mealId}`, token);
}

/**
 * Copy meal
 */
export async function copyMeal(
  token: string,
  mealId: string,
  targetDate: string,
  targetMealType?: string
): Promise<void> {
  await apiPost(`${DIET_BASE}/meals/${mealId}/copy`, {
    target_date: targetDate,
    target_meal_type: targetMealType,
  }, token);
}

/**
 * Mark meal as eaten
 */
export async function markMealEaten(
  token: string,
  mealId: string,
  data: MarkMealEatenRequest
): Promise<DietLog> {
  return apiPost<DietLog>(`${DIET_BASE}/meals/${mealId}/mark-eaten`, data, token);
}

// ==================== Log APIs ====================

/**
 * Get logs by date
 */
export async function getLogsByDate(
  token: string,
  logDate: string
): Promise<{ logs: DietLog[]; date: string }> {
  return apiGet(`${DIET_BASE}/logs?log_date=${logDate}`, token);
}

/**
 * Create log
 */
export async function createLog(token: string, data: CreateLogRequest): Promise<DietLog> {
  return apiPost<DietLog>(`${DIET_BASE}/logs`, data, token);
}

/**
 * Create log from text (AI parsing)
 */
export async function createLogFromText(
  token: string,
  data: LogFromTextRequest
): Promise<DietLog> {
  return apiPost<DietLog>(`${DIET_BASE}/logs/from-text`, data, token);
}

/**
 * Get log by ID
 */
export async function getLog(token: string, logId: string): Promise<DietLog> {
  return apiGet<DietLog>(`${DIET_BASE}/logs/${logId}`, token);
}

/**
 * Delete log
 */
export async function deleteLog(token: string, logId: string): Promise<void> {
  await apiDelete(`${DIET_BASE}/logs/${logId}`, token);
}

/**
 * Update log
 */
export async function updateLog(
  token: string,
  logId: string,
  data: UpdateLogRequest
): Promise<DietLog> {
  const response = await fetch(`${API_BASE}${DIET_BASE}/logs/${logId}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    throw new Error('Failed to update log');
  }

  return response.json();
}

// ==================== Analysis APIs ====================

/**
 * Get daily summary
 */
export async function getDailySummary(
  token: string,
  targetDate: string
): Promise<DailySummary> {
  return apiGet(`${DIET_BASE}/analysis/daily?target_date=${targetDate}`, token);
}

/**
 * Get weekly summary
 */
export async function getWeeklySummary(
  token: string,
  weekStartDate?: string
): Promise<WeeklySummary> {
  const query = weekStartDate ? `?week_start_date=${weekStartDate}` : '';
  return apiGet(`${DIET_BASE}/analysis/weekly${query}`, token);
}

/**
 * Get deviation analysis
 */
export async function getDeviationAnalysis(
  token: string,
  weekStartDate?: string
): Promise<DeviationAnalysis> {
  const query = weekStartDate ? `?week_start_date=${weekStartDate}` : '';
  return apiGet(`${DIET_BASE}/analysis/deviation${query}`, token);
}

// ==================== Preference APIs ====================

/**
 * Get user preferences
 */
export async function getPreferences(
  token: string
): Promise<{ preference: UserFoodPreference | null }> {
  return apiGet(`${DIET_BASE}/preferences`, token);
}

/**
 * Update user preferences
 */
export async function updatePreferences(
  token: string,
  data: UpdatePreferenceRequest
): Promise<{ preference: UserFoodPreference }> {
  const response = await fetch(`${API_BASE}${DIET_BASE}/preferences`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    throw new Error('Failed to update preferences');
  }

  return response.json();
}

// ==================== Enums API ====================

/**
 * Get enum values
 */
export async function getEnums(): Promise<{
  meal_types: Array<{ value: string; label: string }>;
  days_of_week: Array<{ value: number; label: string }>;
  plan_statuses: Array<{ value: string; label: string }>;
  data_sources: Array<{ value: string; label: string }>;
}> {
  return apiGet(`${DIET_BASE}/enums`);
}


// ==================== Structured profile APIs ====================

export async function getDietProfile(
  token: string
): Promise<UserFoodPreference & { exists?: boolean }> {
  return apiGet(`${DIET_BASE}/profile`, token);
}

export async function updateDietProfile(
  token: string,
  data: UpdatePreferenceRequest
): Promise<UserFoodPreference> {
  return apiPut(`${DIET_BASE}/profile`, data, token);
}

export async function getEffectiveConstraints(token: string): Promise<{
  constraints: string[];
  targets: Record<string, number>;
}> {
  return apiGet(`${DIET_BASE}/profile/effective-constraints`, token);
}

// ==================== Plan generation and execution APIs ====================

export async function generatePlan(
  token: string,
  data: { week_start_date?: string; include_family?: boolean } = {}
): Promise<GeneratePlanResponse> {
  return apiPost(`${DIET_BASE}/plans/generate`, data, token);
}

export async function replacePlanMeal(
  token: string,
  mealId: string
): Promise<DietPlanMeal> {
  return apiPost(`${DIET_BASE}/plans/meals/${mealId}/replace`, {}, token);
}

export async function skipPlanMeal(
  token: string,
  mealId: string
): Promise<DietPlanMeal> {
  return apiPost(`${DIET_BASE}/plans/meals/${mealId}/skip`, {}, token);
}

export async function getTodayView(
  token: string,
  targetDate?: string
): Promise<TodayView> {
  const query = targetDate ? `?target_date=${targetDate}` : '';
  return apiGet(`${DIET_BASE}/today${query}`, token);
}

export async function getAdherence(
  token: string,
  weekStartDate?: string
): Promise<AdherenceSummary> {
  const query = weekStartDate ? `?week_start_date=${weekStartDate}` : '';
  return apiGet(`${DIET_BASE}/analysis/adherence${query}`, token);
}

// ==================== Recipe APIs ====================

export interface RecipeSearchParams {
  q?: string;
  category?: string;
  diet_tag?: string;
  exclude_allergens?: string[];
  max_minutes?: number;
  limit?: number;
}

function withQuery(
  path: string,
  params: Record<string, string | number | boolean | undefined>
): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') {
      search.set(key, String(value));
    }
  });
  const query = search.toString();
  return query ? `${path}?${query}` : path;
}

export async function searchRecipes(
  token: string,
  params: RecipeSearchParams = {}
): Promise<{ items: Recipe[]; count: number }> {
  return apiGet(
    withQuery('/recipes/search', {
      q: params.q,
      category: params.category,
      diet_tag: params.diet_tag,
      exclude_allergens: params.exclude_allergens?.join(','),
      max_minutes: params.max_minutes,
      limit: params.limit,
    }),
    token
  );
}

export async function getRecipeRecommendations(
  token: string,
  limit = 10
): Promise<{ items: Recipe[]; count: number }> {
  return apiGet(withQuery('/recipes/recommendations', { limit }), token);
}

export async function getRecipe(
  token: string,
  recipeId: string,
  params: { servings?: number; unit_system?: 'metric' | 'imperial' } = {}
): Promise<Recipe> {
  return apiGet(
    withQuery(`/recipes/${recipeId}`, {
      servings: params.servings,
      unit_system: params.unit_system,
    }),
    token
  );
}

export async function addRecipeFeedback(
  token: string,
  recipeId: string,
  data: { signal: string; rating?: number; reason?: string }
): Promise<{ feedback: Record<string, unknown> }> {
  return apiPost(`/recipes/${recipeId}/feedback`, data, token);
}

export async function getRecipeReviews(
  token: string,
  recipeId: string
): Promise<RecipeReviewSummary> {
  return apiGet(`/recipes/${recipeId}/reviews`, token);
}

export async function upsertRecipeReview(
  token: string,
  recipeId: string,
  data: { rating: number; comment?: string }
): Promise<{ review: RecipeReview }> {
  return apiPut(`/recipes/${recipeId}/review`, data, token);
}

export async function deleteRecipeReview(
  token: string,
  recipeId: string
): Promise<{ message: string }> {
  return apiDelete(`/recipes/${recipeId}/review`, token);
}

// ==================== Pantry and shopping list APIs ====================

export async function listPantryItems(
  token: string
): Promise<{ items: PantryItem[]; count: number }> {
  return apiGet('/pantry/items', token);
}

export async function addPantryItem(
  token: string,
  data: Partial<Omit<PantryItem, 'id' | 'normalized_name'>> & { name: string }
): Promise<PantryItem> {
  return apiPost('/pantry/items', data, token);
}

export async function updatePantryItem(
  token: string,
  itemId: string,
  data: Partial<Omit<PantryItem, 'id' | 'normalized_name'>>
): Promise<PantryItem> {
  return apiPatch(`/pantry/items/${itemId}`, data, token);
}

export async function deletePantryItem(
  token: string,
  itemId: string
): Promise<{ message: string }> {
  return apiDelete(`/pantry/items/${itemId}`, token);
}

export async function getExpiringPantry(
  token: string,
  days = 3
): Promise<{ items: PantryItem[]; count: number; days: number }> {
  return apiGet(withQuery('/pantry/expiring', { days }), token);
}

export async function generateShoppingList(
  token: string,
  weekStartDate?: string
): Promise<{
  week_start_date: string;
  items: ShoppingListItem[];
  saved_by_pantry: number;
}> {
  return apiPost(
    '/pantry/shopping-list/generate',
    { week_start_date: weekStartDate },
    token
  );
}

export async function getShoppingList(
  token: string,
  weekStartDate?: string
): Promise<{ week_start_date: string; items: ShoppingListItem[]; count: number }> {
  return apiGet(
    withQuery('/pantry/shopping-list', { week_start_date: weekStartDate }),
    token
  );
}

export async function updateShoppingItem(
  token: string,
  itemId: string,
  data: { quantity?: number; unit?: string; checked?: boolean; category?: string }
): Promise<ShoppingListItem> {
  return apiPatch(`/pantry/shopping-list/${itemId}`, data, token);
}

export async function getCookableRecipes(
  token: string,
  limit = 20
): Promise<{ items: CookableRecipe[]; count: number }> {
  return apiGet(withQuery('/pantry/cookable', { limit }), token);
}

// ==================== Nutrition APIs ====================

export async function searchFoods(
  token: string,
  q = '',
  limit = 20
): Promise<{ items: FoodRecord[]; count: number }> {
  return apiGet(withQuery('/nutrition/foods', { q, limit }), token);
}

export async function convertNutrition(
  token: string,
  data: { quantity?: number; unit: string; food_name?: string }
): Promise<UnitConversion> {
  return apiPost('/nutrition/convert', data, token);
}

export async function estimateNutrition(
  token: string,
  items: Array<{
    food_name: string;
    quantity?: number;
    unit?: string;
    weight_g?: number;
  }>
): Promise<NutritionEstimate> {
  return apiPost('/nutrition/estimate', { items }, token);
}

// ==================== Family APIs ====================

export async function listFamilyMembers(token: string): Promise<{
  members: FamilyMember[];
  count: number;
  merged: FamilyMergedContext;
}> {
  return apiGet('/family/members', token);
}

export async function createFamilyMember(
  token: string,
  data: Partial<Omit<FamilyMember, 'id' | 'owner_user_id'>>
): Promise<FamilyMember> {
  return apiPost('/family/members', data, token);
}

export async function updateFamilyMember(
  token: string,
  memberId: string,
  data: Partial<Omit<FamilyMember, 'id' | 'owner_user_id'>>
): Promise<FamilyMember> {
  return apiPatch(`/family/members/${memberId}`, data, token);
}

export async function deleteFamilyMember(
  token: string,
  memberId: string
): Promise<{ message: string }> {
  return apiDelete(`/family/members/${memberId}`, token);
}
