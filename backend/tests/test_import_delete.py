"""导入记录删除接口：DELETE /workspaces/{id}/imports/{id}。

覆盖：成功删除（任务 + 日志 + 错误 + 磁盘文件）、运行中/提交中/已被认领的
排队任务拒绝 409、非管理员拒绝 403、不存在 404、删后 GET 404 且列表不再出现、
重试副本共用文件时不删磁盘文件、提交时保存源文件名、模板历史版本读取。
"""

import gzip
import io
import json

from sqlalchemy import func, select

from app.connectors.base import ColumnInfo, TableSchema, UniqueKey
from app.models.entities import (
    COMMITTING,
    FAILED,
    QUEUED,
    RUNNING,
    SUCCEEDED,
    ImportError,
    ImportLog,
    ImportTask,
)
from test_core import _csrf, _login


class _FakeTarget:
    """模板创建只用 get_table_schema 探查目标表结构。"""

    def get_table_schema(self, schema, table):
        return TableSchema(schema="", table_name="bills", columns=[
            ColumnInfo("serial_no", "VARCHAR(64)", nullable=False, comment="流水号"),
            ColumnInfo("month", "VARCHAR(16)", nullable=False, comment="月份"),
            ColumnInfo("amount", "DECIMAL(18,2)", nullable=True, comment="金额"),
        ], unique_keys=[UniqueKey("uk", ("serial_no", "month"))])


def _setup(client, monkeypatch):
    me = _login(client)
    headers = _csrf(client, me)
    workspace = client.post("/api/v1/workspaces", json={"name": "财务部"}, headers=headers).json()
    monkeypatch.setattr("app.api.templates.get_target", lambda item: _FakeTarget())
    datasource = client.post("/api/v1/datasources", json={
        "name": "财务库", "db_type": "postgres", "host": "127.0.0.1", "port": 5432,
        "database": "finance", "username": "ei", "password": "secret"}, headers=headers).json()
    template = client.post(f"/api/v1/workspaces/{workspace['id']}/templates", json={
        "name": "水单", "datasource_id": datasource["id"], "target_table": "bills",
        "strategy": "UPSERT", "business_keys": ["serial_no", "month"],
        "mapping": {"columns": [{"excel_path": ["流水号"], "db_column": "serial_no"},
                                {"excel_path": ["月份"], "db_column": "month"},
                                {"excel_path": ["金额"], "db_column": "amount"}]}}, headers=headers)
    assert template.status_code == 200, template.text
    return workspace["id"], template.json()["id"], datasource["id"], headers


def _submit(client, workspace_id, template_id, headers, filename="月度水单.xlsx"):
    rows = gzip.compress(json.dumps({"_row": 2, "serial_no": "S1", "month": "2026-01",
                                     "amount": "10"}).encode())
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/imports",
        data={"meta": json.dumps({"template_id": template_id, "template_version": 1,
                                  "row_count": 1})},
        files={"file": (filename, io.BytesIO(b"PK\x03\x04fake"), "application/octet-stream"),
               "rows": ("rows.jsonl.gz", io.BytesIO(rows), "application/gzip")},
        headers=headers,
    )
    assert response.status_code == 202, response.text
    return response.json()["id"]


def _set_status(task_id, status, worker_id=None):
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        task = db.get(ImportTask, task_id)
        task.status = status
        if worker_id is not None:
            task.worker_id = worker_id
        db.commit()


def _delete(client, workspace_id, task_id, headers):
    return client.delete(f"/api/v1/workspaces/{workspace_id}/imports/{task_id}", headers=headers)


def test_submit_stores_file_name(env, monkeypatch):
    client, _ = env
    workspace_id, template_id, _datasource_id, headers = _setup(client, monkeypatch)
    task_id = _submit(client, workspace_id, template_id, headers)
    detail = client.get(f"/api/v1/workspaces/{workspace_id}/imports/{task_id}", headers=headers)
    assert detail.json()["file_name"] == "月度水单.xlsx"
    listing = client.get(f"/api/v1/workspaces/{workspace_id}/imports", headers=headers).json()
    assert listing["items"][0]["file_name"] == "月度水单.xlsx"


def test_delete_succeeded_removes_task_logs_errors_and_files(env, monkeypatch):
    client, tmp_path = env
    workspace_id, template_id, _datasource_id, headers = _setup(client, monkeypatch)
    task_id = _submit(client, workspace_id, template_id, headers)
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        db.add(ImportLog(import_id=task_id, level="INFO", code="TASK_STARTED", message="start"))
        db.add(ImportError(import_id=task_id, row_no=2, column="amount", code="TYPE_MISMATCH"))
        db.commit()
    assert (tmp_path / str(task_id) / "source.xlsx").exists()
    _set_status(task_id, SUCCEEDED)

    response = _delete(client, workspace_id, task_id, headers)
    assert response.status_code == 200, response.text
    assert response.json() == {"ok": True}

    assert client.get(f"/api/v1/workspaces/{workspace_id}/imports/{task_id}",
                      headers=headers).status_code == 404
    assert client.get(f"/api/v1/workspaces/{workspace_id}/imports",
                      headers=headers).json()["total"] == 0
    assert not (tmp_path / str(task_id)).exists()
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ImportLog)
                         .where(ImportLog.import_id == task_id)) == 0
        assert db.scalar(select(func.count()).select_from(ImportError)
                         .where(ImportError.import_id == task_id)) == 0


def test_delete_running_rejected_409(env, monkeypatch):
    client, _ = env
    workspace_id, template_id, _datasource_id, headers = _setup(client, monkeypatch)
    task_id = _submit(client, workspace_id, template_id, headers)
    _set_status(task_id, RUNNING, worker_id="worker-1")
    response = _delete(client, workspace_id, task_id, headers)
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "IMPORT_NOT_DELETABLE"
    assert client.get(f"/api/v1/workspaces/{workspace_id}/imports/{task_id}",
                      headers=headers).status_code == 200


def test_delete_committing_rejected_409(env, monkeypatch):
    client, _ = env
    workspace_id, template_id, _datasource_id, headers = _setup(client, monkeypatch)
    task_id = _submit(client, workspace_id, template_id, headers)
    _set_status(task_id, COMMITTING, worker_id="worker-1")
    response = _delete(client, workspace_id, task_id, headers)
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "IMPORT_NOT_DELETABLE"


def test_delete_claimed_queued_rejected_409(env, monkeypatch):
    client, _ = env
    workspace_id, template_id, _datasource_id, headers = _setup(client, monkeypatch)
    task_id = _submit(client, workspace_id, template_id, headers)
    _set_status(task_id, QUEUED, worker_id="worker-1")
    response = _delete(client, workspace_id, task_id, headers)
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "IMPORT_NOT_DELETABLE"


def test_delete_unclaimed_queued_ok(env, monkeypatch):
    client, _ = env
    workspace_id, template_id, _datasource_id, headers = _setup(client, monkeypatch)
    task_id = _submit(client, workspace_id, template_id, headers)
    response = _delete(client, workspace_id, task_id, headers)
    assert response.status_code == 200, response.text


def test_delete_forbidden_for_importer(env, monkeypatch):
    client, _ = env
    workspace_id, template_id, _datasource_id, headers = _setup(client, monkeypatch)
    task_id = _submit(client, workspace_id, template_id, headers)
    importer = client.post("/api/v1/users",
                           json={"username": "zhangsan", "password": "Secret123",
                                 "role": "importer"}, headers=headers).json()
    client.put(f"/api/v1/workspaces/{workspace_id}/members", json={"user_ids": [importer["id"]]},
               headers=headers)
    client.post("/api/v1/auth/logout", headers=headers)
    importer_me = _login(client, "zhangsan", "Secret123")
    response = _delete(client, workspace_id, task_id, _csrf(client, importer_me))
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "FORBIDDEN"


def test_delete_missing_404(env, monkeypatch):
    client, _ = env
    workspace_id, _, _, headers = _setup(client, monkeypatch)
    assert _delete(client, workspace_id, 99999, headers).status_code == 404


def test_delete_original_keeps_files_shared_with_retry_clone(env, monkeypatch):
    client, tmp_path = env
    workspace_id, template_id, _datasource_id, headers = _setup(client, monkeypatch)
    task_id = _submit(client, workspace_id, template_id, headers)
    _set_status(task_id, FAILED)
    retry = client.post(f"/api/v1/workspaces/{workspace_id}/imports/{task_id}/retry",
                        headers=headers)
    assert retry.status_code == 202, retry.text
    clone_id = retry.json()["id"]
    assert clone_id != task_id

    response = _delete(client, workspace_id, task_id, headers)
    assert response.status_code == 200, response.text
    # 副本仍在，且共用的源文件未被删。
    assert client.get(f"/api/v1/workspaces/{workspace_id}/imports/{clone_id}",
                      headers=headers).status_code == 200
    assert (tmp_path / str(task_id) / "source.xlsx").exists()


def test_get_template_version_returns_historical_mapping(env, monkeypatch):
    client, _ = env
    workspace_id, template_id, datasource_id, headers = _setup(client, monkeypatch)
    base = f"/api/v1/workspaces/{workspace_id}/templates/{template_id}"
    updated = client.put(base, json={
        "name": "水单", "datasource_id": datasource_id, "target_table": "bills",
        "strategy": "UPSERT", "business_keys": ["serial_no", "month"],
        "mapping": {"columns": [{"excel_path": ["流水号"], "db_column": "serial_no"},
                                {"excel_path": ["月份"], "db_column": "month"}]}}, headers=headers)
    assert updated.status_code == 200, updated.text
    assert updated.json()["current_version"] == 2

    v1 = client.get(base, params={"version": 1}, headers=headers)
    assert v1.status_code == 200, v1.text
    assert len(v1.json()["mapping"]["columns"]) == 3
    v2 = client.get(base, params={"version": 2}, headers=headers)
    assert len(v2.json()["mapping"]["columns"]) == 2
    assert client.get(base, params={"version": 99}, headers=headers).status_code == 404
    # 不传 version 仍返回当前版本。
    assert client.get(base, headers=headers).json()["current_version"] == 2
