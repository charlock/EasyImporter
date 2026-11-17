"""导入任务记录源文件名。

Revision ID: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 提交时上传的原文件名（file_path 落盘固定为 source.xlsx，原名此前未保留）。
    op.add_column("imports", sa.Column("file_name", sa.String(255), nullable=False,
                                       server_default=""))


def downgrade() -> None:
    op.drop_column("imports", "file_name")
