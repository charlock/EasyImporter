"""模板保存时的校验：映射列存在、策略前提满足、非空字段已覆盖。"""

from app.connectors.base import TableSchema
from app.core.errors import ApiError
from app.models.entities import APPEND, MYSQL, REPLACE_SCOPE, UPSERT
from app.schemas.dto import Mapping, TemplateIn

VARIABLES = {"${import_id}", "${imported_at}", "${operator}"}


def mapped_columns(mapping: Mapping) -> set[str]:
    names = {column.db_column for column in mapping.columns}
    names.update(constant.db_column for constant in mapping.constants)
    if mapping.unpivot:
        names.add(mapping.unpivot.dimension_column)
        names.update(measure.db_column for measure in mapping.unpivot.measures)
    return names


def validate_template(payload: TemplateIn, schema: TableSchema, db_type: str) -> None:
    known = {column.name for column in schema.columns}
    unknown = sorted(mapped_columns(payload.mapping) - known)
    if unknown:
        raise ApiError("TEMPLATE_INVALID", {"unknown_columns": unknown},
                       f"映射到不存在的列：{', '.join(unknown)}")

    if db_type == MYSQL and schema.engine and schema.engine.upper() != "INNODB":
        raise ApiError("TABLE_ENGINE_NOT_TRANSACTIONAL", {"engine": schema.engine})

    if payload.strategy == UPSERT:
        keys = tuple(payload.business_keys)
        if not keys or not any(set(keys) == set(unique.columns) for unique in schema.unique_keys):
            raise ApiError("UNIQUE_KEY_REQUIRED", {"business_keys": list(keys)})
        if db_type == MYSQL:
            mapped = mapped_columns(payload.mapping)
            for unique in schema.unique_keys:
                if set(unique.columns) == set(keys):
                    continue
                if set(unique.columns) & mapped:
                    raise ApiError("UPSERT_AMBIGUOUS_UNIQUE_KEY",
                                   {"index": unique.name, "columns": list(unique.columns)})

    if payload.strategy == REPLACE_SCOPE:
        if not payload.scope_columns:
            raise ApiError("TEMPLATE_INVALID", {"field": "scope_columns"}, "REPLACE_SCOPE 必须指定范围列")
        missing = [column for column in payload.scope_columns if column not in mapped_columns(payload.mapping)]
        if missing:
            raise ApiError("TEMPLATE_INVALID", {"unmapped_scope": missing}, "范围列必须已映射或有常量")

    if payload.strategy == APPEND and payload.business_keys:
        missing = [column for column in payload.business_keys if column not in known]
        if missing:
            raise ApiError("TEMPLATE_INVALID", {"unknown_columns": missing})

    uncovered = [
        column.name for column in schema.columns
        if not column.nullable and column.default is None and column.name not in mapped_columns(payload.mapping)
        and not column.is_primary_key
    ]
    if uncovered:
        raise ApiError("TEMPLATE_INVALID", {"required_unmapped": uncovered},
                       f"非空且无默认值的字段未映射：{', '.join(uncovered)}")

    for constant in payload.mapping.constants:
        if constant.value.startswith("${") and constant.value not in VARIABLES:
            raise ApiError("TEMPLATE_INVALID", {"constant": constant.value}, "不支持的常量变量")
