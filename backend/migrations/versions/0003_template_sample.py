"""模板样例原文件落盘（template_samples 表）。

Revision ID: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 每模板一份样例原文件（最新上传的为准），供再次编辑时回显；与模板行
    # 分离成表，避免列表查询顺带读出二进制大对象。
    op.create_table(
        "template_samples",
        sa.Column("template_id", sa.BigInteger(), sa.ForeignKey("templates.id"), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("template_id"),
    )


def downgrade() -> None:
    op.drop_table("template_samples")
