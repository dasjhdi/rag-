<div align="center">

<img src="./docs/image.png" alt="CookHero Logo" width="512" />

**智能烹饪与饮食管理助手 · 你的个性化饮食英雄**

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.122-009688.svg)](https://fastapi.tiangolo.com/)
[![LangChain](https://img.shields.io/badge/LangChain-1.1-green.svg)](https://www.langchain.com/)
[![Milvus](https://img.shields.io/badge/Milvus-2.6-orange.svg)](https://milvus.io/)
[![NeMo Guardrails](https://img.shields.io/badge/NeMo%20Guardrails-0.12-76B900.svg)](https://github.com/NVIDIA/NeMo-Guardrails)
[![RAGAS](https://img.shields.io/badge/RAGAS-0.2-purple.svg)](https://docs.ragas.io/)
[![License](https://img.shields.io/badge/License-APACHE%202.0-blue.svg)](LICENSE)

简体中文 | [English](./docs/README_EN.md)

---

</div>

<div align="center">
<p align="center">
  <img src="./docs/agent.jpg" width="48%">
  <img src="./docs/demo_2x.gif" width="48%"/>
  <img src="./docs/diet.jpg" width="48%">
  <img src="./docs/statistics.jpg" width="48%">
</p>
</div>

---

## 📖 项目简介

**CookHero**（烹饪英雄）是一个融合 LLM、RAG、Agent、多模态与营养数据分析的个性化饮食管理平台。它不仅是菜谱库，更是一位能陪你做计划、做记录、看数据、给建议的“饮食管理英雄助手”，帮助你把烹饪与健康目标变成可执行的日常。

与常见的“问答式”饮食助手不同，CookHero 把整条链路做成了闭环：**听懂约束 → 排出计划 → 采购补齐 → 按步骤烹饪 → 记回真实数据 → 复盘调整**。其中过敏原过滤、营养配平、库存扣减、单位换算这些“错不起”的环节全部由确定性代码完成，不交给模型自由发挥；模型负责的是理解、解释与生成。

- 🔍 **智能问答**：解答烹饪技巧、食材搭配、营养知识等问题
- 🗓️ **饮食计划**：按饮食档案与营养目标自动生成一周三餐，可单餐替换、可锁定
- 🛒 **采购与库存**：储物柜记录现有食材、临期提醒，一键生成扣减后的购物清单
- 🍳 **烹饪辅助**：结构化菜谱、份量缩放、单位换算、大字步骤与厨房计时器
- 🧾 **AI 记录**：文字/图片/语音一键记录，自动估算热量与宏量营养
- 📊 **营养复盘**：每日/每周统计、计划与实际偏差、今日视图与执行率
- 🛡️ **约束推理**：过敏原与饮食限制做确定性过滤，可解释到“哪条约束、哪个食材”
- 🧠 **深度理解**：多标签意图 + 槽位抽取 + 置信度，支持多轮对话与澄清

CookHero 面向厨房新手、健身/减脂/控糖人群、健康饮食倡导者、过敏体质用户及家庭场景，致力于让烹饪更专业、更智能、更可持续。

> 内部自带的食谱来源于[Anduin2017/HowToCook](https://github.com/Anduin2017/HowToCook)，感谢该项目的贡献者！

---

## ⚡ 技术亮点

- **LLM + RAG 混合检索**：向量 + BM25 + Reranker 组合，配合多级缓存提速
- **约束推理引擎**：硬约束确定性过滤 + 软约束加权打分，每个排除项都能解释原因
- **确定性计划生成**：七因子评分 + 事务落库，同输入同输出，锁定餐次不被覆盖
- **Agent ToolHub**：ReAct 推理 + 工具调用，支持 MCP 动态扩展
- **Subagent 专家体系**：内置 + 用户自定义子代理，按需启用与编排
- **多模态解析**：图片识别与饮食记录联动，覆盖烹饪与记录场景
- **语义评测与观测**：分意图/分桶指标、混淆对分析、多查询离线 A/B、索引指纹校验
- **评估与可观测性**：RAGAS 质量评估 + LLM 使用统计 + 可视化看板
- **安全与合规**：提示词注入防护、速率限制、结构化审计日志
- **现代化全栈**：FastAPI + React + PostgreSQL + Milvus + Redis + MinIO

## ✨ 核心功能

### 1. Agent 智能饮食管家
- **ReAct 模式**：实现推理 + 行动循环，支持自主决策和工具调用
- **多模态支持**：支持上传图片，图片自动上传到 imgbb 持久化存储
- **用户画像集成**：自动读取用户画像和长期指令，提供个性化饮食管理服务
- **Subagent 子代理**：内置/自定义专家可作为工具被调用，独立 system prompt 与工具集
- **Subagent 管理**：个人中心创建/启用/禁用，工具选择器支持 Agents 面板
- **内置工具（15 个）**：
  - 对话与检索：菜谱知识库检索、联网搜索（Tavily）、深度研究、AI 图片生成（DALL·E 3 + imgbb）、计算器、日期时间
  - 饮食闭环：饮食计划、饮食记录、营养分析、菜谱搜索、营养计算、单位换算、食材库存、购物清单、厨房计时
- **MCP 协议支持**：支持用户自定义 MCP 服务器并配置鉴权头；内置高德地图 MCP（15 个工具，含地址解析、路径规划、天气）
- **中文界面**：工具与 MCP 服务统一以中文名称展示，悬停即可查看作用说明，不再暴露 `web_search` 这类英文标识
- **可扩展架构**：通过 AgentHub 统一管理 Agent、Tool 和 Provider
- **上下文压缩**：自动压缩长对话历史，减少 Token 消耗
- **实时反馈**：SSE 事件流，实时展示工具调用过程和结果
- **执行追踪**：主 Agent 与 Subagent 轨迹分层展示，支持调试分析
- **工具选择**：前端可动态选择工具与子代理

### 2. 结构化饮食档案
- 过敏原与严重程度、饮食模式（素食/纯素/无麸质）、疾病忌口、避免与偏好的食材、偏好菜系
- 营养目标：热量、蛋白质、脂肪、碳水、膳食纤维、钠
- 烹饪条件：每日餐数、厨艺水平、单餐最长耗时、预算档位、辣度、单位制、家庭人数
- 档案是**唯一事实源**：对话约束、计划生成、菜谱推荐统一读取，填一次即全链路生效
- 相关接口：`GET/PUT /api/v1/diet/profile`、`GET /api/v1/diet/profile/effective-constraints`

### 3. 智能周计划生成
- 结合档案约束与营养目标，从候选菜谱中生成 7 天三餐并直接落库
- **确定性打分**：热量偏差、蛋白偏差、重复惩罚、同日重复重罚、烹饪时间超预算、菜系偏好、历史反馈、库存覆盖
- 每日热量按早餐 25% / 午餐 40% / 晚餐 35% 分配，同一菜谱一周最多出现 2 次、同一天不重复
- **事务落库**：整周先在内存算完再批量写入，不会留下"周一周二有饭、周三空着"的半成品
- 单餐可替换、可跳过、可锁定；重新生成时不覆盖已锁定餐次
- 返回目标 vs 实际的热量偏差诊断与生成警告

### 4. 菜谱详情与烹饪模式
- 把 Markdown 菜谱解析为结构化实体：食材、用量、步骤、耗时、营养、过敏原与饮食标签
- **份量缩放**：按人数等比缩放；`适量/少许` 等无明确用量的食材不缩放，避免假装精确
- **单位换算**：kg/g、oz/lb、cup/tbsp/tsp 以及计件单位（如鸡蛋 50g/个）
- **烹饪模式**：全屏大字步骤、上一步/下一步、步骤计时器、屏幕常亮
- 支持评分评论、收藏与「做过」等反馈信号

### 5. 储物柜与购物清单
- 记录现有食材（名称、数量、单位、分类、存放位置、保质期），支持临期提醒
- 按周计划自动聚合需求，**优先扣减库存**后再生成购物清单
- 「现有食材能做什么」：按食材覆盖率排序，并列出还缺哪几样
- 清单项支持勾选，方便边买边划

### 6. 饮食记录与营养分析
- 文字/图片/语音一键记录，AI 解析为结构化条目并估算营养
- 计划餐次可一键标记已吃，自动转为真实记录
- 每日/每周营养总览（热量、蛋白、脂肪、碳水）与计划偏差分析
- **营养可信度分级**：命中本地营养表且单位可换算为 high，用量估算为 medium，未命中为 low，不伪造精确值
- 数据来源标记：手动、AI 文本、AI 图片；支持今日视图与执行率复盘

### 7. 约束推理（过敏原与饮食限制）
- **规则优先**：硬约束（过敏原、素食、纯素、无麸质、忌口食材）由确定性代码判断，不交给模型
- **软约束打分**：低脂、控糖、高蛋白、低盐、清淡按正负向关键词加权排序
- **可解释**：每个被排除的菜品都能回答"哪条约束、哪个食材、什么原因"
- **未知保守**：无法提取食材时标记 unknown，不把未知当安全
- **冲突澄清**：如"纯素"却要求含鸡蛋时生成澄清问题，而不是静默选择
- **全排除回退**：候选被全部排除时回退原候选，并强制说明限制与替代方向
- 提供只做纯计算的 `POST /api/v1/constraints/evaluate`，不写库、不调用 LLM

### 8. 家庭与多人份
- 家庭成员独立维护过敏原、饮食限制、热量目标与份量系数
- 约束合并规则：过敏原取并集且全部作为硬约束，热量目标按成员求和，份量按系数放大

### 9. 智能对话式菜谱查询
- 自然语言理解用户需求（如"我想做一道低脂高蛋白的晚餐"）
- 多标签意图识别 + 槽位抽取（食材、时间、口味、禁忌）+ 置信度
- 低置信度时给出澄清信号，而不是硬猜一个答案
- 支持多轮对话，记录上下文历史，流式响应，支持语音输入

### 10. 个性化知识库
- 用户可上传私人食谱，系统自动分析并索引
- 全局食谱库（来自 [HowToCook](https://github.com/Anduin2017/HowToCook)）与个人食谱融合查询
- 支持 Markdown 格式食谱的智能解析

### 11. 混合检索与重排序
- **向量检索**：语义相似度匹配（基于 Milvus）
- **BM25 检索**：中文领域分词 + 关键词精确匹配
- **元数据过滤**：根据烹饪时间、难度、营养成分等筛选
- **三级重排兜底**：远程 Reranker（Qwen3-Reranker）→ 本地 cross-encoder → BM25 → 保持原序，任一级失败只降级不报错
- **多级缓存**：Redis L1 + Milvus L2 双层缓存，语义缓存相似度阈值 0.92
- **索引一致性**：记录 embedding 模型、维度与语料指纹，升级模型时先校验再切流量

### 12. 语义评测与运行时观测
- **分意图/分桶评测**：每类意图的 P/R/F1、各业务桶的 Hit@K 与 MRR、混淆对分析
- **离线 A/B**：多查询改写上线前先跑对比，样本不足时返回 `insufficient_data`，不自动开启
- **运行时指标**：低置信度率、澄清率、检索空结果率、缓存命中率、重排兜底率
- `GET /api/v1/semantic-metrics/summary` 暴露只读指标，只记计数不记用户原始查询

### 13. 多模态支持
- **图片识别**：支持上传食材/菜品/饮食图片进行智能识别
- **意图理解**：结合图片和文字理解用户完整意图
- **多种场景**：菜品识别、食材识别、烹饪指导、饮食记录、食谱查询
- **灵活接入**：支持 OpenAI 兼容的视觉模型 API
- **图片限制**：最多 4 张、单张 10MB（Agent/饮食记录场景）

### 14. 菜谱图片与内容导入
- **图片上屏**：HowToCook 语料中的菜谱图会自动出现在搜索卡片、菜谱详情和烹饪步骤中；卡片使用缩略图接口（`/media/recipes/...?w=640`）降低流量。
- **缺图补齐**：运行 `python -m scripts.fetch_recipe_images` 可为没有成品图的菜谱抓取匹配图片，图片与来源记录在 `data/recipe_images/`，不修改原始 Markdown。当前语料 373 道菜已 100% 有图（补图 195 张，全部经过视觉校验或人工复核）。详见 [菜谱补图说明](docs/RECIPE_IMAGES.md)。
- **链接导入**：粘贴公开菜谱网页链接，自动解析 schema.org JSON-LD（兼容无 JSON-LD 的 DOM 回退）、下载封面图并写入个人知识库；导入后即可搜索、加入计划和参与 RAG 检索。
- **图片识别导入**：上传菜谱照片，调用视觉模型提取菜名、原料、步骤、份量与耗时，同样保存为个人菜谱。
- **安全边界**：导入仅允许公网 http/https 地址，拒绝内网/本机/云元数据地址；图片只暴露白名单后缀，路径穿越会被拒绝。
- **相关接口**：
  - `POST /api/v1/recipes/import/url`
  - `POST /api/v1/recipes/import/image`
  - `GET /media/recipes/{path}`、`GET /media/imports/recipes/{path}`（支持 `?w=` 缩略图）

### 15. RAG 评估与 LLM 使用统计
- **质量监控**：基于 RAGAS 框架的自动化评估，核心指标为忠实度（Faithfulness）与答案相关性（Answer Relevancy）
- **异步评估**：后台异步执行、按比例采样，不影响响应速度；支持趋势查看与质量告警，结果持久化于 PostgreSQL
- **Token 监控**：跟踪每个请求的 Token 使用量、响应时间、思考时间与生成时间
- **统计分析**：按用户、会话、模块统计使用情况，并记录 Agent 工具调用名称，前端提供可视化页面

### 16. 安全防护体系
- **多层防护**：输入验证 → 模式检测 → LLM 深度检测
- **提示词注入防护**：基于规则和 AI 的双重检测机制
- **速率限制**：Redis 滑动窗口算法，按端点类型区分限制
- **账户安全**：登录失败锁定、JWT 过期策略、安全响应头
- **敏感数据保护**：日志脱敏、API Key 过滤
- **安全审计**：结构化 JSON 审计日志，支持 SIEM 系统对接

> 📖 详细安全架构请参阅 [安全策略文档](docs/SECURITY.md)

### 主要接口速览

| 领域 | 代表接口 |
| --- | --- |
| 认证 | `POST /api/v1/auth/register`、`POST /api/v1/auth/login` |
| 对话与 Agent | `POST /api/v1/conversation`、`POST /api/v1/agent/chat`（SSE）、`GET /api/v1/agent/tools` |
| 菜谱 | `GET /api/v1/recipes/search`、`GET /api/v1/recipes/{id}`、`POST /api/v1/recipes/{id}/feedback` |
| 饮食档案 | `GET/PUT /api/v1/diet/profile`、`GET /api/v1/diet/profile/effective-constraints` |
| 计划 | `POST /api/v1/diet/plans/generate`、`POST /api/v1/diet/plans/meals/{id}/replace` |
| 记录与分析 | `POST /api/v1/diet/logs/from-text`、`GET /api/v1/diet/analysis/weekly`、`GET /api/v1/diet/today` |
| 储物柜 | `GET/POST /api/v1/pantry/items`、`GET /api/v1/pantry/expiring`、`GET /api/v1/pantry/cookable` |
| 营养与家庭 | `POST /api/v1/nutrition/estimate`、`GET/POST /api/v1/family/members` |
| 约束推理 | `POST /api/v1/constraints/evaluate` |
| 评测与观测 | `GET /api/v1/evaluation/*`、`GET /api/v1/llm-stats/*`、`GET /api/v1/semantic-metrics/summary` |

完整接口列表见启动后的 Swagger 文档：<http://localhost:8000/docs>

---

## 🚀 快速开始

### 前置要求

- **Python**：>= 3.12
- **Node.js**：>= 18
- **Docker** 和 **Docker Compose**（推荐）

### 方法一：Docker 一键部署（推荐）

1. **克隆项目**
   ```bash
   git clone https://github.com/Decade-qiu/CookHero.git
   cd CookHero
   ```

2. **配置环境变量**
   ```bash
   cp .env.example .env
   # 编辑 .env 文件，填入必要的 API Key
   ```

3. **启动基础设施**
   ```bash
   cd deployments
   docker compose up -d
   ```
   这将启动：
   - PostgreSQL (端口 5432)
   - Redis (端口 6379)
   - Milvus (端口 19530)
   - MinIO (端口 9001)
   - Etcd (内部使用)

4. **安装 Python 依赖并启动后端**
   ```bash
   cd ..
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   
   # 拉取并灌入 HowToCook 菜谱语料（PostgreSQL + Milvus）
   python -m scripts.ingest_recipes --sync
   
   # 启动后端服务
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

5. **启动前端**
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

   > 图片通过 `/media` 提供。开发模式下 Vite 已配置代理；如果前端与后端不同源部署，
   > 在 `frontend/.env` 中设置 `VITE_MEDIA_BASE=https://your-api-host` 即可。

6. **访问应用**
   - 前端：http://localhost:5173
   - 饮食管理：http://localhost:5173/diet
   - 后端 API：http://localhost:8000
   - API 文档：http://localhost:8000/docs

### 方法二：日常启动（本地开发）

首次部署按「方法一」完成后，后续每次开机只需下面 4 步。基础设施跑在 Docker 里，
后端与前端在宿主机上以开发模式运行（支持热重载）。

> **一键启动（Windows，推荐）**
>
> 仓库提供 `scripts/start-dev.ps1`：自动拉起 Docker Desktop 并等待引擎就绪、启动基础设施容器、
> 各开一个窗口运行前后端。
>
> ```powershell
> powershell -ExecutionPolicy Bypass -File scripts\start-dev.ps1          # 启动
> powershell -ExecutionPolicy Bypass -File scripts\start-dev.ps1 -Stop    # 停止
> powershell -ExecutionPolicy Bypass -File scripts\start-dev.ps1 -Check   # 只检查环境
> ```
>
> 脚本与存放位置无关（自动向上查找仓库根目录，也可用 `-Root` 指定），可放在桌面或任意目录。
> 想手动控制每一步，按下面 4 步执行。

1. **启动 Docker Desktop**，然后启动基础设施容器
   ```bash
   cd deployments
   docker compose up -d
   ```
   容器设置了 `restart: always`，Docker Desktop 启动后会自动拉起；该命令是幂等的，重复执行无副作用。

2. **启动后端**（必须在仓库根目录执行，`config.yml` 与 `data/` 都按相对路径解析）
   ```bash
   cd ..                          # 回到仓库根目录
   source .venv/bin/activate      # Windows: .venv\Scripts\Activate.ps1
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

3. **启动前端**（另开一个终端窗口）
   ```bash
   cd frontend
   npm run dev
   ```

4. **访问应用**：http://localhost:5173

注意事项：

- 离线开关 `HF_HUB_OFFLINE=1` 已写入仓库根目录的 `.env`，后端启动时自动加载，**无需再手动 export**。
  嵌入模型（`BAAI/bge-small-zh-v1.5`）首次运行后已缓存到本地，该变量用于跳过 HuggingFace 的网络探测；
  在网络受限的环境下若缺失，启动会长时间卡在重试上。仅在其它 shell 中单独跑脚本时才需要临时 `$env:HF_HUB_OFFLINE='1'`。
- Windows PowerShell 若执行 `npm run dev` 报 `npm.ps1 ... 因为在此系统上禁止运行脚本`，
  执行一次 `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force` 即可；
  也可改用 `npm.cmd run dev`。
- 后端与前端是两个常驻进程，各自占用一个终端窗口，`Ctrl+C` 停止。
- 修改 `.env` 后必须**重启后端**才会生效（环境变量在进程启动时读取一次）。
- 不要关闭 Docker Desktop，否则 PostgreSQL / Redis / Milvus 会随之中断。

---

## ⚙️ 配置说明

### 1. 环境变量 (`.env`)

创建 `.env` 文件（参考 `.env.example`）：

```env
# ==================== LLM API 配置 ====================
# 主 API Key（所有模块的默认 Key）
LLM_API_KEY=your_main_api_key

# 快速模型 API Key（用于意图识别、查询改写等）
FAST_LLM_API_KEY=your_fast_model_api_key

# 视觉模型 API Key（用于多模态分析）
VISION_API_KEY=your_vision_model_api_key

# Reranker API Key（用于结果重排序）
RERANKER_API_KEY=your_reranker_api_key

# ==================== 数据库配置 ====================
DATABASE_PASSWORD=your_postgres_password

# Redis 密码（可选）
REDIS_PASSWORD=your_redis_password

# Milvus 认证（可选）
MILVUS_USER=root
MILVUS_PASSWORD=your_milvus_password

# ==================== Web 搜索 ====================
WEB_SEARCH_API_KEY=your_tavily_api_key

# ==================== MCP 集成 ====================
# 高德地图 MCP 服务 API Key
AMAP_API_KEY=your_amap_api_key

# ==================== 图片生成 ====================
# OpenAI 兼容的图片生成 API Key（DALL-E 3 等）
IMAGE_GENERATION_API_KEY=your_openai_api_key
# imgbb 图床 API Key（用于图片持久化存储）
IMGBB_STORAGE_API_KEY=your_imgbb_api_key

# ==================== 安全认证 ====================
JWT_SECRET_KEY=your_secure_jwt_secret_key
JWT_ALGORITHM=HS256

# 访问令牌过期时间（分钟）
ACCESS_TOKEN_EXPIRE_MINUTES=60

# 刷新令牌过期时间（天）
REFRESH_TOKEN_EXPIRE_DAYS=7

# ==================== 速率限制 ====================
RATE_LIMIT_ENABLED=true
RATE_LIMIT_LOGIN_PER_MINUTE=5
RATE_LIMIT_CONVERSATION_PER_MINUTE=30
RATE_LIMIT_GLOBAL_PER_MINUTE=100

# ==================== 账户安全 ====================
LOGIN_MAX_FAILED_ATTEMPTS=5
LOGIN_LOCKOUT_MINUTES=15
MAX_MESSAGE_LENGTH=10000
MAX_IMAGE_SIZE_MB=5
PROMPT_GUARD_ENABLED=true
```

### 2. 主配置文件 (`config.yml`)

`config.yml` 包含应用的核心配置：

```yaml
# LLM 提供商配置（分层：fast / normal / vision）
llm:
  fast:    # 快速模型（低延迟）
  normal:  # 标准模型
  vision:  # 视觉模型（多模态）

# 数据路径
paths:
  base_data_path: "data/HowToCook"

# 嵌入模型
embedding:
  model_name: "BAAI/bge-small-zh-v1.5"

# 向量存储
vector_store:
  type: "milvus"
  collection_names:
    recipes: "cook_hero_recipes"
    personal: "cook_hero_personal_docs"

# 检索配置
retrieval:
  top_k: 9
  score_threshold: 0.2
  ranker_type: "weighted"
  ranker_weights: [0.8, 0.2]

# 重排序配置
reranker:
  enabled: true
  model_name: "Qwen/Qwen3-Reranker-8B"

# 缓存配置
cache:
  enabled: true
  ttl: 3600
  l2_enabled: true
  similarity_threshold: 0.92

# Web 搜索配置
web_search:
  enabled: true
  max_results: 6

# 视觉/多模态配置
vision:
  model:
    enabled: true
    model_name: "Qwen/QVQ-72B-Preview"

# 评估配置
evaluation:
  enabled: true
  async_mode: true
  sample_rate: 1.0

# MCP 配置
mcp:
  amap:
    enabled: true

# 图片生成配置
image_generation:
  enabled: true
  model: "dall-e-3"

# 图片存储配置（imgbb）
image_storage:
  enabled: true

# 数据库连接
database:
  postgres:
    host: "localhost"
    port: 5432
  redis:
    host: "localhost"
    port: 6379
  milvus:
    host: "localhost"
    port: 19530
```

详细配置说明见 `config.yml` 文件中的注释。

---

### 3. 菜谱语料灌库 (`scripts/ingest_recipes.py`)

`scripts/sync_data.py` 只负责把 HowToCook 的 Markdown 语料克隆/更新到 `data/HowToCook`，
真正把语料写入 PostgreSQL 与 Milvus 的是 `scripts/ingest_recipes.py`。
**请先启动基础设施（第 3 步）再执行灌库**，脚本需要在仓库根目录运行（`config.yml` 与
`data/` 都按相对路径解析）。

```bash
# 拉取语料并灌库（首次推荐）
python -m scripts.ingest_recipes --sync

# 语料已存在，仅重新灌库
python -m scripts.ingest_recipes
```

| 参数 | 说明 |
| --- | --- |
| `--sync` | 灌库前先克隆/更新 HowToCook 语料到 `data/HowToCook` |
| `--rebuild` | 删除并重建 Milvus 的 `cook_hero_recipes` collection（更换嵌入模型或表结构变更时使用） |
| `--dry-run` | 只解析语料并打印数量，不写入任何数据库 |
| `--batch-size` | 每批写入的文档/chunk 数量，默认 `64` |
| `--limit` | 只灌入前 N 篇文档，便于冒烟测试 |

灌库内容：

- 解析 `data/HowToCook/dishes`（菜谱）与 `data/HowToCook/tips`（技巧），
  并自动生成整体/分类/难度索引文档用于推荐。
- 父文档写入 PostgreSQL 的 `knowledge_documents` 表（全局文档 `user_id` 为空）。
- 切分后的 chunk 写入 Milvus 的 `cook_hero_recipes` collection（dense + BM25 混合检索）。
- 脚本是**幂等**的：重复执行会先清除旧的全局文档与向量再写入，不会产生重复数据。
- 结束时会刷新元数据缓存，并清空 Redis(L1) 与 Milvus(L2) 的检索缓存，
  因此无需重启后端即可检索到新语料。

> **提示**：嵌入模型（`BAAI/bge-small-zh-v1.5`）首次使用会自动下载并缓存。
> 离线开关 `HF_HUB_OFFLINE=1` 已写入 `.env`，后端与灌库脚本都会自动读取，无需手动设置；
> 否则 HuggingFace 客户端会先做一次网络探测，在网络受限时可能长时间重试。

参考规模：完整语料约 409 篇文档 / 1944 个 chunk。

---

## 🗺️ 未来规划 (Roadmap)

- [x] **多模态支持**：食材图片识别、菜品识别 ✅
- [x] **RAG 评估系统**：基于 RAGAS 的质量监控 ✅
- [x] **安全防护体系**：输入验证、提示词注入防护、速率限制 ✅
- [x] **LLM 使用统计**：Token 监控、性能分析页面 ✅
- [x] **Agent 智能模式**：ReAct 推理、工具调用、会话管理 ✅
- [x] **Subagent 专家体系**：内置与自定义子代理、可视化追踪 ✅
- [x] **MCP 协议支持**：远程工具加载、高德地图集成、工具名中文化 ✅
- [x] **AI 图片生成**：DALL-E 3 集成、imgbb 持久化存储 ✅
- [x] **饮食计划与记录**：周计划、已吃标记、AI 记录 ✅
- [x] **营养分析与目标追踪**：每日/每周摘要、偏差分析、营养可信度分级 ✅
- [x] **约束推理引擎**：过敏原硬过滤、软约束打分、冲突澄清与替代建议 ✅
- [x] **结构化饮食档案**：过敏原、饮食模式、营养目标、烹饪条件 ✅
- [x] **智能周计划生成**：七因子评分、事务落库、单餐替换与锁定 ✅
- [x] **储物柜与购物清单**：库存扣减、临期提醒、现有食材可做菜 ✅
- [x] **菜谱详情与烹饪模式**：份量缩放、单位换算、大字步骤与计时器 ✅
- [x] **家庭与多人份**：成员约束合并、份量系数 ✅
- [x] **反馈与评价**：收藏/做过/喜欢/不喜欢、评分与评论 ✅
- [x] **语音输入**：基于 Web Speech API 的语音转文字 ✅
- [ ] **语音播报**：烹饪步骤语音朗读
- [ ] **社区功能**：用户分享、评分聚合、评论互动
- [ ] **AR 烹饪指导**：增强现实辅助烹饪
- [ ] **真实用户验证**：小范围灰度，用真实数据驱动检索与推荐的持续优化

---

## 🤝 贡献指南

欢迎贡献代码、提出问题或建议！

1. Fork 本项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 提交 Pull Request

---

## 📄 开源协议

本项目基于 [APACHE LICENSE 2.0](LICENSE) 许可证开源。详情请参阅 LICENSE 文件。

---

## 🙏 致谢

- [HowToCook](https://github.com/Anduin2017/HowToCook) - 优质的开源食谱库
- [LangChain](https://www.langchain.com/) - 强大的 LLM 应用框架
- [Milvus](https://milvus.io/) - 高性能向量数据库
- [FastAPI](https://fastapi.tiangolo.com/) - 现代化的 Python Web 框架
- [NVIDIA NeMo Guardrails](https://developer.nvidia.com/nvidia-nemo) - 先进的安全防护框架
- [RAGAS](https://docs.ragas.io/) - RAG 评估框架

---

<div align="center">

**如果这个项目对您有帮助，请给一个 ⭐️ Star 支持一下！**

</div>
