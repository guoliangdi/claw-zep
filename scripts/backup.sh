#!/usr/bin/env bash
# claw-zep 备份脚本：PostgreSQL（含 AGE 图 + pgvector + 业务数据）+ 对象存储
# 用法：
#   PGHOST=localhost PGUSER=claw_zep_user PGPASSWORD=xxx PGDATABASE=claw_zep \
#   BACKUP_DIR=/backup ./scripts/backup.sh
#
# AGE 的图数据存在 ag_catalog schema + claw_graph schema 中，pg_dump 全库即可覆盖。
set -euo pipefail

PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-claw_zep_user}"
PGDATABASE="${PGDATABASE:-claw_zep}"
BACKUP_DIR="${BACKUP_DIR:-./backup}"
RETAIN_DAYS="${RETAIN_DAYS:-14}"
TS="$(date +%Y%m%d_%H%M%S)"

mkdir -p "$BACKUP_DIR"

echo "[1/3] pg_dump ${PGDATABASE} @ ${PGHOST}:${PGPORT} ..."
# -Fc 自定义格式(可并行恢复)；包含所有 schema（public + ag_catalog + claw_graph）
pg_dump -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" \
    -Fc -f "${BACKUP_DIR}/claw_zep_${TS}.dump"
echo "  -> ${BACKUP_DIR}/claw_zep_${TS}.dump"

echo "[2/3] 对象存储备份 ..."
if command -v mc >/dev/null 2>&1 && [ -n "${MINIO_ALIAS:-}" ]; then
    # MinIO：mc mirror（需先 mc alias set $MINIO_ALIAS ...）
    mc mirror --overwrite "${MINIO_ALIAS}/${OBJECT_STORAGE_BUCKET:-claw-zep-memory-tree}" \
        "${BACKUP_DIR}/object_${TS}/" || echo "  (mc mirror 跳过/失败)"
elif [ -d "./data/object_store" ]; then
    # 本地 fs 降级存储
    tar -czf "${BACKUP_DIR}/object_${TS}.tar.gz" -C ./data object_store
    echo "  -> ${BACKUP_DIR}/object_${TS}.tar.gz"
else
    echo "  (无对象存储数据，跳过)"
fi

echo "[3/3] 清理 ${RETAIN_DAYS} 天前的备份 ..."
find "$BACKUP_DIR" -name 'claw_zep_*.dump' -mtime +"$RETAIN_DAYS" -delete 2>/dev/null || true
find "$BACKUP_DIR" -name 'object_*.tar.gz' -mtime +"$RETAIN_DAYS" -delete 2>/dev/null || true

echo "备份完成。恢复：pg_restore -h HOST -U USER -d claw_zep --clean --if-exists claw_zep_${TS}.dump"
