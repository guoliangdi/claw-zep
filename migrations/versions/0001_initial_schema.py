"""initial schema — 全部业务表

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-15

初始迁移：直接依据 ORM 模型 metadata 创建全部表。
后续结构变更请使用 `alembic revision --autogenerate` 增量生成。
"""
from alembic import op

from core.database import Base
import models  # noqa: F401  确保全部模型注册到 metadata

# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
