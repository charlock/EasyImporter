"""导入任务的执行逻辑，供 worker 调用。

流程：复核全部行 -> 填充常量与默认值 -> 在目标库的一个事务里按策略写入
-> 两阶段提交元数据库状态。任何失败都回滚目标库事务。
"""

import gzip
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.connectors.base import WritePlan
from app.connectors.pool import get_target
from app.core.config import get_settings
from app.models.entities import (
    APPEND,
    CANCELLED,
    COMMITTING,
    FAILED,
    QUEUED,
    RUNNING,
    SUCCEEDED,
    UNKNOWN,
    Datasource,
    ImportError,
    ImportLog,
    ImportTask,
    TableLock,
    TemplateVersion,
    User,
)
from app.rules.engine import CellError, build_rules, find_duplicate_keys, validate_row
from app.schemas.dto import Mapping
from app.services.templates import mapped_columns


def read_rows(path: str) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _log(db: Session, task: ImportTask, code: str, message: str, level: str = "INFO",
         params: dict | None = None) -> None:
    db.add(ImportLog(import_id=task.id, level=level, code=code, params=params or {}, message=message))


def _fail(db: Session, task: ImportTask, code: str, message: str, errors: list[CellError]) -> None:
    task.status = FAILED
    task.failure_code = code
    task.failure_message = message
    task.finished_at = datetime.now(UTC)
    task.error_count = len(errors)
    for error in errors[: get_settings().error_row_limit]:
        db.add(ImportError(import_id=task.id, row_no=error.row_no, column=error.column,
                           code=error.code, params=error.params))
    _log(db, task, code, message, level="ERROR")
    db.query(TableLock).filter(TableLock.import_id == task.id).delete()
    db.commit()


def resolve_constant(value: str, task: ImportTask, operator: str) -> str:
    return {
        "${import_id}": str(task.id),
        "${imported_at}": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "${operator}": operator,
    }.get(value, value)


def execute(db: Session, task: ImportTask) -> None:
    version = db.get(TemplateVersion, (task.template_id, task.template_version))
    datasource = db.get(Datasource, task.datasource_id)
    operator = db.get(User, task.operator_id)
    if version is None or datasource is None:
        _fail(db, task, "TEMPLATE_INVALID", "模板版本或数据源已不存在", [])
        return

    rows = read_rows(task.rows_path)
    target = get_target(datasource)
    schema = target.get_table_schema(version.target_schema or None, version.target_table)
    mapping = Mapping.model_validate(version.mapping)
    rules = [rule for rule in build_rules(schema.columns, version.rule_overrides)
             if rule.db_column in mapped_columns(mapping)]

    cleaned_rows: list[dict] = []
    errors: list[CellError] = []
    for raw in rows:
        row_no = int(raw.get("_row", 0))
        cleaned, row_errors, defaults = validate_row(rules, raw, row_no)
        errors.extend(row_errors)
        for item in defaults:
            _log(db, task, "DEFAULT_APPLIED",
                 f"第 {item['row']} 行 {item['column']} 为空，已按默认值 {item['value']} 处理",
                 level="WARNING", params=item)
        cleaned["_row"] = row_no
        cleaned_rows.append(cleaned)

    errors.extend(find_duplicate_keys(cleaned_rows, version.business_keys))
    if errors:
        _fail(db, task, "ROW_VALIDATION_FAILED", f"复核发现 {len(errors)} 处错误，未写入", errors)
        return

    # constants 由 worker 填充，覆盖前端提交的同名字段。
    for constant in mapping.constants:
        value = resolve_constant(constant.value, task, operator.username if operator else "")
        for row in cleaned_rows:
            row[constant.db_column] = value

    columns = sorted({column for row in cleaned_rows for column in row if column != "_row"})
    scopes = list({tuple(row.get(column) for column in version.scope_columns): {
        column: row.get(column) for column in version.scope_columns
    } for row in cleaned_rows}.values()) if version.scope_columns else []
    plan = WritePlan(strategy=version.strategy, columns=columns, business_keys=version.business_keys,
                     scope_columns=version.scope_columns, scopes=scopes)

    _log(db, task, "TASK_STARTED", f"开始处理，共 {len(rows)} 行，策略 {version.strategy}",
         params={"rows": len(rows), "strategy": version.strategy})
    db.commit()

    try:
        with target.engine.begin() as conn:
            if version.strategy == APPEND and version.business_keys:
                conflicts = target.existing_keys(conn, version.target_schema, version.target_table,
                                                 version.business_keys, cleaned_rows)
                if conflicts:
                    conflict_errors = [
                        CellError(int(row.get("_row", 0)), version.business_keys[0], "DUPLICATE_KEY")
                        for row in cleaned_rows
                        if tuple(row.get(column) for column in version.business_keys) in conflicts
                    ]
                    raise _Conflict(conflict_errors)
            result = _write_with_progress(db, task, target, conn, version, plan, cleaned_rows)
    except _Conflict as conflict:
        _fail(db, task, "DUPLICATE_KEY", f"业务键与已有数据冲突 {len(conflict.errors)} 行", conflict.errors)
        return
    except _Cancelled:
        task.status = CANCELLED
        task.finished_at = datetime.now(UTC)
        _log(db, task, "TASK_CANCELLED", "任务已取消，目标库事务已回滚", level="WARNING")
        db.query(TableLock).filter(TableLock.import_id == task.id).delete()
        db.commit()
        return
    except Exception as exc:  # 写入失败：事务已回滚
        _fail(db, task, "WRITE_FAILED", f"写入失败：{type(exc).__name__}", [])
        return

    task.status = COMMITTING
    db.commit()
    task.status = SUCCEEDED
    task.inserted = result.inserted
    task.updated = result.updated
    task.deleted = result.deleted
    task.counts_exact = result.counts_exact
    task.processed = len(cleaned_rows)
    task.finished_at = datetime.now(UTC)
    _log(db, task, "TASK_SUCCEEDED",
         f"完成：新增 {result.inserted}，更新 {result.updated}，删除 {result.deleted}",
         params={"inserted": result.inserted, "updated": result.updated, "deleted": result.deleted})
    db.query(TableLock).filter(TableLock.import_id == task.id).delete()
    db.commit()


class _Conflict(Exception):
    def __init__(self, errors: list[CellError]):
        self.errors = errors


class _Cancelled(Exception):
    pass


def _write_with_progress(db, task, target, conn, version, plan, rows):
    """分批写入并在每批之后检查取消标记与记录进度。"""
    batch_size = get_settings().batch_size
    written = None
    for start in range(0, len(rows), batch_size):
        db.refresh(task)
        if task.cancel_requested:
            raise _Cancelled()
        part = rows[start:start + batch_size]
        part_plan = WritePlan(strategy=plan.strategy, columns=plan.columns,
                              business_keys=plan.business_keys,
                              scope_columns=plan.scope_columns,
                              scopes=plan.scopes if start == 0 else [])
        outcome = target.write(conn, version.target_schema, version.target_table, part_plan, part)
        if written is None:
            written = outcome
        else:
            written.inserted += outcome.inserted
            written.updated += outcome.updated
            written.counts_exact = written.counts_exact and outcome.counts_exact
        task.processed = min(start + batch_size, len(rows))
        _log(db, task, "BATCH_DONE", f"第 {start + 1}-{task.processed} 行已写入",
             params={"from": start + 1, "to": task.processed})
        db.commit()
    return written


def claim(db: Session, worker_id: str) -> ImportTask | None:
    """领取一条任务：锁定队首、抢占表锁、置为 RUNNING。

    表锁主键冲突说明目标表正被写，跳过该任务继续找下一条。
    """
    dialect = db.bind.dialect.name if db.bind is not None else ""
    locking = " FOR UPDATE SKIP LOCKED" if dialect in {"postgresql", "mysql"} else ""
    queued = db.execute(
        text(f"SELECT id FROM imports WHERE status = :status ORDER BY created_at{locking}"),
        {"status": QUEUED},
    ).scalars().all()
    for import_id in queued:
        task = db.get(ImportTask, import_id)
        if task is None:
            continue
        try:
            with db.begin_nested():
                db.add(TableLock(datasource_id=task.datasource_id, target_schema=task.target_schema,
                                 target_table=task.target_table, import_id=task.id))
                db.flush()
        except Exception:
            continue
        task.status = RUNNING
        task.worker_id = worker_id
        task.started_at = datetime.now(UTC)
        task.heartbeat_at = datetime.now(UTC)
        db.commit()
        return task
    db.rollback()
    return None


def reap(db: Session) -> None:
    """回收心跳超时的任务：RUNNING 判失败，COMMITTING 判未知。"""
    deadline = datetime.now(UTC).timestamp() - get_settings().heartbeat_timeout_seconds
    stale = db.scalars(select(ImportTask).where(ImportTask.status.in_([RUNNING, COMMITTING]))).all()
    for task in stale:
        beat = task.heartbeat_at
        if beat is None or beat.replace(tzinfo=UTC).timestamp() >= deadline:
            continue
        task.status = FAILED if task.status == RUNNING else UNKNOWN
        if task.status == FAILED:
            task.failure_code = "WORKER_LOST"
            task.failure_message = "执行进程中断，事务已回滚"
        task.finished_at = datetime.now(UTC)
        db.query(TableLock).filter(TableLock.import_id == task.id).delete()
    db.commit()


def cleanup_uploads(now: datetime | None = None) -> int:
    """删除超过保留期的上传目录，返回清理的任务数。"""
    root = Path(get_settings().upload_dir)
    if not root.exists():
        return 0
    deadline = (now or datetime.now(UTC)).timestamp() - get_settings().upload_retention_days * 86400
    removed = 0
    for child in root.iterdir():
        if child.is_dir() and child.stat().st_mtime < deadline:
            for item in child.iterdir():
                item.unlink(missing_ok=True)
            child.rmdir()
            removed += 1
    return removed
