FROM python:3.11-slim-bookworm AS build
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*
# 达梦客户端库由 scripts/fetch-dm-drivers.py 在构建前准备。
# 不接达梦时，deploy/drivers/dm/<arch>/ 下只需保留空目录占位（bin/.gitkeep），
# 否则 COPY 源不存在构建会直接失败；占位文件不影响其他数据库。
COPY deploy/drivers/dm/${TARGETARCH}/ /opt/dmdbms/
ENV DM_HOME=/opt/dmdbms LD_LIBRARY_PATH=/opt/dmdbms/bin
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --prefix=/opt/py -r requirements.txt

FROM python:3.11-slim-bookworm
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl libaio1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /opt/dmdbms/bin/ /opt/dmdbms/bin/
COPY --from=build /opt/py /usr/local
ENV DM_HOME=/opt/dmdbms LD_LIBRARY_PATH=/opt/dmdbms/bin

COPY backend/ .
RUN useradd -r -u 10001 app && mkdir -p /data/uploads && chown app /data/uploads
USER app

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
