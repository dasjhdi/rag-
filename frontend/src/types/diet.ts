/**
 * Diet types for frontend
 */

import type { ImageData } from './api';

export interface Dish {
  name: string;
  recipe_id?: string;
  servings?: number;
  ingredients?: Ingredient[];
  weight_g?: number;
  unit?: string;
  calories?: number;
  protein?: number;
  fat?: number;
  carbs?: number;
  nutrition_confidence?: string;
  total_minutes?: number;
}

export interface DietPlanMeal {
  id: string;
  plan_date: string;
  meal_type: string;
  dishes?: Dish[];
  total_calories?: number;
  total_protein?: number;
  total_fat?: number;
  total_carbs?: number;
  notes?: string;
  status?: 'planned' | 'eaten' | 'skipped' | string;
  locked?: boolean;
  generation_batch_id?: string;
  servings?: number;
}

export interface DietPlan {
  user_id: string;
  week_start_date: string;
  meals?: DietPlanMeal[];
}

export interface FoodItem {
  id: string;
  log_id: string;
  food_name: string;
  weight_g?: number;
  unit?: string;
  calories?: number;
  protein?: number;
  fat?: number;
  carbs?: number;
  source: string;
  confidence_score?: number;
  created_at: string;
}

export interface DietLog {
  id: string;
  user_id: string;
  log_date: string;
  meal_type: string;
  plan_meal_id?: string;
  total_calories?: number;
  total_protein?: number;
  total_fat?: number;
  total_carbs?: number;
  notes?: string;
  items?: FoodItem[];
  created_at: string;
  updated_at: string;
}

export interface DailySummary {
  date: string;
  total_calories: number;
  total_protein: number;
  total_fat: number;
  total_carbs: number;
  meals_logged: string[];
  log_count: number;
  nutrition_coverage?: NutritionCoverage;
}

export interface WeeklySummary {
  week_start_date: string;
  week_end_date: string;
  daily_data: Record<string, {
    calories: number;
    protein: number;
    fat: number;
    carbs: number;
    meals: string[];
  }>;
  total_calories: number;
  total_protein: number;
  total_fat: number;
  total_carbs: number;
  avg_daily_calories: number;
}

export interface DeviationAnalysis {
  has_plan: boolean;
  message?: string;
  week_start_date?: string;
  total_plan_calories?: number;
  total_actual_calories?: number;
  total_deviation?: number;
  total_deviation_pct?: number;
  meal_deviations?: Array<{
    meal_key: string;
    plan_calories: number;
    actual_calories: number;
    calories_deviation: number;
    calories_deviation_pct: number;
  }>;
  execution_rate?: number;
}

export interface UserFoodPreference {
  id: string;
  user_id: string;
  common_foods?: Array<{ name: string; frequency?: number; avg_weight?: number }>;
  avoided_foods?: string[];
  allergies?: string[];
  allergy_severity?: Record<string, string>;
  dietary_restrictions?: string[];
  favorite_cuisines?: string[];
  preferred_foods?: string[];
  health_conditions?: string[];
  calorie_goal?: number;
  protein_goal?: number;
  fat_goal?: number;
  carbs_goal?: number;
  fiber_goal?: number;
  sodium_goal?: number;
  meals_per_day?: number;
  cooking_skill?: string;
  max_cook_minutes?: number;
  budget_level?: string;
  household_size?: number;
  unit_system?: string;
  spice_level?: string;
  version?: number;
  diet_tags?: string[];
  avg_daily_calories_min?: number;
  avg_daily_calories_max?: number;
  deviation_patterns?: Array<{ meal_type: string; deviation_rate?: number }>;
  stats?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface AddMealRequest {
  plan_date: string;
  meal_type: string;
  dishes?: Dish[];
  notes?: string;
}

export interface UpdateMealRequest {
  dishes?: Dish[];
  notes?: string;
}

export interface CreateLogRequest {
  log_date: string;
  meal_type: string;
  items?: Array<{
    food_name: string;
    weight_g?: number;
    unit?: string;
    calories?: number;
    protein?: number;
    fat?: number;
    carbs?: number;
  }>;
  plan_meal_id?: string;
  notes?: string;
}

export interface UpdateLogRequest {
  log_date?: string;
  meal_type?: string;
  items?: Array<{
    food_name: string;
    weight_g?: number;
    unit?: string;
    calories?: number;
    protein?: number;
    fat?: number;
    carbs?: number;
  }>;
  notes?: string;
}

export interface LogFromTextRequest {
  text: string;
  images?: ImageData[];
  log_date?: string;
  meal_type?: string;
}

export interface MarkMealEatenRequest {
  log_date?: string;
}

export interface UpdatePreferenceRequest {
  allergy_severity?: Record<string, string>;
  dietary_restrictions?: string[];
  health_conditions?: string[];
  allergies?: string[];
  favorite_cuisines?: string[];
  avoided_foods?: string[];
  disliked_foods?: string[];
  preferred_foods?: string[];
  calorie_goal?: number;
  protein_goal?: number;
  fat_goal?: number;
  carbs_goal?: number;
  fiber_goal?: number;
  sodium_goal?: number;
  meals_per_day?: number;
  cooking_skill?: string;
  max_cook_minutes?: number;
  budget_level?: string;
  household_size?: number;
  unit_system?: string;
  spice_level?: string;
}

export interface Ingredient {
  name: string;
  raw_name?: string;
  quantity?: number | null;
  unit?: string;
  display?: string;
  scalable?: boolean;
  raw?: string;
}

export interface RecipeStep {
  index: number;
  text: string;
  timer_seconds?: number | null;
  image_url?: string | null;
}

export interface RecipeImage {
  url: string;
  alt?: string;
}

export interface NutritionTotals {
  calories: number;
  protein: number;
  fat: number;
  carbs: number;
}

export interface Recipe {
  recipe_id: string;
  title: string;
  description?: string;
  category?: string;
  difficulty?: string;
  source?: string;
  servings: number;
  base_servings: number;
  ingredients: Ingredient[];
  steps: RecipeStep[];
  allergens: string[];
  diet_tags: string[];
  nutrition: {
    totals: NutritionTotals;
    coverage: number;
    confidence: string;
    source?: string;
  };
  total_minutes?: number | null;
  warnings: string[];
  raw_content: string;
  unit_system: string;
  image_url?: string | null;
  images?: RecipeImage[];
}

/** Lightweight recipe card used by the library browser. */
export interface RecipeLibraryItem {
  recipe_id: string;
  title: string;
  description?: string;
  category?: string;
  difficulty?: string;
  total_minutes?: number | null;
  calories?: number | null;
  image_url?: string | null;
  images_count: number;
  ingredients_count: number;
  main_ingredients: string[];
  has_step_images: boolean;
  diet_tags: string[];
  allergens: string[];
  feedback: string[]; // subset of want/favorite/cooked
}

export interface RecipeFacet {
  value: string;
  label: string;
  count: number;
}

export interface RecipeLibraryResponse {
  items: RecipeLibraryItem[];
  total: number;
  offset: number;
  limit: number;
  categories: RecipeFacet[];
  difficulties: RecipeFacet[];
  ingredients: RecipeFacet[];
  minutes_buckets: RecipeFacet[];
}

export type RecipeSortKey = 'name' | 'minutes' | 'calories' | 'ingredients';
export type RecipeFeedbackFilter = 'want' | 'favorite' | 'cooked';

export interface RecipeImportResult {
  document: {
    id: string;
    dish_name: string;
    category: string;
    difficulty: string;
    image_url?: string | null;
  };
  recipe: Recipe;
  source_url?: string;
  imported_from: 'url' | 'image';
}

export interface NutritionCoverage {
  coverage: number;
  known_items: number;
  total_items: number;
  confidence: string;
}

export interface NutritionEstimateItem {
  food_name: string;
  weight_g?: number | null;
  unit?: string | null;
  calories?: number;
  protein?: number;
  fat?: number;
  carbs?: number;
  nutrition_source?: string | null;
  nutrition_confidence?: string;
  nutrition_reason?: string;
}

export interface NutritionEstimate {
  items: NutritionEstimateItem[];
  totals: NutritionTotals;
  coverage: number;
  confidence: string;
  known_items: number;
  total_items: number;
  known_weight_g: number;
}

export interface UnitConversion {
  grams?: number | null;
  milliliters?: number;
  confidence: string;
  reason: string;
  known_unit: boolean;
}

export interface PantryItem {
  id: string;
  name: string;
  normalized_name: string;
  quantity: number;
  unit: string;
  category?: string;
  expires_on?: string | null;
  location?: string;
  notes?: string;
}

export interface ShoppingListItem {
  id: string;
  week_start_date: string;
  name: string;
  normalized_name: string;
  quantity: number;
  unit: string;
  checked: boolean;
  source: string;
  recipe_ids: string[];
}

export interface FamilyMember {
  id: string;
  owner_user_id: string;
  name: string;
  relation?: string;
  birth_year?: number;
  sex?: string;
  allergies: string[];
  dietary_restrictions: string[];
  disliked_foods: string[];
  calorie_goal?: number;
  servings_factor: number;
  notes?: string;
}

export interface RecipeReview {
  id: string;
  user_id: string;
  recipe_id: string;
  rating: number;
  comment?: string;
  created_at: string;
  updated_at: string;
}

export interface RecipeReviewSummary {
  recipe_id: string;
  average_rating: number;
  review_count: number;
  reviews: RecipeReview[];
}

export interface TodayMeal extends DietPlanMeal {
  effective_status: 'planned' | 'eaten' | 'skipped' | string;
}

export interface TodayView {
  date: string;
  has_plan: boolean;
  meals: TodayMeal[];
  next_meal: TodayMeal | null;
  eaten_meals: number;
  skipped_meals: number;
}

export interface AdherenceSummary {
  week_start_date: string;
  planned_meals: number;
  eaten_meals: number;
  skipped_meals: number;
  missed_meals: number;
  execution_rate: number;
  streak_days: number;
  meals: TodayMeal[];
  suggestion: string;
}

export interface FoodRecord {
  name: string;
  aliases: string[];
  per_100g: NutritionTotals;
  default_unit: string;
  unit_grams: Record<string, number>;
}

export interface CookableRecipe {
  recipe_id: string;
  title: string;
  coverage: number;
  matched: string[];
  missing: string[];
  total_minutes?: number | null;
}

export interface FamilyMergedContext {
  allergies: string[];
  dietary_restrictions: string[];
  avoided_foods: string[];
  calorie_goal: number | null;
  household_size: number;
  family_member_count: number;
}

export interface GeneratePlanDiagnostics {
  candidate_count?: number;
  target_calories_per_day?: number;
  target_protein_per_day?: number;
  total_calories?: number;
  deviation_pct?: number;
  warnings?: string[];
  error?: string;
  message?: string;
}

export interface GeneratePlanResponse {
  plan: DietPlan | null;
  diagnostics: GeneratePlanDiagnostics;
}
