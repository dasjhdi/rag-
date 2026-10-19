import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowLeft,
  Loader2,
  Plus,
  ShieldAlert,
  Trash2,
  Users,
} from 'lucide-react';
import { useAuth } from '../../contexts';
import {
  createFamilyMember,
  deleteFamilyMember,
  getDietProfile,
  getEffectiveConstraints,
  listFamilyMembers,
  updateDietProfile,
} from '../../services/api/diet';
import type {
  FamilyMember,
  FamilyMergedContext,
  UpdatePreferenceRequest,
  UserFoodPreference,
} from '../../types/diet';

interface ProfileForm {
  allergies: string;
  dietary_restrictions: string;
  health_conditions: string;
  avoided_foods: string;
  preferred_foods: string;
  favorite_cuisines: string;
  calorie_goal: string;
  protein_goal: string;
  fat_goal: string;
  carbs_goal: string;
  fiber_goal: string;
  sodium_goal: string;
  meals_per_day: string;
  cooking_skill: string;
  max_cook_minutes: string;
  budget_level: string;
  household_size: string;
  unit_system: string;
  spice_level: string;
}

const EMPTY_FORM: ProfileForm = {
  allergies: '',
  dietary_restrictions: '',
  health_conditions: '',
  avoided_foods: '',
  preferred_foods: '',
  favorite_cuisines: '',
  calorie_goal: '2000',
  protein_goal: '90',
  fat_goal: '67',
  carbs_goal: '250',
  fiber_goal: '25',
  sodium_goal: '2000',
  meals_per_day: '3',
  cooking_skill: 'intermediate',
  max_cook_minutes: '60',
  budget_level: 'medium',
  household_size: '1',
  unit_system: 'metric',
  spice_level: 'medium',
};

function listToText(values?: string[]): string {
  return (values || []).join(', ');
}

function textToList(value: string): string[] {
  return value
    .split(',')
    .map(item => item.trim())
    .filter(Boolean);
}

function numberOrUndefined(value: string): number | undefined {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

export default function DietProfilePage() {
  const { token } = useAuth();
  const [form, setForm] = useState<ProfileForm>(EMPTY_FORM);
  const [constraints, setConstraints] = useState<string[]>([]);
  const [members, setMembers] = useState<FamilyMember[]>([]);
  const [merged, setMerged] = useState<FamilyMergedContext | null>(null);
  const [memberName, setMemberName] = useState('');
  const [memberRelation, setMemberRelation] = useState('');
  const [memberAllergies, setMemberAllergies] = useState('');
  const [memberCalories, setMemberCalories] = useState('2000');
  const [memberFactor, setMemberFactor] = useState('1');
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const applyProfile = (profile: UserFoodPreference) => {
    setForm({
      allergies: listToText(profile.allergies),
      dietary_restrictions: listToText(profile.dietary_restrictions),
      health_conditions: listToText(profile.health_conditions),
      avoided_foods: listToText(profile.avoided_foods),
      preferred_foods: listToText(profile.preferred_foods),
      favorite_cuisines: listToText(profile.favorite_cuisines),
      calorie_goal: String(profile.calorie_goal ?? 2000),
      protein_goal: String(profile.protein_goal ?? 90),
      fat_goal: String(profile.fat_goal ?? 67),
      carbs_goal: String(profile.carbs_goal ?? 250),
      fiber_goal: String(profile.fiber_goal ?? 25),
      sodium_goal: String(profile.sodium_goal ?? 2000),
      meals_per_day: String(profile.meals_per_day ?? 3),
      cooking_skill: profile.cooking_skill ?? 'intermediate',
      max_cook_minutes: String(profile.max_cook_minutes ?? 60),
      budget_level: profile.budget_level ?? 'medium',
      household_size: String(profile.household_size ?? 1),
      unit_system: profile.unit_system ?? 'metric',
      spice_level: profile.spice_level ?? 'medium',
    });
  };

  const loadProfile = useCallback(async () => {
    if (!token) return;
    setIsLoading(true);
    setError(null);
    try {
      const [profile, effective, family] = await Promise.all([
        getDietProfile(token),
        getEffectiveConstraints(token),
        listFamilyMembers(token),
      ]);
      applyProfile(profile);
      setConstraints(effective.constraints);
      setMembers(family.members);
      setMerged(family.merged);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载饮食档案失败');
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  useEffect(() => {
    loadProfile();
  }, [loadProfile]);

  const updateField = (key: keyof ProfileForm, value: string) => {
    setForm(prev => ({ ...prev, [key]: value }));
  };

  const saveProfile = async () => {
    if (!token) return;
    setIsSaving(true);
    setError(null);
    setMessage(null);
    const payload: UpdatePreferenceRequest = {
      allergies: textToList(form.allergies),
      dietary_restrictions: textToList(form.dietary_restrictions),
      health_conditions: textToList(form.health_conditions),
      avoided_foods: textToList(form.avoided_foods),
      preferred_foods: textToList(form.preferred_foods),
      favorite_cuisines: textToList(form.favorite_cuisines),
      calorie_goal: numberOrUndefined(form.calorie_goal),
      protein_goal: numberOrUndefined(form.protein_goal),
      fat_goal: numberOrUndefined(form.fat_goal),
      carbs_goal: numberOrUndefined(form.carbs_goal),
      fiber_goal: numberOrUndefined(form.fiber_goal),
      sodium_goal: numberOrUndefined(form.sodium_goal),
      meals_per_day: numberOrUndefined(form.meals_per_day),
      cooking_skill: form.cooking_skill,
      max_cook_minutes: numberOrUndefined(form.max_cook_minutes),
      budget_level: form.budget_level,
      household_size: numberOrUndefined(form.household_size),
      unit_system: form.unit_system,
      spice_level: form.spice_level,
    };
    try {
      const updated = await updateDietProfile(token, payload);
      applyProfile(updated);
      const effective = await getEffectiveConstraints(token);
      setConstraints(effective.constraints);
      setMessage('饮食档案已保存');
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存饮食档案失败');
    } finally {
      setIsSaving(false);
    }
  };

  const addMember = async () => {
    if (!token || !memberName.trim()) return;
    try {
      await createFamilyMember(token, {
        name: memberName.trim(),
        relation: memberRelation.trim() || undefined,
        allergies: textToList(memberAllergies),
        calorie_goal: numberOrUndefined(memberCalories),
        servings_factor: numberOrUndefined(memberFactor) ?? 1,
      });
      setMemberName('');
      setMemberRelation('');
      setMemberAllergies('');
      setMemberCalories('2000');
      setMemberFactor('1');
      const family = await listFamilyMembers(token);
      setMembers(family.members);
      setMerged(family.merged);
      setMessage('家庭成员已添加');
    } catch (err) {
      setError(err instanceof Error ? err.message : '添加家庭成员失败');
    }
  };

  const removeMember = async (memberId: string) => {
    if (!token) return;
    try {
      await deleteFamilyMember(token, memberId);
      const family = await listFamilyMembers(token);
      setMembers(family.members);
      setMerged(family.merged);
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除家庭成员失败');
    }
  };

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-amber-500" />
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-auto p-4 md:p-6">
      <div className="max-w-5xl mx-auto space-y-6">
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
              饮食档案
            </h1>
            <p className="text-sm text-gray-500 mt-1">
              过敏原、饮食限制和营养目标会进入计划生成与对话约束推理
            </p>
          </div>
          <div className="flex gap-2">
            <Link
              to="/diet/pantry"
              className="px-4 py-2 rounded-xl border border-gray-200 dark:border-gray-700 text-sm"
            >
              库存与购物清单
            </Link>
            <Link
              to="/recipes"
              className="px-4 py-2 rounded-xl bg-amber-500 text-white text-sm"
            >
              搜索菜谱
            </Link>
          </div>
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

        <section className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-5">
          <div className="flex items-center gap-2">
            <ShieldAlert className="w-5 h-5 text-red-500" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              有效约束
            </h2>
          </div>
          <div className="flex flex-wrap gap-2 mt-3">
            {constraints.length ? (
              constraints.map(constraint => (
                <span
                  key={constraint}
                  className="px-3 py-1 rounded-full bg-red-50 text-red-600 dark:bg-red-900/30 dark:text-red-300 text-sm"
                >
                  {constraint}
                </span>
              ))
            ) : (
              <span className="text-sm text-gray-400">暂无硬约束</span>
            )}
          </div>
        </section>

        <section className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-5">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">基础档案</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
            {([
              ['allergies', '过敏原（逗号分隔）', '花生, 牛奶'],
              ['dietary_restrictions', '饮食限制', 'vegetarian, gluten_free'],
              ['health_conditions', '健康状况', '高血压, 糖尿病'],
              ['avoided_foods', '不吃的食物', '香菜, 芹菜'],
              ['preferred_foods', '偏好食物', '番茄, 鸡胸肉'],
              ['favorite_cuisines', '偏好菜系', '川菜, 粤菜'],
            ] as Array<[keyof ProfileForm, string, string]>).map(([key, label, placeholder]) => (
              <label key={key} className="text-sm text-gray-600 dark:text-gray-300">
                {label}
                <input
                  value={form[key]}
                  onChange={event => updateField(key, event.target.value)}
                  placeholder={placeholder}
                  className="mt-1 w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-gray-900 dark:text-gray-100"
                />
              </label>
            ))}
          </div>

          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-200 mt-6">
            每日营养目标
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mt-3">
            {([
              ['calorie_goal', '热量 kcal'],
              ['protein_goal', '蛋白质 g'],
              ['fat_goal', '脂肪 g'],
              ['carbs_goal', '碳水 g'],
              ['fiber_goal', '纤维 g'],
              ['sodium_goal', '钠 mg'],
            ] as Array<[keyof ProfileForm, string]>).map(([key, label]) => (
              <label key={key} className="text-sm text-gray-600 dark:text-gray-300">
                {label}
                <input
                  type="number"
                  value={form[key]}
                  onChange={event => updateField(key, event.target.value)}
                  className="mt-1 w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-gray-900 dark:text-gray-100"
                />
              </label>
            ))}
          </div>

          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-200 mt-6">
            烹饪条件
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mt-3">
            <label className="text-sm text-gray-600 dark:text-gray-300">
              每日餐数
              <input
                type="number"
                min={1}
                max={8}
                value={form.meals_per_day}
                onChange={event => updateField('meals_per_day', event.target.value)}
                className="mt-1 w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2"
              />
            </label>
            <label className="text-sm text-gray-600 dark:text-gray-300">
              烹饪水平
              <select
                value={form.cooking_skill}
                onChange={event => updateField('cooking_skill', event.target.value)}
                className="mt-1 w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2"
              >
                <option value="beginner">新手</option>
                <option value="intermediate">进阶</option>
                <option value="advanced">熟练</option>
              </select>
            </label>
            <label className="text-sm text-gray-600 dark:text-gray-300">
              最长烹饪时间（分钟）
              <input
                type="number"
                min={1}
                value={form.max_cook_minutes}
                onChange={event => updateField('max_cook_minutes', event.target.value)}
                className="mt-1 w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2"
              />
            </label>
            <label className="text-sm text-gray-600 dark:text-gray-300">
              预算水平
              <select
                value={form.budget_level}
                onChange={event => updateField('budget_level', event.target.value)}
                className="mt-1 w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2"
              >
                <option value="low">节省</option>
                <option value="medium">适中</option>
                <option value="high">充足</option>
              </select>
            </label>
            <label className="text-sm text-gray-600 dark:text-gray-300">
              家庭人数
              <input
                type="number"
                min={1}
                value={form.household_size}
                onChange={event => updateField('household_size', event.target.value)}
                className="mt-1 w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2"
              />
            </label>
            <label className="text-sm text-gray-600 dark:text-gray-300">
              单位制
              <select
                value={form.unit_system}
                onChange={event => updateField('unit_system', event.target.value)}
                className="mt-1 w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2"
              >
                <option value="metric">公制</option>
                <option value="imperial">英制</option>
              </select>
            </label>
            <label className="text-sm text-gray-600 dark:text-gray-300">
              辣度
              <select
                value={form.spice_level}
                onChange={event => updateField('spice_level', event.target.value)}
                className="mt-1 w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2"
              >
                <option value="none">不辣</option>
                <option value="mild">微辣</option>
                <option value="medium">中辣</option>
                <option value="hot">重辣</option>
              </select>
            </label>
          </div>

          <button
            onClick={saveProfile}
            disabled={isSaving}
            className="mt-6 px-5 py-2.5 rounded-xl bg-amber-500 text-white text-sm hover:bg-amber-600 disabled:opacity-50"
          >
            {isSaving ? '保存中...' : '保存档案'}
          </button>
        </section>

        <section className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-5">
          <div className="flex items-center gap-2">
            <Users className="w-5 h-5 text-amber-500" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              家庭成员
            </h2>
          </div>
          {merged && (
            <p className="text-xs text-gray-500 mt-1">
              合并后：{merged.family_member_count} 人 · {merged.household_size} 份 · 热量目标{' '}
              {merged.calorie_goal ?? '未设置'} kcal
            </p>
          )}
          <div className="grid grid-cols-1 md:grid-cols-5 gap-2 mt-4">
            <input
              value={memberName}
              onChange={event => setMemberName(event.target.value)}
              placeholder="姓名"
              className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm"
            />
            <input
              value={memberRelation}
              onChange={event => setMemberRelation(event.target.value)}
              placeholder="关系"
              className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm"
            />
            <input
              value={memberAllergies}
              onChange={event => setMemberAllergies(event.target.value)}
              placeholder="过敏原"
              className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm"
            />
            <input
              type="number"
              value={memberCalories}
              onChange={event => setMemberCalories(event.target.value)}
              placeholder="热量"
              className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm"
            />
            <div className="flex gap-2">
              <input
                type="number"
                step="0.1"
                value={memberFactor}
                onChange={event => setMemberFactor(event.target.value)}
                placeholder="份量系数"
                className="w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm"
              />
              <button
                onClick={addMember}
                className="p-2 rounded-xl bg-amber-500 text-white"
                title="添加家庭成员"
              >
                <Plus className="w-4 h-4" />
              </button>
            </div>
          </div>
          <div className="mt-4 space-y-2">
            {members.length === 0 ? (
              <div className="text-sm text-gray-400">还没有家庭成员</div>
            ) : (
              members.map(member => (
                <div
                  key={member.id}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-gray-100 dark:border-gray-800 p-3 text-sm"
                >
                  <div>
                    <span className="font-medium text-gray-800 dark:text-gray-100">
                      {member.name}
                    </span>
                    {member.relation && (
                      <span className="text-gray-500 ml-2">{member.relation}</span>
                    )}
                    <div className="text-xs text-gray-500 mt-1">
                      过敏原：{member.allergies.join('、') || '无'} · 热量{' '}
                      {member.calorie_goal ?? 2000} kcal · 份量 {member.servings_factor}
                    </div>
                  </div>
                  <button
                    onClick={() => removeMember(member.id)}
                    className="p-2 rounded-lg text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30"
                    title="删除"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
