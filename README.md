<div align="center">

# 🦞 claw-zep

**私有化 · 自主可控 · 时序记忆存储**

融合 Palantir 级动态时序知识图谱能力
前后端分离 · 多租户 · 全链路双时序

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![License](https://img.shields.io/badge/License-Apache--2.0-green.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](docker-compose.yml)

[功能特性](#-功能特性) · [架构设计](#-架构设计) · [模块功能](#-模块功能详解) · [快速开始](#-快速开始) · [API](#-api-概览) · [接入](#-客户端接入)

</div>

---

## 📖 项目简介

**claw-zep** 是一套可完全私有化部署的「时序知识中台」，为 AI Agent、企业知识库、风险推演等场景提供**带时间维度的长期记忆与知识图谱**能力。

与普通向量记忆库不同，claw-zep 的每一条知识都携带**双时间轴**——既记录"事实何时生效/失效"，也记录"何时被写入系统"。由此可以回答这类问题：

> *"三个月前我们对这家供应商的认知是什么？"*
> *"如果 A 供应商断供，会沿着供应链影响到哪些产品线？"*
> *"这个结论的依据来自哪几条原始记忆？"*

系统直接引入官方 **Graphiti** 作为实体/关系抽取内核（**不重构、只扩展**），在其外层自研调度层接管多租户绑定、时序打标与三大存储分发；当外部大模型不可用时自动降级为内置启发式抽取，确保**纯内网、无外网环境亦可完整运行**。

---

## ✨ 功能特性

| 能力 | 说明 |
|------|------|
| 🕒 **全局双时序模型** | 实体/关系/向量/记忆树节点强制挂载 `valid_from / valid_until / version / source`，支撑知识过期、冲突消解、**任意时间点快照**、**历史版本回溯**、因果推演 |
| 🧠 **基于 Graphiti 扩展** | 复用官方 Graphiti 的 LLM 实体/关系抽取能力，自研调度层注入租户/项目/时序并分发写入图库、向量库、记忆树 |
| 🌳 **OpenHuman 记忆树** | SourceTree / TopicTree / GlobalTree 三层架构，节点 Markdown 在线编辑、绑定图谱实体、版本回溯、**Obsidian 格式导出** |
| 🔍 **混合检索引擎** | 时序过滤 → 向量语义召回 → 图谱关系链路遍历 → 记忆树摘要加权重排，支撑常规问答 + 企业复杂事件溯源 |
| 🧭 **Palantir 级因果推演** | 自然语言提问 → 自动识别种子实体 → 因果链路 BFS → 子图可视化 → 记忆树证据溯源 → LLM 综合结论 |
| 🏢 **企业级多租户** | 超级租户 / 租户管理员 / 项目成员三级架构，全数据携带 `tenant_id`；Project 项目隔离，切换项目自动隔离数据 |
| 🔐 **RBAC + 审计** | 细粒度权限到**按钮级**，JWT + 项目 API Key 双鉴权，全链路增删改查落库审计 |
| 🔌 **OpenClaw / 龙虾接入** | 提供云端记忆插件替换 OpenClaw 本地文件存储，支持多设备跨端同步；附移动端 Agent SDK |
| 🛡️ **自主可控** | 全部组件 Apache-2.0 兼容协议，商用无风险；无外网时启发式抽取 + 哈希向量 + 本地存储全链路降级 |
| 🚀 **一键部署** | `docker compose up` 一键编排后端、前端、Kuzu、Chroma、PostgreSQL、Redis、MinIO、Celery |

---

## 🏗 架构设计

### 四层架构

```
┌──────────────────────────────────────────────────────────────────┐
│  ① 端侧应用层    龙虾移动端 Agent  ·  改造版 OpenClaw  ·  管理后台前端   │
├──────────────────────────────────────────────────────────────────┤
│  ② 网关&调度层   JWT鉴权 · RBAC · 多租户隔离 · 限流 · Celery异步队列     │
├──────────────────────────────────────────────────────────────────┤
│  ③ 统一记忆中枢   ┌─时序引擎─┐ ┌─Graphiti调度─┐ ┌─记忆树─┐ ┌─混合检索─┐ │
│   （核心）        └─────────┘ └──────────────┘ └────────┘ └──────────┘ │
├──────────────────────────────────────────────────────────────────┤
│  ④ 混合存储层    Kuzu(图谱) · Chroma(向量) · PostgreSQL(业务) · MinIO(对象) │
└──────────────────────────────────────────────────────────────────┘
```

### 写入链路

```
文本/对话 ──▶ Episode 入库(PENDING) ──▶ Celery 异步
                                          │
              ┌───────────────────────────┘
              ▼
     Graphiti 抽取实体/关系 (LLM, 无则启发式降级)
              │
              ▼  注入 tenant_id / project_id / valid_from / version
     ┌────────┼─────────────┬──────────────────┐
     ▼        ▼             ▼                  ▼
   Kuzu图库  PG镜像元数据   Chroma向量索引     记忆树 SourceTree 节点
            (时序 supersede)
```

### 检索链路

```
Query ──▶ 时序过滤(as_of) ──▶ 向量语义召回(实体) ──▶ 图谱关系链路扩展 ──▶ 记忆树加权 ──▶ 重排 ──▶ 结果
```

### 技术栈

| 层 | 技术选型 |
|----|----------|
| **后端** | Python 3.11 · FastAPI · Pydantic v2 · SQLAlchemy 2 (async) · Celery · Redis |
| **抽取内核** | Graphiti（vendored，Apache-2.0） |
| **存储** | Kuzu（图）· Chroma（向量）· PostgreSQL（业务/元数据）· MinIO/S3（对象） |
| **前端** | React 18 · TypeScript · Vite · Ant Design 5 · Zustand · React Router 6 · Cytoscape.js · @uiw/react-md-editor |
| **部署** | Docker Compose · Nginx |

---

## 🧩 模块功能详解

### 后端模块（`core/` · `api/` · `models/` · `schemas/`）

| 模块 | 路径 | 职责 |
|------|------|------|
| **配置/基础设施** | `core/config.py` `database.py` `redis_client.py` `celery_app.py` `logging.py` | 全局配置、异步 DB/Redis、Celery 队列、结构化日志 |
| **安全与鉴权** | `core/security.py` `permissions.py` `context.py` | 密码哈希、JWT、API Key、RBAC 权限解析、请求级租户/项目隔离上下文 |
| **时序引擎** ⭐ | `core/temporal/engine.py` | 时序过滤、失效过期、冲突消解（保留最新）、版本演进 `supersede`、快照生成、历史回滚 |
| **Graphiti 调度** ⭐ | `core/services/graphiti_orchestrator.py` `extractors.py` | 包装 Graphiti 抽取（+ 离线启发式降级）→ 时序打标 → 三库分发 |
| **记忆树** ⭐ | `core/memory_tree/` (`service` `builder` `summarizer` `exporter`) | 三层树构建、节点 CRUD、摘要生成、版本历史、Obsidian 导出 |
| **存储适配器** | `core/adapters/` (`kuzu` `chroma` `graph_repo` `object_storage` `embedding`) | 各存储统一封装，均带离线/降级实现 |
| **混合检索** ⭐ | `core/services/retrieval.py` | 常规混合检索 `search()` + Palantir 因果推演 `reason()` |
| **审计服务** | `core/services/audit_service.py` | 统一审计落库 |
| **异步任务** | `core/tasks/` | Episode 抽取、全局摘要构建、过期数据清理 |
| **数据模型** | `models/` | 租户/用户/RBAC/项目/图谱/记忆树/本体/Webhook/审计 + `TemporalMixin` |
| **API 路由** | `api/routers/` | 13 个业务路由模块（详见下） |
| **鉴权依赖** | `api/deps.py` `middlewares/` | JWT/API Key 解析、租户解析、项目上下文、RBAC 校验、请求上下文中间件 |

### 前端页面（`frontend/src/pages/`）

> 复刻 Zep 原生侧边导航布局，顶部全局 **租户/项目** 下拉切换，切换后全页面数据自动隔离；所有操作按钮按 RBAC 权限显隐。

**复刻 Zep 原生页面**
- 🔑 **登录** — JWT 账号密码登录，区分管理员/租户/普通用户
- 🏢 **租户管理**（超管） — 增删停用租户、配额配置
- 📁 **项目管理** — 项目 CRUD、API Key 管理、Ontology 本体在线编辑、成员管理
- 🕸 **图谱管理** — Cytoscape 画布可视化、Episodes 多条件筛选、实体/关系列表
- 🧪 **Playground 调试台** — 在线文本入库、在线检索、自定义时序范围与混合权重
- 👥 **用户权限** — 用户管理、角色 RBAC、细粒度权限分配
- 🔗 **Webhook 配置** — 回调地址管理、订阅记忆变更事件
- 👤 **个人中心** — 密钥、改密、项目快速切换
- 📜 **审计日志** — 全项目操作日志多条件筛选

**自研特色页面（区别于原版 Zep）**
- 🌳 **MemoryTree 记忆树** — 三层树形可视化、源/主题/全局切换、节点 Markdown 在线编辑、版本回溯、MD 导出
- 🕒 **Temporal 时序工作台** — 时间点快照、双时间点差异对比、单实体全生命周期变更链路
- 🧭 **Palantir 企业推演** — 自然语言提问、因果链路推演、图谱可视化、记忆树片段溯源

---

## 🚀 快速开始

### 方式 A：Docker Compose 一键部署（推荐）

```bash
git clone <your-repo-url> claw-zep && cd claw-zep
cp .env.example .env          # 可选：填写 LLM_API_KEY / EMBEDDING_API_KEY（留空走离线模式）
docker compose up -d --build
```

| 服务 | 地址 |
|------|------|
| 管理后台 | http://localhost |
| 后端 API 文档 | http://localhost:8000/api/docs |
| MinIO 控制台 | http://localhost:9001 |

默认超级管理员：`admin@claw-zep.com` / `Admin@123456`（首次启动自动创建，请尽快修改）。

### 方式 B：本地开发

```bash
# 后端
python -m venv .venv && source .venv/Scripts/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head            # 建表
python -m scripts.seed          # 初始化权限/角色/超管
uvicorn main:app --reload

# Celery（另开终端）
celery -A core.celery_app:celery_app worker --beat -Q graphiti,memory_tree,cleanup --loglevel=info

# 前端（另开终端）
cd frontend && npm install && npm run dev    # http://localhost:5173
```

> 💡 **离线/自主可控模式**：不配置 `LLM_API_KEY` / `EMBEDDING_API_KEY` 时，抽取自动降级为启发式、向量降级为确定性哈希、摘要降级为首句截断，全链路仍可运行。接入本地大模型（vLLM / Qwen / 智谱）只需将 `LLM_BASE_URL` 指向兼容 OpenAI 协议的私有地址。

---

## 📡 API 概览

完整交互式文档：`http://localhost:8000/api/docs`，业务接口前缀 `/api/v1`。

**全局请求头**：`Authorization: Bearer <JWT>` · `X-Tenant-ID` · `X-Project-ID`（前端拦截器自动携带）；OpenClaw/SDK 可用 `X-API-Key: cz_live_xxx` 免登录鉴权。

| 模块 | 代表端点 |
|------|----------|
| Auth | `POST /auth/login` · `GET /auth/me` · `POST /auth/refresh` |
| Tenants | `GET/POST /tenants` · `POST /tenants/{id}/suspend` |
| Projects | `GET/POST /projects` · `.../api-keys` · `.../ontology` · `.../members` |
| Graph | `GET /graph/episodes` `/entities` `/relations` `/visualization` |
| Memory | `POST /memory/add` · `POST /memory/search` |
| Temporal | `POST /temporal/snapshot` `/diff` `/lifecycle` |
| MemoryTree | `GET /memory-tree/tree` · `POST /memory-tree/nodes` · `.../rollback/{v}` · `/export` |
| Palantir | `POST /palantir/reason` |
| Users/RBAC | `/users` · `/rbac/roles` `/permissions` `/assign` |
| Webhooks / Audit | `/webhooks` · `/audit` |
| OpenClaw | `/openclaw/memory/add` `/search` `/sync` `/documents/{key}` |

---

## 🔌 客户端接入

### OpenClaw 云端记忆（替换本地文件存储）

```python
from openclaw_cloud_memory import CloudMemory, OpenClawCloudBackend

mem = CloudMemory(base_url="https://claw-zep.example.com",
                  api_key="cz_live_xxx", device_id="laptop-01")
mem.remember("用户偏好深色主题", group_id="prefs")     # 写入可检索记忆
hits = mem.search("主题偏好")                          # 混合检索
mem.save_document("profile", "# 用户画像\n喜欢深色主题")  # 命名文档，多设备覆盖同步

# 直接作为 OpenClaw 记忆后端
backend = OpenClawCloudBackend(mem)
backend.save("会话记忆"); text = backend.load()
```

### 龙虾(Lobster)移动端 Agent（异步）

```python
from openclaw_cloud_memory import AsyncCloudMemory

mem = AsyncCloudMemory(base_url="https://claw-zep.example.com",
                       api_key="cz_live_xxx", device_id="lobster-001")
await mem.remember("用户预订了去上海的机票", group_id="travel")
results = await mem.search("用户的出行安排")
await mem.aclose()
```

---

## 📂 目录结构

```
claw-zep/
├── main.py                     # FastAPI 入口（中间件 / 路由 / lifespan）
├── core/
│   ├── config · database · redis_client · celery_app · logging · exceptions
│   ├── security · permissions · context · bootstrap
│   ├── temporal/engine.py      # ⭐ 时序引擎
│   ├── memory_tree/            # ⭐ 记忆树（service/builder/summarizer/exporter）
│   ├── adapters/               # Kuzu / Chroma / 对象存储 / PG图仓储 / Embedding
│   ├── services/               # ⭐ graphiti_orchestrator / retrieval / audit
│   └── tasks/                  # Celery 任务
├── models/ · schemas/          # ORM 模型（含 TemporalMixin）/ Pydantic DTO
├── api/                        # deps · middlewares · routers(13 模块)
├── graphiti/                   # 官方 Graphiti 源码（vendored）
├── openclaw_plugin/            # OpenClaw 云端记忆（服务端路由 + 客户端 SDK）
├── migrations/                 # Alembic
├── frontend/                   # React 前端（12 页面）
└── docker-compose.yml · Dockerfile · README.md · docs/
```

---

## 🗺 Roadmap

- [ ] 社区检测与图谱聚类（Community 节点）
- [ ] 检索结果的可解释性高亮
- [ ] 多模态记忆（图片/附件向量化）
- [ ] 细粒度行级数据权限（字段脱敏）
- [ ] Grafana 监控面板与指标导出

---

## 🤝 贡献

欢迎 Issue 与 PR。提交前请确保：后端 `python -m py_compile`、前端 `npm run lint`（`tsc --noEmit`）通过。

## 📄 许可证

本项目以 [Apache-2.0](LICENSE) 协议开源。内置组件（Kuzu / Chroma / PostgreSQL / Redis / MinIO / Graphiti）均为 Apache-2.0 或兼容协议，**商用无风险**。

---

<div align="center">
<sub>如果这个项目对你有帮助，欢迎 ⭐ Star 支持！</sub>
</div>
