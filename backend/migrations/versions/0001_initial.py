"""初始表结构。

Revision ID: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("username", sa.String(64), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("must_change_password", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("failed_login_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("token_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "workspaces",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "workspace_members",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("workspace_id", sa.BigInteger, sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id"), nullable=False),
        sa.UniqueConstraint("workspace_id", "user_id"),
    )
    op.create_table(
        "datasources",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("db_type", sa.String(16), nullable=False),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer, nullable=False),
        sa.Column("database", sa.String(128), nullable=False),
        sa.Column("username", sa.String(128), nullable=False),
        sa.Column("password_enc", sa.Text, nullable=False),
        sa.Column("options", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "templates",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("workspace_id", sa.BigInteger, sa.ForeignKey("workspaces.id"), nullable=False, index=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("current_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_archived", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "template_versions",
        sa.Column("template_id", sa.BigInteger, sa.ForeignKey("templates.id"), primary_key=True),
        sa.Column("version", sa.Integer, primary_key=True),
        sa.Column("datasource_id", sa.BigInteger, sa.ForeignKey("datasources.id"), nullable=False),
        sa.Column("target_schema", sa.String(128), nullable=False, server_default=""),
        sa.Column("target_table", sa.String(128), nullable=False),
        sa.Column("sheet", sa.String(128), nullable=False, server_default=""),
        sa.Column("header_start_row", sa.Integer, nullable=False, server_default="1"),
        sa.Column("header_row_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("strategy", sa.String(16), nullable=False),
        sa.Column("business_keys", sa.JSON, nullable=False),
        sa.Column("scope_columns", sa.JSON, nullable=False),
        sa.Column("mapping", sa.JSON, nullable=False),
        sa.Column("rule_overrides", sa.JSON, nullable=False),
        sa.Column("created_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "synonym_groups",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("workspace_id", sa.BigInteger, sa.ForeignKey("workspaces.id"), nullable=False, index=True),
    )
    op.create_table(
        "synonym_terms",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("group_id", sa.BigInteger, sa.ForeignKey("synonym_groups.id"), nullable=False, index=True),
        sa.Column("workspace_id", sa.BigInteger, sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("term", sa.String(128), nullable=False),
        sa.UniqueConstraint("workspace_id", "term"),
    )
    op.create_table(
        "imports",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("workspace_id", sa.BigInteger, sa.ForeignKey("workspaces.id"), nullable=False, index=True),
        sa.Column("template_id", sa.BigInteger, sa.ForeignKey("templates.id"), nullable=False),
        sa.Column("template_version", sa.Integer, nullable=False),
        sa.Column("datasource_id", sa.BigInteger, sa.ForeignKey("datasources.id"), nullable=False),
        sa.Column("target_schema", sa.String(128), nullable=False, server_default=""),
        sa.Column("target_table", sa.String(128), nullable=False),
        sa.Column("strategy", sa.String(16), nullable=False),
        sa.Column("operator_id", sa.BigInteger, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, index=True),
        sa.Column("file_path", sa.Text, nullable=False, server_default=""),
        sa.Column("rows_path", sa.Text, nullable=False, server_default=""),
        sa.Column("report_path", sa.Text, nullable=False, server_default=""),
        sa.Column("row_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("processed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("inserted", sa.Integer, nullable=False, server_default="0"),
        sa.Column("updated", sa.Integer, nullable=False, server_default="0"),
        sa.Column("deleted", sa.Integer, nullable=False, server_default="0"),
        sa.Column("counts_exact", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("error_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failure_code", sa.String(64), nullable=False, server_default=""),
        sa.Column("failure_message", sa.Text, nullable=False, server_default=""),
        sa.Column("worker_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("cancel_requested", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("retry_of", sa.BigInteger, sa.ForeignKey("imports.id")),
    )
    op.create_table(
        "table_locks",
        sa.Column("datasource_id", sa.BigInteger, primary_key=True),
        sa.Column("target_schema", sa.String(128), primary_key=True),
        sa.Column("target_table", sa.String(128), primary_key=True),
        sa.Column("import_id", sa.BigInteger, sa.ForeignKey("imports.id"), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "import_logs",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("import_id", sa.BigInteger, sa.ForeignKey("imports.id"), nullable=False, index=True),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("params", sa.JSON, nullable=False),
        sa.Column("message", sa.Text, nullable=False, server_default=""),
    )
    op.create_table(
        "import_errors",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("import_id", sa.BigInteger, sa.ForeignKey("imports.id"), nullable=False, index=True),
        sa.Column("row_no", sa.Integer, nullable=False),
        sa.Column("column", sa.String(128), nullable=False, server_default=""),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("params", sa.JSON, nullable=False),
    )


def downgrade() -> None:
    for table in ("import_errors", "import_logs", "table_locks", "imports", "synonym_terms",
                  "synonym_groups", "template_versions", "templates", "datasources",
                  "workspace_members", "workspaces", "sessions", "users"):
        op.drop_table(table)
