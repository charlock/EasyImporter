"""worker 入口：循环领取任务并执行。

用法：python -m app.worker
心跳在独立线程里更新，避免达梦上单条慢语句被误判为进程死亡。
收到 SIGTERM/SIGINT 后不再领取新任务，等当前任务执行完再退出
（docker-compose 的 stop_grace_period 给了 5 分钟）。
"""

import logging
import signal
import socket
import threading
import time
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core import crypto
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models.entities import RUNNING, ImportTask
from app.services.imports import claim, cleanup_uploads, execute, reap

WORKER_ID = socket.gethostname()
CLEANUP_INTERVAL_SECONDS = 86400

log = logging.getLogger(__name__)
_shutdown = threading.Event()


def _request_shutdown(signum: int, _frame: object) -> None:
    log.info("收到信号 %s，当前任务完成后退出", signal.Signals(signum).name)
    _shutdown.set()


def _heartbeat(import_id: int, stop: threading.Event) -> None:
    while not stop.wait(get_settings().heartbeat_seconds):
        with SessionLocal() as db:
            task = db.get(ImportTask, import_id)
            if task is None or task.status != RUNNING:
                return
            task.heartbeat_at = datetime.now(UTC)
            db.commit()


def run_once(db: Session) -> bool:
    """领取并执行一条任务。返回是否领到任务。"""
    reap(db)
    task = claim(db, WORKER_ID)
    if task is None:
        return False
    stop = threading.Event()
    beater = threading.Thread(target=_heartbeat, args=(task.id, stop), daemon=True)
    beater.start()
    try:
        execute(db, task)
    finally:
        stop.set()
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    crypto.ensure_keys()
    signal.signal(signal.SIGTERM, _request_shutdown)
    signal.signal(signal.SIGINT, _request_shutdown)
    last_cleanup = 0.0
    while not _shutdown.is_set():
        with SessionLocal() as db:
            worked = run_once(db)
        now = time.time()
        if now - last_cleanup > CLEANUP_INTERVAL_SECONDS:
            cleanup_uploads()
            last_cleanup = now
        if not worked:
            # 用 Event.wait 代替 sleep，空闲时收到信号能立刻退出。
            _shutdown.wait(get_settings().worker_poll_seconds)
    log.info("worker 已退出")


if __name__ == "__main__":
    main()
