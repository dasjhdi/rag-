# CookHero 模型清单与替换指南

> 最后更新：2026-10-29
> 说明：模型名、参数与阈值集中在 `config.yml`；密钥集中在 `.env`。本文档同时标注了代码读取位置，换模型时按图索骥即可。

---

## 一、总览

当前共 **10 个模型**（按名称去重），按 5 类职责使用：三档 LLM、Embedding、重排（远程 + 本地回退）、图像生成。

| 类别 | 模型 | 作用 | 运行位置 |
| --- | --- | --- | --- |
| fast LLM | `deepseek-ai/DeepSeek-V4.1-Flash`<br>`zai-org/GLM-5.3-Flash`<br>`stepfun-ai/Step-3.5-Flash` | 意图识别、查询改写、Agent、子代理、评测等辅助任务 | SiliconFlow API |
| normal LLM | `Qwen/Qwen3-VL-30B-A3B-Instruct`<br>`deepseek-ai/DeepSeek-V3.2` | 最终回答生成、会话压缩 | SiliconFlow API |
| vision LLM | `Qwen/Qwen3-VL-8B-Instruct`（主）<br>`Qwen/Qwen3-VL-30B-A3B-Instruct`（备） | 菜品识别、食材识别 | SiliconFlow API |
| Embedding | `BAAI/bge-small-zh-v1.5` | 文本向量化（菜谱库、个人文档、语义缓存、RAGAS） | 本地 CPU |
| Reranker（主） | `Qwen/Qwen3-Reranker-8B` | 检索结果精排 | SiliconFlow `/rerank` |
| Reranker（本地回退） | `bge-reranker-v2-m3` | 远程重排失败时的本地精排 | 本地（`D:/models/bge-reranker-v2-m3`） |
| 图像生成 | `Kwai-Kolors/Kolors` | Agent 配图生成 | SiliconFlow API |
| 评测 | 复用 fast 层 | RAGAS 的 faithfulness / answer_relevancy | 随 fast 层 |

选模方式不同：**fast / normal 每次调用随机选一个**（负载均衡），**vision 按列表顺序回退**。

---

## 二、配置入口

| 位置 | 内容 | 说明 |
| --- | --- | --- |
| `config.yml` → `llm.fast` | 模型名、base_url、temperature、max_tokens | 辅助任务 |
| `config.yml` → `llm.normal` | 同上 | 最终回答 |
| `config.yml` → `llm.vision` | 同上 + 图片归一化参数、超时 | 视觉识别 |
| `config.yml` → `embedding.model_name` | 向量模型 | 换模型需重建索引 |
| `config.yml` → `reranker` | 重排模型、阈值、本地回退路径 | |
| `config.yml` → `image_generation` | 图像生成模型与网关 | |
| `config.yml` → `evaluation` | 评测开关、指标、采样率、用哪一层 | |
| `.env` | 各层 API Key | 只覆盖密钥，**不能覆盖模型名** |

密钥与配置层的对应关系（`app/config/config_loader.py` 的 `load_llm_config`）：

| 环境变量 | 覆盖的层 |
| --- | --- |
| `LLM_API_KEY` | `llm.normal.api_key` |
| `FAST_LLM_API_KEY`（或 `LLM_FAST_API_KEY`） | `llm.fast.api_key` |
| `VISION_API_KEY` | `llm.vision.api_key`，缺省继承 `LLM_API_KEY` |
| `RERANKER_API_KEY` | `reranker.api_key`，缺省继承 `LLM_API_KEY` |
| `IMAGE_GENERATION_API_KEY` | `image_generation.api_key` |

`app/config/llm_config.py`、`app/config/rag_config.py` 里的默认值只在 `config.yml` 缺字段时生效，正常修改以 YAML 为准。**配置在进程启动时加载，改完必须重启后端。**

---

## 三、逐个模型的位置

### 3.1 fast 层（三个模型随机选一）

- 配置：`config.yml` → `llm.fast.model_names`（可增删，列表越长越分散）
- 读取：`app/llm/provider.py` 的 `pick_model()`（`random.choice`）
- 调用点：

| 功能 | 位置 |
| --- | --- |
| 意图识别 | `app/conversation/intent.py`（默认 `LLMType.FAST`） |
| 会话查询改写 | `app/conversation/query_rewriter.py` |
| 元数据过滤 | `app/rag/pipeline/metadata_filter.py` |
| 检索内改写 | `app/rag/pipeline/generation.py`（`rewrite_query`） |
| 多查询分解（默认关闭） | `app/rag/pipeline/query_planner.py`，受 `retrieval.multi_query_enabled` 控制 |
| 联网搜索决策 | `app/tools/web_search.py`（temperature 0.3，绑定 tool） |
| Agent 主循环 | `app/agent/service.py` |
| Agent 上下文压缩 | `app/agent/context.py` |
| 子代理 | `app/agent/subagents/base.py` |
| 饮食自然语言解析 | `app/diet/service.py` |
| RAGAS 评测 | `app/services/evaluation_service.py`（`evaluation.llm_type` 指定） |

**注意**：换模型前先确认目标模型支持 function calling / tool calling——Agent、联网搜索、元数据过滤都依赖它。

### 3.2 normal 层

- 配置：`config.yml` → `llm.normal`
- 读取：`app/conversation/llm_orchestrator.py`（流式回答）
- 输出上限：`max_tokens` 是总上限，实际按意图收窄，见 `app/conversation/answer_policy.py` 的 `INTENT_MAX_TOKENS`：

| 意图 | 上限（token） |
| --- | --- |
| recipe_search | 1600 |
| recommendation | 1300 |
| cooking_tips | 1200 |
| ingredient_info | 900 |
| general_chat | 700 |

调整回答长度时，**先改这张表，再考虑 `llm.normal.max_tokens`**。

**注意**：当前列表里 `Qwen/Qwen3-VL-30B-A3B-Instruct` 是多模态模型，这里只按文本使用；它与 vision 层的 30B 是同一模型，共享配额。

### 3.3 vision 层

- 配置：`config.yml` → `llm.vision`
- 读取：`app/vision/provider.py`，按 `model_names` 顺序尝试，失败切换下一个
- 归一化参数（同段内）：

| 参数 | 当前值 | 作用 |
| --- | --- | --- |
| `max_image_edge` | 1024 | 长边上限 |
| `jpeg_quality` | 85 | JPEG 质量 |
| `max_payload_mb` | 2.0 | 单图体积上限 |
| `request_timeout` | 60 | 单次请求超时（秒） |

**注意**：`config.yml` 第 5 节的 `vision.model`（`qwen3.7-flash` + qianwen 地址）是**遗留配置，不生效**，视觉只读 `llm.vision`。换视觉模型时请确认目标模型支持 `image_url` data URL 与 JSON 输出。

### 3.4 Embedding

- 配置：`config.yml` → `embedding.model_name`
- 读取：`app/rag/embeddings/embedding_factory.py`（HuggingFace，本地 CPU，归一化向量）
- 使用方：菜谱库、个人文档库、L2 语义缓存、RAGAS
- 索引清单：`data/index/recipes_manifest.json` 记录了 `embedding_model` 与 `dimension`

**这是唯一必须动数据的模型**，步骤见第五节。

### 3.5 Reranker

- 配置：`config.yml` → `reranker`
- 主模型：`type: siliconflow` + `model_name` + `base_url`（`app/rag/rerankers/siliconflow_reranker.py`）
- 回退链：`app/services/rag_service.py` 中组装 `FaultTolerantReranker(SiliconFlow → 本地 cross-encoder → 词法重排)`
- 本地回退：`local_cross_encoder_enabled`、`local_cross_encoder_model`（当前 `D:/models/bge-reranker-v2-m3`）

**注意**：重排失败是**静默降级**，不会报错。换模型后如果效果变差，先看后台「链路指标」里的重排回退率。

### 3.6 图像生成

- 配置：`config.yml` → `image_generation`（`model` / `base_url` / `enabled`）
- 读取：`app/agent/tools/common/image_generator.py`
- 接口要求：OpenAI 兼容的 `images.generate`

### 3.7 RAGAS 评测

- 配置：`config.yml` → `evaluation`
- 只能用 `llm_type: fast|normal` 选择层级，**不能单独指定模型**
- 当前 `sample_rate: 0.1`，指标 `faithfulness`、`answer_relevancy`
- 若要给评测单独配模型，需在 `evaluation_service.py` 中新增一档配置

---

## 四、功能 → 层映射（写死在代码里）

以下位置决定“某功能用哪一层”。只换模型名不必改它们；**要让某功能换层才需要改代码**。

| 功能 | 位置 | 当前层 |
| --- | --- | --- |
| 意图识别 | `app/conversation/intent.py` + `conversation_service.py` | fast |
| 会话查询改写 | `app/conversation/query_rewriter.py` + `conversation_service.py` | fast |
| 最终回答 | `app/conversation/llm_orchestrator.py` + `conversation_service.py` | normal |
| 会话历史压缩 | `app/context/compress.py` + `conversation_service.py` | normal |
| 元数据过滤 | `app/rag/pipeline/metadata_filter.py` + `rag_service.py` | fast |
| 检索内改写 | `app/rag/pipeline/generation.py` + `rag_service.py` | fast |
| 多查询分解 | `app/rag/pipeline/query_planner.py` | fast |
| 联网搜索决策 | `app/tools/web_search.py` | fast |
| Agent 主循环 | `app/agent/service.py` | fast |
| Agent 上下文压缩 | `app/agent/context.py` | fast |
| 子代理 | `app/agent/subagents/base.py` | fast |
| 饮食解析 | `app/diet/service.py` | fast |
| 图片识别 | `app/vision/provider.py` | vision |
| RAGAS 评测 | `app/services/evaluation_service.py` | 由 `evaluation.llm_type` 决定 |

---

## 五、替换流程

### A. 换 LLM 层（最常见）

1. 改 `config.yml` 对应层的 `model_names` / `base_url` / `temperature` / `max_tokens`；
2. 若换服务商：改 `base_url`，并在 `.env` 更新对应 Key（`FAST_LLM_API_KEY` / `LLM_API_KEY` / `VISION_API_KEY`）；
3. 重启后端；
4. 验证：`python -c "from app.config import settings; print(settings.llm.fast.model_names)"`；
5. 发一条对话/一张图片，确认后台「模型调用」页出现新模型名。

### B. 换 Embedding（唯一需要重建数据）

1. 改 `embedding.model_name`；
2. 重建菜谱索引：`python -m scripts.ingest_recipes --rebuild`；
3. 校验清单：
   ```bash
   python -m scripts.check_index_manifest \
     --manifest data/index/recipes_manifest.json \
     --collection cook_hero_recipes \
     --embedding-model <新模型名> \
     --corpus-version howtocook-v1 \
     --dimension <新维度>
   ```
   并同步更新 `data/index/recipes_manifest.json`；
4. 个人文档集合 `cook_hero_personal_docs` **没有现成重建脚本**，旧向量维度不兼容。稳妥做法是换新集合名（`vector_store.collection_names.personal`），让用户重新上传；
5. L2 语义缓存无需手动清理：缓存作用域包含 embedding 模型名（`app/rag/cache/cache_manager.py` 的 `build_cache_scope`），换模型后不会命中旧缓存。

### C. 换 Reranker

1. 改 `reranker.model_name` / `base_url` / `score_threshold`；
2. 需要本地回退时，确认 `local_cross_encoder_model` 路径存在；
3. 重启后端；
4. 观察后台「链路指标」的重排回退率，确认没有静默降级。

### D. 换视觉模型

1. 改 `llm.vision.model_names`（顺序即优先级）；
2. 确认模型支持图片输入与 JSON 输出；
3. 如果新模型更慢：调大 `request_timeout`，或调小 `max_image_edge`（默认 1024 已能覆盖菜品识别）；
4. 用一张真实菜品图验证，观察「链路指标」的 P95 与超时率。

### E. 换图像生成模型

1. 改 `image_generation.model` / `base_url`；
2. 确认新网关兼容 OpenAI `images.generate`（`size` / `quality` / `style` 参数若被拒，需要在 `image_generator.py` 里裁剪）；
3. 让 Agent 生成一张图验证。

---

## 六、验证清单

| 检查项 | 方法 |
| --- | --- |
| 配置是否生效 | `python -c "from app.config import settings; print(settings.llm.fast.model_names)"` |
| 实际调用到哪个模型 | 后台「模型调用」页按 `model_name` 分组；或 `llm_usage_logs.model_name` |
| 视觉延迟/超时 | 后台「诊断 → 链路指标」：P95、超时率、按模型分布 |
| 检索质量 | 后台「质量监控」的 faithfulness / answer_relevancy；离线可用 `python -m scripts.eval_semantic --predictions <jsonl>` |
| 索引一致性 | `python -m scripts.check_index_manifest ...` |
| 回归测试 | `pytest tests -q` |

---

## 七、常见问题

| 现象 | 可能原因 | 处理 |
| --- | --- | --- |
| `403 AccessDenied.Unpurchased` | 该 Key 无权使用目标模型（服务商侧额度/权限） | 换模型或换 Key；密钥与 `base_url` 必须属于同一服务商 |
| `404 Model not exist` | `model_names` 与服务商模型目录不一致 | 用 `/v1/models` 核对准确模型名 |
| 改了 `config.yml` 不生效 | 未重启，或改到了遗留的 `vision.model` 段 | 重启后端；视觉只认 `llm.vision` |
| 换 embedding 后检索全空 | 维度不匹配、集合未重建 | 按第五节 B 重建并校验 manifest |
| 重排效果变差但无报错 | 远程重排失败，已降级到词法 | 查看重排回退率与后端日志 |
| 视觉偶发超时 | 模型冷启动或图片过大 | 服务端已归一化到 1024px；必要时调低 `max_image_edge` |
| 成本突然上升 | 换了更贵的模型，或 fast 列表里混入高价模型 | 查「用量看板」按模型分布；必要时砍掉列表中的高价模型 |

---

## 八、维护约定

1. 改模型时同步更新本文件「总览」表与对应小节；
2. `config.yml` 中已废弃的段落在本文件「注意」里标注，避免误改；
3. 换 embedding 必须更新 `data/index/recipes_manifest.json`，否则清单校验会失败；
4. 新增“按功能分配模型”的能力前，先评估是否需要把第四节表格里的硬编码改为配置项——当前 13 处调用点分散，收益有限。
