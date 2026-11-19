"""数据源登记与目标库元数据探查。响应永远不包含密码。"""

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.pool import check_host_allowed, drop_target, get_target
from app.core.crypto import encrypt
from app.core.db import get_session
from app.core.errors import ApiError
from app.core.security import ensure_member, require_admin, require_admin_write
from app.models.entities import DB_TYPES, POSTGRES, UPSERT, Datasource, TemplateVersion, User
from app.schemas.dto import (
    AutoCreateRequest,
    ColumnOut,
    DatasourceIn,
    DatasourceOut,
    InferRequest,
    InferResponse,
    InferredColumnOut,
    TableInfoOut,
    TableSchemaOut,
)
from app.services.table_inference import (
    InvalidColumn,
    InvalidIdentifier,
    build_create_table_ddl,
    infer_columns,
    validate_identifier,
    validate_unique_keys,
)

router = APIRouter(prefix="/datasources", tags=["datasources"])
# 智能建表端点挂在 /workspaces/{wid}/datasources/{id}/... 下；现有 router 带
# /datasources 前缀，无法直接承载该路径，故同文件内另设一个无前缀 router，
# main.py 里一并注册。对外 URL 与约定一致。
workspace_router = APIRouter(tags=["datasources"])


def _out(item: Datasource) -> DatasourceOut:
    return DatasourceOut(id=item.id, name=item.name, db_type=item.db_type, host=item.host, port=item.port,
                         database=item.database, username=item.username, options=item.options or {})


@router.get("", response_model=list[DatasourceOut])
def list_datasources(_: User = Depends(require_admin), db: Session = Depends(get_session)):
    return [_out(item) for item in db.scalars(select(Datasource).order_by(Datasource.id))]


@router.post("", response_model=DatasourceOut)
def create_datasource(payload: DatasourceIn, _: User = Depends(require_admin_write),
                      db: Session = Depends(get_session)):
    if payload.db_type not in DB_TYPES or not payload.password:
        raise ApiError("VALIDATION_FAILED", {"field": "db_type" if payload.db_type not in DB_TYPES else "password"})
    check_host_allowed(payload.host)
    item = Datasource(name=payload.name, db_type=payload.db_type, host=payload.host, port=payload.port,
                      database=payload.database, username=payload.username,
                      password_enc=encrypt(payload.password), options=payload.options)
    db.add(item)
    db.commit()
    return _out(item)


@router.put("/{datasource_id}", response_model=DatasourceOut)
def update_datasource(datasource_id: int, payload: DatasourceIn, _: User = Depends(require_admin_write),
                      db: Session = Depends(get_session)):
    item = _get(db, datasource_id)
    if payload.db_type not in DB_TYPES:
        raise ApiError("VALIDATION_FAILED", {"field": "db_type"})
    check_host_allowed(payload.host)
    item.name, item.db_type, item.host, item.port = payload.name, payload.db_type, payload.host, payload.port
    item.database, item.username, item.options = payload.database, payload.username, payload.options
    if payload.password:
        item.password_enc = encrypt(payload.password)
    drop_target(item.id)
    db.commit()
    return _out(item)


@router.delete("/{datasource_id}")
def delete_datasource(datasource_id: int, _: User = Depends(require_admin_write),
                      db: Session = Depends(get_session)):
    _get(db, datasource_id)
    if db.scalar(select(TemplateVersion.template_id).where(
            TemplateVersion.datasource_id == datasource_id).limit(1)):
        raise ApiError("DATASOURCE_IN_USE")
    drop_target(datasource_id)
    db.query(Datasource).filter(Datasource.id == datasource_id).delete()
    db.commit()
    return {"ok": True}


@router.post("/{datasource_id}/test")
def test_datasource(datasource_id: int, _: User = Depends(require_admin_write),
                    db: Session = Depends(get_session)):
    item = _get(db, datasource_id)
    try:
        get_target(item).test_connection()
    except Exception as exc:
        raise ApiError("DATASOURCE_UNREACHABLE", {"reason": type(exc).__name__}) from exc
    return {"ok": True}


@router.get("/{datasource_id}/tables")
def list_tables(datasource_id: int, schema: str | None = None, _: User = Depends(require_admin),
                db: Session = Depends(get_session)):
    item = _get(db, datasource_id)
    schema = schema or (item.options or {}).get("schema")
    try:
        tables = get_target(item).list_tables(schema)
    except Exception as exc:
        raise ApiError("DATASOURCE_UNREACHABLE", {"reason": type(exc).__name__}) from exc
    return [{"schema": table.schema, "name": table.name} for table in tables]


@router.get("/{datasource_id}/tables/{table}/schema", response_model=TableSchemaOut)
def table_schema(datasource_id: int, table: str, schema: str | None = None,
                 _: User = Depends(require_admin), db: Session = Depends(get_session)):
    item = _get(db, datasource_id)
    schema = schema or (item.options or {}).get("schema")
    try:
        result = get_target(item).get_table_schema(schema, table)
    except Exception as exc:
        raise ApiError("DATASOURCE_UNREACHABLE", {"reason": type(exc).__name__}) from exc
    return TableSchemaOut.model_validate({
        "schema": result.schema,
        "table_name": result.table_name,
        "columns": [ColumnOut(**column.__dict__) for column in result.columns],
        "unique_keys": [{"name": key.name, "columns": list(key.columns)} for key in result.unique_keys],
        "engine": result.engine,
    })


def _get(db: Session, datasource_id: int) -> Datasource:
    item = db.get(Datasource, datasource_id)
    if item is None:
        raise ApiError("NOT_FOUND")
    return item


def _invalid_identifier(exc: InvalidIdentifier):
    raise ApiError("INVALID_IDENTIFIER", message=str(exc)) from exc


def _invalid_column(exc: InvalidColumn):
    raise ApiError("VALIDATION_FAILED", {"field": "columns"}, message=str(exc)) from exc


@workspace_router.post("/workspaces/{workspace_id}/datasources/{datasource_id}/tables/infer",
                       response_model=InferResponse)
def infer_table(workspace_id: int, datasource_id: int, payload: InferRequest,
                user: User = Depends(require_admin_write), db: Session = Depends(get_session)):
    """智能建表试算：只推断类型并返回 DDL，不建表、不连目标库。"""
    ensure_member(db, user, workspace_id)
    _get(db, datasource_id)
    try:
        if payload.target_schema:
            validate_identifier(payload.target_schema, "Schema 名")
        table = payload.table_name or f"import_{date.today().strftime('%Y%m%d')}"
        validate_identifier(table, "表名")
        validate_unique_keys(
            [{"db_column": column.db_column} for column in payload.columns], payload.unique_keys)
        inferred = infer_columns(
            [{"db_column": column.db_column, "samples": column.samples} for column in payload.columns])
        ddl = build_create_table_ddl(
            payload.target_schema, table,
            [{"db_column": item.db_column, "db_type": item.db_type, "nullable": item.nullable}
             for item in inferred],
            payload.unique_keys)
    except InvalidIdentifier as exc:
        _invalid_identifier(exc)
    except InvalidColumn as exc:
        _invalid_column(exc)
    return InferResponse(
        columns=[InferredColumnOut(db_column=item.db_column, db_type=item.db_type,
                                   nullable=item.nullable) for item in inferred],
        ddl=ddl)


@workspace_router.post("/workspaces/{workspace_id}/datasources/{datasource_id}/tables/auto-create",
                       response_model=TableInfoOut)
def auto_create_table(workspace_id: int, datasource_id: int, payload: AutoCreateRequest,
                      user: User = Depends(require_admin_write), db: Session = Depends(get_session)):
    """智能建表执行：仅支持 PostgreSQL；表已存在返回 409 并附已存在表的列清单。"""
    ensure_member(db, user, workspace_id)
    item = _get(db, datasource_id)
    if item.db_type != POSTGRES:
        raise ApiError("UNSUPPORTED_DATASOURCE", {"db_type": item.db_type})
    try:
        if payload.target_schema:
            validate_identifier(payload.target_schema, "Schema 名")
        validate_identifier(payload.target_table, "表名")
        validate_unique_keys(
            [{"db_column": column.db_column} for column in payload.columns], payload.unique_keys)
        # UPSERT 没带业务键时直接拒绝：否则会建出一张没有唯一约束的表，而后续
        # 保存模板在 validate_template 里报 UNIQUE_KEY_REQUIRED 失败，孤表
        # 就留下了。校验放在 create_table 之前，表根本不会建出来。
        if (payload.strategy or "").upper() == UPSERT and not payload.unique_keys:
            raise ApiError("UNIQUE_KEY_REQUIRED", {"business_keys": []})
        columns = [{"db_column": column.db_column, "db_type": column.db_type,
                    "nullable": column.nullable} for column in payload.columns]
        ddl = build_create_table_ddl(payload.target_schema, payload.target_table, columns,
                                     payload.unique_keys)
    except InvalidIdentifier as exc:
        _invalid_identifier(exc)
    except InvalidColumn as exc:
        _invalid_column(exc)
    try:
        target = get_target(item)
        schema = payload.target_schema or _default_schema(target)
        if target.table_exists(schema or None, payload.target_table):
            existing = target.get_table_schema(schema or None, payload.target_table)
            raise ApiError("TABLE_EXISTS", {
                "schema": existing.schema, "table": existing.table_name,
                "columns": [ColumnOut(**column.__dict__).model_dump() for column in existing.columns],
                "unique_keys": [{"name": key.name, "columns": list(key.columns)}
                                for key in existing.unique_keys],
            })
        target.create_table(ddl)
    except ApiError:
        raise
    except Exception as exc:
        # 建表竞态：并发建表成功后本方再报已存在，仍按 409 处理。
        try:
            if target.table_exists(schema or None, payload.target_table):
                raise ApiError("TABLE_EXISTS", {"schema": schema,
                                                "table": payload.target_table}) from exc
        except ApiError:
            raise
        except Exception:
            pass
        raise ApiError("DATASOURCE_UNREACHABLE", {"reason": type(exc).__name__}) from exc
    return TableInfoOut(schema=schema, name=payload.target_table)


def _default_schema(target) -> str:
    """目标库默认 schema；取不到（如 SQLite 测试替身）时返回空串走无限定建表。"""
    try:
        return target._default_schema()
    except Exception:
        return ""
