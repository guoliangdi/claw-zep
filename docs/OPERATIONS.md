# claw-zep 运维手册

## 健康与可观测

| 端点 | 说明 |
|------|------|
| `GET /health` | 存活探针（liveness），轻量 |
| `GET /health/ready` | 就绪探针（readiness）：深度检查 PostgreSQL / Redis / pgvector / AGE |
| `GET /metrics` | Prometheus 文本格式指标（请求数、状态分布、累计耗时、in-flight） |

`/health/ready` 返回示例：
```json
{"status":"ready","storage_backend":"postgres",
 "checks":{"postgres":"ok","redis":"ok","pgvector":"ok","age":"ok"}}
```
- `status=ready` 全绿；`degraded` 表示 PostgreSQL 异常（致命）。Redis/AGE 不可用为非致命（限流 fail-open、图遍历回退 SQL）。

Prometheus 抓取配置：
```yaml
scrape_configs:
  - job_name: claw-zep
    metrics_path: /metrics
    static_configs: [{ targets: ['claw-zep-backend:8000'] }]
```

## 限流

- per-tenant（无租户则按 API Key / 客户端 IP）固定窗口，每分钟上限 `RATE_LIMIT_REQUESTS_PER_MINUTE`（默认 100）。
- 超限返回 `429` + `Retry-After`；正常响应带 `X-RateLimit-Remaining`。
- **Redis 不可用时 fail-open**（放行，不阻断业务）。生产务必保证 Redis 可用，限流才生效。

## 备份与恢复

```bash
# 备份（PG 全库含 AGE 图 + pgvector + 业务；对象存储）
PGHOST=<host> PGUSER=claw_zep_user PGPASSWORD=<pwd> PGDATABASE=claw_zep \
  BACKUP_DIR=/backup ./scripts/backup.sh

# 恢复
pg_restore -h <host> -U claw_zep_user -d claw_zep --clean --if-exists /backup/claw_zep_<ts>.dump
```
- AGE 图数据位于 `ag_catalog` + `claw_graph` schema，`pg_dump` 全库已覆盖，无需单独导出。
- 建议 cron 每日备份，保留期由 `RETAIN_DAYS`（默认 14）控制。

## 存储后端

`STORAGE_BACKEND=postgres`（推荐）：单 PostgreSQL = Apache AGE（图）+ pgvector（向量）+ 业务/时序镜像表。
- 镜像表为**时序事实源**，支持任意时间点快照；AGE 为当前状态图，做 VLE 路径遍历；AGE 不可用自动回退 SQL。
- 私有化单实例部署：PG 原生安装即可（见 `deploy/postgres/` Dockerfile 或 apt 原生安装 AGE+pgvector）。

`STORAGE_BACKEND=kuzu_chroma`（旧）：Kuzu 图 + Chroma 向量，多服务，保留兼容。

## 离线 / 自主可控

不配置 `LLM_API_KEY` / `EMBEDDING_API_KEY` 时全链路降级（启发式抽取 / 哈希向量 / 首句摘要），纯内网可运行。接本地大模型把 `LLM_BASE_URL` / `EMBEDDING_BASE_URL` 指向兼容 OpenAI 协议的私有地址（如 vLLM）。
