#!/bin/bash
# 离线环境安装：导入镜像、首次生成主密钥、启动。
# 升级时沿用已有的 EI_SECRET_KEY，否则已登记的数据源密码无法解密。
set -euo pipefail

docker load -i images.tar

if [ ! -f .env ]; then
  cp .env.example .env
fi

if ! grep -q '^EI_SECRET_KEY=.\+' .env; then
  KEY=$(python3 -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())" 2>/dev/null \
    || openssl rand -base64 32)
  if grep -q '^EI_SECRET_KEY=' .env; then
    sed -i.bak "s|^EI_SECRET_KEY=.*|EI_SECRET_KEY=${KEY}|" .env
  else
    echo "EI_SECRET_KEY=${KEY}" >> .env
  fi
  echo "已生成 EI_SECRET_KEY，请立即备份 .env，丢失后已登记的数据源密码无法解密。"
fi

docker compose up -d
echo "已启动。浏览器打开 http://<服务器>/ ，用 admin 和 EI_ADMIN_INIT_PASSWORD 登录。"
