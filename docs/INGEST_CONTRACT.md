# claw-zep 结构化直灌契约（worldmonitor 接入）

上游（worldmonitor）完成实体/关系抽取后，把**三元组**推送给 claw-zep；claw-zep 负责
时序打标、同名实体合并、写入图谱(AGE)+向量(pgvector)+时序镜像表，**不调用 LLM**。

---

## 1. 鉴权

项目级 API Key（在 claw-zep 后台 `项目 → API Key` 生成，形如 `cz_live_xxx`），
请求头携带：

```
X-API-Key: cz_live_xxxxxxxx
```

一个 API Key 绑定一个 Project，数据自动落到该项目（隔离边界）。

---

## 2. 端点

```
POST /api/v1/ingest/bulk
Content-Type: application/json
X-API-Key: cz_live_xxx
```

JWT 调用（后台/调试）：`POST /api/v1/ingest/bulk/jwt`，头带 `Authorization: Bearer` + `X-Project-ID`，需 `memory:write` 权限。

---

## 3. 请求体

```jsonc
{
  "source": "worldmonitor",            // 来源标签
  "group_id": null,                     // 可选，批次/会话分组
  "default_valid_from": null,           // 可选，缺省时序锚点
  "build_memory_tree": false,           // 高吞吐建议 false
  "records": [                          // 单批 ≤ 2000 条
    {
      "name": "signal-123",             // 可选，源文档标题
      "text": "原始正文（可选，留存溯源）",
      "valid_from": "2026-06-01T00:00:00Z",   // 事件/发布时间（时序锚点）
      "source_ref": {                   // 可选，溯源
        "table": "material_public_signals", "id": "123", "url": "https://..."
      },
      "entities": [
        {"name": "沪硅产业", "entity_type": "Supplier", "summary": "12寸硅片供应商", "attributes": {"country": "CN"}},
        {"name": "12寸硅片", "entity_type": "Material"}
      ],
      "relations": [
        {"source": "沪硅产业", "relation_type": "SUPPLIES", "target": "12寸硅片",
         "fact": "沪硅产业供应12寸硅片", "confidence": 0.9, "valid_from": null}
      ]
    }
  ]
}
```

### 字段语义

| 字段 | 说明 |
|------|------|
| `records[].valid_from` | **事件业务时间**（事实何时发生/发布），不是入库时间。决定时序轴位置，支撑"某时间点快照""风险传导随时间演化"。缺省取 `default_valid_from` → 当前时间 |
| `relations[].source/target` | **填实体 name**，必须出现在同一 record 的 `entities` 中 |
| `entity.name + entity_type` | **逻辑身份**：跨 record/跨批次同名同类型实体自动**合并到同一节点**（不会重复建点，version 递增） |
| `confidence` | 0~1，用于 Palantir 推演的链路权重 |
| `source_ref` | 溯源信息，原样留存到 Episode |

### 响应

```jsonc
{"source": "worldmonitor", "project_id": "...", "records": 2, "episodes": 2,
 "entities": 4, "relations": 2, "elapsed_ms": 419.0}
```

---

## 4. 时间格式

ISO-8601 带时区，如 `2026-06-01T00:00:00Z` 或 `2026-06-01T08:00:00+08:00`。

---

## 5. 批量与一致性

- 单次请求 `records ≤ 2000`，**整批一个事务**（全成功或全回滚）。更大量请用 SDK 自动分批。
- 同名实体合并、时序冲突消解由 claw-zep 处理，上游无需去重。

---

## 6. worldmonitor 侧改造建议

worldmonitor 现有 LLM 流水线（`admin_ai_templates` + `ai_processing_results`）已具备抽取能力，建议：

1. **新增一个抽取模板**（task_type 如 `extract_triples`），输入文档/信号，
   输出 `{entities:[...], relations:[...]}` JSON，存入 `ai_processing_results`。
2. **半结构化数据直接映射**（无需 LLM）：
   - `material_suppliers` → 实体 `{name: supplier_name, entity_type: "Supplier", attributes:{country, region, export_control_risk}}`
   - `material_public_signals` → 实体 `{name: material_name, entity_type: "Material"}` + 关系 `信号—ABOUT→材料`，`risk_level` 入 attributes
   - 供应商↔材料 → 关系 `供应商—SUPPLIES→材料`
3. 用 `claw_ingest_sdk.ClawIngest` 推送（见 `integrations/worldmonitor/claw_ingest_sdk.py`）。

---

## 7. Python SDK 示例

```python
from claw_ingest_sdk import ClawIngest

cz = ClawIngest("https://claw-zep.internal", "cz_live_xxx")

records = []
for row in fetch_material_signals():        # worldmonitor 的 MySQL 查询
    records.append(ClawIngest.record(
        name=row["title"],
        source_ref={"table": "material_public_signals", "id": row["signal_id"]},
        valid_from=row["published_at"],
        entities=[
            ClawIngest.entity(row["material_name"], "Material",
                              attributes={"risk_level": row["risk_level"]}),
        ],
        relations=[],
    ))

resp = cz.push(records, source="worldmonitor")   # 自动分批
print(resp)
cz.close()
```
