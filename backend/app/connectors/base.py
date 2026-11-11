"""目标库适配层的公共类型与接口。业务代码只依赖这里，不出现方言判断。"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy.engine import Connection


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    type: str
    comment: str = ""
    nullable: bool = True
    default: str | None = None
    is_primary_key: bool = False


@dataclass(frozen=True)
class UniqueKey:
    name: str
    columns: tuple[str, ...]


@dataclass(frozen=True)
class TableInfo:
    schema: str
    name: str
    comment: str = ""


@dataclass
class TableSchema:
    schema: str
    table_name: str
    columns: list[ColumnInfo]
    unique_keys: list[UniqueKey] = field(default_factory=list)
    engine: str = ""  # 仅 MySQL 有意义，用于拒绝非 InnoDB

    def column(self, name: str) -> ColumnInfo | None:
        return next((item for item in self.columns if item.name == name), None)


@dataclass
class WritePlan:
    """一次写入的完整计划，由 worker 根据模板版本构造。"""

    strategy: str
    columns: list[str]
    business_keys: list[str] = field(default_factory=list)
    scope_columns: list[str] = field(default_factory=list)
    # REPLACE_SCOPE 的删除范围：每个元素是一行范围列取值。
    scopes: list[dict] = field(default_factory=list)


@dataclass
class WriteResult:
    inserted: int = 0
    updated: int = 0
    deleted: int = 0
    counts_exact: bool = True


class Connector(Protocol):
    def list_tables(self, schema: str | None) -> list[TableInfo]: ...

    def get_table_schema(self, schema: str | None, table: str) -> TableSchema: ...

    def test_connection(self) -> None: ...

    def write(self, conn: Connection, schema: str | None, table: str, plan: WritePlan,
              rows: Iterable[dict]) -> WriteResult: ...
