# 接口设计

> 上级文档：[设计方案](design.md) · [架构设计](architecture.md)

## 约定

- 前缀 `/api/v1`，JSON，时间用 ISO 8601 UTC。
- 认证用会话 Cookie，写操作需带 `X-CSRF-Token` 头。
- 分页参数 `page`（从 1 开始）、`size`（默认 20，最大 100），返回 `{ "items": [], "total": 0, "page": 1, "size": 20 }`。
- 出错时返回对应的 HTTP 状态码和下面的结构。`message` 是默认中文说明，前端按 `code + params` 翻译成当前语言。

```json
{ "code": "TEMPLATE_HEADER_MISMATCH", "message": "缺少必需列：水单号", "params": { "missing": ["水单号"] } }
```

## 相对原方案的变化

| 原接口 | 问题 | 新接口 |
|---|---|---|
| `GET /database/schema?connection_string=…` | 密码出现在 URL 里，会被代理和浏览器记录；任何人都能连任意库 | `GET /datasources/{id}/tables/{table}/schema`，只认已登记的数据源 |
| `POST /imports/task` | 不带原始文件，出问题无法追溯 | `POST /workspaces/{ws}/imports`，multipart 同时上传文件和规范行 |
| `GET /imports/records` 和 `/tasks/{id}/logs` 分开 | 记录和日志属于同一个任务 | 统一为 `/imports/{id}` 及其子资源 |

## 认证

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/auth/login` | 用户名密码登录，设置会话 Cookie |
| POST | `/auth/logout` | 退出 |
| GET | `/auth/me` | 当前用户、角色、所属工作区、CSRF token |
| GET | `/health` | 健康检查，不需要登录 |

## 工作区与用户（管理员）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET / POST | `/workspaces` | 列表（导入员只看到自己所在的）/ 新建 |
| PUT / DELETE | `/workspaces/{ws}` | 修改 / 删除（有模板或任务时不允许删除） |
| GET / PUT | `/workspaces/{ws}/members` | 查看 / 整体设置成员 |
| GET / POST / PUT | `/users`、`/users/{id}` | 用户管理；用户可停用，不可删除 |

## 数据源（管理员）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET / POST | `/datasources` | 列表 / 登记 |
| PUT / DELETE | `/datasources/{id}` | 修改（密码字段留空表示不改）/ 删除（被模板引用时不允许） |
| POST | `/datasources/{id}/test` | 测试连接 |
| GET | `/datasources/{id}/tables?schema=` | 表列表 |
| GET | `/datasources/{id}/tables/{table}/schema?schema=` | 表结构。`schema` 省略时用数据源 `options.schema`，再省略用连接默认 schema；响应里返回实际 schema 名 |

登记请求：

```json
{ "name": "财务库-生产", "db_type": "postgres", "host": "10.0.1.20", "port": 5432,
  "database": "finance", "username": "ei_writer", "password": "******", "options": { "schema": "public" } }
```

`db_type` 取值 `postgres | mysql | dameng`。响应中不包含 `password`。

表结构响应：

```json
{
  "table_name": "financial_waterbill",
  "columns": [
    { "name": "id", "type": "BIGINT", "comment": "主键ID", "nullable": false, "default": "nextval(...)", "is_primary_key": true },
    { "name": "serial_no", "type": "VARCHAR(64)", "comment": "流水号/水单号", "nullable": false, "default": null, "is_primary_key": false },
    { "name": "sales_amount", "type": "DECIMAL(18,2)", "comment": "销售额", "nullable": true, "default": null, "is_primary_key": false }
  ],
  "unique_keys": [ { "name": "uk_serial_month", "columns": ["serial_no", "month"] } ]
}
```

## 模板

| 方法 | 路径 | 说明 | 角色 |
|---|---|---|---|
| GET | `/workspaces/{ws}/templates` | 列表 | 成员 |
| POST | `/workspaces/{ws}/templates` | 新建 | 管理员 |
| GET | `/workspaces/{ws}/templates/{id}` | 详情（含映射） | 成员 |
| PUT / DELETE | `/workspaces/{ws}/templates/{id}` | 修改（版本号 +1）/ 删除 | 管理员 |
| POST | `/workspaces/{ws}/templates/{id}/clone` | 复制 | 管理员 |
| GET | `/workspaces/{ws}/templates/{id}/rules` | 下发的校验规则 | 成员 |
| POST | `/workspaces/{ws}/templates/suggest-mapping` | 根据表头路径和目标表给出自动匹配结果 | 管理员 |
| GET / POST | `/workspaces/{ws}/synonym-groups` | 同义词组列表 / 新建，请求体 `{ "terms": ["水单号", "流水号", "serial_no"] }` | 管理员 |
| PUT / DELETE | `/workspaces/{ws}/synonym-groups/{id}` | 修改组内词条 / 删除组 | 管理员 |

模板请求体：

```json
{
  "name": "财务水单通用模板",
  "description": "适用于多公司各月份复合水单导入",
  "datasource_id": 3,
  "target_schema": "public",
  "target_table": "financial_waterbill",
  "sheet": "Sheet1",
  "header_start_row": 1,
  "header_row_count": 2,
  "strategy": "UPSERT",
  "business_keys": ["serial_no", "month"],
  "scope_columns": [],
  "mapping": { "columns": [], "unpivot": null, "constants": [] },
  "rule_overrides": [ { "db_column": "company", "required": true, "enum": ["A公司", "B公司"] } ]
}
```

`mapping` 结构见[设计方案第 9 节](design.md#9-映射模型)。保存时后端会校验：映射到的列都存在于目标表；`UPSERT` 时 `business_keys` 必须对应目标表上的某个唯一索引；`REPLACE_SCOPE` 时 `scope_columns` 不能为空，且都已映射或有常量；非空且无默认值的字段都已映射或有常量；MySQL 目标表必须是 InnoDB；MySQL 上 `UPSERT` 时，目标表的其他唯一索引不能包含已映射的列。`target_schema` 省略时，后端解析为实际 schema 名后再保存。

自动匹配请求与响应：

```json
// 请求
{ "datasource_id": 3, "target_schema": "public", "target_table": "financial_waterbill",
  "paths": [["水单号"], ["1月份", "销售额"], ["1月份", "利润"]], "unpivot_leaf_mode": true }
// 响应
{ "suggestions": [
  { "excel_path": ["水单号"], "db_column": "serial_no", "score": 80, "reason": "SYNONYM" },
  { "excel_path": ["1月份", "销售额"], "db_column": "sales_amount", "score": 90, "reason": "COMMENT_EXACT" }
] }
```

## 导入

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/workspaces/{ws}/imports` | 提交导入任务（multipart） |
| GET | `/workspaces/{ws}/imports?status=&template_id=&page=&size=` | 记录列表 |
| GET | `/workspaces/{ws}/imports/{id}` | 详情与进度 |
| GET | `/workspaces/{ws}/imports/{id}/logs?after_id=` | 日志，增量拉取 |
| GET | `/workspaces/{ws}/imports/{id}/errors?page=&size=` | 逐行错误 |
| GET | `/workspaces/{ws}/imports/{id}/error-report` | 下载错误报告 xlsx |
| GET | `/workspaces/{ws}/imports/{id}/file` | 下载原始文件 |
| POST | `/workspaces/{ws}/imports/{id}/cancel` | 请求取消 |
| POST | `/workspaces/{ws}/imports/{id}/retry` | 用同样的文件和数据创建新任务。仅限 `FAILED` / `CANCELLED`；原始文件已清理时返回 `410 IMPORT_FILES_EXPIRED` |
| POST | `/workspaces/{ws}/imports/{id}/resolve` | 管理员核对 `UNKNOWN` 任务后标记，`{ "outcome": "CONFIRMED_WRITTEN" \| "CONFIRMED_NOT_WRITTEN" }`，分别转为 `SUCCEEDED` / `FAILED` |
| POST | `/workspaces/{ws}/imports/preview-scope` | `REPLACE_SCOPE` 提交前预估删除行数 |

提交请求（multipart）：

| 字段 | 内容 |
|---|---|
| `meta` | JSON：`{ "template_id": 12, "template_version": 4, "row_count": 8500 }` |
| `file` | 原始 xlsx |
| `rows` | gzip 压缩的 JSON Lines，每行一个对象，键为库字段名，附带 `_row`（Excel 原始行号） |

后端对 `rows` 的约束：解压后超过 `EI_ROWS_MAX_MB`（默认 200）立即中止并返回 `413 PAYLOAD_TOO_LARGE`；行数必须等于 `meta.row_count`；不属于模板映射列的键直接丢弃；`constants` 和默认值由 worker 填充，前端提交的同名字段被覆盖。

- `template_version` 与当前版本不一致时返回 `409 TEMPLATE_VERSION_CHANGED`，前端提示重新加载模板。
- 成功返回 `202`：`{ "id": 1024, "status": "QUEUED" }`。

详情响应：

```json
{ "id": 1024, "status": "RUNNING", "template_id": 12, "template_version": 4, "operator": "zhangsan",
  "row_count": 8500, "processed": 3000, "inserted": 0, "updated": 0, "deleted": 0, "error_count": 0,
  "created_at": "2026-11-09T18:22:00Z", "started_at": "2026-11-09T18:22:01Z", "finished_at": null }
```

`preview-scope` 请求与响应：

```json
// 请求
{ "template_id": 12, "template_version": 4,
  "scopes": [ { "company": "A公司", "month": "2026-01" }, { "company": "B公司", "month": "2026-02" } ] }
// 响应
{ "estimated_delete": 8210, "scope_count": 2 }
```

`scopes` 是前端从本次数据里取出的范围列去重组合。返回值仅用于确认页展示，worker 执行时会按实际数据重新计算。

任务状态：`QUEUED`、`RUNNING`、`COMMITTING`、`SUCCEEDED`、`FAILED`、`CANCELLED`、`UNKNOWN`。`UNKNOWN` 表示 worker 在提交目标库的过程中中断，数据可能已经写入，需要管理员核对。`FAILED` 时详情里带 `failure_code` 和 `failure_message`。`inserted` / `updated` 在 MySQL 和达梦上是估算值，响应里带 `"counts_exact": false`。

进度用轮询获取（运行中每 2 秒一次）。万行级任务一般在一分钟内结束，第一版不需要 SSE 或 WebSocket。

日志响应：

```json
[
  { "id": 1, "ts": "2026-11-09T18:22:01Z", "level": "INFO", "code": "TASK_STARTED", "params": { "rows": 8500, "strategy": "UPSERT" }, "message": "开始处理，共 8500 行，策略 UPSERT" },
  { "id": 2, "ts": "2026-11-09T18:22:02Z", "level": "INFO", "code": "BATCH_DONE", "params": { "from": 1, "to": 1000 }, "message": "第 1-1000 行已写入" },
  { "id": 3, "ts": "2026-11-09T18:22:03Z", "level": "WARNING", "code": "DEFAULT_APPLIED", "params": { "row": 452, "column": "sales_amount", "value": "0.00" }, "message": "第 452 行销售额为空，已按默认值 0.00 处理" }
]
```

## 主要错误码

| 错误码 | HTTP | 含义 |
|---|---|---|
| `UNAUTHORIZED` / `FORBIDDEN` | 401 / 403 | 未登录 / 无权限 |
| `VALIDATION_FAILED` | 422 | 请求参数不合法 |
| `DATASOURCE_UNREACHABLE` | 502 | 连接目标库失败 |
| `DATASOURCE_HOST_NOT_ALLOWED` | 422 | 主机不在白名单内 |
| `TEMPLATE_HEADER_MISMATCH` | 422 | 上传文件缺少模板要求的表头 |
| `TEMPLATE_VERSION_CHANGED` | 409 | 模板已被修改 |
| `UNIQUE_KEY_REQUIRED` | 422 | UPSERT 缺少可用的唯一索引 |
| `UPSERT_AMBIGUOUS_UNIQUE_KEY` | 422 | MySQL 目标表的其他唯一索引包含已映射的列 |
| `TABLE_ENGINE_NOT_TRANSACTIONAL` | 422 | MySQL 目标表不是 InnoDB |
| `PAYLOAD_TOO_LARGE` | 413 | 上传文件或解压后的规范行超过上限 |
| `IMPORT_FILES_EXPIRED` | 410 | 原始文件已过保留期清理，不能重新执行 |
| `IMPORT_NOT_RETRYABLE` | 409 | 任务状态不允许重新执行（如 `UNKNOWN`、`SUCCEEDED`） |
| `DUPLICATE_KEY_IN_FILE` | 任务失败原因 | 本次数据内业务键重复 |
| `ROW_VALIDATION_FAILED` | 任务失败原因 | 后端复核发现错误行 |
| `DUPLICATE_KEY` | 任务失败原因 | APPEND 遇到业务键冲突 |
| `WORKER_LOST` | 任务失败原因 | worker 在执行阶段中断，事务已回滚 |
