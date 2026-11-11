# 部署方案

> 上级文档：[设计方案](design.md) · [架构设计](architecture.md)

## 1. 部署单元

| 服务 | 镜像 | 说明 |
|---|---|---|
| `web` | `easyimporter-web` | Nginx：前端静态文件 + `/api` 反向代理 |
| `api` | `easyimporter-backend` | `uvicorn app.main:app` |
| `worker` | `easyimporter-backend` | 同一镜像，启动命令为 `python -m app.worker` |
| `db` | `postgres:16-alpine` | 元数据库，可替换为外部的达梦或 MySQL |

卷：`pgdata`（元数据库）、`uploads`（原始文件和规范行，api 和 worker 共用）。

## 2. 支持的环境

| 环境 | 做法 |
|---|---|
| x86 Linux，可联网 | 从镜像仓库拉取，`docker compose up -d` |
| x86 Linux，内网离线 | 用离线包：`docker load` 导入镜像后启动 |
| 信创（麒麟 / 统信 + 鲲鹏 / 飞腾 ARM） | 用 arm64 离线包；元数据库可以指向达梦 |

镜像用 `docker buildx` 一次构建 `linux/amd64` 和 `linux/arm64` 两个架构，基础镜像 `python:3.11-slim-bookworm` 和 `nginx:alpine` 都提供这两个架构。目标机器没有 Docker 时的 systemd 安装方式留作后续工作，第一版不提供。

## 3. 达梦驱动

官方 [dmPython](https://pypi.org/project/dmpython/) 是 C 扩展，运行时需要达梦客户端的 `libdmdpi.so` 等动态库。这些库不在 PyPI 上，每个架构都要从达梦安装包里单独取出。做法如下：

1. 在 `deploy/drivers/dm/{amd64,arm64}/` 放对应架构的达梦客户端完整目录（`bin/` 动态库和 `include/` 头文件都要，dmPython 从源码编译时需要头文件）。这些文件不提交到代码库，构建前由脚本从内部制品库拉取。
2. Dockerfile 按 `TARGETARCH` 复制对应目录，设置 `DM_HOME` 和 `LD_LIBRARY_PATH`，再安装 dmPython 和 [dmSQLAlchemy](https://pypi.org/project/dmSQLAlchemy/)。dmPython 从源码编译，构建阶段需要 `gcc`，所以默认采用多阶段构建（见第 6 节）。
3. 如果 ARM 上实测有问题，备选第三方纯 Python 驱动 [dmPython-pure](https://pypi.org/project/dmPython-pure/)。它不是达梦官方维护，M0 要先确认它在 PyPI 上确实可安装、且能连上 DM8，再决定是否采用。

## 4. 配置项

所有配置通过环境变量注入，放在 `.env` 里，`.env` 不提交到代码库，仓库只提供 `.env.example`。

| 变量 | 必填 | 说明 |
|---|---|---|
| `EI_DATABASE_URL` | 是 | 元数据库连接，如 `postgresql+psycopg://ei:***@db:5432/easyimporter` 或 `dm+dmPython://…` |
| `EI_SECRET_KEY` | 是 | 32 字节随机值（base64），主密钥。启动时用 HKDF 派生出加密子密钥（加密数据源密码）和签名子密钥，互不复用。丢失后已登记的数据源密码无法解密，需要备份 |
| `EI_ADMIN_INIT_PASSWORD` | 首次启动 | 初始管理员 `admin` 的密码，首次登录后强制修改 |
| `EI_UPLOAD_DIR` | 否 | 默认 `/data/uploads` |
| `EI_UPLOAD_MAX_MB` | 否 | 单个上传文件上限，默认 20 |
| `EI_ROWS_MAX_MB` | 否 | 规范行解压后的上限，默认 200，防止 gzip 炸弹 |
| `EI_UPLOAD_RETENTION_DAYS` | 否 | 原始文件保留天数，默认 90 |
| `EI_DATASOURCE_ALLOWED_HOSTS` | 否 | 数据源主机白名单，逗号分隔，支持 CIDR |
| `EI_COOKIE_SECURE` | 否 | 默认 `false`。compose 默认只暴露 HTTP 的 80 端口，设为 `true` 会导致登录失败；启用 HTTPS（见第 5 节）后改为 `true` |
| `POSTGRES_PASSWORD` | 用内置 db 时 | 内置元数据库密码 |

## 5. docker-compose.yml

```yaml
services:
  web:
    image: ${EI_REGISTRY:-easyimporter}/easyimporter-web:${EI_VERSION:-latest}
    ports: ["80:80"]
    depends_on: [api]
    restart: unless-stopped

  api:
    image: ${EI_REGISTRY:-easyimporter}/easyimporter-backend:${EI_VERSION:-latest}
    command: ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "172.16.0.0/12"]
    env_file: .env
    volumes: ["uploads:/data/uploads"]
    depends_on:
      db: { condition: service_healthy }
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8000/api/v1/health"]
      interval: 15s
    restart: unless-stopped

  worker:
    image: ${EI_REGISTRY:-easyimporter}/easyimporter-backend:${EI_VERSION:-latest}
    command: ["python", "-m", "app.worker"]
    env_file: .env
    volumes: ["uploads:/data/uploads"]
    stop_grace_period: 5m
    depends_on:
      db: { condition: service_healthy }
    restart: unless-stopped

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: ei
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in .env}
      POSTGRES_DB: easyimporter
    volumes: ["pgdata:/var/lib/postgresql/data"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ei -d easyimporter"]
      interval: 10s
    restart: unless-stopped

volumes:
  pgdata:
  uploads:
```

相对原方案的改动：
- 密码不再写死在 compose 文件里，改由 `.env` 提供。
- 元数据库不再对宿主机暴露 5432 端口。
- `depends_on` 改为等待数据库健康检查通过。
- 新增 `worker` 服务和 `uploads` 卷。
- 数据库迁移由 api 容器启动时执行 `alembic upgrade head`（用数据库锁防止多实例同时迁移）。
- 使用外部元数据库（如达梦）时，删除 `db` 服务，把 `EI_DATABASE_URL` 指向外部地址。
- `--forwarded-allow-ips` 只信任 Docker 默认网段，避免客户端伪造 `X-Forwarded-For`。自定义了 compose 网络地址段时要同步修改。
- 默认只有 HTTP。生产环境在 nginx 里加 TLS（证书放 `deploy/certs/`，由 nginx 挂载），然后把 `EI_COOKIE_SECURE` 设为 `true`。

## 6. 后端 Dockerfile

```dockerfile
FROM python:3.11-slim-bookworm AS build
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*
COPY deploy/drivers/dm/${TARGETARCH}/ /opt/dmdbms/
ENV DM_HOME=/opt/dmdbms LD_LIBRARY_PATH=/opt/dmdbms/bin
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --prefix=/opt/py -r requirements.txt

FROM python:3.11-slim-bookworm
ARG TARGETARCH
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl libaio1 \
    && rm -rf /var/lib/apt/lists/*

# 运行阶段只保留达梦动态库和已编译的 Python 依赖（构建前由 scripts/fetch-dm-drivers.sh 准备）
COPY --from=build /opt/dmdbms/bin/ /opt/dmdbms/bin/
COPY --from=build /opt/py /usr/local
ENV DM_HOME=/opt/dmdbms LD_LIBRARY_PATH=/opt/dmdbms/bin

COPY backend/ .
RUN useradd -r -u 10001 app && mkdir -p /data/uploads && chown app /data/uploads
USER app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

相对原方案：以非 root 用户运行；多阶段构建，`gcc` 只留在构建阶段，运行镜像里只有达梦动态库和编译产物。

前端 Dockerfile 用两阶段：`node:20-alpine` 执行 `npm ci && npm run build`，产物复制到 `nginx:alpine`。nginx 配置放在镜像的 `/etc/nginx/templates/default.conf.template`，由官方镜像的 envsubst 机制在启动时渲染，因为静态配置读不到环境变量：

```nginx
client_max_body_size ${EI_BODY_MAX_MB}m;   # 需同时容纳原始文件和 gzip 后的规范行，默认取 EI_UPLOAD_MAX_MB 的 1.2 倍
```

同时配置 SPA 回退到 `index.html`，并把 `/api` 代理到 `api:8000`。

## 7. 构建与离线包

```bash
# 双架构构建并推送
docker buildx build --platform linux/amd64,linux/arm64 -t $REG/easyimporter-backend:$VER -f deploy/backend.Dockerfile --push .
docker buildx build --platform linux/amd64,linux/arm64 -t $REG/easyimporter-web:$VER -f deploy/web.Dockerfile --push .
```

离线包由 `scripts/make-offline-bundle.sh <arch>` 生成。`docker save` 只保存本机已有的平台，所以脚本要先 `docker pull --platform linux/<arch>` 每个镜像，再 `docker save`。内容为：

```
easyimporter-<version>-<arch>/
  images.tar            docker save 导出的 web、backend、postgres 镜像（目标架构）
  docker-compose.yml
  .env.example
  install.sh            docker load + 首次生成 EI_SECRET_KEY + docker compose up -d
  README.md             安装、升级、备份说明
```

`install.sh` 只在 `.env` 里没有 `EI_SECRET_KEY` 时才生成，升级时沿用已有的，否则所有已登记的数据源密码都会解不开。

## 8. 运维

- **备份**：元数据库每日备份（`pg_dump` 或达梦 `dexp`）；`EI_SECRET_KEY` 单独妥善保存；`uploads` 卷按保留期备份。
- **升级**：替换镜像版本后 `docker compose up -d`，api 启动时自动迁移。worker 收到停止信号后会等当前任务结束再退出；compose 里 `stop_grace_period: 5m`，超时才被 SIGKILL。
- **日志**：所有服务输出到 stdout，用 `docker compose logs` 查看，或接入公司的日志平台。
- **清理**：worker 每天清理超过保留期的上传文件。

## 9. CI

第一版建议在公司现有的 CI 平台上配置：
1. 前端 `lint + vitest`，后端 `ruff + pytest`。
2. 集成测试：用 docker 启动 PostgreSQL、MySQL 和达梦（达梦官方提供 Docker 镜像，需确认授权）三个目标库，覆盖三种策略。
3. 打 tag 时执行双架构构建、推送镜像，并生成两个架构的离线包作为制品。
