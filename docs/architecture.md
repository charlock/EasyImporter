# 架构设计

> 上级文档：[设计方案](design.md)

## 1. 组件

```
浏览器 (Vue 3 + shadcn-vue)
  ├─ Web Worker：ExcelJS 解析、表头识别、规范化、规则校验
  └─ 网格：预览与编辑
        │ HTTPS（上传用 multipart，行数据 gzip）
        ▼
Nginx（静态资源 + 反向代理）
        ▼
API 服务 (FastAPI)              Worker 进程（同一镜像，不同启动命令）
  - 认证与权限                    - 领取任务、复核、写入目标库
  - 数据源 / 模板 / 任务管理       - 写日志与进度
  - 目标表元数据探查               - 心跳、取消
        │                                │
        └──── 元数据库（默认 PG，可选达梦 / MySQL）+ 文件存储（本地卷）
                                         │
                         目标库：PostgreSQL / MySQL / 达梦 DM8
```

## 2. 技术选型

| 领域 | 选型 | 相对原方案的变化与原因 |
|---|---|---|
| 前端框架 | Vue 3 + Vite + TypeScript + Pinia + vue-router | 不变 |
| UI | shadcn-vue + Tailwind CSS | 不变 |
| 主题 | `@vueuse/core` 的 `useColorMode` | `useDark` 只有明 / 暗两态，`useColorMode` 直接支持 light / dark / auto |
| 国际化 | vue-i18n | 后端错误改为返回 `code + params`，由前端翻译 |
| Excel 解析 | ExcelJS，在 Web Worker 里运行，按需加载 | 避免 5 万行解析时页面卡死；ExcelJS 体积约 1 MB，不进首屏 |
| 数据网格 | 待技术验证（见设计方案待定问题 6） | shadcn-vue 不含数据网格 |
| 后端 | Python 3.11 + FastAPI + Pydantic v2 + Alembic | 不变 |
| 数据访问 | SQLAlchemy 2.0 同步引擎；FastAPI 路由用普通 `def`，在线程池里执行 | 原方案的“全异步”和达梦同步驱动冲突。1 到 5 人并发下线程池足够，元数据库换成达梦也不受影响 |
| 驱动 | psycopg 3、PyMySQL、dmPython + dmSQLAlchemy | 三种库都用同步驱动，写法一致 |
| 任务队列 | 元数据库里的任务表 + 独立 worker 进程 | 替代 `BackgroundTasks`：重启不丢任务，可取消，可看进度 |

## 3. 前端

### 路由

| 路径 | 页面 | 角色 |
|---|---|---|
| `/login` | 登录 | 全部 |
| `/workspaces` | 工作区列表 | 全部（导入员只看到自己的） |
| `/admin/datasources` | 数据源管理 | 管理员 |
| `/admin/users` | 用户管理 | 管理员 |
| `/w/:workspaceId/templates` | 模板列表与模板编辑（映射台） | 管理员编辑，导入员只读 |
| `/w/:workspaceId/import` | 选模板、上传、网格校验与编辑、提交 | 全部 |
| `/w/:workspaceId/imports` | 导入记录列表 | 全部 |
| `/w/:workspaceId/imports/:importId` | 任务详情：进度、日志、错误明细 | 全部 |

原方案的 `/:workspaceId/records` 和 `/:workspaceId/logs` 合并为“导入记录 + 任务详情”。系统日志不面向业务用户展示，运维通过容器日志查看。

### 目录结构

```
frontend/src/
  api/           接口封装（按资源分文件）
  components/    通用组件；ui/ 下是 shadcn-vue 生成的组件
  features/
    header/      表头识别（纯函数，可单测）
    mapping/     映射、拆行、自动匹配（纯函数，可单测）
    rules/       规则执行器（与后端共用 fixtures）
    grid/        网格封装
  workers/       parse.worker.ts：解析 + 规范化 + 校验
  layouts/       LayoutHeader（工作区切换、语言、主题、用户菜单）
  locales/       zh-CN.json、en-US.json
  pages/         与路由一一对应
  stores/        Pinia：auth、workspace、importSession
```

`features/` 下的模块都是不依赖 Vue 的纯 TypeScript，既能在 Web Worker 里运行，也方便写单元测试。

### 主题与语言

- `useColorMode` 管理 `light / dark / auto`，结果写在 `<html class>` 上，Tailwind 用 `darkMode: 'class'`，选择保存在 localStorage。
- vue-i18n 管理 `zh-CN / en-US`，默认跟随浏览器语言，选择保存在 localStorage。后端错误码在 `locales/*.json` 的 `errors` 下翻译。

## 4. 后端

### 目录结构

```
backend/app/
  main.py            FastAPI 入口
  worker.py          worker 入口：循环领取任务
  core/              配置、加密、认证、错误码
  api/               路由（按资源分文件）
  models/            元数据库 ORM 模型
  schemas/           Pydantic 请求与响应模型
  services/          业务逻辑：模板、导入、规则生成
  connectors/        目标库适配：base.py + postgres.py / mysql.py / dameng.py
  rules/             规则复核（Pydantic 实现）
backend/migrations/  Alembic
fixtures/rules/      前后端共享的规则测试样例
```

### 目标库适配层

每种库实现同一个接口，业务代码不出现方言判断：

```python
class Connector(Protocol):
    def list_tables(self, schema: str | None) -> list[TableInfo]: ...
    def get_table_schema(self, schema: str | None, table: str) -> TableSchema: ...   # 字段、类型、注释、可空、默认值、主键、唯一索引、表引擎（MySQL）
    def test_connection(self) -> None: ...
    def write(self, conn, schema: str | None, table: str, plan: WritePlan, rows: Iterable[dict]) -> WriteResult: ...
```

| 能力 | PostgreSQL | MySQL | 达梦 DM8 |
|---|---|---|---|
| 字段与注释 | `information_schema.columns` + `pg_description` | `information_schema.columns.COLUMN_COMMENT` | `ALL_TAB_COLUMNS` + `ALL_COL_COMMENTS` |
| 表引擎 | 不适用 | `information_schema.tables.ENGINE`，必须是 InnoDB | 不适用 |
| 唯一索引 | `pg_index` | `information_schema.statistics` | `ALL_INDEXES` + `ALL_IND_COLUMNS` |
| UPSERT | `ON CONFLICT … DO UPDATE` | `ON DUPLICATE KEY UPDATE` | `MERGE INTO … USING` |

- 连接池按数据源缓存，数据源修改后重建。
- `schema` 为空时使用连接的默认 schema（PostgreSQL 为 `search_path`，MySQL 为连接的库，达梦为登录用户同名模式）。模板保存的是解析后的实际 schema 名，之后不会因为默认值变化而写错表。

## 5. 元数据库

| 表 | 主要字段 |
|---|---|
| `users` | id, username, password_hash, role(`admin`/`importer`), is_active, must_change_password, failed_login_count, locked_until |
| `sessions` | id(随机 256 位，存哈希), user_id, csrf_token, created_at, last_seen_at, expires_at |
| `workspaces` | id, name, description |
| `workspace_members` | workspace_id, user_id |
| `datasources` | id, name, db_type, host, port, database, username, password_enc, options(json) |
| `templates` | id, workspace_id, name, description, current_version, is_archived, created_at, updated_at |
| `template_versions` | template_id, version, datasource_id, target_schema, target_table, sheet, header_start_row, header_row_count, strategy, business_keys(json), scope_columns(json), mapping(json), rule_overrides(json), created_by, created_at；主键 (template_id, version) |
| `synonym_groups` | id, workspace_id |
| `synonym_terms` | group_id, term；同一工作区内 term 唯一 |
| `imports` | id, workspace_id, template_id, template_version, datasource_id, target_schema, target_table, strategy, operator_id, status, file_path, rows_path, report_path, row_count, processed, inserted, updated, deleted, error_count, failure_code, failure_message, worker_id, created_at, started_at, finished_at, heartbeat_at, cancel_requested, retry_of |
| `table_locks` | datasource_id, target_schema, target_table, import_id, locked_at；主键 (datasource_id, target_schema, target_table) |
| `import_logs` | id, import_id, ts, level, code, params(json), message |
| `import_errors` | id, import_id, row_no, column, code, params(json) |

- 模板每次保存都在 `template_versions` 新增一行，`templates.current_version` 指向最新版本，旧版本不改不删。导入任务记录用的版本号，模板修改后历史任务仍能复现。
- `imports` 冗余保存数据源、目标表和策略的快照，便于按表查询，也避免历史记录随模板改动而变化。`inserted / updated` 在 MySQL 和达梦上为估算值，见设计方案第 12 节。
- `import_errors` 只保存前 1000 条，`error_count` 记录总数，完整错误在错误报告文件里。

## 6. 任务执行

状态：`QUEUED → RUNNING → COMMITTING → SUCCEEDED`；任何阶段可进入 `FAILED`；`QUEUED` 和 `RUNNING` 可进入 `CANCELLED`；`COMMITTING` 中断进入 `UNKNOWN`。

1. **提交**：API 收到提交后，把原始文件和规范行（gzip JSON Lines）写入 `uploads/{import_id}/`，插入 `imports`（`QUEUED`），返回 `202`。
2. **领取**：worker 每 2 秒在元数据库的一个事务里执行：
   1. `SELECT … FROM imports WHERE status='QUEUED' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1`；
   2. `INSERT INTO table_locks (datasource_id, target_schema, target_table, import_id)`。主键冲突说明这张表正在被写：回滚本事务，把这条任务记入本轮的跳过名单，继续尝试下一条 `QUEUED`，直到领到一个任务或本轮没有可领的；
   3. 把任务改为 `RUNNING`，写入 `worker_id`、`started_at`，提交。

   同表串行由 `table_locks` 的主键保证。仅靠 `SKIP LOCKED` 不够：两个 worker 可能各自锁住同一张表的两个不同任务。
3. **执行**：在目标库开一个事务，按批写入（每批 1000 行，便于检查取消和记录进度）。每批写完后更新 `processed`，并检查 `cancel_requested`，若为真则回滚目标库事务，置 `CANCELLED`。
4. **心跳**：执行期间，另起一个线程、用独立的元数据库连接，每 10 秒更新 `heartbeat_at`。心跳不能和写入放在同一线程，因为达梦上单条批量语句可能执行超过 2 分钟，会被误判为进程已死。
5. **提交两个库**：
   1. 元数据库：把状态改为 `COMMITTING`，提交；
   2. 目标库：提交事务；
   3. 元数据库：改为 `SUCCEEDED`，写入统计，删除 `table_locks` 对应行，提交。

   失败时（任何一步之前）：回滚目标库事务，置 `FAILED`，删除锁。
6. **回收**：每个 worker 在每轮轮询时（不只是启动时）检查心跳超过 2 分钟的任务：
   - `RUNNING` → `FAILED`（`WORKER_LOST`）。进程崩溃时目标库连接断开，数据库自动回滚，目标表不会留下半批数据；
   - `COMMITTING` → `UNKNOWN`。目标库可能已经提交，也可能没有，系统无法判断；
   - 两种情况都删除对应的 `table_locks`。
7. **重新执行**：`FAILED` 和 `CANCELLED` 的任务可以重新执行，生成一个新任务（`retry_of` 指向原任务），原始文件和规范行沿用原任务的。`UNKNOWN` 的任务**不允许**重新执行：界面提示管理员到目标库核对数据，然后手动标记为“已确认成功”或“已确认未写入”，标记为后者后才允许重新执行。原始文件清理后（默认 90 天）不能再重新执行。
8. **规模**：默认运行 1 个 worker 进程；可以多开，`table_locks` 保证同表串行。

## 7. 可扩展性

当单文件超过十万行时，演进路线是：解析搬到后端（python-calamine 流式读取），规范行写入暂存表，网格改为分页编辑，写入改为分批提交加暂存表切换。规则、模板和任务模型不需要改。
