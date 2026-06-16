# claw-zep 后端镜像
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 系统依赖（构建 graphiti/kuzu/asyncpg 等）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# 先拷贝依赖清单与 vendored graphiti（利用层缓存）
COPY requirements.txt ./
COPY graphiti ./graphiti
RUN pip install -r requirements.txt

# 拷贝源码
COPY . .

# 数据目录（Kuzu / Chroma / 导出 / 对象存储 fallback）
RUN mkdir -p /app/data

EXPOSE 8000

# 入口：等待依赖 → 执行迁移 → 启动
CMD ["sh", "-c", "alembic upgrade head || true; uvicorn main:app --host 0.0.0.0 --port 8000"]
