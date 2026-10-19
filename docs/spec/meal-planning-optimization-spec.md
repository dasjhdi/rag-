# 需求规格：CookHero 饮食闭环优化（P0/P1/P2）

- 规格编号：`MP-SPEC-001`
- 版本：v1.0
- 状态：已实现（P0/P1/P2，2026-10-17）
- 上游能力：`SU-SPEC-002`（语义理解）、`CR-SPEC-001`（约束推理）
- 定位：把现有“对话 + 饮食记录”扩展为“档案 → 计划 → 采购 → 烹饪 → 记录 → 反馈”的完整闭环。

---

## 1. 背景与目标

### 1.1 现状

项目已经具备对话式 RAG、意图识别、槽位抽取、约束推理、周计划餐次增删改、文字/图片饮食记录、营养汇总和 Agent 工具。但存在四个断点：

1. 用户饮食档案只有自由文本和少量偏好字段，过敏原、饮食模式、营养目标无法稳定保存和复用。
2. 周计划只能手工维护，Agent 生成的计划是 Markdown 文本，不落库、不参与营养配平。
3. 菜谱没有结构化实体，前端没有菜谱详情和烹饪模式。
4. 计划、库存、采购、反馈、家庭场景之间没有数据连接。

### 1.2 目标

1. 建立结构化饮食档案，并让对话、计划、菜谱、记录统一读取。
2. 提供确定性的周计划生成与单餐替换，生成结果直接落库。
3. 提供结构化菜谱详情、份量缩放、单位换算和烹饪步骤。
4. 提供食材库存、临期提醒、购物清单和“现有食材能做什么”。
5. 建立推荐反馈、评分评论和个性化排序。
6. 提高营养数据的可追溯性，标注来源、置信度和覆盖率。
7. 提供今日视图、执行率和周复盘。
8. 支持家庭多成员、语音输入、单位制和 Agent 工具扩展。

### 1.3 非目标

- 不做疾病诊断，不替代营养师或医生。
- 不引入新的外部付费服务；无法联网时全部能力可降级。
- 不实现 AR 烹饪指导。
- 不重写现有语义理解与约束推理主链路，只做兼容扩展。

---

## 2. 术语

| 术语 | 含义 |
| --- | --- |
| 饮食档案 | 用户过敏原、饮食模式、疾病忌口、营养目标、烹饪条件等结构化信息 |
| 有效约束 | 用户本次输入 + 饮食档案 + 家庭成员约束合并后的约束集合 |
| 结构化菜谱 | 含食材、用量、步骤、时间、营养、过敏原和饮食标签的菜谱实体 |
| 计划生成 | 从候选菜谱中按约束、营养、时间和多样性选择并落库的过程 |
| 反馈信号 | 浏览、收藏、做过、喜欢、不喜欢、跳过等行为 |
| 营养覆盖率 | 有可信营养来源的食品项占总食品项的比例 |

---

## 3. P0 需求

### MP-01 结构化饮食档案

**需求**：在现有 `user_food_preferences` 上扩展结构化字段，并提供独立档案接口。

字段：

- `allergies`、`allergy_severity`
- `dietary_restrictions`
- `health_conditions`
- `avoided_foods`、`preferred_foods`、`favorite_cuisines`
- `calorie_goal`、`protein_goal`、`fat_goal`、`carbs_goal`、`fiber_goal`、`sodium_goal`
- `meals_per_day`、`cooking_skill`、`max_cook_minutes`、`budget_level`
- `household_size`、`unit_system`、`spice_level`

接口：

- `GET /api/v1/diet/profile`
- `PUT /api/v1/diet/profile`
- `GET /api/v1/diet/profile/effective-constraints`

验收：

- AC-01.1 更新后读回字段一致，不再静默丢弃。
- AC-01.2 档案中的过敏原和饮食模式自动进入对话约束推理。
- AC-01.3 档案中的营养目标参与计划生成。
- AC-01.4 旧 `PUT /diet/preferences` 保持兼容。

测试映射：`tests/test_diet_profile.py`

### MP-02 智能周计划生成

**需求**：根据档案、约束、候选菜谱和营养目标生成一周计划并落库。

接口：

- `POST /api/v1/diet/plans/generate`
- `POST /api/v1/diet/plans/meals/{meal_id}/replace`
- `POST /api/v1/diet/plans/meals/{meal_id}/skip`

规则：

1. 硬约束先过滤，过敏原零容忍。
2. 每日热量按早餐 25%、午餐 40%、晚餐 35% 分配。
3. 优先满足蛋白质目标，其次控制脂肪和碳水偏差。
4. 同一菜谱一周最多出现 2 次，同一天不重复。
5. 优先低烹饪时间、偏好菜系和正向反馈，惩罚负向反馈。
6. 已锁定餐次不被覆盖。

验收：

- AC-02.1 7 天计划一次生成并可直接读取。
- AC-02.2 过敏原候选不会进入结果。
- AC-02.3 计划总热量与目标偏差可计算并返回诊断。
- AC-02.4 单餐替换不改变其他餐次。
- AC-02.5 无候选时返回可解释错误，不写入半成品。

测试映射：`tests/test_plan_generator.py`

### MP-03 菜谱详情与烹饪模式

**需求**：把知识库菜谱解析为结构化菜谱，并提供详情和烹饪模式。

接口：

- `GET /api/v1/recipes/search`
- `GET /api/v1/recipes/{recipe_id}`
- `GET /api/v1/recipes/{recipe_id}?servings=4&unit_system=imperial`

能力：

- 食材、用量、单位、步骤、计时、份量、时间、难度、过敏原、饮食标签。
- 份量缩放和公制/英制换算。
- 前端 `/recipes/:id` 详情页与 `/recipes/:id/cook` 烹饪模式。

验收：

- AC-03.1 菜谱文档可解析出至少食材和步骤。
- AC-03.2 份量翻倍时用量按比例变化。
- AC-03.3 步骤中的分钟数被识别为计时器。
- AC-03.4 解析失败时返回原文和明确警告，不伪造结构。

测试映射：`tests/test_recipe_parser.py`

---

## 4. P1 需求

### MP-04 食材库存与购物清单

接口：

- `GET/POST /api/v1/pantry/items`
- `PATCH/DELETE /api/v1/pantry/items/{item_id}`
- `GET /api/v1/pantry/expiring`
- `POST /api/v1/pantry/shopping-list/generate`
- `GET /api/v1/pantry/shopping-list`
- `PATCH /api/v1/pantry/shopping-list/{item_id}`
- `GET /api/v1/pantry/cookable`

规则：

- 购物清单按计划食材聚合，扣除库存同单位数量。
- 临期按 `expires_on <= today + days` 判断。
- “能做什么”按库存食材覆盖率排序。

验收：

- AC-04.1 同一食材不同餐次合并。
- AC-04.2 库存足够时购物清单数量为 0 或移除。
- AC-04.3 临期列表按到期日升序。

测试映射：`tests/test_pantry_service.py`

### MP-05 推荐反馈闭环

接口：

- `POST /api/v1/recipes/{recipe_id}/feedback`
- `GET /api/v1/recipes/recommendations`

信号：`view`、`favorite`、`cooked`、`like`、`dislike`、`skip`。

验收：

- AC-05.1 负向反馈降低排序分。
- AC-05.2 收藏和做过提高排序分。
- AC-05.3 反馈按用户隔离。

测试映射：`tests/test_recipe_feedback.py`

### MP-06 营养数据可信度

接口：

- `GET /api/v1/nutrition/foods?q=`
- `POST /api/v1/nutrition/convert`
- `POST /api/v1/nutrition/estimate`

规则：

- 常见食物使用本地营养表，按 100g 计算。
- 支持克、千克、毫升、个、只、碗、勺、杯等换算。
- 无匹配时返回 `confidence=low`，不伪装成精确值。
- 饮食记录自动补齐缺失营养，并写入来源和置信度。

验收：

- AC-06.1 100g 鸡胸肉营养与本地表一致。
- AC-06.2 “2 个鸡蛋”可换算为约 100g。
- AC-06.3 未知食物返回低置信度和明确原因。
- AC-06.4 每日汇总返回营养覆盖率。

测试映射：`tests/test_nutrition_service.py`

### MP-07 计划执行闭环

接口：

- `GET /api/v1/diet/today`
- `GET /api/v1/diet/analysis/adherence`

能力：

- 今日餐次、已吃/未吃/跳过状态、下一餐。
- 周执行率、漏餐数、连续执行天数、周复盘建议。

验收：

- AC-07.1 标记已吃后今日视图状态变化。
- AC-07.2 执行率按计划餐次计算。
- AC-07.3 无计划时返回明确空状态。

测试映射：`tests/test_plan_execution.py`

---

## 5. P2 需求

### MP-08 家庭多成员

接口：

- `GET/POST /api/v1/family/members`
- `PATCH/DELETE /api/v1/family/members/{member_id}`

规则：

- 家庭成员有独立过敏原、饮食限制、热量目标和份量系数。
- 家庭计划取过敏原并集作为硬约束，份量按成员系数汇总。

验收：AC-08.1 成员 CRUD；AC-08.2 家庭约束合并；AC-08.3 家庭份量计算。

测试映射：`tests/test_family_service.py`

### MP-09 语音交互与免手烹饪

能力：

- 对话输入框支持浏览器语音识别。
- 烹饪模式支持大字号、步骤翻页、计时器、屏幕常亮。

验收：AC-09.1 不支持语音时按钮隐藏或降级；AC-09.2 烹饪模式可逐步操作。

测试映射：前端构建 + `tests/test_api_routes.py`

### MP-10 社区评分与评论

接口：

- `GET /api/v1/recipes/{recipe_id}/reviews`
- `PUT /api/v1/recipes/{recipe_id}/review`
- `DELETE /api/v1/recipes/{recipe_id}/review`

验收：AC-10.1 同一用户同一菜谱只有一条评价；AC-10.2 平均分正确；AC-10.3 评价按用户隔离。

测试映射：`tests/test_recipe_reviews.py`

### MP-11 Agent 工具扩展

新增工具：

- `recipe_search`
- `nutrition_calculator`
- `unit_converter`
- `pantry_manager`
- `shopping_list`
- `kitchen_timer`

验收：AC-11.1 工具注册成功；AC-11.2 参数校验失败返回可读错误；AC-11.3 无网络时仍可用。

测试映射：`tests/test_diet_agent_tools.py`

### MP-12 单位制与国际化基础

能力：

- 档案保存 `unit_system`（metric/imperial）。
- 菜谱详情支持切换单位。
- 后端统一换算，前端只展示。

验收：AC-12.1 克/盎司、毫升/杯换算正确；AC-12.2 未知单位不静默转换。

测试映射：`tests/test_nutrition_service.py`

---

## 6. 兼容与降级

- 新增表通过 `create_all` 创建；已有表通过幂等 DDL 补列。
- 所有新能力失败不得阻断对话主链路。
- 无 LLM、无网络、无知识库时，档案、库存、单位换算、营养表仍可用。
- 现有 API 路径和响应字段保持兼容。

## 7. 验收总表

| 编号 | 能力 | 必须通过 |
| --- | --- | --- |
| MP-01 | 结构化档案 | 是 |
| MP-02 | 周计划生成 | 是 |
| MP-03 | 菜谱详情/烹饪 | 是 |
| MP-04 | 库存/购物清单 | 是 |
| MP-05 | 反馈闭环 | 是 |
| MP-06 | 营养可信度 | 是 |
| MP-07 | 执行闭环 | 是 |
| MP-08 | 家庭档案 | 是 |
| MP-09 | 语音/免手 | 是 |
| MP-10 | 社区评价 | 是 |
| MP-11 | Agent 工具 | 是 |
| MP-12 | 单位制 | 是 |
