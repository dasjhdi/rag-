# 技术设计：CookHero 语义理解能力完善 v2（方案 A2）

- 对应规格：`docs/spec/semantic-understanding-v2-spec.md`
- 版本：v1.0
- 实现状态：已实现
- 技术栈：Python 3.13 / FastAPI / LangChain 1.x / Milvus / Redis / PostgreSQL / jieba / rank-bm25

## 1. 总体设计

### 1.1 设计原则

1. 离线可验证：评测、A/B、指标、清单检查都不依赖外部服务。
2. 默认不改变主链路：多查询与本地 cross-encoder 默认关闭。
3. 失败可降级：新增能力失败时回落到既有确定性行为。
4. 可观测但不泄露：只记录标签、计数、比率和来源名。
5. 配置与代码一致：新增配置必须进入 Pydantic 模型、`config.yml` 和加载白名单。

### 1.2 数据流

```text
用户查询
  -> IntentDetector.detect
       -> 多标签意图 / 槽位 / 置信度
       -> semantic_metrics.record_intent
  -> QueryRewriter
  -> [可选] QueryPlanner.decompose
  -> RAGService._execute_retrieval
       -> CacheManager.get/set
       -> semantic_metrics.record_retrieval(cache_hit=...)
       -> Milvus hybrid search
  -> RAGService._rerank_if_needed
       -> FaultTolerantReranker
            -> 远程 SiliconFlow reranker
            -> [可选] LocalCrossEncoderReranker
            -> LexicalReranker（最终兜底）
       -> semantic_metrics.record_rerank(fallback_used=...)
  -> 生成

离线侧：
  intent_predictions.jsonl -> eval_semantic -> 总体/分意图/分桶/混淆对
  multi_query_ab.jsonl     -> eval_multi_query_ab -> 单查询 vs 多查询 + 上线建议
  recipes_manifest.json    -> check_index_manifest -> 索引一致性
```

## 2. SU-8 分意图与分桶评测

### 2.1 模块位置

- `app/evaluation/semantic_metrics.py`：新增 `LabelMetrics`、`per_label_metrics`、`confusion_pairs`、`bucket_metrics`。
- `scripts/eval_semantic.py`：在现有汇总上追加 `per_intent`、`confusions`、`buckets`。

### 2.2 指标定义

对每个标签 `L`：

```text
TP = gold=L 且 predicted=L
FP = gold!=L 且 predicted=L
FN = gold=L 且 predicted!=L
precision = TP / (TP + FP)
recall    = TP / (TP + FN)
f1        = 2PR / (P + R)
support   = gold=L 的数量
```

分母为 0 时对应指标为 `0.0`。标签集合取 gold 与 predicted 的并集，保证“只被误判成某标签”的情况也能被看到。

### 2.3 分桶

评测记录新增可选字段 `bucket`，建议取值：`recipe`、`ingredient`、`technique`、`recommendation`、`chat`。

`bucket_metrics` 对每个桶分别计算意图准确率、宏平均 F1、Hit@K、MRR 与样本数。缺失 `bucket` 的记录归入 `default`。

### 2.4 混淆对

`confusion_pairs` 返回 `(gold, predicted, count)`，按 `count` 降序、再按 `gold`、`predicted` 升序排序，默认最多 10 条。只统计错误组合，避免正确样本淹没信号。

### 2.5 输出兼容

原有输出 `records`、`intent`、`retrieval` 保持不变；新增字段只追加，不删除、不重命名。

## 3. SU-9 多查询离线 A/B

### 3.1 输入格式

`data/eval/multi_query_ab.jsonl` 每行：

```json
{"query":"有番茄和鸡蛋，想做快手菜","bucket":"recipe","relevant_ids":["r1","r2"],"single_ranked_ids":["r1","r9","r2"],"multi_ranked_ids":["r1","r2","r9"]}
```

### 3.2 逐条判定

1. 先比较 `hit_at_k`，高者胜。
2. 相同则比较 `mrr`，高者胜。
3. 仍相同则平局。

没有 `relevant_ids` 的记录跳过，不参与检索指标与胜负统计。

### 3.3 上线建议

```text
if samples < min_samples: action = insufficient_data
elif hit_delta >= min_hit_delta and mrr_delta >= min_mrr_delta and wins > losses:
    action = enable
else:
    action = keep_disabled
```

`reasons` 必须包含触发该结论的具体条件。默认 `min_samples=10`，低于该样本量不给出开启建议。

### 3.4 与线上开关的关系

A/B 只产出建议，不自动修改配置。上线动作仍是人工把 `retrieval.multi_query_enabled` 改为 `true`，并观察 SU-10 的检索指标。

## 4. SU-10 语义观测

### 4.1 采集器

`SemanticMetricsCollector` 使用 `threading.Lock` 保护计数，只保存整数与按标签/来源的计数，不保存原始查询。

内部结构：

```text
intent:    total, low_confidence, clarification_signals, by_intent
retrieval: total, hit, empty, cache_hits, cache_misses, by_source
rerank:    total, fallbacks
```

`snapshot()` 输出计数与派生比率：

```text
low_confidence_rate        = low_confidence / intent.total
clarification_signal_rate  = clarification_signals / intent.total
retrieval_hit_rate         = hit / retrieval.total
retrieval_empty_rate       = empty / retrieval.total
cache_hit_rate             = cache_hits / (cache_hits + cache_misses)
rerank_fallback_rate       = fallbacks / rerank.total
```

所有除法在分母为 0 时返回 `0.0`，并四舍五入到 4 位小数。

### 4.2 接入点

| 位置 | 事件 |
| --- | --- |
| `IntentDetector.detect` | 记录 `intent`、`confidence`、`needs_clarification` |
| `RAGService._retrieve_from_source` | 缓存命中/未命中；最终文档数（0 记为空结果） |
| `RAGService._rerank_if_needed` | 重排是否触发兜底 |

采集调用放在主逻辑之后，并用 `try/except` 包裹，确保观测失败不影响回答。

### 4.3 API

新增 `app/api/v1/endpoints/semantic_metrics.py`，提供 `GET {API_V1_STR}/semantic-metrics/summary`，返回 `semantic_metrics.snapshot()`。该接口只读，不做重置；测试通过 `reset()` 隔离状态。

### 4.4 多进程说明

当前实现是进程内计数，适合单实例和开发环境。多 worker 部署时每个进程各自计数；若需要全局聚合，后续可定期写入 Redis/PostgreSQL，或接入 Prometheus。本次不引入外部依赖。

## 5. SU-11 本地 Cross-Encoder 重排

### 5.1 设计

`LocalCrossEncoderReranker` 不直接依赖 `sentence_transformers`，而是接收 scorer 函数：

```python
Scorer = Callable[[str, list[str]], Sequence[float]]
```

测试注入假 scorer，生产注入真实模型，避免把模型加载写死在业务代码里。

### 5.2 执行流程

```text
if not documents: return []
if scorer is None: return fallback_or_identity()
try:
    scores = await asyncio.to_thread(scorer, query, [d.page_content for d in documents])
    validate len(scores) == len(documents)
    stable sort by score desc
    write rerank_score, rerank_backend="cross_encoder"
except Exception:
    return fallback_or_identity()
```

`fallback_or_identity()` 优先调用 fallback（通常是 `LexicalReranker`）；fallback 也失败时保持原序，写入 `rerank_score=0.0`、`rerank_backend="identity"`。

### 5.3 与远程重排的组合

```text
primary  = SiliconFlowReranker（若 reranker.enabled）
fallback = LocalCrossEncoderReranker（若 local_cross_encoder_enabled 且 scorer 可用）
           否则 LexicalReranker
self.reranker = FaultTolerantReranker(primary, fallback)
```

失败顺序：远程 -> 本地 cross-encoder -> 本地 BM25 -> 原序。

### 5.4 模型加载

`build_sentence_transformer_scorer(model_name)` 延迟导入 `sentence_transformers`：

- 未安装：记录 warning，返回 `None`。
- 已安装：构造 `CrossEncoder(model_name)`，返回 `lambda query, docs: model.predict([(query, d) for d in docs])`。

默认 `local_cross_encoder_enabled: false`，普通部署不会触发模型下载或额外内存占用。

### 5.5 本机启用示例

模型下载到独立目录后，在 `config.yml` 中指向本地路径即可离线加载：

```yaml
reranker:
  local_cross_encoder_enabled: true
  local_cross_encoder_model: "D:/models/bge-reranker-v2-m3"
```

`bge-reranker-v2-m3` 约 2.2GB，启动时会同步加载到内存，进程常驻内存会相应增加；
首次加载约需数秒。若需要恢复默认行为，把开关改回 `false` 即可，无需删除模型文件。

## 6. SU-12 索引清单与一致性检查

### 6.1 清单结构

```json
{"collection":"cook_hero_recipes","embedding_model":"BAAI/bge-small-zh-v1.5","corpus_version":"howtocook-v1","dimension":512,"document_count":0,"chunk_count":0,"source_digest":"sha256:...","created_at":"2026-10-17T00:00:00+00:00"}
```

`source_digest` 由 `fingerprint_texts` 生成：按输入顺序对每段文本做 UTF-8 编码，写入 8 字节长度前缀后再写入内容，最后计算 SHA-256。长度前缀用于区分 `["a", "b"]` 与 `["ab"]` 这类文本边界差异。没有提供 `texts` 时为空字符串。

### 6.2 一致性检查

`check_manifest` 比较 `collection`、`embedding_model`、`corpus_version`、`dimension` 四项。不一致时返回人类可读的问题列表，例如：

```text
embedding_model mismatch: manifest=BAAI/bge-small-zh-v1.5 expected=BAAI/bge-large-zh-v1.5
```

清单为 `None` 时返回 `["manifest_missing"]`。

### 6.3 embedding 升级 runbook

1. 修改 `config.yml` 的 `embedding.model_name` 与 `vector_store.collection_names`（建议新集合名带版本后缀）。
2. 用新模型重建 Milvus 集合，记录实际维度、文档数、分块数。
3. 运行 `build_manifest` 生成新清单，写入 `data/index/<collection>_manifest.json`。
4. 运行 `check_index_manifest.py`，确认四项全部一致。
5. 更新 `cache.corpus_version`，使旧缓存自动失效（SU-4 已支持）。
6. 切换流量前保留旧集合与旧清单，便于回滚。

## 7. 配置变更

```yaml
retrieval:
  multi_query_enabled: false
  max_queries: 3

reranker:
  local_cross_encoder_enabled: false
  local_cross_encoder_model: null
```

`load_rag_config` 需要把 `local_cross_encoder_enabled`、`local_cross_encoder_model` 从 `config.yml` 的 `reranker` 段透传给 `RerankerConfig`，避免“配置写了但代码读不到”。

## 8. 失败模式与降级

| 失败 | 行为 |
| --- | --- |
| 评测 JSONL 某行非法 | 脚本报错并以非 0 退出，指出行号 |
| A/B 样本不足 | 返回 `insufficient_data`，不自动开启 |
| 指标采集异常 | 记录 warning，主链路继续 |
| cross-encoder 未安装 | 返回 `None`，使用 BM25 兜底 |
| cross-encoder 推理异常 | 使用 BM25 兜底 |
| BM25 也无信号 | 保持原序，写 0 分 |
| 索引清单缺失 | 检查脚本返回 `manifest_missing` 并非 0 退出 |

## 9. 性能与安全

- 指标采集：常数时间字典更新，单次开销远小于 1ms。
- A/B 与评测：纯 Python 计算，40～100 条记录可忽略不计。
- cross-encoder：默认关闭；开启后只在远程重排失败时触发。
- 索引清单：只保存元数据与摘要，不保存文档正文。
- 安全：不记录用户原始查询、密钥、文档内容；清单不含连接凭据。

## 10. 上线顺序

1. 先上线评测与观测（无行为变化）。
2. 跑 A/B，确认多查询收益后再改 `multi_query_enabled`。
3. 需要更强兜底时再安装 `sentence_transformers`，配置本地 cross-encoder 并观察延迟。
4. embedding 升级严格按 runbook 执行，先新集合、后切流量、保留回滚路径。
