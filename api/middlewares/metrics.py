"""
轻量指标中间件（无外部依赖，进程内计数）
==========================================
统计请求数、状态分布、累计耗时，供 /metrics 以 Prometheus 文本格式暴露。
"""
import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# 进程内指标寄存器
_REGISTRY = {
    "requests_total": defaultdict(int),       # key: (method, status_class) -> count
    "duration_sum": 0.0,
    "duration_count": 0,
    "inflight": 0,
}


def snapshot() -> dict:
    return _REGISTRY


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in ("/metrics", "/health"):
            return await call_next(request)
        _REGISTRY["inflight"] += 1
        start = time.perf_counter()
        status = 500
        try:
            resp = await call_next(request)
            status = resp.status_code
            return resp
        finally:
            dur = time.perf_counter() - start
            _REGISTRY["requests_total"][(request.method, f"{status // 100}xx")] += 1
            _REGISTRY["duration_sum"] += dur
            _REGISTRY["duration_count"] += 1
            _REGISTRY["inflight"] -= 1


def render_prometheus() -> str:
    reg = _REGISTRY
    lines = [
        "# HELP claw_requests_total Total HTTP requests by method and status class",
        "# TYPE claw_requests_total counter",
    ]
    for (method, sc), n in sorted(reg["requests_total"].items()):
        lines.append(f'claw_requests_total{{method="{method}",status="{sc}"}} {n}')
    lines += [
        "# HELP claw_request_duration_seconds_sum Cumulative request duration",
        "# TYPE claw_request_duration_seconds_sum counter",
        f"claw_request_duration_seconds_sum {reg['duration_sum']:.6f}",
        "# TYPE claw_request_duration_seconds_count counter",
        f"claw_request_duration_seconds_count {reg['duration_count']}",
        "# HELP claw_requests_inflight In-flight requests",
        "# TYPE claw_requests_inflight gauge",
        f"claw_requests_inflight {reg['inflight']}",
    ]
    return "\n".join(lines) + "\n"
