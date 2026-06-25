# claw-zep 专用 PostgreSQL：内置 Apache AGE（图）+ pgvector（向量）
# 基于 Apache AGE 官方镜像（已含 PG + AGE），再编译安装 pgvector
#
# 注意：AGE 官方镜像 tag 随版本变化，若构建报 "manifest unknown"，
#   到 https://hub.docker.com/r/apache/age/tags 选一个 PG16 的可用 tag，
#   构建时覆盖： docker compose build --build-arg AGE_IMAGE=apache/age:<tag> postgres
ARG AGE_IMAGE=apache/age:PG16_latest
ARG PGVECTOR_VERSION=v0.8.0
FROM ${AGE_IMAGE}

ARG PGVECTOR_VERSION
USER root

# 编译 pgvector（与基础镜像同一 PG 大版本）
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends build-essential git ca-certificates postgresql-server-dev-16; \
    git clone --depth 1 --branch ${PGVECTOR_VERSION} https://github.com/pgvector/pgvector.git /tmp/pgvector; \
    cd /tmp/pgvector; \
    make; \
    make install; \
    rm -rf /tmp/pgvector; \
    apt-get purge -y build-essential git; \
    apt-get autoremove -y; \
    rm -rf /var/lib/apt/lists/*

# 启动时自动预加载 AGE（避免每连接 LOAD）。pgvector 无需预加载。
RUN echo "shared_preload_libraries = 'age'" >> /usr/share/postgresql/postgresql.conf.sample

# 首次初始化时创建扩展（应用层 pg_init 也会幂等创建，双保险）
COPY init-extensions.sql /docker-entrypoint-initdb.d/10-init-extensions.sql

USER postgres
