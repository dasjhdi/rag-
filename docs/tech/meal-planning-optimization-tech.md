# 技术设计：CookHero 饮食闭环优化（P0/P1/P2）

- 对应规格：`docs/spec/meal-planning-optimization-spec.md`
- 版本：v1.0
- 状态：已实现（P0/P1/P2，2026-10-17）
- 技术栈：Python 3.13 / FastAPI / SQLAlchemy Async / PostgreSQL / React 19 / Vite

## 1. 设计原则

1. 规则优先：过敏原、营养配平、库存扣减、单位换算全部由确定性代码完成。
2. 单一事实源：饮食档案是约束和目标的唯一来源，计划、菜谱、Agent 工具统一读取。
3. 可解释：每个推荐、过滤、购物清单数量都能给出原因。
4. 可降级：知识库、LLM、网络不可用时，档案、库存、换算、营养表仍可用。
5. 向后兼容：不删除现有字段和接口，新增字段全部可空或有默认值。
6. 小步落库：计划生成先在内存完成，全部成功后再批量写入，避免半成品。

## 2. 模块结构

```text
app/diet/
  database/
    models.py                 # 扩展偏好；新增库存、清单、反馈、评价、家庭成员
    repository.py             # 计划/记录/偏好
    planning_repository.py    # 计划批量写入、锁定、状态
    pantry_repository.py      # 库存和购物清单
    feedback_repository.py    # 反馈与评价
    family_repository.py      # 家庭成员
  recipes/
    parser.py                 # Markdown -> 结构化菜谱
    service.py                # 菜谱检索、详情、缩放、换算
    repository.py             # 知识库文档查询
  nutrition/
    data/foods.json           # 本地营养表（每 100g）
    service.py                # 单位换算、营养估算、记录补全
  planning/
    generator.py              # 纯函数：候选 -> 周计划
    service.py                # 编排：档案、候选、落库、替换
  pantry/
    service.py                # 库存、购物清单、可做菜
  feedback/
    service.py                # 反馈、评价、排序
  family/
    service.py                # 家庭成员与约束合并
  profile/
    service.py                # 档案读写、有效约束

app/api/v1/endpoints/
  diet.py                     # 档案、生成、今日、执行率
  recipes.py                  # 菜谱、反馈、评价
  pantry.py                   # 库存、购物清单、可做菜
  nutrition.py                # 营养查询与换算
  family.py                   # 家庭成员
```

## 3. 数据模型

### 3.1 扩展 `user_food_preferences`

新增列：

```text
allergies JSON
allergy_severity JSON
dietary_restrictions JSON
favorite_cuisines JSON
preferred_foods JSON
health_conditions JSON
calorie_goal INTEGER
protein_goal FLOAT
fat_goal FLOAT
carbs_goal FLOAT
fiber_goal FLOAT
sodium_goal FLOAT
meals_per_day INTEGER DEFAULT 3
cooking_skill VARCHAR(20) DEFAULT 'intermediate'
max_cook_minutes INTEGER DEFAULT 60
budget_level VARCHAR(20) DEFAULT 'medium'
household_size INTEGER DEFAULT 1
unit_system VARCHAR(20) DEFAULT 'metric'
spice_level VARCHAR(20) DEFAULT 'medium'
version INTEGER DEFAULT 1
```

### 3.2 扩展 `diet_plan_meals`

```text
status VARCHAR(20) DEFAULT 'planned'   # planned/eaten/skipped
locked BOOLEAN DEFAULT false
generation_batch_id VARCHAR(64)
servings FLOAT
```

`dishes` 中每个菜品新增可选字段：

```json
{
  "recipe_id": "uuid",
  "name": "番茄炒蛋",
  "servings": 2,
  "ingredients": [{"name": "鸡蛋", "quantity": 2, "unit": "个"}],
  "calories": 320,
  "protein": 18,
  "fat": 16,
  "carbs": 22,
  "nutrition_confidence": "medium"
}
```

### 3.3 新增表

| 表 | 关键字段 |
| --- | --- |
| `pantry_items` | user_id, name, normalized_name, quantity, unit, category, expires_on, location |
| `shopping_list_items` | user_id, week_start_date, name, normalized_name, quantity, unit, checked, source |
| `recipe_feedback` | user_id, recipe_id, signal, rating, reason, created_at |
| `recipe_reviews` | user_id, recipe_id, rating, comment, unique(user_id, recipe_id) |
| `family_members` | owner_user_id, name, relation, allergies, dietary_restrictions, calorie_goal, servings_factor |

### 3.4 迁移

项目使用 `Base.metadata.create_all`，不会自动给已有表补列。新增 `app/database/migrations.py`：

- 启动时在 `create_all` 之后执行。
- 仅对 PostgreSQL 执行 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`。
- 所有语句幂等，失败只记录 warning，不阻断启动。

## 4. 菜谱解析

### 4.1 输入

`KnowledgeDocumentModel` 的 `dish_name`、`content`、`category`、`difficulty`、`source`。

### 4.2 章节识别

原料标题：`必备原料和工具`、`必备原料`、`原料`、`食材`、`配料`、`主料`、`辅料`。
步骤标题：`操作`、`步骤`、`做法`、`烹饪步骤`、`制作`。

### 4.3 食材行解析

```text
- 鸡蛋 2 个
- 番茄 300g
- 盐 适量
```

正则拆分为 `quantity`、`unit`、`name`。支持中文单位和常见英文单位。

### 4.4 步骤解析

按有序列表或编号行拆分；用正则提取 `(\d+)\s*(分钟|min|秒|小时)` 生成 `timer_seconds`。

### 4.5 营养与标签

- 食材归一化使用 `app.knowledge.ontology.normalize_ingredient`。
- 过敏原使用 `allergens_for`。
- 饮食标签使用 `diet_tags_for`。
- 营养使用本地营养表估算；覆盖率低于 50% 时标记 `confidence=low`。

### 4.6 份量缩放

`scale = target_servings / base_servings`。仅缩放有数值的食材；`适量`、`少许` 不缩放，返回 `scalable=false`。

## 5. 计划生成

### 5.1 候选集

从 `knowledge_documents` 读取公开菜谱和当前用户个人菜谱：

```sql
WHERE source_type = 'recipes'
  AND is_dish_index = false
  AND (user_id IS NULL OR user_id = :user_id)
```

限制 500 条，避免一次加载过多。

### 5.2 约束过滤

复用 `constraint_reasoner.evaluate_documents`。档案约束通过 `parse_constraints(profile_constraints=...)` 合并。

### 5.3 评分函数

```text
score =
  - abs(meal_calories - target_calories) / target_calories * 100
  - abs(protein - target_protein) / max(target_protein, 1) * 30
  - repeat_count * 25
  - same_day_duplicate * 1000
  - cook_time_over_budget * 0.5
  + cuisine_match * 8
  + feedback_score
  + pantry_coverage * 10
```

每天按早餐 25%、午餐 40%、晚餐 35% 选择。先选早餐，再午餐、晚餐，避免同一天重复。

### 5.4 落库

1. 读取已有计划，保留 `locked=true` 的餐次。
2. 生成其余餐次。
3. 在一个事务中删除未锁定餐次并批量插入新餐次。
4. 返回计划、目标、实际、偏差、警告和候选数。

## 6. 库存与购物清单

### 6.1 聚合

遍历计划餐次的 `dishes[].ingredients[]`。以 `normalized_name + unit` 为键累加数量。没有结构化食材的手工餐次以菜名 + `份` 聚合。

### 6.2 扣减

同 `normalized_name + unit` 的库存数量从需求中扣除。剩余量 <= 0 时不进入清单。

### 6.3 可做菜

对每个候选菜谱计算：

```text
coverage = 已匹配食材数 / 总食材数
missing = 缺失食材列表
```

按 `coverage` 降序、缺失数升序排序。

## 7. 营养可信度

### 7.1 本地表

`foods.json` 每项：

```json
{
  "name": "鸡胸肉",
  "aliases": ["鸡胸", "鸡脯肉"],
  "per_100g": {"calories": 133, "protein": 19.4, "fat": 5.0, "carbs": 2.5},
  "default_unit": "g"
}
```

### 7.2 单位换算

```text
1 kg = 1000 g
1 oz = 28.3495 g
1 lb = 453.592 g
1 cup = 240 ml
1 tbsp = 15 ml
1 tsp = 5 ml
```

计件单位使用食物级 `unit_grams`：鸡蛋 50g/个、番茄 150g/个、香蕉 120g/根等。

### 7.3 置信度

- `high`：食物命中本地表且单位可换算。
- `medium`：食物命中但用量为估算。
- `low`：食物未命中或单位未知。

## 8. 反馈与评价

### 8.1 反馈分

```text
view +1
favorite +8
cooked +10
like +6
dislike -12
skip -6
```

同一用户同一菜谱取最近 20 条信号求和，并限制在 [-30, 30]。

### 8.2 评价

`recipe_reviews` 对 `(user_id, recipe_id)` 唯一。平均分和评价数由聚合查询计算。

## 9. 家庭

家庭约束合并：

- 过敏原取并集，全部作为硬约束。
- 饮食限制取并集。
- 份量系数 = 所有成员 `servings_factor` 之和，默认 1。
- 热量目标 = 所有成员 `calorie_goal` 之和（缺省按成人 2000）。

## 10. 前端

新增页面：

- `RecipeDetailPage`：菜谱详情、份量缩放、单位切换、评分评论、开始烹饪。
- `CookingModePage`：大字号步骤、上一步/下一步、计时器、屏幕常亮。
- `DietProfilePage`：档案、家庭、库存入口。

新增组件：

- `VoiceInputButton`：Web Speech API，浏览器不支持时隐藏。
- `RecipeCard`、`NutritionBadge`。

新增路由：

- `/recipes/:id`
- `/recipes/:id/cook`
- `/diet/profile`

## 11. Agent 工具

| 工具 | 作用 |
| --- | --- |
| `recipe_search` | 搜索结构化菜谱 |
| `nutrition_calculator` | 按食材和用量计算营养 |
| `unit_converter` | 厨房单位换算 |
| `pantry_manager` | 查询/添加/删除库存 |
| `shopping_list` | 生成/读取购物清单 |
| `kitchen_timer` | 生成计时建议（不依赖后台任务） |

## 12. 错误与降级

- 计划生成无候选：返回 422 和 `no_candidates`。
- 菜谱解析失败：返回原文、空结构、`warnings`。
- 营养未知：返回 `confidence=low`，不抛异常。
- 库存/清单数据库异常：接口返回 503，Agent 工具返回 `success=false`。
- 对话档案读取失败：记录 warning，继续原有链路。

## 13. 测试策略

- 纯函数单测：解析、缩放、营养换算、计划评分、购物清单聚合、家庭约束合并。
- 服务单测：用内存 fake repository。
- API 路由测试：检查路径注册和请求模型。
- 回归测试：现有 230 个用例全部通过。
- 前端：`npm run build` 通过。
