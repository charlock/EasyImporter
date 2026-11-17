"""模板列表 include_archived 参数：默认不含已归档，传参后含已归档。

删除是软删除（is_archived=true），列表页靠 include_archived=true 才能在删除后
继续看到该行并显示“已归档”徽章；模板下拉等其他调用方不传参，行为不变。
"""

from app.connectors.base import ColumnInfo, TableSchema, UniqueKey
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
    return workspace["id"], template.json()["id"], headers


def test_list_excludes_archived_by_default(env, monkeypatch):
    client, _tmp = env
    workspace_id, template_id, headers = _setup(client, monkeypatch)
    base = f"/api/v1/workspaces/{workspace_id}/templates"

    listed = client.get(base, headers=headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [template_id]

    deleted = client.delete(f"{base}/{template_id}", headers=headers)
    assert deleted.status_code == 200, deleted.text

    listed = client.get(base, headers=headers)
    assert listed.status_code == 200
    assert listed.json() == []


def test_list_include_archived_shows_archived_row(env, monkeypatch):
    client, _tmp = env
    workspace_id, template_id, headers = _setup(client, monkeypatch)
    base = f"/api/v1/workspaces/{workspace_id}/templates"

    deleted = client.delete(f"{base}/{template_id}", headers=headers)
    assert deleted.status_code == 200, deleted.text

    listed = client.get(f"{base}?include_archived=true", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["id"] == template_id
    assert listed.json()[0]["is_archived"] is True
