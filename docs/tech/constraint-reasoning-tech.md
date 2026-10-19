# 技术设计：CookHero 约束推理能力（方案 B）

- 对应规格：`docs/spec/constraint-reasoning-spec.md`
- 版本：v1.0
- 状态：已实现（2026-10-17）
- 技术栈：Python 3.13 / FastAPI / LangChain Document / 现有食材本体

## 1. 总体设计

### 1.1 设计原则

1. 规则优先：硬约束由确定性代码判断，不交给 LLM 自由发挥。
2. 解释优先：每个排除项都能回答“哪条约束、哪个食材、什么原因”。
3. 未知保守：无法提取食材时标记未知，不把未知当作安全。
4. 可降级：任何约束推理异常都不阻断对话主链路。
5. 默认可控：配置可一键关闭，关闭后行为与 v2 完全一致。

### 1.2 数据流

```text
用户查询 + IntentDetectionResult.slots
  -> parse_constraints
       -> ConstraintProfile（硬约束/软约束/未知项）
  -> detect_conflicts
       -> 冲突列表 + 澄清问题
  -> RAG 检索
  -> evaluate_documents
       -> 食材提取
       -> 硬约束过滤
       -> 软约束打分与稳定排序
       -> 替代建议
  -> 重建 context/sources
  -> 生成提示词追加约束解释
  -> LLM 回答
```

## 2. 模块结构

```text
app/reasoning/constraints/
  __init__.py
  models.py          # Constraint / Profile / Assessment / Decision
  parser.py          # 槽位与原文解析
  conflicts.py       # 冲突检测与澄清问题
  substitutions.py   # 静态替代建议
  evaluator.py       # 食材提取、硬过滤、软打分
  service.py         # 对外编排入口
```

`app/knowledge/ontology.py` 增加：

- `find_ingredients(text)`：从文本中识别已知食材，返回规范化名称。
- `extract_ingredients_from_document(text, title)`：优先读取原料章节。

## 3. 约束解析

### 3.1 词表

解析器维护四张静态词表：

| 类型 | 示例 | 严重级别 |
| --- | --- | --- |
| 过敏原 | 花生、坚果、牛奶、鸡蛋、海鲜、鱼、大豆、小麦、芝麻 | hard |
| 饮食模式 | 素食、纯素、无麸质 | hard |
| 营养目标 | 低脂、控糖、高蛋白、低盐 | soft |
| 口味 | 清淡、不辣 | soft |

过敏原和饮食模式使用 ontology 中的英文标签作为 `value`，避免中文别名扩散到下游。

### 3.2 原文模式

```text
(不吃|不要|不能吃|忌|避免|对)(短语)
(短语)过敏
```

命中短语后：

1. 先尝试匹配过敏原词表；
2. 再尝试匹配饮食模式/营养目标词表；
3. 再通过 `find_ingredients` 匹配已知食材；
4. 都不命中时写入 `unknown_terms`。

### 3.3 去重

约束以 `(kind, value)` 为唯一键；同一约束同时来自槽位和原文时保留 `slot` 来源，避免重复展示。

## 4. 候选评估

### 4.1 食材提取

1. 优先匹配 Markdown 二级标题：`必备原料和工具`、`原料`、`食材`、`配料`。
2. 章节不存在时回退到“标题 + 全文”。
3. 用 ontology 的别名表做最长优先匹配。
4. 先屏蔽已知的非食材短语，例如“鱼香肉丝”“鱼香茄子”“素鸡”“素肉”，避免把菜名中的字误判为食材。

### 4.2 硬约束

| 约束 | 判断 | 证据 |
| --- | --- | --- |
| 过敏原 | `allergens_for(ingredients)` 包含目标 | `explain_allergens` 给出贡献食材 |
| 素食 | `vegetarian` 不在 `diet_tags_for` | 缺失标签 + 食材列表 |
| 纯素 | `vegan` 不在 `diet_tags_for` | 缺失标签 + 食材列表 |
| 无麸质 | `gluten_free` 不在 `diet_tags_for` | 缺失标签 + 食材列表 |
| 忌口食材 | 规范化食材出现在列表 | 食材名 |

没有提取到任何已知食材时，`unknown=True`，不生成硬排除，只在提示词中标注“无法确认”。

### 4.3 软约束

软约束使用保守关键词规则：

| 约束 | 正向信号 | 负向信号 |
| --- | --- | --- |
| 低脂 | 蒸、煮、凉拌、少油 | 油炸、黄油、奶油、五花肉、肥肉 |
| 控糖 | 无糖、低糖、控糖 | 糖、冰糖、蜂蜜、蛋糕、奶茶 |
| 高蛋白 | 鸡蛋、鸡肉、牛肉、鱼、虾、豆腐、牛奶 | — |
| 低盐 | 少盐、低盐、清淡 | 盐、酱油、蚝油、豆瓣酱、腌 |
| 清淡 | 清淡、不辣、微辣 | 辣椒、小米辣、花椒、豆瓣酱 |

评分：

```text
score = 1.0 - 0.12 * 软约束未命中数 + 0.03 * 软约束命中数
score = clamp(score, 0.0, 1.0)
```

排序键为 `(-score, 原始下标)`，保证同分稳定。

### 4.4 全量排除回退

如果硬约束排除了所有候选：

1. 保留原候选顺序；
2. `fallback_used=True`；
3. 提示词明确写出“没有找到完全满足硬约束的候选，请说明限制并给出替代方向”。

## 5. 冲突检测

冲突来源：

- 纯素 + 非纯素食材；
- 素食 + 非素食食材；
- 无麸质 + 非无麸质食材；
- 过敏原 + 含该过敏原的显式食材；
- 同一食材同时 `include` 与 `exclude`。

冲突时：

- `needs_clarification=True`；
- 生成一句中文问题；
- 提示词要求模型先澄清，或在回答开头明确说明冲突，不得静默选择。

## 6. 对话集成

### 6.1 意图之后

```python
decision = constraint_reasoner.analyze(
    text=ctx.message,
    slots=intent_result.slots,
)
ctx.constraint_decision = decision
ctx.constraint_context = decision.prompt_block
```

有约束时追加 thinking：

```text
🧭 约束推理：硬约束 2 项，软约束 1 项
```

### 6.2 检索之后

```python
decision = constraint_reasoner.evaluate_documents(
    retrieval_result.documents,
    ctx.constraint_decision,
)
ctx.constraint_decision = decision
retrieval_result.documents = decision.filtered_documents
retrieval_result.context = "\n\n".join(doc.page_content for doc in docs)
       retrieval_result.sources = rag_service_instance._extract_sources(docs)
```

### 6.3 生成提示词

`_build_combined_context_prompt` 增加 `constraint_context` 段，位置在 RAG 上下文之前，确保模型先看到硬约束。

## 7. API

`POST /api/v1/constraints/evaluate`

请求：

```json
{
  "text": "我对花生过敏，想吃鸡肉",
  "diet_constraints": ["花生过敏"],
  "ingredients": [],
  "candidates": [
    {"id": "d1", "title": "宫保鸡丁", "content": "## 必备原料和工具\n- 鸡胸肉\n- 花生米"},
    {"id": "d2", "title": "清蒸鸡", "content": "## 必备原料和工具\n- 鸡肉"}
  ]
}
```

响应包含：`profile`、`conflicts`、`needs_clarification`、`assessments`、`kept_ids`、`removed_ids`、`fallback_used`、`prompt_block`。

API 只做纯计算，不写数据库、不调用 LLM。

## 8. 配置

```yaml
constraint_reasoning:
  enabled: true
  strict_allergens: true
  max_candidates: 20
```

- `enabled=false`：对话与 API 都跳过约束推理。
- `strict_allergens=false`：过敏原只作为软约束（默认不建议关闭）。
- `max_candidates`：单次评估候选上限，超出部分保持原序追加。

## 9. 失败模式与降级

| 失败 | 行为 |
| --- | --- |
| ontology 数据缺失 | 返回空食材，标记 unknown，不误排除 |
| 约束解析异常 | 记录 warning，返回空 profile |
| 候选内容为空 | 标记 unknown，保留候选 |
| 全部候选被排除 | 回退原候选并提示 |
| API 输入非法 | FastAPI 返回 422 |

## 10. 安全与隐私

- 不记录用户原始查询到指标。
- API 不持久化候选内容。
- 替代建议只给方向，不承诺医学安全。
- 过敏原判断基于静态本体，必须提示用户核对配料表。
