"""Alembic 迁移环境。元数据库换达梦或 MySQL 时，URL 由 EI_DATABASE_URL 决定。"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

from app.core.config import get_settings
from app.core.db import Base
from app.models import entities  # noqa: F401  确保模型注册到 metadata

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# 多个 api 副本同时启动时，用数据库会话级锁保证只有一个在跑迁移，其余等待后发现已是最新。
_LOCK_KEY = 726_001  # pg_advisory_lock 的 bigint 键，任意固定值
_LOCK_NAME = "easyimporter_migrate"
_LOCK_TIMEOUT_SECONDS = 600


def _acquire_lock(connection) -> None:
    name = connection.dialect.name
    if name == "postgresql":
        connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": _LOCK_KEY})
    elif name == "mysql":
        got = connection.execute(
            text("SELECT GET_LOCK(:name, :timeout)"),
            {"name": _LOCK_NAME, "timeout": _LOCK_TIMEOUT_SECONDS},
        ).scalar()
        if got != 1:
            raise RuntimeError("等待迁移锁超时，可能有其他实例正在迁移")
    # SQLite（测试）与达梦：单实例部署，不加锁。
    connection.commit()


def _release_lock(connection) -> None:
    name = connection.dialect.name
    if name == "postgresql":
        connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _LOCK_KEY})
    elif name == "mysql":
        connection.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": _LOCK_NAME})
    connection.commit()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        _acquire_lock(connection)
        try:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
            connection.commit()
        finally:
            _release_lock(connection)


run_migrations_online()
