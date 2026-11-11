"""数据源连接池缓存与主机白名单。"""

import ipaddress
from functools import lru_cache

from sqlalchemy.engine import URL

from app.connectors.target import TargetDatabase
from app.core.config import get_settings
from app.core.crypto import decrypt
from app.core.errors import ApiError
from app.models.entities import DAMENG, MYSQL, POSTGRES, Datasource

_DRIVERS = {POSTGRES: "psycopg", MYSQL: "pymysql", DAMENG: "dmPython"}
_SCHEMES = {POSTGRES: "postgresql", MYSQL: "mysql", DAMENG: "dm"}

_pool: dict[int, TargetDatabase] = {}


def check_host_allowed(host: str) -> None:
    allowed = get_settings().allowed_hosts
    if not allowed:
        return
    for item in allowed:
        if "/" in item:
            try:
                if ipaddress.ip_address(host) in ipaddress.ip_network(item, strict=False):
                    return
            except ValueError:
                continue
        elif host == item:
            return
    raise ApiError("DATASOURCE_HOST_NOT_ALLOWED", {"host": host})


def build_url(datasource: Datasource) -> str:
    return URL.create(
        drivername=f"{_SCHEMES[datasource.db_type]}+{_DRIVERS[datasource.db_type]}",
        username=datasource.username,
        password=decrypt(datasource.password_enc),
        host=datasource.host,
        port=datasource.port,
        database=datasource.database,
    ).render_as_string(hide_password=False)


def get_target(datasource: Datasource) -> TargetDatabase:
    cached = _pool.get(datasource.id)
    if cached is None:
        cached = TargetDatabase(datasource.db_type, build_url(datasource))
        _pool[datasource.id] = cached
    return cached


def drop_target(datasource_id: int) -> None:
    cached = _pool.pop(datasource_id, None)
    if cached is not None:
        cached.engine.dispose()


@lru_cache
def sqlite_target(url: str) -> TargetDatabase:
    """测试用：把 SQLite 当作 postgres 方言（双引号标识符）。"""
    return TargetDatabase(POSTGRES, url)
