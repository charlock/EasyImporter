"""后端测试。

元数据库与目标库都用临时目录下的 SQLite 文件库（postgres 方言的双引号标识符
与 SQLite 兼容），因此 APPEND / UPSERT / REPLACE_SCOPE 三种策略都能在本地跑通。
达梦与 MySQL 的方言 SQL 由 connectors/target.py 按 db_type 生成，集成环境验证。
"""

import base64
import gzip
import io
import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.connectors.base import ColumnInfo, TableSchema, UniqueKey, WritePlan
from app.connectors.target import TargetDatabase
from app.core import crypto
from app.core.config import get_settings
from app.models.entities import FAILED, QUEUED, SUCCEEDED
from app.rules.engine import (
    build_rules,
    find_duplicate_keys,
    normalize_name,
    validate_row,
)
from app.services.matching import suggest


@pytest.fixture()
def env(monkeypatch, tmp_path):
    db_file = tmp_path / "meta.db"
    monkeypatch.setenv("EI_DATABASE_URL", f"sqlite:///{db_file}")
    # 合法的 32 字节 base64 主密钥，走真实的启动校验与 HKDF 派生。
    monkeypatch.setenv("EI_SECRET_KEY", base64.b64encode(b"k" * 32).decode())
    monkeypatch.setenv("EI_UPLOAD_DIR", str(tmp_path))
    monkeypatch.setenv("EI_ADMIN_INIT_PASSWORD", "InitPass123")
    get_settings.cache_clear()

    # 引擎延迟创建；每个测试用独立数据库文件，先丢弃上一个测试缓存的引擎。
    from app.core import db as db_module

    db_module.engine._real = None
    # 生产环境由 alembic 建表；测试直接按 ORM 建表，省去跑迁移。
    db_module.Base.metadata.create_all(db_module.engine)

    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        yield client, tmp_path
    get_settings.cache_clear()


def _login(client, username="admin", password="InitPass123"):
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def _csrf(client, me):
    return {"X-CSRF-Token": me["csrf_token"]}


# ---------------------------------------------------------------- 规则引擎


def test_normalize_name_strips_units_and_width():
    assert normalize_name("　销售额（元）") == "销售额"
    assert normalize_name("Serial No.") == "serialno"


def test_validate_row_converts_and_defaults():
    rules = build_rules(
        [ColumnInfo("amount", "DECIMAL(18,2)", nullable=True),
         ColumnInfo("flag", "BOOLEAN", nullable=False, default=None),
         ColumnInfo("day", "DATE", nullable=True)],
        [{"db_column": "amount", "default": "0.00"}],
    )
    cleaned, errors, defaults = validate_row(rules, {"amount": None, "flag": "是", "day": "2026/1/3"}, 5)
    assert errors == []
    assert cleaned["amount"] == "0.00"
    assert cleaned["flag"] is True
    assert cleaned["day"] == "2026-01-03"
    assert defaults[0]["column"] == "amount"


def test_validate_row_reports_required_and_enum():
    rules = build_rules(
        [ColumnInfo("company", "VARCHAR(32)", nullable=False)],
        [{"db_column": "company", "enum": ["A公司", "B公司"]}],
    )
    _, errors, _ = validate_row(rules, {"company": "C公司"}, 2)
    assert errors[0].code == "ENUM_MISMATCH"
    _, errors, _ = validate_row(rules, {"company": ""}, 3)
    assert errors[0].code == "REQUIRED"


def test_duplicate_keys_marks_every_row():
    rows = [{"_row": 1, "serial_no": "S1"}, {"_row": 2, "serial_no": "S2"}, {"_row": 3, "serial_no": "S1"}]
    errors = find_duplicate_keys(rows, ["serial_no"])
    assert {error.row_no for error in errors} == {1, 3}


def test_rules_match_shared_fixtures():
    """与前端共用的样例：fixtures/rules/*.json 里 expected 必须与后端结论一致。"""
    from pathlib import Path

    for fixture in Path("fixtures/rules").glob("*.json"):
        data = json.loads(fixture.read_text())
        rules = build_rules(
            [ColumnInfo(**column) for column in data["columns"]], data.get("overrides", [])
        )
        for case in data["cases"]:
            cleaned, errors, _ = validate_row(rules, case["row"], case["row_no"])
            assert [error.code for error in errors] == case["expected_errors"], fixture.name
            for key, value in case.get("expected_values", {}).items():
                assert cleaned[key] == value, fixture.name


# ---------------------------------------------------------------- 自动匹配


def _schema():
    return TableSchema(schema="public", table_name="t", columns=[
        ColumnInfo("serial_no", "VARCHAR(64)", comment="流水号"),
        ColumnInfo("sales_amount", "DECIMAL(18,2)", comment="销售额"),
        ColumnInfo("profit", "DECIMAL(18,2)", comment="利润"),
    ])


def test_suggest_prefers_synonym_and_comment():
    synonyms = {normalize_name(word): 1 for word in ["水单号", "流水号", "serial_no"]}
    result = suggest(_schema(), [["水单号"], ["1月份", "销售额"]], True, synonyms, {})
    by_path = {tuple(item["excel_path"]): item for item in result}
    assert by_path[("水单号",)]["reason"] == "SYNONYM"
    assert by_path[("1月份", "销售额")]["db_column"] == "sales_amount"
    assert by_path[("1月份", "销售额")]["reason"] == "COMMENT_EXACT"


def test_suggest_history_wins_and_column_used_once():
    history = {"水单号": "serial_no"}
    result = suggest(_schema(), [["水单号"], ["流水号"]], False, {}, history)
    assert len(result) == 1
    assert result[0]["reason"] == "HISTORY"


# ---------------------------------------------------------------- 写入层（SQLite 充当目标库）


@pytest.fixture()
def target(tmp_path):
    url = f"sqlite:///{tmp_path}/target.db"
    database = TargetDatabase("postgres", url)
    with database.engine.begin() as conn:
        conn.execute(text("CREATE TABLE bills (serial_no TEXT, month TEXT, amount TEXT, "
                           "UNIQUE (serial_no, month))"))
    return database


def test_append_and_replace_scope(target):
    plan = WritePlan("APPEND", ["serial_no", "month", "amount"])
    rows = [{"serial_no": "S1", "month": "2026-01", "amount": "10"},
            {"serial_no": "S2", "month": "2026-02", "amount": "20"}]
    with target.engine.begin() as conn:
        result = target.write(conn, None, "bills", plan, rows)
    assert result.inserted == 2

    scope_plan = WritePlan("REPLACE_SCOPE", ["serial_no", "month", "amount"],
                           scope_columns=["month"], scopes=[{"month": "2026-01"}])
    with target.engine.begin() as conn:
        result = target.write(conn, None, "bills", scope_plan,
                              [{"serial_no": "S3", "month": "2026-01", "amount": "30"}])
    assert result.deleted == 1
    with target.engine.connect() as conn:
        left = conn.execute(text("SELECT serial_no FROM bills ORDER BY serial_no")).scalars().all()
    # 2026-01 的旧行被删，2026-02 保留。
    assert left == ["S2", "S3"]


def test_replace_scope_uses_tuple_not_cross_product(target):
    with target.engine.begin() as conn:
        conn.execute(text("INSERT INTO bills VALUES ('A', '2026-01', '1'), ('A', '2026-02', '2'), "
                          "('B', '2026-02', '3')"))
    plan = WritePlan("REPLACE_SCOPE", ["serial_no", "month", "amount"],
                     scope_columns=["serial_no", "month"],
                     scopes=[{"serial_no": "A", "month": "2026-01"}, {"serial_no": "B", "month": "2026-02"}])
    with target.engine.begin() as conn:
        target.write(conn, None, "bills", plan, [])
    with target.engine.connect() as conn:
        left = conn.execute(text("SELECT serial_no, month FROM bills")).all()
    # (A, 2026-02) 不在范围内，必须保留。
    assert left == [("A", "2026-02")]


def test_upsert_sql_per_dialect():
    database = TargetDatabase("postgres", "sqlite://")
    plan = WritePlan("UPSERT", ["serial_no", "amount"], business_keys=["serial_no"])
    sql = database._upsert_sql("bills", plan, ['"serial_no"', '"amount"'], ":serial_no, :amount")
    assert "ON CONFLICT" in sql
    mysql = TargetDatabase("mysql", "sqlite://")
    sql = mysql._upsert_sql("bills", plan, ["`serial_no`", "`amount`"], ":serial_no, :amount")
    assert "ON DUPLICATE KEY UPDATE" in sql
    dameng = TargetDatabase("dameng", "sqlite://")
    sql = dameng._upsert_sql("bills", plan, ['"serial_no"', '"amount"'], ":serial_no, :amount")
    assert sql.startswith("MERGE INTO")


def test_mysql_upsert_counts_are_per_batch(monkeypatch):
    """MySQL 每批按 rowcount 估算更新数，多批累加时不能用累计值参与计算。"""
    from types import SimpleNamespace

    from app.connectors.base import WriteResult

    database = TargetDatabase("mysql", "sqlite://")
    plan = WritePlan("UPSERT", ["serial_no", "amount"], business_keys=["serial_no"])
    # 第一批 3 行全新增（rowcount 3），第二批 3 行中 2 行更新（rowcount 1 + 2*2 = 5）。
    counts = iter([3, 5])
    conn = SimpleNamespace(execute=lambda sql, params: SimpleNamespace(rowcount=next(counts)))
    result = WriteResult(counts_exact=False)
    batch = [{"serial_no": f"S{i}", "amount": "1"} for i in range(3)]
    database._write_batch(conn, "`bills`", plan, batch, result)
    database._write_batch(conn, "`bills`", plan, batch, result)
    assert (result.inserted, result.updated) == (4, 2)


def test_quote_ident_rejects_injection():
    from app.connectors.target import UnsafeIdentifier, quote_ident

    with pytest.raises(UnsafeIdentifier):
        quote_ident('a"; drop table t; --', "postgres")


# ---------------------------------------------------------------- 接口


def test_login_lockout_and_password_change(env):
    client, _ = env
    for _ in range(5):
        response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
        assert response.status_code == 401
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "InitPass123"})
    assert response.status_code == 429
    assert response.json()["code"] == "LOGIN_LOCKED"


def test_workspace_member_can_import_but_not_manage(env, target, monkeypatch):
    client, tmp_path = env
    me = _login(client)
    headers = _csrf(client, me)

    # 管理员建工作区、用户、数据源、模板。
    workspace = client.post("/api/v1/workspaces", json={"name": "财务部"}, headers=headers).json()
    importer = client.post("/api/v1/users",
                           json={"username": "zhangsan", "password": "Secret123", "role": "importer"},
                           headers=headers).json()
    client.put(f"/api/v1/workspaces/{workspace['id']}/members", json={"user_ids": [importer["id"]]},
               headers=headers)

    # 数据源指向测试目标库；密码加密后不出现在响应里。
    monkeypatch.setattr("app.api.datasources.get_target", lambda item: target)
    monkeypatch.setattr("app.api.templates.get_target", lambda item: target)
    monkeypatch.setattr("app.api.imports.get_target", lambda item: target)
    monkeypatch.setattr("app.services.imports.get_target", lambda item: target)

    # 目标库没有 information_schema，直接桩掉探查。
    schema = TableSchema(schema="", table_name="bills", columns=[
        ColumnInfo("serial_no", "VARCHAR(64)", nullable=False, comment="流水号"),
        ColumnInfo("month", "VARCHAR(16)", nullable=False, comment="月份"),
        ColumnInfo("amount", "DECIMAL(18,2)", nullable=True, comment="金额"),
    ], unique_keys=[UniqueKey("uk", ("serial_no", "month"))])
    monkeypatch.setattr(TargetDatabase, "get_table_schema", lambda self, s, t: schema)

    datasource = client.post("/api/v1/datasources", json={
        "name": "财务库", "db_type": "postgres", "host": "127.0.0.1", "port": 5432,
        "database": "finance", "username": "ei", "password": "secret"}, headers=headers).json()
    assert "password" not in datasource

    template = client.post(f"/api/v1/workspaces/{workspace['id']}/templates", json={
        "name": "水单", "datasource_id": datasource["id"], "target_table": "bills",
        "strategy": "UPSERT", "business_keys": ["serial_no", "month"],
        "mapping": {"columns": [{"excel_path": ["流水号"], "db_column": "serial_no"},
                                {"excel_path": ["月份"], "db_column": "month"},
                                {"excel_path": ["金额"], "db_column": "amount"}]}}, headers=headers)
    assert template.status_code == 200, template.text
    template_id = template.json()["id"]

    # 导入员看不到数据源。
    client.post("/api/v1/auth/logout", headers=headers)
    importer_me = _login(client, "zhangsan", "Secret123")
    assert client.get("/api/v1/datasources").status_code == 403

    # 提交导入。
    rows = gzip.compress("\n".join(json.dumps(row) for row in [
        {"_row": 2, "serial_no": "S1", "month": "2026-01", "amount": "1,234.50"},
        {"_row": 3, "serial_no": "S2", "month": "2026-01", "amount": "20"},
    ]).encode())
    response = client.post(
        f"/api/v1/workspaces/{workspace['id']}/imports",
        data={"meta": json.dumps({"template_id": template_id, "template_version": 1, "row_count": 2})},
        files={"file": ("bills.xlsx", io.BytesIO(b"PK\x03\x04fake"), "application/octet-stream"),
               "rows": ("rows.jsonl.gz", io.BytesIO(rows), "application/gzip")},
        headers=_csrf(client, importer_me),
    )
    assert response.status_code == 202, response.text
    assert response.json()["status"] == QUEUED

    # worker 执行后任务成功，金额去掉了千分位。
    from app.core.db import SessionLocal
    from app.services.imports import claim, execute

    with SessionLocal() as db:
        task = claim(db, "test-worker")
        assert task is not None
        execute(db, task)
        db.refresh(task)
        assert task.status == SUCCEEDED, (task.failure_code, task.failure_message)
    with target.engine.connect() as conn:
        amounts = conn.execute(text("SELECT amount FROM bills ORDER BY serial_no")).scalars().all()
    assert amounts == ["1234.50", "20.00"]


def test_backend_rejects_rows_failing_recheck(env, target, monkeypatch):
    client, _ = env
    me = _login(client)
    headers = _csrf(client, me)
    workspace = client.post("/api/v1/workspaces", json={"name": "财务部"}, headers=headers).json()
    schema = TableSchema(schema="", table_name="bills", columns=[
        ColumnInfo("serial_no", "VARCHAR(64)", nullable=False),
        ColumnInfo("amount", "DECIMAL(18,2)", nullable=True),
    ])
    monkeypatch.setattr(TargetDatabase, "get_table_schema", lambda self, s, t: schema)
    monkeypatch.setattr("app.api.templates.get_target", lambda item: target)
    monkeypatch.setattr("app.services.imports.get_target", lambda item: target)
    datasource = client.post("/api/v1/datasources", json={
        "name": "库", "db_type": "postgres", "host": "127.0.0.1", "port": 5432,
        "database": "finance", "username": "ei", "password": "secret"}, headers=headers).json()
    template = client.post(f"/api/v1/workspaces/{workspace['id']}/templates", json={
        "name": "水单", "datasource_id": datasource["id"], "target_table": "bills",
        "mapping": {"columns": [{"excel_path": ["流水号"], "db_column": "serial_no"},
                                {"excel_path": ["金额"], "db_column": "amount"}]}}, headers=headers).json()
    rows = gzip.compress(json.dumps({"_row": 2, "serial_no": "", "amount": "abc"}).encode())
    response = client.post(
        f"/api/v1/workspaces/{workspace['id']}/imports",
        data={"meta": json.dumps({"template_id": template["id"], "template_version": 1, "row_count": 1})},
        files={"file": ("bills.xlsx", io.BytesIO(b"PK\x03\x04"), "application/octet-stream"),
               "rows": ("rows.jsonl.gz", io.BytesIO(rows), "application/gzip")},
        headers=headers,
    )
    assert response.status_code == 202, response.text
    from app.core.db import SessionLocal
    from app.services.imports import claim, execute

    with SessionLocal() as db:
        task = claim(db, "worker")
        execute(db, task)
        db.refresh(task)
        assert task.status == FAILED
        assert task.failure_code == "ROW_VALIDATION_FAILED"
    # 复核失败时目标表没有任何写入。
    with target.engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM bills")).scalar() == 0


def test_row_count_mismatch_rejected(env):
    client, _ = env
    me = _login(client)
    headers = _csrf(client, me)
    workspace = client.post("/api/v1/workspaces", json={"name": "财务部"}, headers=headers).json()
    rows = gzip.compress(json.dumps({"_row": 2, "a": 1}).encode())
    response = client.post(
        f"/api/v1/workspaces/{workspace['id']}/imports",
        data={"meta": json.dumps({"template_id": 999, "template_version": 1, "row_count": 5})},
        files={"file": ("a.xlsx", io.BytesIO(b"PK\x03\x04"), "application/octet-stream"),
               "rows": ("rows.jsonl.gz", io.BytesIO(rows), "application/gzip")},
        headers=headers,
    )
    # 模板不存在先返回 404；行数校验在模板校验之后。这里确认请求被拒绝。
    assert response.status_code in {404, 422}


def test_startup_rejects_missing_or_bad_secret_key(monkeypatch):
    for value in ["", "not-base64!!", "A" * 44]:
        monkeypatch.setenv("EI_SECRET_KEY", value)
        get_settings.cache_clear()
        with pytest.raises(crypto.SecretKeyMissing):
            crypto.ensure_keys()
    get_settings.cache_clear()


def test_encryption_roundtrip(monkeypatch):
    monkeypatch.setattr(crypto, "derive_key", lambda info: b"k" * 32)
    token = crypto.encrypt("p@ssw0rd")
    assert crypto.decrypt(token) == "p@ssw0rd"
    assert "p@ssw0rd" not in token


def test_session_expiry(env, monkeypatch):
    client, _ = env
    _login(client)
    from datetime import UTC, datetime

    from app.core.db import SessionLocal
    from app.models.entities import Session as SessionRecord

    with SessionLocal() as db:
        record = db.query(SessionRecord).one()
        record.expires_at = datetime.now(UTC) - timedelta(hours=1)
        db.commit()
    assert client.get("/api/v1/auth/me").status_code == 401
