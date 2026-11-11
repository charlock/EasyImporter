"""三种目标库共用的元数据探查与写入实现。

探查 SQL 按方言区分，写入语句按方言生成，参数一律走绑定参数，
表名和列名来自元数据探查结果并经过白名单校验，不拼接用户输入。
"""

import re
from collections.abc import Iterable

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from app.connectors.base import (
    ColumnInfo,
    TableInfo,
    TableSchema,
    UniqueKey,
    WritePlan,
    WriteResult,
)
from app.core.config import get_settings
from app.models.entities import DAMENG, MYSQL, POSTGRES, REPLACE_SCOPE, UPSERT

# 标识符只允许字母、数字、下划线与中文，防止拼接注入。
_IDENT = re.compile(r"^[\w一-鿿]+$")


class UnsafeIdentifier(ValueError):
    pass


def quote_ident(name: str, dialect: str) -> str:
    if not _IDENT.match(name):
        raise UnsafeIdentifier(f"非法标识符: {name}")
    if dialect == MYSQL:
        return f"`{name}`"
    return f'"{name}"'


class TargetDatabase:
    """一个已登记数据源的连接。engine 由连接池缓存复用。"""

    def __init__(self, dialect: str, url: str):
        self.dialect = dialect
        self.engine: Engine = create_engine(url, pool_pre_ping=True)

    # ---- 元数据探查 -------------------------------------------------------

    def test_connection(self) -> None:
        with self.engine.connect() as conn:
            conn.execute(text("SELECT 1"))

    def list_tables(self, schema: str | None) -> list[TableInfo]:
        schema = schema or self._default_schema()
        sql = {
            POSTGRES: "SELECT table_schema, table_name FROM information_schema.tables "
                      "WHERE table_schema = :schema AND table_type = 'BASE TABLE' ORDER BY table_name",
            MYSQL: "SELECT table_schema, table_name FROM information_schema.tables "
                   "WHERE table_schema = :schema AND table_type = 'BASE TABLE' ORDER BY table_name",
            DAMENG: 'SELECT OWNER, TABLE_NAME FROM ALL_TABLES WHERE OWNER = :schema ORDER BY TABLE_NAME',
        }[self.dialect]
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), {"schema": schema}).all()
        return [TableInfo(schema=row[0], name=row[1]) for row in rows]

    def get_table_schema(self, schema: str | None, table: str) -> TableSchema:
        schema = schema or self._default_schema()
        with self.engine.connect() as conn:
            columns = self._columns(conn, schema, table)
            unique_keys = self._unique_keys(conn, schema, table)
            engine_name = self._engine_name(conn, schema, table)
        return TableSchema(schema=schema, table_name=table, columns=columns,
                           unique_keys=unique_keys, engine=engine_name)

    def _default_schema(self) -> str:
        with self.engine.connect() as conn:
            if self.dialect == POSTGRES:
                return conn.execute(text("SELECT current_schema()")).scalar() or "public"
            if self.dialect == MYSQL:
                return conn.execute(text("SELECT DATABASE()")).scalar() or ""
            return conn.execute(text("SELECT USER FROM DUAL")).scalar() or ""

    def _columns(self, conn: Connection, schema: str, table: str) -> list[ColumnInfo]:
        if self.dialect == DAMENG:
            sql = text(
                "SELECT c.COLUMN_NAME, c.DATA_TYPE, c.DATA_LENGTH, c.DATA_PRECISION, c.DATA_SCALE, "
                "c.NULLABLE, c.DATA_DEFAULT, m.COMMENTS "
                "FROM ALL_TAB_COLUMNS c LEFT JOIN ALL_COL_COMMENTS m "
                "ON m.OWNER = c.OWNER AND m.TABLE_NAME = c.TABLE_NAME AND m.COLUMN_NAME = c.COLUMN_NAME "
                "WHERE c.OWNER = :schema AND c.TABLE_NAME = :table ORDER BY c.COLUMN_ID"
            )
        elif self.dialect == POSTGRES and conn.dialect.name == "postgresql":
            # 真实 PG：用 pg_catalog.col_description 读列注释。information_schema
            # 里没有注释字段，之前这里取字面量 ''，导致自动匹配在 PG 上丢掉
            # “注释 90 分”这一档。SQLite 替身（测试用）走下面的旧分支。
            sql = text(
                "SELECT column_name, data_type, character_maximum_length, numeric_precision, "
                "numeric_scale, is_nullable, column_default, "
                "pg_catalog.col_description(format('%I.%I', table_schema, table_name)::regclass, "
                "ordinal_position) "
                "FROM information_schema.columns "
                "WHERE table_schema = :schema AND table_name = :table ORDER BY ordinal_position"
            )
        else:
            sql = text(
                "SELECT column_name, data_type, character_maximum_length, numeric_precision, "
                "numeric_scale, is_nullable, column_default, "
                + ("column_comment" if self.dialect == MYSQL else "''")
                + " FROM information_schema.columns "
                "WHERE table_schema = :schema AND table_name = :table ORDER BY ordinal_position"
            )
        pk = self._primary_keys(conn, schema, table)
        result: list[ColumnInfo] = []
        for row in conn.execute(sql, {"schema": schema, "table": table}):
            result.append(ColumnInfo(
                name=row[0],
                type=_render_type(row[1], row[2], row[3], row[4]),
                nullable=str(row[5]).upper() in {"YES", "Y"},
                default=None if row[6] in (None, "") else str(row[6]).strip(),
                comment="" if row[7] is None else str(row[7]),
                is_primary_key=row[0] in pk,
            ))
        return result

    def _primary_keys(self, conn: Connection, schema: str, table: str) -> set[str]:
        if self.dialect == DAMENG:
            sql = text(
                "SELECT cc.COLUMN_NAME FROM ALL_CONSTRAINTS c JOIN ALL_CONS_COLUMNS cc "
                "ON cc.OWNER = c.OWNER AND cc.CONSTRAINT_NAME = c.CONSTRAINT_NAME "
                "WHERE c.OWNER = :schema AND c.TABLE_NAME = :table AND c.CONSTRAINT_TYPE = 'P'"
            )
        else:
            sql = text(
                "SELECT kcu.column_name FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu "
                "ON kcu.constraint_name = tc.constraint_name AND kcu.table_schema = tc.table_schema "
                "WHERE tc.table_schema = :schema AND tc.table_name = :table AND tc.constraint_type = 'PRIMARY KEY'"
            )
        return {row[0] for row in conn.execute(sql, {"schema": schema, "table": table})}

    def _unique_keys(self, conn: Connection, schema: str, table: str) -> list[UniqueKey]:
        if self.dialect == POSTGRES:
            sql = text(
                "SELECT i.relname, a.attname FROM pg_index x "
                "JOIN pg_class t ON t.oid = x.indrelid JOIN pg_class i ON i.oid = x.indexrelid "
                "JOIN pg_namespace n ON n.oid = t.relnamespace "
                "JOIN LATERAL unnest(x.indkey) WITH ORDINALITY AS k(attnum, ord) ON true "
                "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum "
                "WHERE n.nspname = :schema AND t.relname = :table AND x.indisunique "
                "ORDER BY i.relname, k.ord"
            )
        elif self.dialect == MYSQL:
            sql = text(
                "SELECT index_name, column_name FROM information_schema.statistics "
                "WHERE table_schema = :schema AND table_name = :table AND non_unique = 0 "
                "ORDER BY index_name, seq_in_index"
            )
        else:
            sql = text(
                "SELECT i.INDEX_NAME, c.COLUMN_NAME FROM ALL_INDEXES i "
                "JOIN ALL_IND_COLUMNS c ON c.INDEX_OWNER = i.OWNER AND c.INDEX_NAME = i.INDEX_NAME "
                "WHERE i.OWNER = :schema AND i.TABLE_NAME = :table AND i.UNIQUENESS = 'UNIQUE' "
                "ORDER BY i.INDEX_NAME, c.COLUMN_POSITION"
            )
        grouped: dict[str, list[str]] = {}
        for name, column in conn.execute(sql, {"schema": schema, "table": table}):
            grouped.setdefault(name, []).append(column)
        return [UniqueKey(name=name, columns=tuple(columns)) for name, columns in grouped.items()]

    def _engine_name(self, conn: Connection, schema: str, table: str) -> str:
        if self.dialect != MYSQL:
            return ""
        sql = text("SELECT engine FROM information_schema.tables "
                   "WHERE table_schema = :schema AND table_name = :table")
        return conn.execute(sql, {"schema": schema, "table": table}).scalar() or ""

    # ---- 写入 -------------------------------------------------------------

    def write(self, conn: Connection, schema: str | None, table: str, plan: WritePlan,
              rows: Iterable[dict]) -> WriteResult:
        schema = schema or ""
        qualified = _qualified(self.dialect, schema, table)
        # UPSERT 在三种库上都拿不到精确的新增/更新拆分（见 _write_batch），其余策略是精确值。
        result = WriteResult(counts_exact=plan.strategy != UPSERT)
        if plan.strategy == REPLACE_SCOPE:
            result.deleted = self._delete_scope(conn, qualified, plan)
        batch: list[dict] = []
        for row in rows:
            batch.append({column: row.get(column) for column in plan.columns})
            if len(batch) >= get_settings().batch_size:
                self._write_batch(conn, qualified, plan, batch, result)
                batch = []
        if batch:
            self._write_batch(conn, qualified, plan, batch, result)
        return result

    def _delete_scope(self, conn: Connection, qualified: str, plan: WritePlan) -> int:
        """按范围列组合的去重值删除，组合超过阈值时拆多条语句，仍在同一事务内。"""
        columns = plan.scope_columns
        quoted = [quote_ident(column, self.dialect) for column in columns]
        deleted = 0
        chunk = get_settings().scope_tuple_chunk
        for start in range(0, len(plan.scopes), chunk):
            part = plan.scopes[start:start + chunk]
            params: dict = {}
            if len(columns) == 1:
                names = []
                for index, scope in enumerate(part):
                    params[f"p{index}"] = scope[columns[0]]
                    names.append(f":p{index}")
                sql = f"DELETE FROM {qualified} WHERE {quoted[0]} IN ({', '.join(names)})"
            else:
                clauses = []
                for index, scope in enumerate(part):
                    terms = []
                    for column, quoted_column in zip(columns, quoted):
                        key = f"p{index}_{column}"
                        params[key] = scope[column]
                        terms.append(f"{quoted_column} = :{key}")
                    clauses.append("(" + " AND ".join(terms) + ")")
                sql = f"DELETE FROM {qualified} WHERE " + " OR ".join(clauses)
            deleted += conn.execute(text(sql), params).rowcount or 0
        return deleted

    def _write_batch(self, conn: Connection, qualified: str, plan: WritePlan, batch: list[dict],
                     result: WriteResult) -> None:
        quoted = [quote_ident(column, self.dialect) for column in plan.columns]
        placeholders = ", ".join(f":{column}" for column in plan.columns)
        insert = f"INSERT INTO {qualified} ({', '.join(quoted)}) VALUES ({placeholders})"
        if plan.strategy == UPSERT:
            sql = self._upsert_sql(qualified, plan, quoted, placeholders)
        else:
            sql = insert
        outcome = conn.execute(text(sql), batch)
        affected = outcome.rowcount or 0
        if plan.strategy != UPSERT:
            result.inserted += affected
            return
        # 每批单独估算，再累加到总数，不能用累计值参与本批计算。
        if self.dialect == MYSQL:
            # ON DUPLICATE KEY：新增计 1、更新计 2、值未变计 0，据此估算更新行数。
            batch_updated = min(max(affected - len(batch), 0), len(batch))
        else:
            # PostgreSQL ON CONFLICT 与达梦 MERGE 只返回总行数，拆不出更新，全部计入新增。
            batch_updated = 0
        result.updated += batch_updated
        result.inserted += len(batch) - batch_updated

    def _upsert_sql(self, qualified: str, plan: WritePlan, quoted: list[str], placeholders: str) -> str:
        keys = [quote_ident(column, self.dialect) for column in plan.business_keys]
        updates = [column for column in plan.columns if column not in plan.business_keys]
        assignments = ", ".join(
            f"{quote_ident(column, self.dialect)} = EXCLUDED.{quote_ident(column, self.dialect)}"
            if self.dialect == POSTGRES
            else f"{quote_ident(column, self.dialect)} = VALUES({quote_ident(column, self.dialect)})"
            for column in updates
        )
        if self.dialect == POSTGRES:
            return (f"INSERT INTO {qualified} ({', '.join(quoted)}) VALUES ({placeholders}) "
                    f"ON CONFLICT ({', '.join(keys)}) DO UPDATE SET {assignments}")
        if self.dialect == MYSQL:
            return (f"INSERT INTO {qualified} ({', '.join(quoted)}) VALUES ({placeholders}) "
                    f"ON DUPLICATE KEY UPDATE {assignments}")
        # 达梦：MERGE INTO。USING 里放一条 SELECT 绑定参数。
        select_list = ", ".join(f":{column} AS {quote_ident(column, self.dialect)}" for column in plan.columns)
        match = " AND ".join(
            f"t.{quote_ident(column, self.dialect)} = s.{quote_ident(column, self.dialect)}"
            for column in plan.business_keys
        )
        set_clause = ", ".join(
            f"t.{quote_ident(column, self.dialect)} = s.{quote_ident(column, self.dialect)}"
            for column in updates
        )
        return (f"MERGE INTO {qualified} t USING (SELECT {select_list} FROM DUAL) s ON ({match}) "
                f"WHEN MATCHED THEN UPDATE SET {set_clause} "
                f"WHEN NOT MATCHED THEN INSERT ({', '.join(quoted)}) "
                f"VALUES ({', '.join('s.' + item for item in quoted)})")

    def existing_keys(self, conn: Connection, schema: str | None, table: str, key_columns: list[str],
                      rows: list[dict]) -> set[tuple]:
        """APPEND 预检查：查出本次数据里已经存在于目标表的业务键。"""
        qualified = _qualified(self.dialect, schema or "", table)
        found: set[tuple] = set()
        chunk = get_settings().scope_tuple_chunk
        for start in range(0, len(rows), chunk):
            part = rows[start:start + chunk]
            params: dict = {}
            if len(key_columns) == 1:
                names = []
                for index, row in enumerate(part):
                    params[f"p{index}"] = row.get(key_columns[0])
                    names.append(f":p{index}")
                where = f"{quote_ident(key_columns[0], self.dialect)} IN ({', '.join(names)})"
            else:
                clauses = []
                for index, row in enumerate(part):
                    terms = []
                    for column in key_columns:
                        key = f"p{index}_{column}"
                        params[key] = row.get(column)
                        terms.append(f"{quote_ident(column, self.dialect)} = :{key}")
                    clauses.append("(" + " AND ".join(terms) + ")")
                where = " OR ".join(clauses)
            selected = ", ".join(quote_ident(column, self.dialect) for column in key_columns)
            for row in conn.execute(text(f"SELECT {selected} FROM {qualified} WHERE {where}"), params):
                found.add(tuple(row))
        return found

    def count_scope(self, schema: str | None, table: str, scope_columns: list[str],
                    scopes: list[dict]) -> int:
        """REPLACE_SCOPE 预估将被删除的行数，只用于确认页展示。"""
        plan = WritePlan(strategy=REPLACE_SCOPE, columns=[], scope_columns=scope_columns, scopes=scopes)
        qualified = _qualified(self.dialect, schema or "", table)
        with self.engine.connect() as conn:
            return self._count(conn, qualified, plan)

    def _count(self, conn: Connection, qualified: str, plan: WritePlan) -> int:
        columns = plan.scope_columns
        total = 0
        chunk = get_settings().scope_tuple_chunk
        for start in range(0, len(plan.scopes), chunk):
            part = plan.scopes[start:start + chunk]
            params: dict = {}
            quoted = [quote_ident(column, self.dialect) for column in columns]
            if len(columns) == 1:
                names = [f":p{index}" for index in range(len(part))]
                for index, scope in enumerate(part):
                    params[f"p{index}"] = scope[columns[0]]
                where = f"{quoted[0]} IN ({', '.join(names)})"
            else:
                clauses = []
                for index, scope in enumerate(part):
                    terms = []
                    for column, quoted_column in zip(columns, quoted):
                        key = f"p{index}_{column}"
                        params[key] = scope[column]
                        terms.append(f"{quoted_column} = :{key}")
                    clauses.append("(" + " AND ".join(terms) + ")")
                where = " OR ".join(clauses)
            total += conn.execute(text(f"SELECT COUNT(*) FROM {qualified} WHERE {where}"), params).scalar() or 0
        return total


def _qualified(dialect: str, schema: str, table: str) -> str:
    table_sql = quote_ident(table, dialect)
    if schema:
        return f"{quote_ident(schema, dialect)}.{table_sql}"
    return table_sql


def _render_type(data_type: str, char_len, precision, scale) -> str:
    base = str(data_type).upper()
    if char_len and "CHAR" in base:
        return f"{base}({int(char_len)})"
    if precision and scale is not None and base in {"NUMERIC", "DECIMAL", "NUMBER"}:
        return f"{base}({int(precision)},{int(scale)})"
    return base
