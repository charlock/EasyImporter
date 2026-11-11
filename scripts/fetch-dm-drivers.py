#!/usr/bin/env python3
"""从内部制品库拉取达梦客户端库到 deploy/drivers/dm/<arch>/。

这些动态库和头文件有授权限制，不进代码库。构建镜像前执行：

    python scripts/fetch-dm-drivers.py --arch amd64 --source <制品库目录>

没有制品库时，M0 阶段可以跳过，后端在不连接达梦的情况下正常运行。
"""

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arch", choices=["amd64", "arm64"], required=True)
    parser.add_argument("--source", type=Path, required=True, help="达梦客户端完整目录")
    args = parser.parse_args()
    destination = ROOT / "deploy" / "drivers" / "dm" / args.arch
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(args.source, destination)
    print(f"已复制达梦驱动到 {destination}")


if __name__ == "__main__":
    main()
