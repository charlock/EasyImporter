"""元数据库引擎与会话。同步 SQLAlchemy，路由用普通 def 在线程池执行。"""

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _engine():
    url = get_settings().database_url
    # SQLite（测试）不支持连接池参数。
    if url.startswith("sqlite"):
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False, "timeout": 30},
            poolclass=StaticPool,
        )

        @event.listens_for(engine, "connect")
        def _enable_wal(conn, _record):
            # WAL 让读写不再互相阻塞，测试里同库多连接才不会报 database is locked。
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")

        return engine
    return create_engine(url, pool_size=10, max_overflow=10, pool_pre_ping=True)


class _LazyEngine:
    """首次使用时才建引擎，使测试能在导入后改写数据库地址。"""

    def __init__(self):
        self._real = None

    def _get(self):
        if self._real is None:
            self._real = _engine()
        return self._real

    def __getattr__(self, name):
        return getattr(self._get(), name)


engine = _LazyEngine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
