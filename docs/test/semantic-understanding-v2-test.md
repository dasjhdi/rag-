# 测试方案：CookHero 语义理解能力完善 v2（方案 A2）

- 对应规格：`docs/spec/semantic-understanding-v2-spec.md`
- 对应技术设计：`docs/tech/semantic-understanding-v2-tech.md`
- 版本：v1.0

## 1. 测试目标

验证 SU-8～SU-12 的功能、边界、降级与兼容性，确保：

1. 新增评测与 A/B 结果数值正确、可复现。
2. 观测指标计数与比率正确，且不改变主链路行为。
3. 本地 cross-encoder 在 scorer 正常/缺失/异常时都能稳定降级。
4. 索引清单可持久化、可校验，能发现 embedding/语料不一致。
5. 既有 v1 测试不回归。

## 2. 测试环境

- Python：项目 `.venv`（3.13）
- 依赖：pytest、pytest-asyncio、jieba、rank-bm25、LangChain
- 约束：所有用例离线运行，不连接 Milvus、Redis、PostgreSQL，不下载模型
- 临时文件：使用工作区内唯一文件名，测试结束清理；不使用 `tmp_path` fixture
- 缓存：运行 pytest 时加 `-p no:cacheprovider`

## 3. 测试分层

| 层级 | 范围 | 用例文件 |
| --- | --- | --- |
| 纯函数 | 指标、A/B、指纹、清单检查 | `tests/test_bucketed_metrics.py`、`tests/test_ab_compare.py`、`tests/test_index_manifest.py` |
| 组件 | 采集器、cross-encoder 重排器 | `tests/test_semantic_observability.py`、`tests/test_cross_encoder_reranker.py` |
| 集成 | 意图识别 → 采集器；RAG 重排 → 采集器 | `tests/test_semantic_observability.py` |
| 端到端 | 评测 runner、A/B runner、清单脚本 | 对应测试文件中的 `main()` 用例 |
| 回归 | v1 全部语义测试 | `tests/test_*.py`（排除 `tests/test_mcp.py`） |

## 4. SU-8 测试用例

| 用例 | 输入 | 期望 |
| --- | --- | --- |
| T-8.1 | `[("a","a"),("a","b"),("b","a")]` | `per_label_metrics` 含 a/b；a 的 precision=0.5、recall=0.5、f1=0.5、support=2；b 的 support=1 |
| T-8.2 | 空 pairs | 返回 `{}` |
| T-8.3 | `[("a","b"),("a","b"),("b","a")]` | 混淆对 `("a","b",2)` 在 `("b","a",1)` 前 |
| T-8.4 | 混淆对 limit=1 | 只返回第一条 |
| T-8.5 | 含 `bucket` 与不含 `bucket` 的记录 | 分桶结果包含 `default` |
| T-8.6 | 空 records | `bucket_metrics` 返回 `{}` |
| T-8.7 | 评测 JSONL 40+ 条 | 输出含 `per_intent`、`confusions`、`buckets`，总体字段仍存在 |

## 5. SU-9 测试用例

| 用例 | 输入 | 期望 |
| --- | --- | --- |
| T-9.1 | 单查询 Hit@5=0、多查询 Hit@5=1 | 该记录 multi 胜 |
| T-9.2 | 两者 Hit 相同，multi MRR 更高 | 该记录 multi 胜 |
| T-9.3 | 两者 Hit 与 MRR 都相同 | 平局 |
| T-9.4 | 多查询排序更差 | single 胜 |
| T-9.5 | 无 `relevant_ids` | 跳过，不计入 samples |
| T-9.6 | 缺失 `single_ranked_ids` | 按空列表处理 |
| T-9.7 | 样本数 < min_samples | `insufficient_data` |
| T-9.8 | Hit/MRR 均不降且 wins > losses | `enable` |
| T-9.9 | MRR 下降 | `keep_disabled`，原因含 MRR |
| T-9.10 | 分桶记录 | 输出按桶的 delta 与胜负平 |
| T-9.11 | 运行 `eval_multi_query_ab.py` | 返回 0，输出合法 JSON |

## 6. SU-10 测试用例

| 用例 | 输入 | 期望 |
| --- | --- | --- |
| T-10.1 | 记录 4 次意图，其中 1 次低置信、1 次需澄清 | total=4、low_confidence=1、clarification_signals=1 |
| T-10.2 | 记录 2 次检索，1 次命中、1 次空 | hit=1、empty=1、hit_rate=0.5、empty_rate=0.5 |
| T-10.3 | 缓存 1 命中、1 未命中 | cache_hit_rate=0.5 |
| T-10.4 | 重排 2 次、1 次兜底 | rerank_fallback_rate=0.5 |
| T-10.5 | 空采集器 snapshot | 所有比率为 0.0 |
| T-10.6 | 按意图/来源记录 | `by_intent`、`by_source` 计数正确 |
| T-10.7 | `reset()` | 全部归零 |
| T-10.8 | 多线程并发记录 | 总计数不丢 |
| T-10.9 | 假 LLM 返回意图 | `IntentDetector.detect` 后采集器 total 增加 |
| T-10.10 | 假 reranker 触发兜底 | `_rerank_if_needed` 后 fallbacks 增加 |
| T-10.11 | 调用 API summary 函数 | 返回 snapshot 结构 |

## 7. SU-11 测试用例

| 用例 | 输入 | 期望 |
| --- | --- | --- |
| T-11.1 | scorer 返回 `[0.1, 0.9, 0.5]` | 顺序为第 2、3、1 条；分数写入 metadata；backend=cross_encoder |
| T-11.2 | 同分文档 | 保持原有相对顺序 |
| T-11.3 | scorer=None + fallback | 调用 fallback，结果来自 fallback |
| T-11.4 | scorer=None + 无 fallback | 原序，分数 0，backend=identity |
| T-11.5 | scorer 抛异常 + fallback | 调用 fallback |
| T-11.6 | scorer 返回长度不匹配 + fallback | 调用 fallback |
| T-11.7 | 空文档 | 返回空，scorer 调用次数为 0 |
| T-11.8 | 同步 scorer | 正常返回，不阻塞事件循环（实现使用 `asyncio.to_thread`） |
| T-11.9 | `build_sentence_transformer_scorer` 在未安装依赖时 | 返回 None，不抛异常 |

## 8. SU-12 测试用例

| 用例 | 输入 | 期望 |
| --- | --- | --- |
| T-12.1 | 相同有序文本 | 指纹相同 |
| T-12.2 | 文本内容变化 | 指纹变化 |
| T-12.3 | build → save → load | 字段一致 |
| T-12.4 | 不存在的清单 | `load_manifest` 返回 None |
| T-12.5 | 四项全部一致 | `check_manifest` 返回 `[]` |
| T-12.6 | collection 不一致 | 返回 collection mismatch |
| T-12.7 | embedding_model 不一致 | 返回 embedding_model mismatch |
| T-12.8 | corpus_version 不一致 | 返回 corpus_version mismatch |
| T-12.9 | dimension 不一致 | 返回 dimension mismatch |
| T-12.10 | manifest=None | 返回 `["manifest_missing"]` |
| T-12.11 | 运行 `check_index_manifest.py` 一致清单 | 退出码 0，输出 issues=[] |
| T-12.12 | 运行脚本检查不一致清单 | 退出码 1，输出 issues 非空 |

## 9. 回归测试

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

已知无关失败：`tests/test_mcp.py` 中 2 个用例引用不存在的 `register_amap_mcp`，不属于本次范围。

## 10. 验收命令与预期

```bash
python -m pytest tests -q -p no:cacheprovider --ignore=tests/test_mcp.py
```

预期：全部通过（0 failed）。

```bash
python -m scripts.eval_semantic --predictions data/eval/intent_predictions.jsonl
```

预期：输出总体、`per_intent`、`confusions`、`buckets`，JSON 合法。

```bash
python -m scripts.eval_multi_query_ab --predictions data/eval/multi_query_ab.jsonl
```

预期：输出单/多查询指标、delta、胜负平、分桶与 `recommendation.action`。

```bash
python -m scripts.check_index_manifest --manifest data/index/recipes_manifest.json --collection cook_hero_recipes --embedding-model BAAI/bge-small-zh-v1.5 --corpus-version howtocook-v1 --dimension 512
```

预期：退出码 0，`issues` 为空。

## 11. 缺陷处理

- 任一 AC 未满足：回到对应需求条目修复，并补充/调整测试。
- 测试期望值写错：先核对输入与公式，再修正断言；不得为了通过而放宽实现。
- 发现无关既有缺陷：记录在最终汇报中，不在本迭代擅自修复。

---

## 12. 实际执行结果

- 执行日期：2026-10-17
- 单元/集成测试：`176 passed, 1 warning`（`tests/test_mcp.py` 除外）
- 新增用例：SU-8 至 SU-12 共 56 条，全部通过
- `scripts.eval_semantic`：退出码 0，输出 45 条记录的分意图、分桶与混淆对
- `scripts.eval_multi_query_ab`：退出码 0，输出 `recommendation.action=enable`
- `scripts.check_index_manifest`：退出码 0，输出 `ok=true`、`issues=[]`
- 唯一警告为 `jieba` 依赖的 `pkg_resources` 弃用提示，不影响功能
- 已知无关失败：`tests/test_mcp.py` 中 2 个用例引用不存在的 `register_amap_mcp`
- 本地重排冒烟测试：加载 `D:\models\bge-reranker-v2-m3` 成功；查询“番茄炒蛋怎么做”时目标文档得分 `0.9965` 并排第一，`rerank_backend=cross_encoder`
