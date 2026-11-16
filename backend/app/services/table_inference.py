"""智能建表：类型推断与 CREATE TABLE 生成。

纯函数，不碰数据库、不读配置，可直接单测。所有标识符（schema、表名、列名）
只接受 ``^[a-zA-Z_][a-zA-Z0-9_]*$``，中文名直接拒绝；生成的 DDL 只含白名单
内的类型，表名与列名在校验后才拼进语句。
"""

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime

IDENT_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
MAX_IDENTIFIER_LENGTH = 63
MAX_CONSTRAINT_LENGTH = 63
INT32_MIN = -(2 ** 31)
INT32_MAX = 2 ** 31 - 1

ALLOWED_DB_TYPES = frozenset({
    "INTEGER", "BIGINT", "NUMERIC(18,4)", "DATE", "TIMESTAMP", "BOOLEAN", "VARCHAR(255)", "TEXT",
})

_BOOL_STRINGS = {"是": True, "否": False, "true": True, "false": False, "1": True, "0": False}
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$")


class InvalidIdentifier(ValueError):
    """标识符不合法（中文名、非法字符、超长）。"""


class InvalidColumn(ValueError):
    """列定义不合法（重复列名、业务键不在列中、类型不在白名单）。"""


@dataclass(frozen=True)
class InferredColumn:
    db_column: str
    db_type: str
    nullable: bool


def validate_identifier(name: object, kind: str = "标识符") -> str:
    """校验单个标识符；非法时抛 InvalidIdentifier，由端点转 400。"""
    if (not isinstance(name, str) or not IDENT_PATTERN.match(name)
            or len(name.encode()) > MAX_IDENTIFIER_LENGTH):
        raise InvalidIdentifier(
            f"{kind} {name!r} 不合法：只允许英文字母、数字与下划线，且以字母或下划线开头，"
            "长度不超过 63 字节；中文名请改用英文字段名")
    return name


def normalize_db_type(raw: object) -> str:
    """把请求里的类型归一化并查白名单；不在白名单内抛 InvalidColumn。"""
    if not isinstance(raw, str):
        raise InvalidColumn(f"类型 {raw!r} 不合法")
    normalized = re.sub(r"\s+", "", raw).upper()
    if normalized not in ALLOWED_DB_TYPES:
        raise InvalidColumn(f"类型 {raw!r} 不在支持列表内：{sorted(ALLOWED_DB_TYPES)}")
    return normalized


def _classify(value: object) -> str:
    """把单个样本值归为 boolean / integer / float / date / timestamp / string。"""
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        # Excel 里整数常以 1.0 的形式出现，数学上是整数就按整数算。
        return "integer" if value.is_integer() else "float"
    if isinstance(value, str):
        text = value.strip()
        if text.lower() in _BOOL_STRINGS:
            return "boolean"
        if _DATE_RE.match(text):
            try:
                date.fromisoformat(text)
                return "date"
            except ValueError:
                return "string"
        if _DATETIME_RE.match(text):
            try:
                datetime.fromisoformat(text.replace("Z", "+00:00"))
                return "timestamp"
            except ValueError:
                return "string"
    return "string"


def infer_column_type(samples: list) -> str:
    """按 §3.5 规则从一列样本值推断 PostgreSQL 类型。

    全整数且在 int32 内 → INTEGER；超出 int32 → BIGINT；含小数 → NUMERIC(18,4)；
    ISO 日期/时间字符串 → DATE / TIMESTAMP；是/否/true/false（含布尔值与
    '1'/'0' 字符串）→ BOOLEAN；其余 → VARCHAR(255)，最长值 >255 则 TEXT；
    全空列 → VARCHAR(255)。空值（None 与空字符串）不参与类型判定。
    """
    values = [value for value in samples if value is not None and value != ""]
    if not values:
        return "VARCHAR(255)"
    kinds = [_classify(value) for value in values]
    if all(kind == "boolean" for kind in kinds):
        return "BOOLEAN"
    if all(kind in {"integer", "float"} for kind in kinds):
        if any(kind == "float" for kind in kinds):
            return "NUMERIC(18,4)"
        if all(INT32_MIN <= value <= INT32_MAX for value in values):
            return "INTEGER"
        return "BIGINT"
    if all(kind in {"date", "timestamp"} for kind in kinds):
        return "TIMESTAMP" if any(kind == "timestamp" for kind in kinds) else "DATE"
    longest = max(len(str(value)) for value in values)
    return "TEXT" if longest > 255 else "VARCHAR(255)"


def infer_columns(columns: list[dict]) -> list[InferredColumn]:
    """对 infer 请求的列清单做标识符校验并逐列推断类型与可空性。

    可空规则：样本里出现过空值（None 或空字符串）即 nullable；无样本时也视为
    可空（没有任何非空证据）。
    """
    seen: set[str] = set()
    result: list[InferredColumn] = []
    for column in columns:
        name = validate_identifier(column.get("db_column"), "字段名")
        if name in seen:
            raise InvalidColumn(f"字段名重复：{name}")
        seen.add(name)
        samples = column.get("samples") or []
        result.append(InferredColumn(
            db_column=name,
            db_type=infer_column_type(samples),
            nullable=any(value is None or value == "" for value in samples) or not samples,
        ))
    return result


def validate_unique_keys(columns: list[dict], unique_keys: list[str]) -> list[str]:
    """校验业务键：标识符合法且必须在列清单里。"""
    names = {column["db_column"] for column in columns}
    validated: list[str] = []
    for key in unique_keys or []:
        validate_identifier(key, "业务键")
        if key not in names:
            raise InvalidColumn(f"业务键 {key} 不在列清单里")
        if key not in validated:
            validated.append(key)
    return validated


def unique_constraint_name(table: str, columns: list[str]) -> str:
    """约束名 uq_<表>_<列1>_<列2>；超 PG 63 字节限制时截断并加 hash 后缀。"""
    name = "uq_" + table + "_" + "_".join(columns)
    if len(name.encode()) <= MAX_CONSTRAINT_LENGTH:
        return name
    suffix = hashlib.sha1(name.encode()).hexdigest()[:8]
    keep = MAX_CONSTRAINT_LENGTH - len(suffix) - 1
    return name[:keep] + "_" + suffix


def build_create_table_ddl(schema: str, table: str, columns: list[dict],
                           unique_keys: list[str] | None = None) -> str:
    """生成完整 CREATE TABLE 语句（PostgreSQL 方言，含唯一约束）。

    schema 为空时不带 schema 限定。columns 每项含 db_column / db_type /
    nullable；db_type 只接受白名单内的值。
    """
    validate_identifier(table, "表名")
    if schema:
        validate_identifier(schema, "Schema 名")
    if not columns:
        raise InvalidColumn("至少需要一列")
    seen: set[str] = set()
    definitions: list[str] = []
    for column in columns:
        name = validate_identifier(column["db_column"], "字段名")
        if name in seen:
            raise InvalidColumn(f"字段名重复：{name}")
        seen.add(name)
        db_type = normalize_db_type(column["db_type"])
        nullable = column.get("nullable", True)
        definitions.append(f'  "{name}" {db_type}' + ("" if nullable else " NOT NULL"))
    keys = validate_unique_keys(columns, unique_keys or [])
    if keys:
        constraint = unique_constraint_name(table, keys)
        joined = ", ".join(f'"{key}"' for key in keys)
        definitions.append(f'  CONSTRAINT "{constraint}" UNIQUE ({joined})')
    qualified = f'"{schema}"."{table}"' if schema else f'"{table}"'
    return "CREATE TABLE " + qualified + " (\n" + ",\n".join(definitions) + "\n);"
