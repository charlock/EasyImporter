"""校验规则的生成与执行。

规则由目标表元数据推导，管理员可通过 rule_overrides 收紧（加必填、枚举、
正则、默认值），不能放宽。前端按同一份 JSON 规则做实时提示，worker 复核时
执行本模块。前后端共用 fixtures/rules/*.json 保证结论一致。
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.connectors.base import ColumnInfo

TYPE_MAP = {
    "string": "string",
    "integer": "integer",
    "decimal": "decimal",
    "boolean": "boolean",
    "date": "date",
    "datetime": "datetime",
}

# 库类型 -> 规则类型
_DB_TYPE_RULES: list[tuple[str, str]] = [
    ("BOOL", "boolean"),
    ("INT", "integer"),
    ("BIGINT", "integer"),
    ("SMALLINT", "integer"),
    ("TINYINT", "integer"),
    ("NUMERIC", "decimal"),
    ("DECIMAL", "decimal"),
    ("NUMBER", "decimal"),
    ("FLOAT", "decimal"),
    ("DOUBLE", "decimal"),
    ("REAL", "decimal"),
    ("DATETIME", "datetime"),
    ("TIMESTAMP", "datetime"),
    ("DATE", "date"),
    ("CHAR", "string"),
    ("TEXT", "string"),
    ("CLOB", "string"),
    ("VARCHAR", "string"),
]

_BOOL_TRUE = {"是", "y", "yes", "true", "1"}
_BOOL_FALSE = {"否", "n", "no", "false", "0"}
_DATE_FORMATS = ["%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"]
_UNIT_SUFFIX = re.compile(r"[（(][^）)]*[）)]$")
_PUNCT = re.compile(r"[\s\-_.,，。、/\\:：;；'\"`]+")


def rule_type_of(db_type: str) -> str:
    upper = db_type.upper()
    for marker, rule_type in _DB_TYPE_RULES:
        if marker in upper:
            return rule_type
    return "string"


def _varchar_length(db_type: str) -> int | None:
    match = re.search(r"\((\d+)", db_type)
    if match and "CHAR" in db_type.upper():
        return int(match.group(1))
    return None


def _decimal_spec(db_type: str) -> tuple[int | None, int | None]:
    match = re.search(r"\((\d+)\s*,\s*(\d+)\)", db_type)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None, None


@dataclass
class Rule:
    db_column: str
    type: str = "string"
    precision: int | None = None
    scale: int | None = None
    required: bool = False
    default: str | None = None
    max_length: int | None = None
    enum: list[str] | None = None
    pattern: str | None = None

    def to_dict(self) -> dict:
        return {
            "db_column": self.db_column,
            "type": self.type,
            "precision": self.precision,
            "scale": self.scale,
            "required": self.required,
            "default": self.default,
            "max_length": self.max_length,
            "enum": self.enum,
            "pattern": self.pattern,
        }


def build_rules(columns: list[ColumnInfo], overrides: list[dict]) -> list[Rule]:
    """由目标表元数据生成规则，再套用模板里的收紧项。"""
    by_name = {override["db_column"]: override for override in overrides}
    rules: list[Rule] = []
    for column in columns:
        rule = Rule(
            db_column=column.name,
            type=rule_type_of(column.type),
            required=not column.nullable and column.default is None,
            max_length=_varchar_length(column.type),
        )
        precision, scale = _decimal_spec(column.type)
        rule.precision, rule.scale = precision, scale
        override = by_name.get(column.name)
        if override:
            # 只允许收紧：必填可以从 false 变 true，不能反过来。
            if override.get("required") is True:
                rule.required = True
            if "enum" in override and override["enum"]:
                rule.enum = [str(item) for item in override["enum"]]
            if override.get("pattern"):
                rule.pattern = str(override["pattern"])
            if "default" in override and override["default"] is not None:
                rule.default = str(override["default"])
            if override.get("max_length"):
                limit = int(override["max_length"])
                rule.max_length = min(rule.max_length or limit, limit)
        rules.append(rule)
    return rules


@dataclass
class CellError:
    row_no: int
    column: str
    code: str
    params: dict = field(default_factory=dict)


def _is_blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _convert(rule: Rule, raw: object) -> tuple[object, str | None]:
    """返回 (转换后的值, 错误码)。错误码为 None 表示成功。"""
    text = str(raw).strip() if not isinstance(raw, (int, float, Decimal)) else raw
    if rule.enum is not None and str(text) not in rule.enum:
        return None, "ENUM_MISMATCH"
    if rule.type == "string":
        value = str(text)
        if rule.max_length and len(value) > rule.max_length:
            return None, "TOO_LONG"
        if rule.pattern and not re.fullmatch(rule.pattern, value):
            return None, "PATTERN_MISMATCH"
        return value, None
    if rule.type == "integer":
        try:
            number = Decimal(str(text).replace(",", ""))
        except InvalidOperation:
            return None, "TYPE_MISMATCH"
        if number != number.to_integral_value():
            return None, "TYPE_MISMATCH"
        return int(number), None
    if rule.type == "decimal":
        try:
            number = Decimal(str(text).replace(",", "").replace("%", ""))
        except InvalidOperation:
            return None, "TYPE_MISMATCH"
        if rule.scale is not None:
            number = round(number, rule.scale)
        return str(number), None
    if rule.type == "boolean":
        token = str(text).strip().lower()
        if token in _BOOL_TRUE:
            return True, None
        if token in _BOOL_FALSE:
            return False, None
        return None, "TYPE_MISMATCH"
    if rule.type in ("date", "datetime"):
        if isinstance(raw, (int, float, Decimal)):
            # Excel 序列号：以 1899-12-30 为原点（ExcelJS 已处理 1904 日期系统）。
            origin = date(1899, 12, 30)
            converted = origin.toordinal() + int(Decimal(str(raw)))
            parsed = date.fromordinal(converted)
            return (parsed.isoformat() if rule.type == "date" else f"{parsed.isoformat()}T00:00:00"), None
        for fmt in _DATE_FORMATS:
            try:
                parsed_dt = datetime.strptime(str(text), fmt)
            except ValueError:
                continue
            if rule.type == "date":
                return parsed_dt.date().isoformat(), None
            return parsed_dt.strftime("%Y-%m-%dT%H:%M:%S"), None
        return None, "TYPE_MISMATCH"
    return str(text), None


def validate_row(rules: list[Rule], row: dict, row_no: int) -> tuple[dict, list[CellError], list[dict]]:
    """校验并转换一行。

    返回 (清洗后的行, 错误列表, 默认值日志)。空值命中默认值时不报错，
    由调用方记录 DEFAULT_APPLIED。
    """
    cleaned: dict = {}
    errors: list[CellError] = []
    defaults: list[dict] = []
    for rule in rules:
        raw = row.get(rule.db_column)
        if _is_blank(raw):
            if rule.default is not None:
                converted, error = _convert(rule, rule.default)
                if error:
                    errors.append(CellError(row_no, rule.db_column, error))
                else:
                    cleaned[rule.db_column] = converted
                    defaults.append({"row": row_no, "column": rule.db_column, "value": rule.default})
            elif rule.required:
                errors.append(CellError(row_no, rule.db_column, "REQUIRED"))
            else:
                cleaned[rule.db_column] = None
            continue
        converted, error = _convert(rule, raw)
        if error:
            errors.append(CellError(row_no, rule.db_column, error))
        else:
            cleaned[rule.db_column] = converted
    return cleaned, errors, defaults


def find_duplicate_keys(rows: list[dict], business_keys: list[str]) -> list[CellError]:
    """业务键在本次数据内不能重复，重复的每一行都标出。"""
    if not business_keys:
        return []
    seen: dict[tuple, int] = {}
    duplicates: set[int] = set()
    for index, row in enumerate(rows):
        key = tuple(row.get(column) for column in business_keys)
        if any(part is None or part == "" for part in key):
            continue
        if key in seen:
            duplicates.add(seen[key])
            duplicates.add(index)
        else:
            seen[key] = index
    return [
        CellError(int(rows[index].get("_row", index + 1)), business_keys[0], "DUPLICATE_KEY_IN_FILE",
                  {"columns": business_keys})
        for index in sorted(duplicates)
    ]


def normalize_name(text: str) -> str:
    """自动匹配用的归一化：去空白标点、全角转半角、英文小写、去单位后缀。"""
    chars = []
    for char in text:
        code = ord(char)
        chars.append(chr(code - 0xFEE0) if 0xFF01 <= code <= 0xFF5E else char)
    collapsed = "".join(chars).replace("　", " ")
    collapsed = _UNIT_SUFFIX.sub("", collapsed.strip())
    return _PUNCT.sub("", collapsed).lower()
