# 需求规格：CookHero 约束推理能力（方案 B）

- 规格编号：`CR-SPEC-001`
- 版本：v1.0
- 状态：已实现（2026-10-17）
- 上游能力：`SU-SPEC-001`（食材/过敏原本体）、`SU-SPEC-002`（语义理解 v2）
- 定位：在语义理解之后，把“过敏、忌口、素食、控糖、低脂”等自然语言约束转成可执行的硬/软约束，并对候选菜谱做确定性过滤、排序、冲突检测和解释。

---

## 1. 背景与目标

### 1.1 现状

当前系统已经能够：

- 从用户查询中抽取 `diet_constraints`、`ingredients`、`tastes` 等槽位；
- 通过 `app/knowledge/ontology.py` 做食材别名归一、过敏原和饮食标签推导；
- 通过 RAG 检索候选菜谱，并通过重排得到排序结果。

但槽位目前只进入提示词，没有真正参与候选筛选。结果是：

- 用户说“花生过敏”，模型仍可能推荐宫保鸡丁；
- 用户说“素食”，检索结果仍可能包含肉类菜谱；
- 约束冲突（例如“纯素但要用鸡蛋”）不会被显式发现；
- 过滤原因不可解释，无法判断是知识缺失还是规则命中。

### 1.2 目标

1. 把自然语言饮食约束解析为结构化约束，区分硬约束和软约束。
2. 对候选菜谱做确定性评估：命中硬约束直接排除，软约束参与排序。
3. 对冲突约束给出显式告警和澄清问题，不静默替用户做选择。
4. 为每一条排除/保留给出可追溯原因和食材证据。
5. 提供替代食材建议，但必须标注“需确认”，不能伪装成确定性结论。
6. 接入对话主链路和只读/无副作用 API，并保持默认行为可控。
7. 提供离线评测集和脚本，验证约束解析与过滤的准确率。

### 1.3 非目标

- 不实现通用 SAT/SMT 或线性规划求解器。
- 不替代营养师，不做疾病诊断。
- 不自动修改用户健康档案或饮食计划。
- 不对未知食材做“安全”假设；未知时明确标记为“无法确认”。
- 不引入新的外部服务或模型依赖。

---

## 2. 术语

| 术语 | 含义 |
| --- | --- |
| 硬约束 | 违反后必须排除候选，例如过敏原、素食、明确忌口 |
| 软约束 | 不排除候选，只影响排序，例如低脂、控糖、高蛋白、清淡 |
| 约束画像 | 一次请求解析出的全部约束、来源和未知项 |
| 评估结果 | 单个候选菜谱的食材、命中约束、分数、排除原因 |
| 冲突 | 两条约束不可能同时满足，或用户显式要求与饮食模式矛盾 |

---

## 3. 需求条目

### SU-13 约束模型与解析

**需求**：把 `diet_constraints` 槽位和用户原文解析为结构化约束。

**接口**：

```python
# app/reasoning/constraints/models.py
class ConstraintKind(str, Enum):
    ALLERGEN = "allergen"
    DIET = "diet"
    EXCLUDE_INGREDIENT = "exclude_ingredient"
    INCLUDE_INGREDIENT = "include_ingredient"
    NUTRITION = "nutrition"
    TASTE = "taste"

class ConstraintSeverity(str, Enum):
    HARD = "hard"
    SOFT = "soft"

@dataclass(frozen=True)
class Constraint:
    kind: ConstraintKind
    value: str
    severity: ConstraintSeverity
    source: str = "slot"
    label: str = ""

@dataclass
class ConstraintProfile:
    constraints: list[Constraint]
    unknown_terms: list[str]

# app/reasoning/constraints/parser.py
def parse_constraints(
    *,
    text: str = "",
    diet_constraints: Iterable[str] = (),
    ingredients: Iterable[str] = (),
    tastes: Iterable[str] = (),
) -> ConstraintProfile: ...
```

**验收标准**：

- AC-13.1 支持过敏原：花生、坚果、牛奶/乳制品、鸡蛋、海鲜、鱼、大豆、小麦/麸质、芝麻。
- AC-13.2 支持饮食模式：素食、纯素/全素、无麸质。
- AC-13.3 支持营养目标：低脂/减脂、控糖/低糖、高蛋白、低盐/清淡。
- AC-13.4 支持显式忌口：“不吃猪肉”“不要花生”“对虾过敏”。
- AC-13.5 同一约束去重；`source` 区分 `slot` 与 `text`。
- AC-13.6 无法识别的约束词进入 `unknown_terms`，不静默丢弃。
- AC-13.7 过敏原和饮食模式为硬约束；营养目标和口味为软约束。

**测试映射**：`tests/test_constraint_parser.py`

---

### SU-14 候选菜谱评估与硬过滤

**需求**：从菜谱标题和“必备原料和工具”等章节提取食材，评估硬约束并过滤候选。

**接口**：

```python
# app/reasoning/constraints/evaluator.py
def assess_document(document, profile: ConstraintProfile) -> DishAssessment: ...

def evaluate_documents(
    documents: Sequence,
    profile: ConstraintProfile,
) -> list[DishAssessment]: ...
```

**验收标准**：

- AC-14.1 优先从“必备原料和工具/原料/食材/配料”章节提取食材；缺失时回退到标题和全文。
- AC-14.2 食材别名归一复用 `app/knowledge/ontology.py`，不重复维护别名表。
- AC-14.3 命中过敏原硬约束时排除，并给出过敏原、贡献食材和原文证据。
- AC-14.4 命中素食/纯素/无麸质硬约束时排除，并给出缺失的饮食标签。
- AC-14.5 命中显式忌口食材时排除。
- AC-14.6 无法提取任何已知食材时标记 `unknown=True`，不因“未知”而误排除。
- AC-14.7 所有候选都被排除时回退到原候选，并设置 `fallback_used=True`，避免空上下文。
- AC-14.8 过滤顺序稳定：保留项按软约束分数降序，同分保持原顺序。

**测试映射**：`tests/test_constraint_evaluator.py`

---

### SU-15 软约束排序与替代建议

**需求**：对未触发硬约束的候选，按软约束命中情况调整排序，并给出保守的替代建议。

**接口**：

```python
# app/reasoning/constraints/evaluator.py
def soft_score(document, profile: ConstraintProfile) -> tuple[float, list[str], list[str]]: ...

def substitution_hints(profile: ConstraintProfile) -> list[str]: ...
```

**验收标准**：

- AC-15.1 低脂、控糖、高蛋白、低盐、清淡使用可解释关键词规则，不调用模型。
- AC-15.2 每个软约束命中/未命中都记录原因，便于前端或日志展示。
- AC-15.3 软约束只影响排序，不单独导致候选被排除。
- AC-15.4 替代建议只来自静态映射，必须包含“需确认”提示。
- AC-15.5 未识别约束不参与打分。

**测试映射**：`tests/test_constraint_evaluator.py`

---

### SU-16 冲突检测与澄清

**需求**：识别约束之间的直接矛盾，并生成澄清问题。

**接口**：

```python
# app/reasoning/constraints/conflicts.py
def detect_conflicts(profile: ConstraintProfile) -> list[str]: ...
def build_clarification_question(conflicts: Sequence[str]) -> Optional[str]: ...
```

**验收标准**：

- AC-16.1 纯素 + 鸡蛋/牛奶/肉类食材 → 冲突。
- AC-16.2 素食 + 肉类食材 → 冲突。
- AC-16.3 无麸质 + 小麦/面粉/面条 → 冲突。
- AC-16.4 过敏原 + 显式要求包含含该过敏原的食材 → 冲突。
- AC-16.5 同一食材同时被要求包含和排除 → 冲突。
- AC-16.6 冲突时 `needs_clarification=True`，并生成一句可直接展示给用户的中文问题。
- AC-16.7 冲突不阻止系统给出候选，但提示词必须要求模型先澄清或明确标注冲突。

**测试映射**：`tests/test_constraint_conflicts.py`

---

### SU-17 对话与 RAG 集成

**需求**：约束画像进入对话主链路；检索后对候选做过滤；提示词携带约束解释。

**接口**：

```python
# app/reasoning/constraints/service.py
class ConstraintReasoner:
    def analyze(self, *, text: str, slots=None) -> ConstraintDecision: ...
    def evaluate_documents(self, documents, decision: ConstraintDecision) -> ConstraintDecision: ...

# app/conversation/types.py
@dataclass
class ChatContext:
    constraint_context: str = ""
    constraint_decision: Optional[Any] = None
```

**验收标准**：

- AC-17.1 意图识别后立即解析约束，并写入 `ChatContext`。
- AC-17.2 有约束时输出一条 thinking 事件，说明硬/软约束数量。
- AC-17.3 RAG 检索后按硬约束过滤，并重建 `context` 与 `sources`。
- AC-17.4 生成提示词包含约束解释、排除原因和“未知不臆测”要求。
- AC-17.5 无约束时主链路行为与 v2 一致。
- AC-17.6 约束推理异常只记录 warning，不影响回答生成。
- AC-17.7 新增 `POST /api/v1/constraints/evaluate`，输入文本/约束/候选，返回画像、评估、保留/排除结果。

**测试映射**：`tests/test_constraint_integration.py`、`tests/test_constraint_api.py`

---

### SU-18 离线评测与配置

**需求**：提供可复现的约束评测集、脚本和配置开关。

**接口**：

```python
# scripts/eval_constraints.py
def evaluate_cases(cases: Sequence[dict]) -> dict: ...
def main(argv: Optional[list[str]] = None) -> int: ...
```

**配置**：

```yaml
constraint_reasoning:
  enabled: true
  strict_allergens: true
  max_candidates: 20
```

**验收标准**：

- AC-18.1 新增 `data/eval/constraint_cases.jsonl`，至少 12 条，覆盖过敏、素食、纯素、无麸质、忌口、冲突和未知。
- AC-18.2 脚本输出逐条通过/失败、保留/排除集合和总体通过率。
- AC-18.3 存在失败用例时退出码为 1。
- AC-18.4 配置默认开启，但 `enabled=false` 时完全跳过约束推理。
- AC-18.5 评测不依赖网络、Milvus、Redis、PostgreSQL 或模型下载。

**测试映射**：`tests/test_constraint_eval.py`

---

## 4. 非功能性需求

- NFR-11 可离线性：全部规则、测试和评测离线运行。
- NFR-12 确定性：相同输入必须得到相同过滤和排序结果。
- NFR-13 可解释性：每个排除项至少包含约束、食材/标签和原因。
- NFR-14 安全默认：未知食材不视为安全；未知约束不丢弃。
- NFR-15 低开销：单次评估为线性扫描，不调用 LLM。
- NFR-16 向后兼容：无约束请求不改变现有检索与生成行为。

---

## 5. 交付物清单

| 需求 | 新增 | 修改 |
| --- | --- | --- |
| SU-13 | `app/reasoning/constraints/models.py`、`parser.py` | `app/knowledge/ontology.py` |
| SU-14 | `app/reasoning/constraints/evaluator.py` | — |
| SU-15 | `app/reasoning/constraints/substitutions.py` | — |
| SU-16 | `app/reasoning/constraints/conflicts.py` | — |
| SU-17 | `app/reasoning/constraints/service.py`、`app/api/v1/endpoints/constraints.py` | `app/conversation/types.py`、`app/services/conversation_service.py`、`app/main.py` |
| SU-18 | `app/config/constraint_config.py`、`scripts/eval_constraints.py`、`data/eval/constraint_cases.jsonl` | `app/config/config_loader.py`、`app/config/config.py`、`config.yml` |

---

## 6. 验收方法

```bash
python -m pytest tests -q -p no:cacheprovider
python -m scripts.eval_constraints --cases data/eval/constraint_cases.jsonl
```

两条命令全部成功，且约束评测通过率为 100%，视为本次迭代验收通过。

---

## 7. 实现与验收结果

### 7.1 实际交付

| 需求 | 实现文件 |
| --- | --- |
| SU-13 | `app/reasoning/constraints/models.py`、`parser.py`、`app/knowledge/ontology.py` |
| SU-14 | `app/reasoning/constraints/evaluator.py` |
| SU-15 | `app/reasoning/constraints/substitutions.py` |
| SU-16 | `app/reasoning/constraints/conflicts.py` |
| SU-17 | `app/reasoning/constraints/service.py`、`app/api/v1/endpoints/constraints.py`、`app/conversation/types.py`、`app/services/conversation_service.py`、`app/main.py` |
| SU-18 | `app/config/constraint_config.py`、`scripts/eval_constraints.py`、`data/eval/constraint_cases.jsonl`、`app/config/config_loader.py`、`app/config/config.py`、`config.yml` |

### 7.2 实现补充

- 新增 `is_known_ingredient`，用于区分“已知但不满足饮食标签”和“本体中不存在”。
- 新增 `diet_offenders`，按饮食模式逐食材判断冲突；无麸质模式下肉类/鱼类不因缺少标签被误排除。
- 新增 `rebuild_retrieval_result`，统一重建过滤后的 `documents/context/sources`。
- 新增 `ConstraintDecision.ordered_kept_ids`，保证 API 返回的保留顺序与软约束排序一致。
- 实际 RAG 源码方法名为 `_extract_sources`，集成时按源码调用。

### 7.3 验收结果

| 命令 | 结果 |
| --- | --- |
| `python -m pytest tests -q -p no:cacheprovider` | `230 passed` |
| `python -m scripts.eval_constraints --cases data/eval/constraint_cases.jsonl` | `16/16` 通过，通过率 `100.00%` |

约束相关新增测试共 51 项，全部通过。

### 7.4 已知无关问题

- `app/conversation/types.py` 既有 `web_searta` 拼写问题未在本次修改。
