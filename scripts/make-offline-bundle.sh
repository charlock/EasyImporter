#!/bin/bash
# 生成离线安装包：easyimporter-<version>-<arch>/
# 用法：scripts/make-offline-bundle.sh amd64 1.0.0
set -euo pipefail

ARCH=${1:?arch required, amd64 or arm64}
VERSION=${2:-latest}
REGISTRY=${EI_REGISTRY:-easyimporter}
OUT="easyimporter-${VERSION}-${ARCH}"

mkdir -p "$OUT"
for image in easyimporter-web easyimporter-backend; do
  docker pull --platform "linux/${ARCH}" "${REGISTRY}/${image}:${VERSION}"
done
docker pull --platform "linux/${ARCH}" postgres:16-alpine
docker save \
  "${REGISTRY}/easyimporter-web:${VERSION}" \
  "${REGISTRY}/easyimporter-backend:${VERSION}" \
  postgres:16-alpine \
  -o "${OUT}/images.tar"
cp docker-compose.yml .env.example "${OUT}/"
cp scripts/install.sh "${OUT}/"
echo "离线包已生成：${OUT}"
