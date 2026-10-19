import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Loader2, Package, Plus, ShoppingCart, Trash2 } from 'lucide-react';
import { useAuth } from '../../contexts';
import {
  addPantryItem,
  deletePantryItem,
  generateShoppingList,
  getCookableRecipes,
  getExpiringPantry,
  getShoppingList,
  listPantryItems,
  updatePantryItem,
  updateShoppingItem,
} from '../../services/api/diet';
import type { CookableRecipe, PantryItem, ShoppingListItem } from '../../types/diet';
import { BackButton } from '../../components/common';

function currentWeekStart(): string {
  const today = new Date();
  const day = today.getDay();
  const diff = today.getDate() - day + (day === 0 ? -6 : 1);
  const monday = new Date(today.setDate(diff));
  return monday.toISOString().split('T')[0];
}

export default function PantryPage() {
  const { token } = useAuth();
  const [items, setItems] = useState<PantryItem[]>([]);
  const [expiring, setExpiring] = useState<PantryItem[]>([]);
  const [shopping, setShopping] = useState<ShoppingListItem[]>([]);
  const [cookable, setCookable] = useState<CookableRecipe[]>([]);
  const [name, setName] = useState('');
  const [quantity, setQuantity] = useState('1');
  const [unit, setUnit] = useState('g');
  const [expiresOn, setExpiresOn] = useState('');
  const [weekStart] = useState(currentWeekStart);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    if (!token) return;
    setIsLoading(true);
    setError(null);
    try {
      const [pantry, expiry, list, recipes] = await Promise.all([
        listPantryItems(token),
        getExpiringPantry(token, 3),
        getShoppingList(token, weekStart),
        getCookableRecipes(token, 10),
      ]);
      setItems(pantry.items);
      setExpiring(expiry.items);
      setShopping(list.items);
      setCookable(recipes.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载库存失败');
    } finally {
      setIsLoading(false);
    }
  }, [token, weekStart]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const addItem = async () => {
    if (!token || !name.trim()) return;
    try {
      await addPantryItem(token, {
        name: name.trim(),
        quantity: Number(quantity) || 0,
        unit: unit.trim() || 'g',
        expires_on: expiresOn || undefined,
      });
      setName('');
      setQuantity('1');
      setExpiresOn('');
      setMessage('食材已加入库存');
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : '添加库存失败');
    }
  };

  const updateQuantity = async (item: PantryItem, value: string) => {
    if (!token) return;
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed < 0) return;
    try {
      await updatePantryItem(token, item.id, { quantity: parsed });
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : '更新库存失败');
    }
  };

  const removeItem = async (itemId: string) => {
    if (!token) return;
    try {
      await deletePantryItem(token, itemId);
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除库存失败');
    }
  };

  const createShoppingList = async () => {
    if (!token) return;
    try {
      const result = await generateShoppingList(token, weekStart);
      setShopping(result.items);
      setMessage(`购物清单已生成，库存抵扣 ${result.saved_by_pantry} 项`);
    } catch (err) {
      setError(err instanceof Error ? err.message : '生成购物清单失败');
    }
  };

  const toggleShoppingItem = async (item: ShoppingListItem) => {
    if (!token) return;
    try {
      const updated = await updateShoppingItem(token, item.id, {
        checked: !item.checked,
      });
      setShopping(prev =>
        prev.map(current => (current.id === updated.id ? updated : current))
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : '更新购物清单失败');
    }
  };

  return (
    <div className="flex-1 overflow-auto p-4 md:p-6">
      <div className="max-w-6xl mx-auto space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <BackButton fallbackTo="/diet" label="返回饮食管理" />
            <div className="ch-eyebrow mt-4">Pantry & Shopping</div>
            <h1 className="ch-display text-[2rem] text-ink-900 dark:text-cream-50 mt-1">
              库存与购物清单
            </h1>
            <p className="text-sm text-ink-500 dark:text-ink-300 mt-1.5">
              按本周计划聚合食材，自动扣除库存并提示临期食材
            </p>
          </div>
          <button
            onClick={createShoppingList}
            className="ch-btn ch-btn-primary"
          >
            <ShoppingCart className="w-4 h-4" />
            生成本周购物清单
          </button>
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

        <section className="ch-card p-5">
          <div className="flex items-center gap-2">
            <Package className="w-5 h-5 text-ember-500" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">我的库存</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-5 gap-2 mt-4">
            <input
              value={name}
              onChange={event => setName(event.target.value)}
              placeholder="食材名称"
              className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm"
            />
            <input
              type="number"
              min={0}
              value={quantity}
              onChange={event => setQuantity(event.target.value)}
              placeholder="数量"
              className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm"
            />
            <input
              value={unit}
              onChange={event => setUnit(event.target.value)}
              placeholder="单位"
              className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm"
            />
            <input
              type="date"
              value={expiresOn}
              onChange={event => setExpiresOn(event.target.value)}
              className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm"
            />
            <button
              onClick={addItem}
              className="inline-flex items-center justify-center gap-1 rounded-xl bg-ember-500 text-white text-sm"
            >
              <Plus className="w-4 h-4" />
              添加
            </button>
          </div>

          {isLoading ? (
            <div className="flex justify-center py-10">
              <Loader2 className="w-6 h-6 animate-spin text-ember-500" />
            </div>
          ) : items.length === 0 ? (
            <div className="text-sm text-gray-400 mt-4">库存为空，先添加一些食材吧。</div>
          ) : (
            <div className="mt-4 divide-y divide-gray-100 dark:divide-gray-800">
              {items.map(item => (
                <div
                  key={item.id}
                  className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm"
                >
                  <div>
                    <span className="font-medium text-gray-800 dark:text-gray-100">
                      {item.name}
                    </span>
                    <span className="text-xs text-gray-500 ml-2">
                      {item.expires_on ? `到期 ${item.expires_on}` : '无到期日'}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      min={0}
                      defaultValue={item.quantity}
                      onBlur={event => updateQuantity(item, event.target.value)}
                      className="w-24 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-2 py-1 text-sm"
                    />
                    <span className="text-gray-500">{item.unit}</span>
                    <button
                      onClick={() => removeItem(item.id)}
                      className="p-1.5 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30 rounded"
                      title="删除"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <section className="ch-card p-5">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">临期提醒</h2>
            {expiring.length === 0 ? (
              <div className="text-sm text-gray-400 mt-3">未来 3 天没有临期食材</div>
            ) : (
              <div className="mt-3 space-y-2">
                {expiring.map(item => (
                  <div
                    key={item.id}
                    className="flex items-center justify-between rounded-xl bg-amber-50 dark:bg-amber-900/20 px-3 py-2 text-sm"
                  >
                    <span className="text-gray-800 dark:text-gray-100">{item.name}</span>
                    <span className="text-amber-700 dark:text-ember-300">
                      {item.expires_on} · {item.quantity}{item.unit}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="ch-card p-5">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">现有食材能做</h2>
            <div className="mt-3 space-y-2">
              {cookable.length === 0 ? (
                <div className="text-sm text-gray-400">还没有可推荐菜谱</div>
              ) : (
                cookable.map(item => (
                  <Link
                    key={item.recipe_id}
                    to={`/recipes/${item.recipe_id}`}
                    className="block rounded-xl border border-gray-100 dark:border-gray-800 px-3 py-2 text-sm hover:bg-gray-50 dark:hover:bg-gray-800"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-gray-800 dark:text-gray-100">{item.title}</span>
                      <span className="text-xs text-ember-600 dark:text-ember-300">
                        {Math.round(item.coverage * 100)}%
                      </span>
                    </div>
                    {item.missing.length > 0 && (
                      <div className="text-xs text-gray-500 mt-1">
                        缺：{item.missing.join('、')}
                      </div>
                    )}
                  </Link>
                ))
              )}
            </div>
          </section>
        </div>

        <section className="ch-card p-5">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              本周购物清单
            </h2>
            <span className="text-xs text-gray-500">周起始 {weekStart}</span>
          </div>
          {shopping.length === 0 ? (
            <div className="text-sm text-gray-400 mt-3">
              清单为空。生成本周购物清单后会显示在这里。
            </div>
          ) : (
            <div className="mt-3 space-y-2">
              {shopping.map(item => (
                <label
                  key={item.id}
                  className="flex items-center justify-between gap-3 rounded-xl border border-gray-100 dark:border-gray-800 px-3 py-2 text-sm cursor-pointer"
                >
                  <span className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={item.checked}
                      onChange={() => toggleShoppingItem(item)}
                      className="rounded"
                    />
                    <span
                      className={
                        item.checked
                          ? 'line-through text-gray-400'
                          : 'text-gray-800 dark:text-gray-100'
                      }
                    >
                      {item.name}
                    </span>
                  </span>
                  <span className="text-gray-500">
                    {item.quantity} {item.unit}
                  </span>
                </label>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
