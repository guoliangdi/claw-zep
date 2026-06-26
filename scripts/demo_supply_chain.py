"""
半导体供应链 Demo 种子脚本
==========================
向运行中的 claw-zep 灌入一张『带时间线的半导体供应链知识图谱』，并演示
Palantir 式推演："某材料断供 → 沿供应链影响哪些下游"。

前置：claw-zep 后端在运行（默认 http://localhost:8000）。
用法：
    python scripts/demo_supply_chain.py [--base http://localhost:8000] \
        [--email admin@claw-zep.com] [--password Admin@123456]

脚本会（幂等）：
  1. 创建租户「半导体供应链」+ 项目「supply-chain-demo」+ API Key
  2. 用结构化直灌 SDK 灌入供应商/材料/晶圆厂三层链路 + 风险信号（带 valid_from 时间线）
  3. 跑一次 /palantir/reason 推演并打印因果链路
"""
import argparse
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "integrations", "worldmonitor"))
from claw_ingest_sdk import ClawIngest  # noqa: E402

E = ClawIngest.entity
R = ClawIngest.relation
REC = ClawIngest.record


def build_records():
    """三层供应链：供应商 →SUPPLIES→ 材料 →SUPPLIES→ 晶圆厂 →PRODUCES→ 产品。"""
    def sup(name): return E(name, "Supplier")
    def mat(name, **a): return E(name, "Material", attributes=a)
    def fab(name): return E(name, "Fab")
    def prod(name): return E(name, "Product")

    records = [
        # —— 供应商 → 材料（2025 既有产能）——
        REC(name="供应关系-硅片", valid_from="2025-06-01T00:00:00Z",
            source_ref={"table": "material_suppliers", "id": "huatech"},
            entities=[sup("沪硅产业"), sup("SUMCO"), mat("12寸硅片")],
            relations=[R("沪硅产业", "SUPPLIES", "12寸硅片", confidence=0.9),
                       R("SUMCO", "SUPPLIES", "12寸硅片", confidence=0.85)]),
        REC(name="供应关系-光刻胶", valid_from="2025-06-01T00:00:00Z",
            entities=[sup("信越化学"), mat("ArF光刻胶")],
            relations=[R("信越化学", "SUPPLIES", "ArF光刻胶", confidence=0.9)]),
        REC(name="供应关系-氟化氢", valid_from="2025-06-01T00:00:00Z",
            entities=[sup("森田化学"), mat("高纯氟化氢")],
            relations=[R("森田化学", "SUPPLIES", "高纯氟化氢", confidence=0.8)]),

        # —— 材料 → 晶圆厂 ——
        REC(name="材料-晶圆厂", valid_from="2025-06-01T00:00:00Z",
            entities=[mat("12寸硅片"), mat("ArF光刻胶"), mat("高纯氟化氢"),
                      fab("中芯国际"), fab("长江存储")],
            relations=[
                R("12寸硅片", "SUPPLIES", "中芯国际", confidence=0.9),
                R("12寸硅片", "SUPPLIES", "长江存储", confidence=0.9),
                R("ArF光刻胶", "SUPPLIES", "中芯国际", confidence=0.85),
                R("高纯氟化氢", "SUPPLIES", "中芯国际", confidence=0.8),
                R("高纯氟化氢", "SUPPLIES", "长江存储", confidence=0.8),
            ]),
        # —— 晶圆厂 → 产品 ——
        REC(name="晶圆厂-产品", valid_from="2025-06-01T00:00:00Z",
            entities=[fab("中芯国际"), fab("长江存储"), prod("14nm逻辑芯片"), prod("3D NAND闪存")],
            relations=[
                R("中芯国际", "PRODUCES", "14nm逻辑芯片", confidence=0.9),
                R("长江存储", "PRODUCES", "3D NAND闪存", confidence=0.9),
            ]),

        # —— 风险信号（带时间线，模拟 worldmonitor material_public_signals）——
        REC(name="信号-光刻胶涨价", valid_from="2026-02-10T00:00:00Z",
            text="信越化学 ArF 光刻胶交期延长、价格上涨",
            source_ref={"table": "material_public_signals", "id": "s-2026-02"},
            entities=[mat("ArF光刻胶", risk_level="medium", signal="价格上涨")],
            relations=[]),
        REC(name="信号-氟化氢出口管制", valid_from="2026-03-15T00:00:00Z",
            text="高纯氟化氢被列入出口管制，供应存在中断风险",
            source_ref={"table": "material_public_signals", "id": "s-2026-03"},
            entities=[mat("高纯氟化氢", risk_level="high", signal="出口管制")],
            relations=[]),
        REC(name="信号-硅片产能紧张", valid_from="2026-04-20T00:00:00Z",
            text="12寸硅片全球产能紧张",
            source_ref={"table": "material_public_signals", "id": "s-2026-04"},
            entities=[mat("12寸硅片", risk_level="medium", signal="产能紧张")],
            relations=[]),
    ]
    return records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.getenv("CLAW_BASE", "http://localhost:8000"))
    ap.add_argument("--email", default="admin@claw-zep.com")
    ap.add_argument("--password", default="Admin@123456")
    args = ap.parse_args()
    B = args.base.rstrip("/") + "/api/v1"
    c = httpx.Client(timeout=60)

    # 1. 登录
    tok = c.post(f"{B}/auth/login", json={"email": args.email, "password": args.password}).json()["access_token"]
    H = {"Authorization": f"Bearer {tok}"}

    # 2. 租户（幂等）
    tenants = c.get(f"{B}/tenants", headers=H, params={"page_size": 200}).json().get("items", [])
    t = next((x for x in tenants if x["slug"] == "semicon"), None)
    if not t:
        t = c.post(f"{B}/tenants", headers=H, json={"name": "半导体供应链", "slug": "semicon"}).json()
    tid = t["id"]
    HT = {**H, "X-Tenant-ID": tid}

    # 3. 项目（幂等）
    projects = c.get(f"{B}/projects", headers=HT).json()
    p = next((x for x in projects if x["slug"] == "supply-chain-demo"), None)
    if not p:
        p = c.post(f"{B}/projects", headers=HT,
                   json={"name": "supply-chain-demo", "slug": "supply-chain-demo",
                         "description": "半导体供应链时序知识图谱 Demo"}).json()
    pid = p["id"]
    HP = {**HT, "X-Project-ID": pid}

    # 4. API Key + 结构化直灌
    key = c.post(f"{B}/projects/{pid}/api-keys", headers=HT, json={"name": "demo-seed"}).json()["api_key"]
    cz = ClawIngest(args.base, key)
    resp = cz.push(build_records(), source="worldmonitor-demo")
    cz.close()
    print(f"\n✓ 灌入完成: {resp}")

    # 5. 推演演示
    print("\n" + "=" * 60)
    print("Palantir 推演：高纯氟化氢供应中断会影响哪些下游？")
    print("=" * 60)
    r = c.post(f"{B}/palantir/reason", headers=HP,
               json={"question": "高纯氟化氢 供应中断 会影响哪些下游产品线",
                     "max_hops": 4, "max_paths": 20}).json()
    print(f"种子实体: {[s['name'] for s in r.get('seed_entities', [])]}")
    print(f"因果链路({len(r.get('causal_paths', []))}):")
    for path in r.get("causal_paths", [])[:10]:
        print(f"  · {path.get('narrative')}  (置信 {path.get('score')})")
    print(f"\n子图: {r['graph']['node_count']} 节点 / {r['graph']['edge_count']} 边")
    print("\n前端体验：登录后顶部切到租户『半导体供应链』+ 项目『supply-chain-demo』，")
    print("打开『企业推演』输入上面的问题；或『图谱管理』看画布、『时序快照』选不同时间点看风险演化。")


if __name__ == "__main__":
    main()
