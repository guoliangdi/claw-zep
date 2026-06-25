-- claw-zep PostgreSQL 首次初始化：启用 AGE + pgvector 扩展
-- 应用层 core/adapters/pg_init.py 会再次幂等创建图与向量表，此处仅保证扩展就绪。

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS age;

LOAD 'age';
SET search_path = ag_catalog, "$user", public;

-- 创建图命名空间（若不存在）
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM ag_catalog.ag_graph WHERE name = 'claw_graph') THEN
        PERFORM ag_catalog.create_graph('claw_graph');
    END IF;
END
$$;
