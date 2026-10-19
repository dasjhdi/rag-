# 需求规格：CookHero 语义理解能力完善（方案 A）

- 规格编号：`SU-SPEC-001`
- 版本：v1.1
- 状态：已实现，语义理解相关测试通过
- 对应推荐方案：`推荐方案 A. 语义理解怎么做得更好`
- 技术栈：Python 3.12+ / FastAPI / LangChain 1.x / Milvus / Redis / PostgreSQL

---

## 1. 背景与目标

### 1.1 现状缺口

CookHero 的语义理解链路已完整（意图识别→改写→混合检索→重排→生成），但存在四类结构性缺口：

| 编号 | 缺口 | 证据 |
| --- | --- | --- |
| G-1 | 结构化输出依赖正则兜底，无 schema 强约束、无失败重试 | `app/utils/structured_json.py` |
| G-2 | 意图识别为单标签 5 类、无置信度、无槽位抽取，低置信度直接猜测 | `app/conversation/intent.py:129` |
| G-3 | 检索为单查询混合召回，无查询分解；中文分词无领域词典与本地兜底；远程重排失败仅降级为原序 | `app/rag/pipeline/retrieval.py:41`、`app/rag/rerankers/siliconflow_reranker.py:56` |
| G-4 | 语义缓存 scope 未含语料版本与 embedding 版本，存在脏读；多模态识别结果未回流检索 | `app/rag/cache/cache_manager.py:133`、`app/vision/agent.py:283` |

### 1.2 目标

1. 关键 LLM 结构化调用具备 schema 强约束 + 校验失败重试 + 确定性降级。
2. 意图理解由"单标签分类"升级为"多标签意图 + 领域槽位 + 置信度 + 澄清信号"。
3. 检索侧引入查询分解、中文领域分词与本地词法重排兜底。
4. 建立食材/过敏原本体，作为结构化语义底座（并为后续约束推理提供输入）。
5. 打通多模态识别结果到检索的反向回流。
6. 建立可离线运行、可量化的语义评测基线。

### 1.3 非目标（本迭代不做）

- 更换 embedding 模型并重建 Milvus 索引（`embedding.model_name` 配置项已支持，切换与重建属运维动作）。
- 引入本地大参数量 cross-encoder 重排模型（本迭代仅做轻量词法兜底）。
- 食谱截图 OCR。
- CI 流水线接入（本迭代交付可被 CI 直接调用的离线 runner）。

---

## 2. 需求条目

### SU-1 结构化输出层

**需求**：提供统一的结构化输出调用入口，约束顺序为「原生 json_schema → 携带错误的修复重试 → 正则兜底解析」。

**接口**：

```python
# app/llm/structured.py
class StructuredOutputError(Exception): ...

async def invoke_structured(
    invoker,                      # LLMInvoker 或任意具备 ainvoke(messages, **kwargs) 的对象
    messages: list,
    schema: type[BaseModel],
    *,
    max_attempts: int = 2,
    validator: Callable[[BaseModel], None] | None = None,
    use_native_schema: bool = True,
) -> BaseModel: ...

def supports_native_json_schema(invoker) -> bool: ...   # 带进程内缓存的能力探测
def reset_capability_cache() -> None: ...                # 测试用
```

**验收标准**：

- AC-1.1 原生支持时使用 `response_format={"type": "json_schema", ...}`；不支持时退化为 `{"type": "json_object"}`。
- AC-1.2 首次解析/校验失败时，携带校验错误信息进行至多 `max_attempts` 次修复重试。
- AC-1.3 全部失败时抛 `StructuredOutputError`，信息含最后一次原始响应片段与错误原因。
- AC-1.4 `validator` 抛出的异常与 `ValidationError` 走同一重试路径。
- AC-1.5 能力探测结果缓存，同一 invoker 不重复探测。
- AC-1.6 不改变 `extract_first_valid_json` 既有行为。

**测试映射**：`tests/test_structured_output.py`

---

### SU-2 意图理解升级（多标签 + 槽位 + 置信度）

**需求**：`IntentDetector.detect()` 在保持既有返回字段语义不变的前提下，新增多标签意图、领域槽位与置信度，低置信度时给出澄清信号。

**接口**：

```python
# app/conversation/intent.py
@dataclass
class QuerySlots:
    ingredients: list[str]
    dish_names: list[str]
    tastes: list[str]
    meal_type: str | None            # breakfast/lunch/dinner/snack
    time_budget_minutes: int | None
    diet_constraints: list[str]
    servings: int | None

@dataclass
class IntentDetectionResult:
    need_rag: bool                   # 兼容字段：由 intents 推导
    intent: QueryIntent              # 兼容字段：主意图
    reason: str
    raw: dict
    intents: list[QueryIntent]       # 新增
    confidence: float                # 新增
    slots: QuerySlots                # 新增
    needs_clarification: bool        # 新增
```

**验收标准**：

- AC-2.1 新格式响应可解析出多标签 `intents`、`confidence` 与完整 `slots`。
- AC-2.2 旧格式响应（仅 `need_rag`/`intent`/`reason`）仍可解析，`intents` 回填主意图，`slots` 为空。
- AC-2.3 `need_rag` 与 `intents` 一致：含任一非闲聊意图为 `True`，全闲聊或为空为 `False`。
- AC-2.4 `confidence < CONFIDENCE_THRESHOLD`（默认 0.5）时 `needs_clarification=True`。
- AC-2.5 LLM 异常或输出不可解析时返回安全默认（`need_rag=False`、`general_chat`），不抛异常。
- AC-2.6 槽位清洗：未知餐次置 `None`，非法时间置 `None`，列表去重去空串。

**测试映射**：`tests/test_intent_upgrade.py`

---

### SU-3 检索语义增强

#### SU-3.1 查询分解（multi-query）

**需求**：提供 LLM 驱动的查询分解器，将复杂查询拆为互补子查询，与原查询合并去重并限制数量。

**接口**：

```python
# app/rag/pipeline/query_planner.py
class QueryPlanner:
    async def decompose(self, query: str, *, history_text: str = "",
                        user_id=None, conversation_id=None) -> list[str]: ...

def merge_queries(original: str, generated: Sequence[str], max_queries: int) -> list[str]  # 纯函数
```

**验收标准**：

- AC-3.1.1 输出首项恒为原查询（保证召回不劣化）。
- AC-3.1.2 归一化后去重，长度不超过 `max_queries`。
- AC-3.1.3 LLM 失败或返回空时降级为 `[原查询]`。
- AC-3.1.4 `merge_queries` 为纯函数，可独立单测。

**测试映射**：`tests/test_query_planner.py`

#### SU-3.2 中文领域分词与本地 BM25

**需求**：提供基于 jieba + 领域词典的中文分词与本地 BM25 排序工具，作为 Milvus 内建 BM25 的对照与兜底。

**接口**：

```python
# app/rag/pipeline/text_tokenizer.py
def load_domain_terms() -> list[str]: ...
def tokenize(text: str, *, drop_stopwords: bool = True) -> list[str]: ...
def bm25_scores(query: str, docs: Sequence[str]) -> list[float]: ...
def bm25_rank(query: str, docs: Sequence[str], top_k: int) -> list[tuple[int, float]]: ...
```

**验收标准**：

- AC-3.2.1 领域词（如「红烧肉」「番茄炒蛋」）不被切碎。
- AC-3.2.2 停用词被移除；空输入返回空列表。
- AC-3.2.3 `bm25_rank` 对含目标关键词的文档给更高分且顺序正确。
- AC-3.2.4 词典文件缺失时降级为纯 jieba 分词，不抛异常。

**测试映射**：`tests/test_text_tokenizer.py`

#### SU-3.3 重排兜底

**需求**：远程 reranker 不可用时，用本地词法重排保证排序不劣化到原序。

**接口**：

```python
# app/rag/rerankers/lexical_reranker.py
class LexicalReranker(BaseReranker):
    async def rerank(self, query: str, documents: list[Document]) -> list[Document]: ...

class FaultTolerantReranker(BaseReranker):
    def __init__(self, primary: BaseReranker | None, fallback: BaseReranker): ...
```

**验收标准**：

- AC-3.3.1 `LexicalReranker` 按 BM25 相关性重排并写入 `metadata["rerank_score"]`。
- AC-3.3.2 主重排器抛异常或返回空时切换到兜底实现。
- AC-3.3.3 主重排器正常时兜底实现不被调用。
- AC-3.3.4 空文档列表直接返回空，不调用任何实现。

**测试映射**：`tests/test_reranker_fallback.py`

---

### SU-4 语义缓存 scope 维度

**需求**：缓存隔离维度由单一 scope 字符串升级为结构化 scope（用户 + 语料版本 + embedding 版本）。

**接口**：

```python
# app/rag/cache/cache_manager.py
def build_cache_scope(user_id: str | None = None, *,
                      corpus_version: str | None = None,
                      embedding_model: str | None = None) -> str: ...
```

**验收标准**：

- AC-4.1 不同 `corpus_version` 或 `embedding_model` 生成不同 scope，互不命中。
- AC-4.2 相同输入生成相同 scope（幂等）。
- AC-4.3 无任何维度时退化为 `global`，保持既有行为兼容。
- AC-4.4 L1 key 包含完整 scope，scope 不同则 key 不同。

**测试映射**：`tests/test_cache_scope.py`

---

### SU-5 食材与过敏原本体

**需求**：建立可扩展的食材归一化、别名映射、过敏原推导与饮食标签推导能力。

**接口**：

```python
# app/knowledge/ontology.py
def normalize_ingredient(name: str) -> str: ...
def canonicalize_ingredients(names: Iterable[str]) -> list[str]: ...
def allergens_for(names: Iterable[str]) -> set[str]: ...
def diet_tags_for(names: Iterable[str]) -> set[str]: ...
def explain_allergens(names: Iterable[str]) -> dict[str, list[str]]: ...
```

**验收标准**：

- AC-5.1 别名归一化：土豆/洋芋/马铃薯 归一到同一标准名。
- AC-5.2 过敏原覆盖直接命中与别名命中（花生酱 → peanut）。
- AC-5.3 饮食标签识别非素食成分并据此排除 vegetarian/vegan。
- AC-5.4 未知食材不抛异常，返回空标签集合。
- AC-5.5 输入去重、忽略大小写与首尾空白；空输入返回空结果。

**测试映射**：`tests/test_knowledge_ontology.py`

---

### SU-6 多模态到检索的桥接

**需求**：图片识别出的食材/菜名回流为检索查询的一部分，使「拍照找菜谱」链路可检索。

**接口**：

```python
# app/vision/agent.py
class VisionAgent:
    def build_retrieval_query(self, result: VisionAnalysisResult,
                              user_query: str = "") -> str | None: ...
```

**验收标准**：

- AC-6.1 非食物图片返回 `None`。
- AC-6.2 识别到食材时返回查询含归一化食材名。
- AC-6.3 无食材但有菜名时返回菜名查询。
- AC-6.4 两者皆无时返回 `None`（回落原文字查询）。
- AC-6.5 输出为单行、去重、长度受控。

**测试映射**：`tests/test_vision_rag_bridge.py`

---

### SU-7 语义评测基线

**需求**：提供纯函数指标与可离线运行的评测 runner，覆盖意图分类与检索排序质量。

**接口**：

```python
# app/evaluation/semantic_metrics.py
def intent_accuracy(pairs: Sequence[tuple[str, str]]) -> float: ...
def intent_macro_f1(pairs: Sequence[tuple[str, str]]) -> float: ...
def hit_at_k(ranked_ids: Sequence[str], relevant: set[str], k: int) -> float: ...
def mrr(ranked_ids: Sequence[str], relevant: set[str]) -> float: ...
def average(values: Sequence[float]) -> float: ...
```

**验收标准**：

- AC-7.1 指标在构造样本上给出预期数值（含空集合与无命中边界）。
- AC-7.2 `hit_at_k` 的 `k` 截断正确，`k<=0` 返回 0.0。
- AC-7.3 `mrr` 无命中返回 0.0，命中位置为 1 时返回 1.0。
- AC-7.4 评测数据以 JSONL 存于 `data/eval/`，runner 支持 `--predictions` 离线模式。

**测试映射**：`tests/test_semantic_metrics.py`

---

## 3. 非功能性需求

- NFR-1 向后兼容：`IntentDetectionResult` 既有字段与语义不变，`conversation_service` 无需改动即可运行。
- NFR-2 可选开关：新增检索能力由配置开关控制，默认不改变既有成本与延迟模型。
- NFR-3 失败降级：所有新增 LLM 调用失败时回落既有确定性行为，不中断主链路。
- NFR-4 可离线性：新增模块的单测不依赖网络、Milvus、Redis、PostgreSQL。
- NFR-5 可观测：沿用 `llm_context` 做用量统计，沿用 `logging` 输出诊断。

---

## 4. 交付物清单

| 需求 | 新增 | 修改 |
| --- | --- | --- |
| SU-1 | `app/llm/structured.py` | `app/llm/__init__.py` |
| SU-2 | — | `app/conversation/intent.py` |
| SU-3.1 | `app/rag/pipeline/query_planner.py` | `app/services/rag_service.py`、`app/rag/pipeline/retrieval.py`、`app/config/rag_config.py`、`config.yml` |
| SU-3.2 | `app/rag/pipeline/text_tokenizer.py`、`app/rag/pipeline/reference/domain_dict.txt` | — |
| SU-3.3 | `app/rag/rerankers/lexical_reranker.py` | `app/services/rag_service.py`、`app/rag/rerankers/siliconflow_reranker.py` |
| SU-4 | — | `app/rag/cache/cache_manager.py`、`app/rag/cache/__init__.py`、`app/services/rag_service.py`、`app/config/rag_config.py`、`app/config/config_loader.py`、`config.yml` |
| SU-5 | `app/knowledge/__init__.py`、`app/knowledge/ontology.py`、`app/knowledge/data/ingredients.json` | — |
| SU-6 | — | `app/vision/agent.py`、`app/services/conversation_service.py` |
| SU-7 | `app/evaluation/semantic_metrics.py`、`scripts/eval_semantic.py`、`data/eval/*.jsonl` | — |
| 测试 | `tests/test_*.py`、`pytest.ini` | — |

---

## 5. 验收方法

```bash
# 语义理解相关全量离线单测（排除既有的 MCP 用例）
python -m pytest tests -q --ignore=tests/test_mcp.py

# 语义评测（离线模式，读取预置预测结果）
python -m scripts.eval_semantic --predictions data/eval/intent_predictions.jsonl
```

全部用例通过即视为本次迭代验收通过；任一 AC 未满足需回到对应需求条目修复。

---

## 6. 实现与验收结果

- 实现日期：2026-10-17
- 测试结果：`120 passed`（`tests/test_mcp.py` 除外）
- 评测结果：意图准确率 `0.8333`、意图宏平均 F1 `0.8267`、Hit@5 `0.8`、MRR `0.55`
- 默认配置：`multi_query_enabled: false`、`max_queries: 3`、`corpus_version: "howtocook-v1"`
- 已知无关失败：`tests/test_mcp.py` 的 2 个用例引用了不存在的 `register_amap_mcp`，属于本次改动之外的既有问题，未在本迭代处理。
