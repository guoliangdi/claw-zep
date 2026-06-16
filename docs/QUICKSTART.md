# claw-zep 启动文档（Quickstart）

## 一键启动（Docker Compose）

```bash
cp .env.example .env          # 可选：填写 LLM_API_KEY / EMBEDDING_API_KEY
docker compose up -d --build
```

启动后服务清单：

| 服务 | 容器 | 端口 | 说明 |
|------|------|------|------|
| 前端 | claw-zep-frontend | 80 | 管理后台（Nginx + React） |
| 后端 | claw-zep-backend | 8000 | FastAPI（/api/docs） |
| Celery | claw-zep-worker | - | 异步抽取 + 定时摘要/清理 |
| PostgreSQL | claw-zep-postgres | 5432 | 业务/元数据 |
| Redis | claw-zep-redis | 6379 | 缓存 + Celery broker |
| Chroma | claw-zep-chroma | 8001 | 向量库 |
| MinIO | claw-zep-minio | 9000/9001 | 对象存储 |

> Kuzu 为嵌入式图库，随后端进程运行（数据在 `backend_data` 卷）。

## 首次登录

- 地址：`http://localhost`
- 账号：`admin@claw-zep.com`
- 密码：`Admin@123456`（请在「个人中心」立即修改）

## 上手流程

1. 超级管理员登录 → **租户管理** 创建租户（可同时创建租户管理员）。
2. 顶部切换/创建 **项目**（自动分配 Kuzu 图与 Chroma 集合）。
3. **Playground** 写入文本 → 实时抽取实体/关系入库。
4. **图谱管理** 查看 Cytoscape 画布；**记忆树** 查看三层结构。
5. **时序快照** 做时间点快照/差异/生命周期；**企业推演** 输入业务问题做因果推演。
6. **项目 → API Key** 生成 `cz_live_xxx`，供 OpenClaw / 龙虾移动端接入（见 README）。

## 常用运维

```bash
docker compose logs -f backend          # 查看后端日志
docker compose exec backend alembic upgrade head   # 手动迁移
docker compose exec backend python -m scripts.seed # 重新初始化权限/超管（幂等）
docker compose down                      # 停止（保留数据卷）
docker compose down -v                   # 停止并清空数据
```

## 离线 / 自主可控模式

不配置 `LLM_API_KEY` / `EMBEDDING_API_KEY` 时：
- 实体/关系抽取自动降级为内置**启发式抽取器**；
- 向量化降级为**确定性哈希向量**；
- 记忆树摘要降级为**首句截断**。

全部检索、时序、推演链路仍可运行，便于纯内网/无外网环境验证与部署。如需接入本地大模型（vLLM/Qwen/智谱等），将 `LLM_BASE_URL` 指向兼容 OpenAI 协议的私有化地址即可。
