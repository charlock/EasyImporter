"""数据源登记与目标库元数据探查。响应永远不包含密码。"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.pool import check_host_allowed, drop_target, get_target
from app.core.crypto import encrypt
from app.core.db import get_session
from app.core.errors import ApiError
from app.core.security import require_admin, require_admin_write
from app.models.entities import DB_TYPES, Datasource, TemplateVersion, User
from app.schemas.dto import ColumnOut, DatasourceIn, DatasourceOut, TableSchemaOut

router = APIRouter(prefix="/datasources", tags=["datasources"])


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
