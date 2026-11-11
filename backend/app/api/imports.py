"""导入任务：提交、查询、取消、重试、人工核对、范围预估、错误报告。"""

import gzip
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.connectors.pool import get_target
from app.core.config import get_settings
from app.core.db import get_session
from app.core.errors import ApiError
from app.core.security import (
    current_session,
    current_user,
    ensure_member,
    require_admin_write,
)
from app.models.entities import (
    CANCELLED,
    FAILED,
    QUEUED,
    RUNNING,
    SUCCEEDED,
    UNKNOWN,
    Datasource,
    ImportError,
    ImportLog,
    ImportTask,
    Template,
    TemplateVersion,
    User,
)
from app.schemas.dto import (
    ImportErrorOut,
    ImportLogOut,
    ImportMeta,
    ImportOut,
    Page,
    PreviewScopeIn,
    ResolveIn,
)
from app.services.imports import read_rows

router = APIRouter(tags=["imports"])

XLSX_MAGIC = b"PK"


def _out(task: ImportTask, operator: str = "") -> ImportOut:
    return ImportOut(
        id=task.id, status=task.status, template_id=task.template_id,
        template_version=task.template_version, operator=operator, target_table=task.target_table,
        strategy=task.strategy, row_count=task.row_count, processed=task.processed,
        inserted=task.inserted, updated=task.updated, deleted=task.deleted,
        counts_exact=task.counts_exact, error_count=task.error_count, failure_code=task.failure_code,
        failure_message=task.failure_message, created_at=task.created_at, started_at=task.started_at,
        finished_at=task.finished_at,
    )


@router.post("/workspaces/{workspace_id}/imports", status_code=202, response_model=ImportOut)
def submit_import(
    workspace_id: int,
    meta: str = Form(),
    file: UploadFile = File(),
    rows: UploadFile = File(),
    user: User = Depends(current_session),
    db: Session = Depends(get_session),
):
    ensure_member(db, user, workspace_id)
    try:
        payload = ImportMeta.model_validate_json(meta)
    except ValueError as exc:
        raise ApiError("VALIDATION_FAILED", {"field": "meta"}) from exc

    template = db.get(Template, payload.template_id)
    if template is None or template.workspace_id != workspace_id:
        raise ApiError("NOT_FOUND")
    if template.current_version != payload.template_version:
        raise ApiError("TEMPLATE_VERSION_CHANGED",
                       {"current": template.current_version, "submitted": payload.template_version})
    version = db.get(TemplateVersion, (template.id, payload.template_version))

    content = file.file.read()
    if not file.filename or not file.filename.lower().endswith(".xlsx") or not content.startswith(XLSX_MAGIC):
        raise ApiError("INVALID_FILE_TYPE")
    if len(content) > get_settings().upload_max_mb * 1024 * 1024:
        raise ApiError("PAYLOAD_TOO_LARGE", {"limit_mb": get_settings().upload_max_mb})

    task = ImportTask(
        workspace_id=workspace_id, template_id=template.id, template_version=payload.template_version,
        datasource_id=version.datasource_id, target_schema=version.target_schema,
        target_table=version.target_table, strategy=version.strategy, operator_id=user.id,
        row_count=payload.row_count,
    )
    db.add(task)
    db.flush()

    directory = Path(get_settings().upload_dir) / str(task.id)
    directory.mkdir(parents=True, exist_ok=True)
    file_path = directory / "source.xlsx"
    rows_path = directory / "rows.jsonl.gz"
    file_path.write_bytes(content)
    _store_rows(rows, rows_path, payload.row_count)
    task.file_path = str(file_path)
    task.rows_path = str(rows_path)
    db.commit()
    return _out(task, user.username)


def _store_rows(upload: UploadFile, destination: Path, declared: int) -> None:
    """解压校验行数后原样落盘。超过解压上限立即中止，防止 gzip 炸弹。"""
    raw = upload.file.read()
    limit = get_settings().rows_max_mb * 1024 * 1024
    try:
        with gzip.GzipFile(fileobj=_Bytes(raw)) as handle:
            total = 0
            count = 0
            chunks = []
            while chunk := handle.read(1024 * 1024):
                total += len(chunk)
                if total > limit:
                    raise ApiError("PAYLOAD_TOO_LARGE", {"limit_mb": get_settings().rows_max_mb})
                chunks.append(chunk)
                count += chunk.count(b"\n")
    except ApiError:
        raise
    except (OSError, EOFError, gzip.BadGzipFile) as exc:
        raise ApiError("VALIDATION_FAILED", {"field": "rows"}) from exc
    text = b"".join(chunks)
    actual = len([line for line in text.split(b"\n") if line.strip()])
    if actual != declared:
        raise ApiError("ROW_COUNT_MISMATCH", {"declared": declared, "actual": actual})
    destination.write_bytes(raw)


class _Bytes:
    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self._data) - self._pos
        chunk = self._data[self._pos:self._pos + size]
        self._pos += len(chunk)
        return chunk


@router.get("/workspaces/{workspace_id}/imports", response_model=Page)
def list_imports(workspace_id: int, status: str | None = None, template_id: int | None = None,
                 page: int = 1, size: int = 20, user: User = Depends(current_user),
                 db: Session = Depends(get_session)):
    ensure_member(db, user, workspace_id)
    size = max(1, min(size, 100))
    query = select(ImportTask).where(ImportTask.workspace_id == workspace_id)
    if status:
        query = query.where(ImportTask.status == status)
    if template_id:
        query = query.where(ImportTask.template_id == template_id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    tasks = db.scalars(query.order_by(ImportTask.id.desc()).offset((page - 1) * size).limit(size)).all()
    names = _operator_names(db, tasks)
    return Page(items=[_out(task, names.get(task.operator_id, "")).model_dump() for task in tasks],
                total=total or 0, page=page, size=size)


@router.get("/workspaces/{workspace_id}/imports/{import_id}", response_model=ImportOut)
def get_import(workspace_id: int, import_id: int, user: User = Depends(current_user),
               db: Session = Depends(get_session)):
    ensure_member(db, user, workspace_id)
    task = _task(db, workspace_id, import_id)
    operator = db.get(User, task.operator_id)
    return _out(task, operator.username if operator else "")


@router.get("/workspaces/{workspace_id}/imports/{import_id}/logs", response_model=list[ImportLogOut])
def import_logs(workspace_id: int, import_id: int, after_id: int = 0, user: User = Depends(current_user),
                db: Session = Depends(get_session)):
    ensure_member(db, user, workspace_id)
    _task(db, workspace_id, import_id)
    logs = db.scalars(select(ImportLog).where(ImportLog.import_id == import_id, ImportLog.id > after_id)
                      .order_by(ImportLog.id).limit(500)).all()
    return [ImportLogOut(id=item.id, ts=item.ts, level=item.level, code=item.code, params=item.params,
                         message=item.message) for item in logs]


@router.get("/workspaces/{workspace_id}/imports/{import_id}/errors", response_model=Page)
def import_errors(workspace_id: int, import_id: int, page: int = 1, size: int = 50,
                  user: User = Depends(current_user), db: Session = Depends(get_session)):
    ensure_member(db, user, workspace_id)
    task = _task(db, workspace_id, import_id)
    size = max(1, min(size, 100))
    query = select(ImportError).where(ImportError.import_id == import_id)
    items = db.scalars(query.order_by(ImportError.id).offset((page - 1) * size).limit(size)).all()
    return Page(items=[ImportErrorOut(id=item.id, row_no=item.row_no, column=item.column, code=item.code,
                                      params=item.params).model_dump() for item in items],
                total=task.error_count, page=page, size=size)


@router.get("/workspaces/{workspace_id}/imports/{import_id}/file")
def download_file(workspace_id: int, import_id: int, user: User = Depends(current_user),
                  db: Session = Depends(get_session)):
    ensure_member(db, user, workspace_id)
    task = _task(db, workspace_id, import_id)
    if not task.file_path or not Path(task.file_path).exists():
        raise ApiError("IMPORT_FILES_EXPIRED")
    return FileResponse(task.file_path, filename=f"import-{task.id}.xlsx")


@router.get("/workspaces/{workspace_id}/imports/{import_id}/error-report")
def error_report(workspace_id: int, import_id: int, user: User = Depends(current_user),
                 db: Session = Depends(get_session)):
    ensure_member(db, user, workspace_id)
    task = _task(db, workspace_id, import_id)
    if not task.rows_path or not Path(task.rows_path).exists():
        raise ApiError("IMPORT_FILES_EXPIRED")
    errors = db.scalars(select(ImportError).where(ImportError.import_id == import_id)).all()
    by_row: dict[int, list[str]] = {}
    for error in errors:
        by_row.setdefault(error.row_no, []).append(f"{error.column}: {error.code}")
    workbook = Workbook()
    sheet = workbook.active
    rows = read_rows(task.rows_path)
    headers = sorted({key for row in rows for key in row if key != "_row"}) + ["错误说明"]
    sheet.append(headers)
    for row in rows:
        sheet.append([row.get(key, "") for key in headers[:-1]]
                     + ["; ".join(by_row.get(int(row.get("_row", 0)), []))])
    destination = Path(get_settings().upload_dir) / str(task.id) / "error-report.xlsx"
    workbook.save(destination)
    return FileResponse(destination, filename=f"import-{task.id}-errors.xlsx")


@router.post("/workspaces/{workspace_id}/imports/{import_id}/cancel")
def cancel_import(workspace_id: int, import_id: int, user: User = Depends(current_session),
                  db: Session = Depends(get_session)):
    ensure_member(db, user, workspace_id)
    task = _task(db, workspace_id, import_id)
    if task.status == QUEUED:
        task.status = CANCELLED
        task.finished_at = datetime.now(UTC)
    elif task.status == RUNNING:
        task.cancel_requested = True
    else:
        raise ApiError("IMPORT_NOT_RETRYABLE")
    db.commit()
    return {"ok": True}


@router.post("/workspaces/{workspace_id}/imports/{import_id}/retry", status_code=202, response_model=ImportOut)
def retry_import(workspace_id: int, import_id: int, user: User = Depends(current_session),
                 db: Session = Depends(get_session)):
    ensure_member(db, user, workspace_id)
    task = _task(db, workspace_id, import_id)
    if task.status not in {FAILED, CANCELLED}:
        raise ApiError("IMPORT_NOT_RETRYABLE", {"status": task.status})
    if not task.file_path or not Path(task.file_path).exists():
        raise ApiError("IMPORT_FILES_EXPIRED")
    clone = ImportTask(
        workspace_id=workspace_id, template_id=task.template_id, template_version=task.template_version,
        datasource_id=task.datasource_id, target_schema=task.target_schema, target_table=task.target_table,
        strategy=task.strategy, operator_id=user.id, file_path=task.file_path, rows_path=task.rows_path,
        row_count=task.row_count, retry_of=task.id,
    )
    db.add(clone)
    db.commit()
    return _out(clone, user.username)


@router.post("/workspaces/{workspace_id}/imports/{import_id}/resolve", response_model=ImportOut)
def resolve_import(workspace_id: int, import_id: int, payload: ResolveIn,
                   user: User = Depends(require_admin_write), db: Session = Depends(get_session)):
    ensure_member(db, user, workspace_id)
    task = _task(db, workspace_id, import_id)
    if task.status != UNKNOWN:
        raise ApiError("IMPORT_NOT_RESOLVABLE")
    if payload.outcome == "CONFIRMED_WRITTEN":
        task.status = SUCCEEDED
    elif payload.outcome == "CONFIRMED_NOT_WRITTEN":
        task.status = FAILED
        task.failure_code = "CONFIRMED_NOT_WRITTEN"
    else:
        raise ApiError("VALIDATION_FAILED", {"field": "outcome"})
    db.commit()
    return _out(task)


@router.post("/workspaces/{workspace_id}/imports/preview-scope")
def preview_scope(workspace_id: int, payload: PreviewScopeIn, user: User = Depends(current_user),
                  db: Session = Depends(get_session)):
    ensure_member(db, user, workspace_id)
    template = db.get(Template, payload.template_id)
    if template is None or template.workspace_id != workspace_id:
        raise ApiError("NOT_FOUND")
    if template.current_version != payload.template_version:
        raise ApiError("TEMPLATE_VERSION_CHANGED")
    version = db.get(TemplateVersion, (template.id, payload.template_version))
    datasource = db.get(Datasource, version.datasource_id)
    try:
        count = get_target(datasource).count_scope(version.target_schema, version.target_table,
                                                   version.scope_columns, payload.scopes)
    except Exception as exc:
        raise ApiError("DATASOURCE_UNREACHABLE", {"reason": type(exc).__name__}) from exc
    return {"estimated_delete": count, "scope_count": len(payload.scopes)}


def _task(db: Session, workspace_id: int, import_id: int) -> ImportTask:
    task = db.get(ImportTask, import_id)
    if task is None or task.workspace_id != workspace_id:
        raise ApiError("NOT_FOUND")
    return task


def _operator_names(db: Session, tasks: list[ImportTask]) -> dict[int, str]:
    ids = {task.operator_id for task in tasks}
    if not ids:
        return {}
    return dict(db.execute(select(User.id, User.username).where(User.id.in_(ids))).all())
