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


_cached_engine = None


def _engine_cached():
    """首次使用时才建引擎，使测试能在导入后改写数据库地址。返回真正的 Engine 对象。"""
    global _cached_engine
    if _cached_engine is None:
        _cached_engine = _engine()
    return _cached_engine


class _EngineAccessor:
    """供测试使用的 engine 入口：其余属性转发到真正的 Engine。

    测试在每个用例前执行 ``db_module.engine._real = None`` 来丢弃旧引擎，
    再用 ``Base.metadata.create_all(db_module.engine)`` 建表；这两个操作
    都走这里。应用代码本身不再把这个代理对象当作 Session 的 bind
    （那会触发每条语句换连接的问题），只通过 _LazySession.get_bind 取真引擎。
    """

    @property
    def _real(self):
        return _cached_engine

    @_real.setter
    def _real(self, value):
        global _cached_engine
        if value is None:
            _cached_engine = None

    def __getattr__(self, name):
        return getattr(_engine_cached(), name)


engine = _EngineAccessor()


class _LazySession(Session):
    """把引擎创建推迟到首次使用，但交给 SQLAlchemy 的必须是真正的 Engine。

    原先的 _LazyEngine 代理对象不是 Engine 实例，Session 在同一个事务里
    会对每条语句各取一个新连接：flush 后再读看不到刚写入的行，建模板时
    template_versions 的外键因此报 templates.id 不存在（真实 PG 上复现，
    SQLite + StaticPool 因共用同一连接而掩盖了这个问题）。
    """

    def get_bind(self, mapper=None, clause=None, **kw):
        return _engine_cached()


SessionLocal = sessionmaker(class_=_LazySession, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
