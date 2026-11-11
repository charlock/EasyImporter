"""元数据库 ORM 模型，对应架构设计第 5 节的表结构。"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.sqlite import INTEGER as _SQLITE_INTEGER
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.core.db import Base


class BigIntPK(TypeDecorator):
    """自增主键：PostgreSQL/MySQL/达梦用 BIGINT，SQLite 用 INTEGER 以获得 rowid 自增。"""

    impl = BigInteger
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "sqlite":
            return dialect.type_descriptor(_SQLITE_INTEGER())
        return dialect.type_descriptor(BigInteger())


ADMIN = "admin"
IMPORTER = "importer"

# 导入任务状态
QUEUED = "QUEUED"
RUNNING = "RUNNING"
COMMITTING = "COMMITTING"
SUCCEEDED = "SUCCEEDED"
FAILED = "FAILED"
CANCELLED = "CANCELLED"
UNKNOWN = "UNKNOWN"
TERMINAL_STATUSES = {SUCCEEDED, FAILED, CANCELLED, UNKNOWN}

APPEND = "APPEND"
UPSERT = "UPSERT"
REPLACE_SCOPE = "REPLACE_SCOPE"
STRATEGIES = {APPEND, UPSERT, REPLACE_SCOPE}

POSTGRES = "postgres"
MYSQL = "mysql"
DAMENG = "dameng"
DB_TYPES = {POSTGRES, MYSQL, DAMENG}


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default=IMPORTER)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped[User] = relationship()


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)


class Datasource(Base):
    __tablename__ = "datasources"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    db_type: Mapped[str] = mapped_column(String(16), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    database: Mapped[str] = mapped_column(String(128), nullable=False)
    username: Mapped[str] = mapped_column(String(128), nullable=False)
    password_enc: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Template(Base):
    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TemplateVersion(Base):
    __tablename__ = "template_versions"

    template_id: Mapped[int] = mapped_column(ForeignKey("templates.id"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    datasource_id: Mapped[int] = mapped_column(ForeignKey("datasources.id"), nullable=False)
    target_schema: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    target_table: Mapped[str] = mapped_column(String(128), nullable=False)
    sheet: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    header_start_row: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    header_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    strategy: Mapped[str] = mapped_column(String(16), nullable=False, default=APPEND)
    business_keys: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    scope_columns: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    mapping: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    rule_overrides: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SynonymGroup(Base):
    __tablename__ = "synonym_groups"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)


class SynonymTerm(Base):
    __tablename__ = "synonym_terms"
    __table_args__ = (UniqueConstraint("workspace_id", "term"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("synonym_groups.id"), nullable=False, index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    term: Mapped[str] = mapped_column(String(128), nullable=False)


class ImportTask(Base):
    __tablename__ = "imports"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("templates.id"), nullable=False)
    template_version: Mapped[int] = mapped_column(Integer, nullable=False)
    datasource_id: Mapped[int] = mapped_column(ForeignKey("datasources.id"), nullable=False)
    target_schema: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    target_table: Mapped[str] = mapped_column(String(128), nullable=False)
    strategy: Mapped[str] = mapped_column(String(16), nullable=False)
    operator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=QUEUED, index=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    rows_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    report_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    counts_exact: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_code: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    failure_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    worker_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    retry_of: Mapped[int | None] = mapped_column(ForeignKey("imports.id"))


class TableLock(Base):
    __tablename__ = "table_locks"

    datasource_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    target_schema: Mapped[str] = mapped_column(String(128), primary_key=True, default="")
    target_table: Mapped[str] = mapped_column(String(128), primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("imports.id"), nullable=False)
    locked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ImportLog(Base):
    __tablename__ = "import_logs"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("imports.id"), nullable=False, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    level: Mapped[str] = mapped_column(String(16), nullable=False, default="INFO")
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    params: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")


class ImportError(Base):
    __tablename__ = "import_errors"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("imports.id"), nullable=False, index=True)
    row_no: Mapped[int] = mapped_column(Integer, nullable=False)
    column: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    params: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
