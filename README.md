# EasyImporter

把带多级合并表头的 Excel 按模板导入 PostgreSQL、MySQL 或达梦 DM8。

管理员配置一次模板，之后业务人员自己上传文件、在网格里修正数据、提交导入，不需要再用 Navicat / DBeaver 手工整理表格和对字段。

## 功能

- **复合表头识别**：读取合并单元格，还原表头层级，例如 `["1月份", "销售额"]`。
- **两种映射**：宽表直映（一个表头路径对应一个库字段），长表拆行（一行 Excel 按月份等维度拆成多行）。
- **自动匹配字段**：按历史映射、字段注释、字段名、同义词表打分，管理员确认或调整。
- **先校验再写入**：后端根据目标表结构生成校验规则，前端实时标出错误，后端提交时再复核一遍。
- **三种写入策略**：`APPEND` 只插入，`UPSERT` 按业务键更新或插入，`REPLACE_SCOPE` 按范围（如月份）替换。每个任务在一个事务里执行，失败则全部回滚。
- **可追溯**：留存原始文件、任务日志、逐行错误，可以下载错误报告。
- **工作区隔离与角色**：管理员管理数据源和模板，导入员只能在所属工作区导入，看不到数据库连接信息。
- 中文 / English，明 / 暗 / 跟随系统主题。

## 架构

```
浏览器 (Vue 3, ExcelJS 在 Web Worker 中解析)
        │
Nginx ──┤
        ▼
API (FastAPI) ── 元数据库 (默认 PostgreSQL，可换达梦 / MySQL；用达梦或 MySQL 时迁移矩阵要在 M1 验证) ── Worker (写入目标库)
                                                                    │
                                              PostgreSQL / MySQL / 达梦 DM8
```

| 层 | 技术 |
|---|---|
| 前端 | Vue 3、Vite、TypeScript、Pinia、vue-router、vue-i18n、ExcelJS、@tanstack/vue-virtual；样式为手写 CSS 变量（`src/styles/base.css`），未引入 UI 组件库 |
| 后端 | Python 3.11、FastAPI、Pydantic v2、SQLAlchemy 2.0（同步）、Alembic |
| 驱动 | psycopg 3、PyMySQL、dmPython + dmSQLAlchemy |
| 任务 | 元数据库任务表 + 独立 worker 进程 |
| 部署 | Docker Compose，amd64 / arm64 双架构镜像，提供离线包 |

## 文档

| 文档 | 内容 |
|---|---|
| [设计方案](docs/design.md) | 问题、前提、方案对比、表头识别、映射、自动匹配、校验、写入策略、安全、待定问题、里程碑 |
| [架构设计](docs/architecture.md) | 组件、选型理由、前后端目录、目标库适配层、元数据库表、任务执行 |
| [接口设计](docs/api.md) | REST 接口、请求与响应示例、错误码 |
| [部署方案](docs/deployment.md) | 部署单元、三种环境、达梦驱动、配置项、compose、Dockerfile、离线包、运维 |
| [原始方案](docs/archive/README-original.md) | 本项目最初的方案草稿，仅供对照 |

## 状态

前后端主体功能已实现：登录与改密、工作区与成员、数据源、模板（映射、常量、拆行、校验规则、同义词）、浏览器端解析与校验、网格编辑、三种写入策略、任务轮询、取消、重试与人工核对。

尚未在真实环境验证的部分：PostgreSQL / MySQL 元数据库的迁移锁、达梦 `MERGE` 写入、worker 收到信号后的停机流程、5 万行网格的实际性能。详见[设计方案 · 里程碑](docs/design.md#17-里程碑)。

## 本地开发

```bash
export $(grep -v "^#" .env | xargs)   # EI_DATABASE_URL、EI_SECRET_KEY 等，见 .env.example
uv venv .venv && uv pip install -r backend/requirements.txt --python .venv/bin/python
cd backend && ../.venv/bin/alembic upgrade head && ../.venv/bin/uvicorn app.main:app --reload
../.venv/bin/python -m app.worker   # 另开终端，在 backend/ 下运行
```

```bash
cd frontend && npm install && npm run dev   # http://localhost:5173，/api 代理到 8000
```

测试：后端 `cd backend && ../.venv/bin/python -m pytest -q`；前端 `cd frontend && npm test && npm run build`。前后端规则引擎共用 `fixtures/rules/*.json`。

## 快速开始

```bash
cp .env.example .env   # 填写 EI_SECRET_KEY、POSTGRES_PASSWORD、EI_ADMIN_INIT_PASSWORD
docker compose up -d
```

浏览器打开 `http://<服务器>/`，用 `admin` 和初始密码登录。离线和信创环境的安装方式见[部署方案](docs/deployment.md)。
