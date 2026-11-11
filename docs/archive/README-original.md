这份基于 shadcn-vue 和 FastAPI 的 Excel 动态模板映射与批量入库系统的完整方案设计，满足了多数据库支持、复合表头识别、国际化（i18n）以及多主题切换等全套业务要求。

一、 前后端技术架构

1. 全景技术架构图

+-----------------------------------------------------------------------------+

| 前端呈现层 (Vue 3) |
| [Vite + TypeScript] + [shadcn-vue (Radix Vue)] + [Tailwind CSS] + [Pinia] |
| - 国际化: vue-i18n (中/英) - 主题控制: @vueuse/core (useDark) |
| - Excel解析: exceljs - 网格编辑: 自研简易虚拟网格 / exceljs 预览数据 |
+-----------------------------------------------------------------------------+
│
HTTPS / JSON
│
+-----------------------------------------------------------------------------+

| 后端服务层 (FastAPI) |
| [Python 3.11] + [FastAPI] + [SQLAlchemy 2.0] + [Alembic] + [Pydantic v2] |
| - 异步引擎: Asyncio - 任务队列: 后台后台线程异步分批处理 (BackgroundTasks) |
| - 数据库适配器: asyncpg (PG) / aiomysql (MySQL) / dmPython (达梦) |
+-----------------------------------------------------------------------------+
│
┌──────────────┼──────────────┐
▼ ▼ ▼
[ PostgreSQL ] [ MySQL ] [ 达梦数据库 ]

二、 前端功能与页面设计 (shadcn-vue)

1. 核心路由与 Workspace 设计

系统采用多工作区（Workspace）隔离模板和导入记录，用户可在顶部导航栏进行 Workspace 切换。
• /workspaces: 工作区管理列表
• /:workspaceId/templates: 模板定义与映射台
• /:workspaceId/import: 文件导入与快速编辑面板
• /:workspaceId/records: 导入历史与分批记录
• /:workspaceId/logs: 全局导入日志/系统日志查询

2. 核心页面视觉与交互设计

A. 主题与 i18n 顶栏组件 (LayoutHeader.vue)

利用 shadcn-vue 的 DropdownMenu、Button 组件和 @vueuse/core 实现：
• 语言切换：支持简体中文、English，一键改变全局 t() 渲染。
• 主题切换：支持明朗（Light）、暗黑（Dark）和系统跟随（System），通过切换 HTML 的 class="dark" 实现 Tailwind 色值无缝过渡。

B. 模板创建与字段匹配台 (TemplateConfig.vue)

• Excel 复合表头识别：上传 Excel 后，利用 exceljs 扫描前 \(N\) 行，通过 worksheet.getImages() 及 cell.isMerged 属性还原层级树。
• 基本列：["流水号"] \(\rightarrow \) 叶子节点。
• 复合列：A1:B1 合并为“1月份”，A2为“销售额”，B2为“利润” \(\rightarrow \) 构造路径 ["1月份", "销售额"] 和 ["1月份", "利润"]。
• 智能连线匹配：页面左侧展示 Excel 树状/扁平路径，右侧展示从后端接口拉取的数据库字段。
• 算法：系统自动计算字符串相似度（编辑距离），将 1月份_销售额 与数据库字段注释（如 January Sales Amount）或字段名（如 jan_sales）进行最佳比对并自动连线建立映射。
• 手动调整：用户可通过鼠标拖拽或 shadcn-vue 的 Select 下拉框覆盖自动匹配的结果。
• 插入覆盖策略：通过 RadioGroup 提供：1. APPEND：仅追加（遇主键重复报错或跳过）。2. UPSERT：存在则依据唯一索引更新，不存在则插入。3. TRUNCATE_INSERT：先清空当前工作区/月份对应数据，再全新插入。

C. 导入数据网格预览与编辑 (ImportGrid.vue)

• 基于 exceljs 将用户上传的万条数据转换为扁平 JSON。
• 结合表格及虚拟滚动技术承载万条数据，用户可以在此查阅已被识别映射的列，支持对单元格内容的双击快速修改、复制粘贴、拖拽等行为，确认无误后再触发批量入库。

三、 后端功能与接口设计 (FastAPI)

1. 核心功能设计

• 多数据库元数据探查：动态建立目标数据库连接（MySQL/PG/达梦），执行系统表查询获取字段名、数据类型和注释，统一格式化返回给前端。
• 异步分批流式处理：为了防止万条数据导入导致网络超时，后端接收到规范 JSON 后，立即创建导入记录（状态为 PROCESSING）并返回成功，随后利用 FastAPI BackgroundTasks 在后台开启分批（Chunk Size: 1000）写入。

2. API 接口定义规范 (OpenAPI/Swagger)

① 数据表结构获取接口

• URL: GET /api/v1/database/schema
• 请求参数: db_type (mysql/postgres/dm), connection_string, table_name
• 返回格式:
json
{
"table_name": "financial_waterbill",
"columns": [
{"name": "id", "type": "BIGINT", "comment": "主键ID", "is_nullable": false},
{"name": "serial_no", "type": "VARCHAR(64)", "comment": "流水号/水单号", "is_nullable": false},
{"name": "sales_amount", "type": "DECIMAL(18,2)", "comment": "销售额", "is_nullable": true},
{"name": "profit_margin", "type": "DECIMAL(18,2)", "comment": "利润", "is_nullable": true}
]
}
请谨慎使用此类代码。

② 模板保存与加载接口

• 保存: POST /api/v1/templates
• 加载: GET /api/v1/templates/{template_id}
• 请求体 (Pydantic):
json
{
"name": "财务水单通用模板",
"description": "适用于多公司各月份复合水单导入",
"workspace_id": "ws_001",
"strategy": "UPSERT",
"mappings": [
{"excel_path": ["1月份", "销售额"], "db_column": "sales_amount"},
{"excel_path": ["1月份", "利润"], "db_column": "profit_margin"},
{"excel_path": ["水单号"], "db_column": "serial_no"}
]
}
请谨慎使用此类代码。

③ 导入记录与流式日志接口

• 创建导入任务: POST /api/v1/imports/task （支持分批任务派发）
• 分页查询记录: GET /api/v1/imports/records?workspace_id=ws_001&page=1&size=10
• 查看实时日志: GET /api/v1/imports/tasks/{task_id}/logs
• 日志返回格式:
json
[
{"timestamp": "2026-11-09T18:22:00Z", "level": "INFO", "message": "解析Excel成功，共 8500 行数据"},
{"timestamp": "2026-11-09T18:22:01Z", "level": "INFO", "message": "第1批次(1-1000行)开始处理，策略：UPSERT"},
{"timestamp": "2026-11-09T18:22:03Z", "level": "WARNING", "message": "第 452 行金额字段为空，已按默认值0.00处理"}
]
请谨慎使用此类代码。

四、 部署脚本设计

采用 Docker Compose 方案实现一键微服务化单机/集群部署。

1. 后端 Dockerfile

dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安装达梦等数据库所需的依赖客户端底层库（如需）

RUN apt-get update && apt-get install -y --no-install-recommends libaio1 curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
请谨慎使用此类代码。

2. 全栈部署 docker-compose.yml

yaml
version: '3.8'

services:

# 后端 FastAPI 服务

backend:
build:
context: ./backend
dockerfile: Dockerfile
environment: - DATABASE_URL=postgresql+asyncpg://postgres:secret@db:5432/excel_importer - APP_ENV=production
ports: - "8000:8000"
volumes: - ./backend/logs:/app/logs
depends_on: - db
restart: always

# 前端 Nginx 服务

frontend:
build:
context: ./frontend
dockerfile: Dockerfile # 采用标准的 npm run build 后将 dist 挂载至 nginx:alpine
ports: - "80:80"
depends_on: - backend
restart: always

# 系统元数据库（以 PostgreSQL 为例）

db:
image: postgres:15-alpine
environment: - POSTGRES_USER=postgres - POSTGRES_PASSWORD=secret - POSTGRES_DB=excel_importer
ports: - "5432:5432"
volumes: - pgdata:/var/lib/postgresql/data
restart: always

volumes:
pgdata:
