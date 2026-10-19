# 测试方案：CookHero 约束推理能力（方案 B）

- 对应规格：`docs/spec/constraint-reasoning-spec.md`
- 对应技术设计：`docs/tech/constraint-reasoning-tech.md`
- 版本：v1.0
- 状态：已实现（2026-10-17）

## 1. 测试目标

验证 SU-13～SU-18 的解析、过滤、排序、冲突、集成、API 和离线评测，确保：

1. 硬约束不会漏判，软约束不会误排除。
2. 未知食材和未知约束不会被静默当成安全。
3. 冲突可解释、可澄清。
4. 无约束请求行为不变。
5. 全部用例离线运行。

## 2. 测试环境

- Python：项目 `.venv`（3.13）
- 依赖：pytest、pytest-asyncio、现有 LangChain Document
- 约束：不连接 Milvus、Redis、PostgreSQL，不下载模型
- 临时文件：使用工作区内唯一文件名，测试结束清理
- 缓存：运行 pytest 加 `-p no:cacheprovider`

## 3. 测试分层

| 层级 | 范围 | 用例文件 |
| --- | --- | --- |
| 纯函数 | 解析、冲突、软打分、替代建议 | `tests/test_constraint_parser.py`、`tests/test_constraint_conflicts.py` |
| 组件 | 食材提取、文档评估、过滤回退 | `tests/test_constraint_evaluator.py` |
| 集成 | 对话上下文、提示词、RAG 过滤 | `tests/test_constraint_integration.py` |
| API | 请求/响应结构 | `tests/test_constraint_api.py` |
| 端到端 | 评测脚本与数据集 | `tests/test_constraint_eval.py` |
| 回归 | v1/v2 全部语义测试 | `tests/test_*.py`（排除 `tests/test_mcp.py`） |

## 4. SU-13 测试用例

| 用例 | 输入 | 期望 |
| --- | --- | --- |
| T-13.1 | `diet_constraints=["花生过敏"]` | 生成 allergen=peanut，hard |
| T-13.2 | `"我对牛奶过敏"` | 生成 allergen=milk，hard |
| T-13.3 | `"我是纯素"` | 生成 vegan + vegetarian，hard |
| T-13.4 | `"无麸质，低脂，高蛋白"` | gluten_free hard；low_fat/high_protein soft |
| T-13.5 | `"不吃猪肉"` | exclude_ingredient=猪肉，hard |
| T-13.6 | 重复约束 | 只保留一条 |
| T-13.7 | `"不要放香菜"` | exclude_ingredient=香菜 |
| T-13.8 | 未知约束 `"不要放某某神秘酱"` | 进入 unknown_terms |
| T-13.9 | `ingredients=["鸡蛋"]` | include_ingredient=鸡蛋，soft |

## 5. SU-14 测试用例

| 用例 | 输入 | 期望 |
| --- | --- | --- |
| T-14.1 | 菜谱含“花生米”，花生过敏 | 被排除，证据含花生 |
| T-14.2 | 菜谱含“五花肉”，素食 | 被排除，原因含 vegetarian |
| T-14.3 | 菜谱含“鸡蛋”，纯素 | 被排除 |
| T-14.4 | 菜谱含“面粉”，无麸质 | 被排除 |
| T-14.5 | 菜谱含“猪肉”，不吃猪肉 | 被排除 |
| T-14.6 | 空内容候选 | `unknown=True`，不排除 |
| T-14.7 | 全部候选违规 | 回退原候选，`fallback_used=True` |
| T-14.8 | 两个候选软分不同 | 高分在前；同分保持原序 |
| T-14.9 | 标题“鱼香肉丝”，鱼过敏 | 不因“鱼”字误排除 |

## 6. SU-15 测试用例

| 用例 | 输入 | 期望 |
| --- | --- | --- |
| T-15.1 | 低脂 + 油炸菜谱 | 软约束未命中，不排除 |
| T-15.2 | 低脂 + 清蒸菜谱 | 软约束命中，排序靠前 |
| T-15.3 | 控糖 + 冰糖菜谱 | 软约束未命中 |
| T-15.4 | 高蛋白 + 鸡胸肉菜谱 | 软约束命中 |
| T-15.5 | 替代建议 | 包含“需确认” |

## 7. SU-16 测试用例

| 用例 | 输入 | 期望 |
| --- | --- | --- |
| T-16.1 | 纯素 + 鸡蛋 | 冲突 |
| T-16.2 | 素食 + 五花肉 | 冲突 |
| T-16.3 | 无麸质 + 面粉 | 冲突 |
| T-16.4 | 花生过敏 + 花生 | 冲突 |
| T-16.5 | 包含鸡蛋 + 排除鸡蛋 | 冲突 |
| T-16.6 | 冲突时 | `needs_clarification=True`，问题非空 |

## 8. SU-17 测试用例

| 用例 | 输入 | 期望 |
| --- | --- | --- |
| T-17.1 | 有约束的 ChatContext | `constraint_context` 非空 |
| T-17.2 | 无约束 | `constraint_context` 为空，主链路不变 |
| T-17.3 | 检索结果含违规候选 | 过滤后 documents/context/sources 同步更新 |
| T-17.4 | 提示词构建 | 包含硬约束与“无法确认”提示 |
| T-17.5 | 约束推理抛异常 | 记录 warning，对话继续 |
| T-17.6 | API 正常请求 | 返回 kept/removed/assessments |
| T-17.7 | API 无候选 | 返回空评估，不报错 |

## 9. SU-18 测试用例

| 用例 | 输入 | 期望 |
| --- | --- | --- |
| T-18.1 | 评测集 12+ 条 | 逐条输出 pass/fail |
| T-18.2 | 全部预期正确 | 退出码 0，通过率 1.0 |
| T-18.3 | 人为错误预期 | 退出码 1 |
| T-18.4 | 配置默认值 | enabled=true、strict_allergens=true |
| T-18.5 | `enabled=false` | 跳过约束推理 |

## 10. 回归测试

必须保持通过：

- `tests/test_structured_output.py`
- `tests/test_intent_upgrade.py`
- `tests/test_query_planner.py`
- `tests/test_text_tokenizer.py`
- `tests/test_reranker_fallback.py`
- `tests/test_cache_scope.py`
- `tests/test_multi_query_merge.py`
- `tests/test_knowledge_ontology.py`
- `tests/test_vision_rag_bridge.py`
- `tests/test_semantic_metrics.py`
- `tests/test_bucketed_metrics.py`
- `tests/test_ab_compare.py`
- `tests/test_semantic_observability.py`
- `tests/test_cross_encoder_reranker.py`
- `tests/test_index_manifest.py`

`tests/test_mcp.py` 中旧函数名 `register_amap_mcp` 已改为公开入口
`register_mcp_servers()`，该文件 3 项测试现已通过。

## 11. 验收命令与预期

```bash
python -m pytest tests -q -p no:cacheprovider
```

预期：全部通过。

```bash
python -m scripts.eval_constraints --cases data/eval/constraint_cases.jsonl
```

预期：退出码 0，`passed == total`。

## 12. 缺陷处理

- 硬约束漏判：视为 P0，必须补测试后修复。
- 软约束误排除：视为 P1，调整规则或严重级别。
- 未知项被当成安全：视为 P0，改为 unknown 并补测试。
- 发现无关既有缺陷：记录在最终汇报中，不擅自修复。

## 13. 实际执行结果

### 13.1 新增测试

| 测试文件 | 结果 |
| --- | --- |
| `tests/test_constraint_parser.py` | 通过 |
| `tests/test_constraint_evaluator.py` | 通过 |
| `tests/test_constraint_conflicts.py` | 通过 |
| `tests/test_constraint_integration.py` | 通过 |
| `tests/test_constraint_api.py` | 通过 |
| `tests/test_constraint_eval.py` | 通过 |

合计 51 项新增测试全部通过。

### 13.2 全量回归

```text
python -m pytest tests -q -p no:cacheprovider
230 passed, 1 warning
```

### 13.3 离线评测

```text
python -m scripts.eval_constraints --cases data/eval/constraint_cases.jsonl
总计 16 条，通过 16 条，失败 0 条，通过率 100.00%
```

### 13.4 说明

- 全量测试包含 `tests/test_mcp.py`；该文件会访问高德 MCP 网络接口，
  缺少 `AMAP_API_KEY` 时会跳过实际注册。
- 评测脚本不连接网络、Milvus、Redis、PostgreSQL，也不下载模型。
