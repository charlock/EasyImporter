"""模板样例落盘（template_samples）：上传 / 下载 / 回显标记 / 克隆复制。

样例只存原文件字节，不解析；再次编辑时编辑器下载后在前端重新解析。
测试用 SQLite 元数据库（test_core 的 env 夹具），目标库用 _FakeTarget 替身。
"""

from types import SimpleNamespace

from app.connectors.base import ColumnInfo, TableSchema, UniqueKey
from test_core import _csrf, _login

XLSX = b"PK\x03\x04" + b"\x00" * 64
XLSX2 = b"PK\x03\x04" + b"\x01" * 32


class _FakeTarget:
    """模板创建只用 get_table_schema 探查目标表结构。"""

    def get_table_schema(self, schema, table):
        return TableSchema(schema="", table_name="bills", columns=[
            ColumnInfo("serial_no", "VARCHAR(64)", nullable=False, comment="流水号"),
            ColumnInfo("month", "VARCHAR(16)", nullable=False, comment="月份"),
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
        "strategy": "APPEND",
        "mapping": {"columns": [{"excel_path": ["流水号"], "db_column": "serial_no"},
                                {"excel_path": ["月份"], "db_column": "month"}]}}, headers=headers)
    assert template.status_code == 200, template.text
    return workspace["id"], template.json()["id"], headers


def _upload(client, base, headers, data=XLSX, filename="sample.xlsx"):
    return client.post(f"{base}/sample", headers=headers,
                       files={"file": (filename, data,
                                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})


def test_upload_download_roundtrip(env, monkeypatch):
    client, _tmp = env
    workspace_id, template_id, headers = _setup(client, monkeypatch)
    base = f"/api/v1/workspaces/{workspace_id}/templates/{template_id}"

    uploaded = _upload(client, base, headers)
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json() == {"ok": True, "file_name": "sample.xlsx", "size": len(XLSX)}

    downloaded = client.get(f"{base}/sample", headers=headers)
    assert downloaded.status_code == 200
    assert downloaded.content == XLSX
    assert "spreadsheetml.sheet" in downloaded.headers["content-type"]

    got = client.get(base, headers=headers)
    assert got.json()["has_sample"] is True
    assert got.json()["sample_file_name"] == "sample.xlsx"
    listed = client.get(f"/api/v1/workspaces/{workspace_id}/templates", headers=headers)
    assert listed.json()[0]["has_sample"] is True


def test_download_without_sample_is_404(env, monkeypatch):
    client, _tmp = env
    workspace_id, template_id, headers = _setup(client, monkeypatch)
    base = f"/api/v1/workspaces/{workspace_id}/templates/{template_id}"
    res = client.get(f"{base}/sample", headers=headers)
    assert res.status_code == 404
    got = client.get(base, headers=headers)
    assert got.json()["has_sample"] is False
    assert got.json()["sample_file_name"] is None


def test_upload_rejects_non_xlsx(env, monkeypatch):
    client, _tmp = env
    workspace_id, template_id, headers = _setup(client, monkeypatch)
    base = f"/api/v1/workspaces/{workspace_id}/templates/{template_id}"

    res = _upload(client, base, headers, data=b"hello", filename="sample.txt")
    assert res.status_code == 422
    assert res.json()["code"] == "INVALID_FILE_TYPE"

    res = _upload(client, base, headers, data=b"not a zip at all", filename="sample.xlsx")
    assert res.status_code == 422
    assert res.json()["code"] == "INVALID_FILE_TYPE"


def test_upload_rejects_oversize(env, monkeypatch):
    client, _tmp = env
    workspace_id, template_id, headers = _setup(client, monkeypatch)
    monkeypatch.setattr("app.api.templates.get_settings",
                        lambda: SimpleNamespace(upload_max_mb=0))
    base = f"/api/v1/workspaces/{workspace_id}/templates/{template_id}"
    res = _upload(client, base, headers)
    assert res.status_code == 413
    assert res.json()["code"] == "PAYLOAD_TOO_LARGE"


def test_upload_replaces_and_clone_copies(env, monkeypatch):
    client, _tmp = env
    workspace_id, template_id, headers = _setup(client, monkeypatch)
    base = f"/api/v1/workspaces/{workspace_id}/templates/{template_id}"

    assert _upload(client, base, headers).status_code == 200
    replaced = _upload(client, base, headers, data=XLSX2, filename="v2.xlsx")
    assert replaced.status_code == 200
    assert replaced.json()["file_name"] == "v2.xlsx"
    assert client.get(f"{base}/sample", headers=headers).content == XLSX2

    cloned = client.post(f"{base}/clone", headers=headers)
    assert cloned.status_code == 200, cloned.text
    clone_id = cloned.json()["id"]
    assert cloned.json()["has_sample"] is True
    assert cloned.json()["sample_file_name"] == "v2.xlsx"
    clone_base = f"/api/v1/workspaces/{workspace_id}/templates/{clone_id}"
    assert client.get(f"{clone_base}/sample", headers=headers).content == XLSX2
