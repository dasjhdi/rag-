# 需求规格：CookHero 语义理解能力完善 v2（方案 A2）

- 规格编号：`SU-SPEC-002`
- 版本：v1.0
- 状态：已实现
- 上游规格：`SU-SPEC-001`（语义理解能力完善 v1）
- 对应推荐方案：`后续语义理解推荐方案`

---

## 1. 背景与目标

### 1.1 v1 已完成

v1 已交付：结构化输出、多标签意图 + 槽位 + 置信度、查询分解、中文领域分词与本地 BM25、重排兜底、缓存 scope、食材/过敏原本体、多模态到检索桥接、离线评测基线。

### 1.2 本次要解决的缺口

| 编号 | 缺口 | 影响 |
| --- | --- | --- |
| G-5 | 评测只有总体指标，没有分意图、分桶和混淆对分析 | 无法定位弱意图与弱场景 |
| G-6 | 查询分解已实现但缺少离线 A/B 证据 | 无法判断是否值得开启，存在盲目上线风险 |
| G-7 | 缺少运行时语义观测 | 低置信度、澄清信号、检索空结果、缓存命中、重排兜底都不可见 |
| G-8 | 本地重排只有 BM25，没有 cross-encoder | 远程重排失败时排序质量上限有限 |
| G-9 | embedding 升级与索引重建缺少指纹和一致性检查 | 容易出现“模型换了、索引没换”的静默脏数据 |

### 1.3 目标

1. 评测支持分意图、分桶、混淆对，并扩充领域评测集。
2. 提供查询分解的离线 A/B 对比与上线决策规则。
3. 提供进程内语义观测指标与只读 API。
4. 提供可插拔的本地 cross-encoder 重排，默认关闭且无强制新依赖。
5. 提供索引清单、语料指纹与一致性检查脚本，支撑 embedding 升级和重建索引。

### 1.4 非目标

- 不做线上流量分桶与实时 A/B 实验平台。
- 不自动下载 embedding 或 cross-encoder 模型，不自动重建 Milvus 索引。
- 不接入 Prometheus/OpenTelemetry 等外部指标系统。
- 不实现通用约束求解器；约束推理仍作为后续独立方案。

---

## 2. 需求条目

### SU-8 分意图与分桶评测

**需求**：在现有总体指标之外，提供按意图标签、按业务桶的指标，以及混淆对分析。

**接口**：

```python
# app/evaluation/semantic_metrics.py
@dataclass(frozen=True)
class LabelMetrics:
    precision: float
    recall: float
    f1: float
    support: int

def per_label_metrics(pairs: Sequence[tuple[str, str]]) -> dict[str, LabelMetrics]: ...
def confusion_pairs(
    pairs: Sequence[tuple[str, str]], *, limit: int = 10
) -> list[tuple[str, str, int]]: ...
def bucket_metrics(
    records: Sequence[dict], *, bucket_key: str = "bucket"
) -> dict[str, dict]: ...
```

**验收标准**：

- AC-8.1 `per_label_metrics` 覆盖 gold 与 predicted 出现过的全部标签，返回 precision/recall/f1/support；未出现的标签 support 为 0。
- AC-8.2 `confusion_pairs` 只统计 gold != predicted 的组合，按次数降序、再按标签名升序，`limit` 生效。
- AC-8.3 `bucket_metrics` 按 `bucket_key` 分组；缺失该字段的记录归入 `default`；空输入返回 `{}`。
- AC-8.4 `scripts/eval_semantic.py` 输出新增 `per_intent`、`confusions`、`buckets`，原有 `records`/`intent`/`retrieval` 字段保持兼容。
- AC-8.5 `data/eval/intent_predictions.jsonl` 至少 40 条，覆盖 5 类意图与 5 个业务桶。

**测试映射**：`tests/test_bucketed_metrics.py`、`tests/test_semantic_metrics.py`

---

### SU-9 查询分解离线 A/B 对比

**需求**：对同一批查询，比较单查询与多查询两套排序结果，给出收益、胜负平和上线建议。

**接口**：

```python
# app/evaluation/ab_compare.py
def compare_configurations(
    records: Sequence[dict], *, k: int = 5
) -> dict: ...

def recommend_rollout(
    result: dict,
    *,
    min_samples: int = 10,
    min_hit_delta: float = 0.0,
    min_mrr_delta: float = 0.0,
) -> dict: ...
```

输入记录字段：`query`、`bucket`、`relevant_ids`、`single_ranked_ids`、`multi_ranked_ids`。

**验收标准**：

- AC-9.1 逐条比较先看 Hit@K，再看 MRR；两者都相同记为平局。
- AC-9.2 汇总输出两套配置的 samples/Hit@K/MRR、delta、wins/losses/ties 与分桶 delta。
- AC-9.3 缺失排序列表按空列表处理；没有 `relevant_ids` 的记录不参与检索指标。
- AC-9.4 样本数小于 `min_samples` 返回 `insufficient_data`；Hit@K 与 MRR 均不低于阈值且 wins > losses 返回 `enable`；其余返回 `keep_disabled`，并给出原因列表。
- AC-9.5 新增 `scripts/eval_multi_query_ab.py`，支持 `--predictions`、`--k`、`--min-samples`，输出 JSON。
- AC-9.6 新增 `data/eval/multi_query_ab.jsonl`，至少 12 条，覆盖多查询收益、持平、退化三类情况。

**测试映射**：`tests/test_ab_compare.py`

---

### SU-10 语义观测指标

**需求**：在进程内记录语义链路关键事件，并提供只读汇总接口。

**接口**：

```python
# app/observability/semantic_metrics.py
class SemanticMetricsCollector:
    def record_intent(
        self, *, intent: str, confidence: float, needs_clarification: bool
    ) -> None: ...
    def record_retrieval(
        self, *, source: str, doc_count: int, cache_hit: bool
    ) -> None: ...
    def record_rerank(self, *, fallback_used: bool) -> None: ...
    def snapshot(self) -> dict: ...
    def reset(self) -> None: ...

semantic_metrics = SemanticMetricsCollector()
```

**验收标准**：

- AC-10.1 计数正确：意图总数、低置信度数、澄清信号数、检索总数/命中/空结果、缓存命中/未命中、重排总数/兜底数。
- AC-10.2 比率在分母为 0 时返回 `0.0`，不抛异常。
- AC-10.3 输出包含 `by_intent` 与 `by_source` 分组计数。
- AC-10.4 `reset()` 清空全部计数。
- AC-10.5 采集器线程安全；采集失败不得中断主链路。
- AC-10.6 `IntentDetector.detect`、`RAGService` 的缓存/检索/重排路径接入采集；新增只读接口 `GET {API_V1_STR}/semantic-metrics/summary`。

**测试映射**：`tests/test_semantic_observability.py`

---

### SU-11 本地 Cross-Encoder 重排

**需求**：提供可插拔的本地 cross-encoder 重排器，作为远程重排失败后的第二层兜底；默认关闭，不引入强制新依赖。

**接口**：

```python
# app/rag/rerankers/cross_encoder_reranker.py
class LocalCrossEncoderReranker(BaseReranker):
    def __init__(
        self,
        scorer: Optional[Callable[[str, list[str]], Sequence[float]]],
        *,
        fallback: Optional[BaseReranker] = None,
        score_key: str = "rerank_score",
    ): ...
    async def rerank(self, query: str, documents: list[Document]) -> list[Document]: ...

def build_sentence_transformer_scorer(
    model_name: str,
) -> Optional[Callable[[str, list[str]], Sequence[float]]]: ...
```

**配置**：

```yaml
reranker:
  local_cross_encoder_enabled: false
  local_cross_encoder_model: null
```

**验收标准**：

- AC-11.1 scorer 返回合法分数时按分数降序稳定排序，写入 `metadata["rerank_score"]` 与 `metadata["rerank_backend"]="cross_encoder"`。
- AC-11.2 scorer 为 None 时调用 fallback；无 fallback 时保持原序、写入 0 分与 `rerank_backend="identity"`。
- AC-11.3 scorer 抛异常或返回长度不匹配时调用 fallback；fallback 也失败时保持原序。
- AC-11.4 空文档列表直接返回空，不调用 scorer。
- AC-11.5 默认配置关闭；`sentence_transformers` 不可用时不影响服务启动。
- AC-11.6 同步 scorer 通过 `asyncio.to_thread` 执行，避免阻塞事件循环。

**测试映射**：`tests/test_cross_encoder_reranker.py`

---

### SU-12 索引清单与一致性检查

**需求**：为 Milvus 集合生成可持久化的索引清单，记录集合、embedding 模型、语料版本、维度、文档/分块数量和语料指纹，并提供一致性检查。

**接口**：

```python
# app/rag/vector_stores/index_manifest.py
def fingerprint_texts(texts: Iterable[str]) -> str: ...
def build_manifest(
    *,
    collection: str,
    embedding_model: str,
    corpus_version: str,
    dimension: int,
    document_count: int = 0,
    chunk_count: int = 0,
    texts: Optional[Iterable[str]] = None,
) -> dict: ...
def save_manifest(path: str | Path, manifest: dict) -> None: ...
def load_manifest(path: str | Path) -> Optional[dict]: ...
def check_manifest(
    manifest: Optional[dict],
    *,
    collection: str,
    embedding_model: str,
    corpus_version: str,
    dimension: int,
) -> list[str]: ...
```

**验收标准**：

- AC-12.1 相同有序文本生成相同指纹；内容变化指纹变化。
- AC-12.2 `save_manifest`/`load_manifest` 往返一致；文件不存在时 `load_manifest` 返回 `None`。
- AC-12.3 `check_manifest` 能检出集合、模型、语料版本、维度四类不一致；一致时返回空列表。
- AC-12.4 清单缺失时返回 `manifest_missing`，脚本以非 0 退出。
- AC-12.5 新增 `scripts/check_index_manifest.py`，输出 JSON 检查结果。
- AC-12.6 新增 `data/index/recipes_manifest.json` 示例清单，与技术文档中的 embedding 升级 runbook 一致。

**测试映射**：`tests/test_index_manifest.py`

---

## 3. 非功能性需求

- NFR-6 可离线性：新增测试不依赖网络、Milvus、Redis、PostgreSQL，也不下载模型。
- NFR-7 向后兼容：评测输出只新增字段，不改变既有字段含义；采集器与重排器默认不改变主链路行为。
- NFR-8 低开销：采集器为内存计数，单次记录应为常数时间，不引入外部依赖。
- NFR-9 默认安全：`multi_query_enabled` 与 `local_cross_encoder_enabled` 默认关闭。
- NFR-10 无敏感信息：指标与清单不得记录用户原始查询、密钥或文档正文。

---

## 4. 交付物清单

| 需求 | 新增 | 修改 |
| --- | --- | --- |
| SU-8 | `tests/test_bucketed_metrics.py` | `app/evaluation/semantic_metrics.py`、`scripts/eval_semantic.py`、`data/eval/intent_predictions.jsonl` |
| SU-9 | `app/evaluation/ab_compare.py`、`scripts/eval_multi_query_ab.py`、`data/eval/multi_query_ab.jsonl`、`tests/test_ab_compare.py` | — |
| SU-10 | `app/observability/__init__.py`、`app/observability/semantic_metrics.py`、`app/api/v1/endpoints/semantic_metrics.py`、`tests/test_semantic_observability.py` | `app/conversation/intent.py`、`app/services/rag_service.py`、`app/main.py` |
| SU-11 | `app/rag/rerankers/cross_encoder_reranker.py`、`tests/test_cross_encoder_reranker.py` | `app/config/rag_config.py`、`app/config/config_loader.py`、`config.yml`、`app/services/rag_service.py` |
| SU-12 | `app/rag/vector_stores/index_manifest.py`、`scripts/check_index_manifest.py`、`data/index/recipes_manifest.json`、`tests/test_index_manifest.py` | — |

---

## 5. 验收方法

```bash
# 1. 语义理解相关全量离线单测（排除既有的 MCP 用例）
python -m pytest tests -q --ignore=tests/test_mcp.py

# 2. 总体语义评测（含分意图、分桶、混淆对）
python -m scripts.eval_semantic --predictions data/eval/intent_predictions.jsonl

# 3. 多查询 A/B 离线对比
python -m scripts.eval_multi_query_ab --predictions data/eval/multi_query_ab.jsonl

# 4. 索引清单一致性检查
python -m scripts.check_index_manifest \
  --manifest data/index/recipes_manifest.json \
  --collection cook_hero_recipes \
  --embedding-model BAAI/bge-small-zh-v1.5 \
  --corpus-version howtocook-v1 \
  --dimension 512
```

四条命令全部成功，且测试无失败，视为本次迭代验收通过。

---

## 6. 实现与验收结果

- 实现日期：2026-10-17
- 测试结果：`176 passed`（排除既有 `tests/test_mcp.py`）
- 新增测试：`test_bucketed_metrics.py`、`test_ab_compare.py`、`test_semantic_observability.py`、`test_cross_encoder_reranker.py`、`test_index_manifest.py`
- 语义评测：45 条记录，意图准确率 `0.8889`、宏平均 F1 `0.8911`、Hit@5 `0.8889`、MRR `0.7778`
- 多查询 A/B：15 条记录，Hit@5 从 `0.7333` 提升到 `0.8`，MRR 从 `0.5556` 提升到 `0.8`，建议 `enable`
- 索引清单：`data/index/recipes_manifest.json` 检查通过，`issues=[]`
- 默认配置：`multi_query_enabled: false`、`local_cross_encoder_enabled: false`
- 本机部署：已下载 `BAAI/bge-reranker-v2-m3` 到 `D:\models\bge-reranker-v2-m3`，并在 `config.yml` 中启用本地重排
- 已知无关失败：`tests/test_mcp.py` 中 2 个用例引用不存在的 `register_amap_mcp`，属于既有问题，未在本迭代处理。
