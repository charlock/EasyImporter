"""智能建表（tables/infer、tables/auto-create）测试。

类型推断是纯函数，直接单测；端点测试沿用 test_core 的 env 夹具（SQLite 元数据
库）与 SQLite 目标库替身，复用其 monkeypatch 手法；真实 PostgreSQL 的建表
验证见任务报告（本地 PG 不可用时记为待 VPS 验证）。
"""

import pytest
from sqlalchemy import text

from app.connectors.base import ColumnInfo, TableSchema, UniqueKey
from app.connectors.target import TargetDatabase
from app.services.table_inference import (
    InvalidColumn,
    InvalidIdentifier,
    build_create_table_ddl,
    infer_column_type,
    infer_columns,
    unique_constraint_name,
    validate_identifier,
)
from test_core import _csrf, _login  # env 夹具见同目录 conftest.py

# ---------------------------------------------------------------- 类型推断


def test_infer_integers_within_int32():
    assert infer_column_type([1, 2, -3]) == "INTEGER"
    assert infer_column_type([2 ** 31 - 1, -(2 ** 31)]) == "INTEGER"
    # Excel 里整数常以 1.0 的形式出现，数学上是整数就按整数算。
    assert infer_column_type([1.0, 2.0]) == "INTEGER"


def test_infer_bigint_beyond_int32():
    assert infer_column_type([2 ** 31]) == "BIGINT"
    assert infer_column_type([-(2 ** 31) - 1]) == "BIGINT"


def test_infer_decimal_for_mixed_int_float():
    assert infer_column_type([1, 2.5]) == "NUMERIC(18,4)"
    assert infer_column_type([1.5, 2.5]) == "NUMERIC(18,4)"


def test_infer_date_and_timestamp_strings():
    assert infer_column_type(["2026-01-01", "2026-01-02"]) == "DATE"
    assert infer_column_type(["2026-01-01T10:00:00", "2026-01-02T11:30:00"]) == "TIMESTAMP"
    assert infer_column_type(["2026-01-01T10:00:00Z"]) == "TIMESTAMP"
    # 日期与时间混合 → TIMESTAMP；非法日期不是日期。
    assert infer_column_type(["2026-01-01", "2026-01-02T10:00:00"]) == "TIMESTAMP"
    assert infer_column_type(["2026-02-30"]) == "VARCHAR(255)"
    assert infer_column_type(["2026/1/3"]) == "VARCHAR(255)"


def test_infer_boolean_all_forms():
    assert infer_column_type([True, False]) == "BOOLEAN"
    assert infer_column_type(["是", "否", "是"]) == "BOOLEAN"
    assert infer_column_type(["true", "FALSE", "True"]) == "BOOLEAN"
    assert infer_column_type(["1", "0", "1"]) == "BOOLEAN"
    assert infer_column_type([True, "否"]) == "BOOLEAN"


def test_infer_all_empty_column():
    assert infer_column_type([None, "", None]) == "VARCHAR(255)"
    assert infer_column_type([]) == "VARCHAR(255)"


def test_infer_varchar_or_text_by_length():
    assert infer_column_type(["abc", "x" * 255]) == "VARCHAR(255)"
    assert infer_column_type(["x" * 256]) == "TEXT"
    # 数字与文本混合、纯数字字符串都落到 VARCHAR（不丢前导零）。
    assert infer_column_type([1, "abc"]) == "VARCHAR(255)"
    assert infer_column_type(["00123", "00456"]) == "VARCHAR(255)"


def test_infer_columns_nullable_and_types():
    result = infer_columns([
        {"db_column": "a", "samples": [1, 2]},
        {"db_column": "b", "samples": [1, None]},
        {"db_column": "c", "samples": []},
    ])
    assert [(item.db_column, item.db_type, item.nullable) for item in result] == [
        ("a", "INTEGER", False), ("b", "INTEGER", True), ("c", "VARCHAR(255)", True),
    ]


def test_validate_identifier_rejects_chinese_and_bad_names():
    assert validate_identifier("sales_amount_1") == "sales_amount_1"
    assert validate_identifier("_private") == "_private"
    for bad in ["销售额", "1abc", "a-b", "a b", "a.b", "", "x" * 64]:
        with pytest.raises(InvalidIdentifier):
            validate_identifier(bad)


def test_unique_constraint_name_truncates_with_hash():
    assert unique_constraint_name("sales", ["serial_no"]) == "uq_sales_serial_no"
    assert unique_constraint_name("sales", ["serial_no", "month"]) == "uq_sales_serial_no_month"
    long_name = unique_constraint_name("a" * 40, ["b" * 30, "c" * 30])
    assert len(long_name.encode()) == 63
    assert long_name == unique_constraint_name("a" * 40, ["b" * 30, "c" * 30])


def test_build_create_table_ddl_exact():
    ddl = build_create_table_ddl("public", "sales", [
        {"db_column": "serial_no", "db_type": "INTEGER", "nullable": False},
        {"db_column": "amount", "db_type": "NUMERIC(18,4)", "nullable": True},
        {"db_column": "name", "db_type": "VARCHAR(255)", "nullable": True},
    ], ["serial_no"])
    assert ddl == (
        'CREATE TABLE "public"."sales" (\n'
        '  "serial_no" INTEGER NOT NULL,\n'
        '  "amount" NUMERIC(18,4),\n'
        '  "name" VARCHAR(255),\n'
        '  CONSTRAINT "uq_sales_serial_no" UNIQUE ("serial_no")\n'
        ");"
    )
    # schema 为空时不带限定；无业务键时无约束行。
    assert build_create_table_ddl("", "t", [
        {"db_column": "a", "db_type": "TEXT", "nullable": True}]).startswith('CREATE TABLE "t" (')


def test_build_create_table_ddl_rejects_bad_input():
    with pytest.raises(InvalidColumn):
        build_create_table_ddl("public", "t", [{"db_column": "a", "db_type": "VARCHAR(100)",
                                                "nullable": True}])
    with pytest.raises(InvalidColumn):
        build_create_table_ddl("public", "t", [{"db_column": "a", "db_type": "TEXT", "nullable": True}],
                               ["missing"])
    with pytest.raises(InvalidColumn):
        build_create_table_ddl("public", "t", [
            {"db_column": "a", "db_type": "TEXT", "nullable": True},
            {"db_column": "a", "db_type": "TEXT", "nullable": True}])
    with pytest.raises(InvalidColumn):
        build_create_table_ddl("public", "t", [])
    with pytest.raises(InvalidIdentifier):
        build_create_table_ddl("public", "销售表", [{"db_column": "a", "db_type": "TEXT",
                                                    "nullable": True}])


# ---------------------------------------------------------------- 端点


def _setup(client, headers, monkeypatch, target, db_type="postgres"):
    workspace = client.post("/api/v1/workspaces", json={"name": "财务部"}, headers=headers).json()
    monkeypatch.setattr("app.api.datasources.get_target", lambda item: target)
    datasource = client.post("/api/v1/datasources", json={
        "name": "库", "db_type": db_type, "host": "127.0.0.1", "port": 5432,
        "database": "finance", "username": "ei", "password": "secret"}, headers=headers).json()
    return workspace["id"], datasource["id"]


def _infer_body(**overrides):
    body = {
        "target_schema": "public", "table_name": "sales",
        "columns": [
            {"db_column": "serial_no", "samples": [1, 2, 3]},
            {"db_column": "amount", "samples": [1.5, 2.5]},
            {"db_column": "day", "samples": ["2026-01-01"]},
            {"db_column": "flag", "samples": [True, False]},
            {"db_column": "name", "samples": ["A公司", "B公司"]},
        ],
        "unique_keys": ["serial_no"],
    }
    body.update(overrides)
    return body


@pytest.fixture()
def target(tmp_path):
    url = f"sqlite:///{tmp_path}/target.db"
    return TargetDatabase("postgres", url)


def test_infer_returns_columns_and_ddl(env, target, monkeypatch):
    client, _ = env
    me = _login(client)
    headers = _csrf(client, me)
    wid, dsid = _setup(client, headers, monkeypatch, target)
    response = client.post(
        f"/api/v1/workspaces/{wid}/datasources/{dsid}/tables/infer",
        json=_infer_body(), headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert [(item["db_column"], item["db_type"], item["nullable"]) for item in data["columns"]] == [
        ("serial_no", "INTEGER", False), ("amount", "NUMERIC(18,4)", False),
        ("day", "DATE", False), ("flag", "BOOLEAN", False), ("name", "VARCHAR(255)", False),
    ]
    assert data["ddl"] == (
        'CREATE TABLE "public"."sales" (\n'
        '  "serial_no" INTEGER NOT NULL,\n'
        '  "amount" NUMERIC(18,4) NOT NULL,\n'
        '  "day" DATE NOT NULL,\n'
        '  "flag" BOOLEAN NOT NULL,\n'
        '  "name" VARCHAR(255) NOT NULL,\n'
        '  CONSTRAINT "uq_sales_serial_no" UNIQUE ("serial_no")\n'
        ");"
    )


def test_infer_defaults_table_name(env, target, monkeypatch):
    client, _ = env
    headers = _csrf(client, _login(client))
    wid, dsid = _setup(client, headers, monkeypatch, target)
    body = _infer_body()
    del body["table_name"]
    response = client.post(
        f"/api/v1/workspaces/{wid}/datasources/{dsid}/tables/infer", json=body, headers=headers)
    assert response.status_code == 200, response.text
    assert '"import_' in response.json()["ddl"]


def test_infer_rejects_bad_identifier_and_too_many_samples(env, target, monkeypatch):
    client, _ = env
    headers = _csrf(client, _login(client))
    wid, dsid = _setup(client, headers, monkeypatch, target)
    body = _infer_body()
    body["columns"][0]["db_column"] = "流水号"
    body["unique_keys"] = []  # 列改名后业务键不再指向它，避免先触发业务键校验
    response = client.post(
        f"/api/v1/workspaces/{wid}/datasources/{dsid}/tables/infer", json=body, headers=headers)
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_IDENTIFIER"
    body = _infer_body()
    body["columns"][0]["samples"] = list(range(201))
    response = client.post(
        f"/api/v1/workspaces/{wid}/datasources/{dsid}/tables/infer", json=body, headers=headers)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_FAILED"


def test_auto_create_then_conflict_409(env, target, monkeypatch):
    client, _ = env
    headers = _csrf(client, _login(client))
    wid, dsid = _setup(client, headers, monkeypatch, target)
    body = {"target_schema": "", "target_table": "tmp_spike_autocreate", "columns": [
        {"db_column": "serial_no", "db_type": "INTEGER", "nullable": False},
        {"db_column": "amount", "db_type": "NUMERIC(18,4)", "nullable": True},
    ], "unique_keys": ["serial_no"]}
    response = client.post(
        f"/api/v1/workspaces/{wid}/datasources/{dsid}/tables/auto-create",
        json=body, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json() == {"schema": "", "name": "tmp_spike_autocreate"}
    with target.engine.connect() as conn:
        assert conn.execute(text(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'tmp_spike_autocreate'"
        )).scalar() == 1

    # 第二次建同一张表 → 409，并附已存在表的列清单（SQLite 替身没有
    # information_schema，沿用现有测试手法桩掉 get_table_schema）。
    schema = TableSchema(schema="", table_name="tmp_spike_autocreate", columns=[
        ColumnInfo("serial_no", "INTEGER", nullable=False),
        ColumnInfo("amount", "NUMERIC(18,4)", nullable=True),
    ], unique_keys=[UniqueKey("uq_tmp_spike_autocreate_serial_no", ("serial_no",))])
    monkeypatch.setattr(TargetDatabase, "get_table_schema", lambda self, s, t: schema)
    response = client.post(
        f"/api/v1/workspaces/{wid}/datasources/{dsid}/tables/auto-create",
        json=body, headers=headers)
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "TABLE_EXISTS"
    params = response.json()["params"]
    assert [column["name"] for column in params["columns"]] == ["serial_no", "amount"]
    assert params["unique_keys"] == [
        {"name": "uq_tmp_spike_autocreate_serial_no", "columns": ["serial_no"]}]


def test_auto_create_rejects_non_postgres_and_bad_input(env, target, monkeypatch):
    client, _ = env
    headers = _csrf(client, _login(client))
    wid, dsid = _setup(client, headers, monkeypatch, target, db_type="mysql")
    body = {"target_schema": "public", "target_table": "t", "columns": [
        {"db_column": "a", "db_type": "TEXT", "nullable": True}]}
    response = client.post(
        f"/api/v1/workspaces/{wid}/datasources/{dsid}/tables/auto-create",
        json=body, headers=headers)
    assert response.status_code == 422
    assert response.json()["code"] == "UNSUPPORTED_DATASOURCE"

    wid, dsid = _setup(client, headers, monkeypatch, target)
    body["target_table"] = "销售表"
    response = client.post(
        f"/api/v1/workspaces/{wid}/datasources/{dsid}/tables/auto-create",
        json=body, headers=headers)
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_IDENTIFIER"
    body["target_table"] = "t"
    body["columns"][0]["db_type"] = "VARCHAR(100)"
    response = client.post(
        f"/api/v1/workspaces/{wid}/datasources/{dsid}/tables/auto-create",
        json=body, headers=headers)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_FAILED"


def test_auto_create_rejects_upsert_without_business_keys(env, target, monkeypatch):
    """UPSERT 没带业务键时建表直接拒掉，表建不出来（不再留孤表）。

    回归 2026-11-18 前端 guard 只拦界面入口、API 直调仍能建出无唯一约束
    的表的缺口：strategy=UPSERT + unique_keys 为空 → 422 UNIQUE_KEY_REQUIRED，
    且目标库里没有这张表；APPEND 不带业务键、UPSERT 带业务键都不受影响。
    """
    client, _ = env
    headers = _csrf(client, _login(client))
    wid, dsid = _setup(client, headers, monkeypatch, target)

    def body(table, strategy, unique_keys):
        return {"target_schema": "", "target_table": table, "strategy": strategy, "columns": [
            {"db_column": "serial_no", "db_type": "INTEGER", "nullable": False},
            {"db_column": "amount", "db_type": "NUMERIC(18,4)", "nullable": True},
        ], "unique_keys": unique_keys}

    response = client.post(
        f"/api/v1/workspaces/{wid}/datasources/{dsid}/tables/auto-create",
        json=body("tmp_upsert_no_keys", "UPSERT", []), headers=headers)
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "UNIQUE_KEY_REQUIRED"
    with target.engine.connect() as conn:
        assert conn.execute(text(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'tmp_upsert_no_keys'"
        )).scalar() == 0

    # APPEND 不带业务键：照常建表，不受影响。
    response = client.post(
        f"/api/v1/workspaces/{wid}/datasources/{dsid}/tables/auto-create",
        json=body("tmp_append_no_keys", "APPEND", []), headers=headers)
    assert response.status_code == 200, response.text

    # UPSERT 带业务键：照常建表。
    response = client.post(
        f"/api/v1/workspaces/{wid}/datasources/{dsid}/tables/auto-create",
        json=body("tmp_upsert_with_keys", "UPSERT", ["serial_no"]), headers=headers)
    assert response.status_code == 200, response.text


def test_table_endpoints_require_admin(env, target, monkeypatch):
    client, _ = env
    me = _login(client)
    headers = _csrf(client, me)
    wid, dsid = _setup(client, headers, monkeypatch, target)
    importer = client.post("/api/v1/users",
                           json={"username": "zhangsan", "password": "Secret123", "role": "importer"},
                           headers=headers).json()
    client.put(f"/api/v1/workspaces/{wid}/members", json={"user_ids": [importer["id"]]},
               headers=headers)
    client.post("/api/v1/auth/logout", headers=headers)
    importer_me = _login(client, "zhangsan", "Secret123")
    importer_headers = _csrf(client, importer_me)
    for url, body in [
        (f"/api/v1/workspaces/{wid}/datasources/{dsid}/tables/infer", _infer_body()),
        (f"/api/v1/workspaces/{wid}/datasources/{dsid}/tables/auto-create",
         {"target_schema": "", "target_table": "t",
          "columns": [{"db_column": "a", "db_type": "TEXT", "nullable": True}]}),
    ]:
        response = client.post(url, json=body, headers=importer_headers)
        assert response.status_code == 403, (url, response.text)
        assert response.json()["code"] == "FORBIDDEN"
    # 未登录 → 401。
    client.post("/api/v1/auth/logout", headers=importer_headers)
    response = client.post(
        f"/api/v1/workspaces/{wid}/datasources/{dsid}/tables/infer", json=_infer_body())
    assert response.status_code == 401
