# 测试计划：CookHero 饮食闭环优化（P0/P1/P2）

- 对应规格：`docs/spec/meal-planning-optimization-spec.md`
- 对应技术设计：`docs/tech/meal-planning-optimization-tech.md`
- 版本：v1.0
- 状态：已执行，全部通过（2026-10-17）

## 1. 测试范围

| 范围 | 类型 | 文件 |
| --- | --- | --- |
| 结构化档案 | 单元 + API | `tests/test_diet_profile.py` |
| 菜谱解析/缩放 | 单元 | `tests/test_recipe_parser.py` |
| 周计划生成 | 单元 + 服务 | `tests/test_plan_generator.py` |
| 库存/购物清单 | 单元 | `tests/test_pantry_service.py` |
| 营养换算 | 单元 | `tests/test_nutrition_service.py` |
| 反馈排序 | 单元 | `tests/test_recipe_feedback.py` |
| 社区评价 | 服务 | `tests/test_recipe_reviews.py` |
| 家庭约束 | 单元 | `tests/test_family_service.py` |
| 执行闭环 | 服务 | `tests/test_plan_execution.py` |
| Agent 工具 | 单元 | `tests/test_diet_agent_tools.py` |
| 路由注册 | API | `tests/test_api_routes.py` |

## 2. 测试环境

- Python：项目 `.venv`
- 命令：`.\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider`
- 前端：`npm run build`
- 不依赖真实 LLM、Milvus、Redis；服务测试使用 fake repository 或纯函数。

## 3. 用例设计

### 3.1 结构化档案

1. 创建档案后读回全部字段。
2. 更新部分字段不覆盖其他字段。
3. 过敏原和饮食限制合并为有效约束。
4. 旧偏好接口字段映射到新字段。
5. 版本号递增。

### 3.2 菜谱解析

1. 解析标准 Markdown 菜谱：食材数量、单位、步骤。
2. 解析无原料章节的菜谱：回退全文并给出 warning。
3. 步骤计时识别：`煮 5 分钟` -> 300 秒。
4. 份量缩放：2 人 -> 4 人，数值翻倍，`适量` 不变。
5. 英制换算：100g -> 3.53oz。
6. 解析空内容不抛异常。

### 3.3 计划生成

1. 7 天 x 3 餐生成 21 个餐次。
2. 花生过敏时含花生菜谱被排除。
3. 同一菜谱一周不超过 2 次。
4. 同一天不重复。
5. 热量目标 2000 时总热量偏差在 ±15% 内。
6. 锁定餐次保持不变。
7. 无候选返回明确错误。

### 3.4 库存/购物清单

1. 同食材不同餐次合并。
2. 库存扣减后剩余量正确。
3. 库存足够时不进入清单。
4. 临期排序正确。
5. 可做菜按覆盖率排序。

### 3.5 营养

1. 鸡胸肉 100g 命中本地表。
2. `2 个鸡蛋` 换算 100g。
3. `1 cup` 牛奶换算 240ml。
4. 未知食物返回 low confidence。
5. 记录补全只填补缺失字段。
6. 每日汇总覆盖率正确。

### 3.6 反馈/评价

1. 喜欢提高排序分，不喜欢降低排序分。
2. 反馈按用户隔离。
3. 同一用户同一菜谱评价更新而非新增。
4. 平均分计算正确。

### 3.7 家庭

1. 成员 CRUD。
2. 过敏原并集。
3. 饮食限制并集。
4. 份量系数求和。

### 3.8 执行闭环

1. 今日视图返回计划餐次和状态。
2. 已吃标记后状态为 eaten。
3. 跳过标记后状态为 skipped。
4. 执行率 = 已吃 / 计划。
5. 无计划返回空状态。

### 3.9 Agent 工具

1. 六个工具注册成功。
2. 单位换算工具返回正确结果。
3. 营养工具未知食物返回 low confidence。
4. 菜谱搜索无结果返回空列表而非异常。
5. 库存工具参数缺失返回可读错误。

## 4. 回归测试

现有全部测试必须通过，重点：

- `tests/test_constraint_parser.py`
- `tests/test_constraint_evaluator.py`
- `tests/test_constraint_integration.py`
- `tests/test_mcp.py`
- `tests/test_intent_upgrade.py`

## 5. 前端验收

1. `npm run build` 无 TypeScript 错误。
2. `/recipes/:id` 可打开详情。
3. `/recipes/:id/cook` 可逐步翻页和计时。
4. 语音按钮在不支持的浏览器中不显示。
5. 单位切换后用量显示变化。
6. 评分/评论提交后列表刷新。

## 6. 通过标准

- 新增测试全部通过。
- 原有测试全部通过。
- 前端构建通过。
- 计划生成无过敏原违规。
- 档案字段无静默丢失。
- 未知营养/单位有明确低置信度标记。


## 7. 执行结果（2026-10-17）

### 7.1 后端

- 命令：`.\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider`
- 结果：`297 passed, 1 warning`
- 编译：`.\.venv\Scripts\python.exe -m compileall app tests -q` 通过

新增测试覆盖：

| 文件 | 用例数 | 结果 |
| --- | --- | --- |
| `tests/test_recipe_parser.py` | 6 | 通过 |
| `tests/test_nutrition_service.py` | 7 | 通过 |
| `tests/test_plan_generator.py` | 10 | 通过 |
| `tests/test_pantry_service.py` | 5 | 通过 |
| `tests/test_plan_execution.py` | 5 | 通过 |
| `tests/test_diet_profile.py` | 6 | 通过 |
| `tests/test_recipe_feedback.py` | 7 | 通过 |
| `tests/test_recipe_reviews.py` | 4 | 通过 |
| `tests/test_family_service.py` | 3 | 通过 |
| `tests/test_diet_agent_tools.py` | 7 | 通过 |
| `tests/test_api_routes.py` | 6 | 通过 |

### 7.2 前端

- 命令：`npm run build`
- 结果：通过，`3067 modules transformed`，生成 `dist/`
- 新增路由：`/recipes`、`/recipes/:id`、`/recipes/:id/cook`、`/diet/profile`、`/diet/pantry`
- 语音输入：`VoiceInputButton` 已接入普通对话与 Agent 对话；不支持 Web Speech API 时自动隐藏
- 烹饪模式：步骤翻页、步骤计时、屏幕常亮降级均已实现

### 7.3 关键验收

- 花生过敏候选在计划生成中被硬过滤，且不会因 fallback 回退。
- 7 天 × 3 餐生成 21 个餐次；同一菜谱一周最多 2 次；同一天不重复。
- 锁定/已吃/已跳过餐次在重新生成时保留，且不会重复插入。
- `2 个鸡蛋` 换算约 100g；`1 杯牛奶` 为 240ml。
- 未知食物返回 `confidence=low`，未知单位不静默换算。
- 购物清单按食材合并并扣除库存；临期列表按到期日排序。
- 今日视图能反映已吃/跳过状态；执行率按计划餐次计算。
- 六个新 Agent 工具均注册成功，参数错误返回可读 `success=false`。
