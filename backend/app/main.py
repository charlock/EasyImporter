"""FastAPI 入口。"""

from contextlib import asynccontextmanager

from argon2 import PasswordHasher
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api import auth, datasources, imports, templates, workspaces
from app.core import crypto
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.errors import ApiError, api_error_handler
from app.models.entities import ADMIN, User

API_PREFIX = "/api/v1"


def init_admin() -> None:
    """首次启动时创建初始管理员，密码取自 EI_ADMIN_INIT_PASSWORD，首次登录强制修改。

    表结构由 alembic 迁移创建（容器启动时先执行 alembic upgrade head），这里不建表。
    """
    with SessionLocal() as db:
        if db.scalar(select(User.id).limit(1)):
            return
        db.add(User(username="admin", role=ADMIN, must_change_password=True,
                    password_hash=PasswordHasher().hash(get_settings().admin_init_password)))
        db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    crypto.ensure_keys()
    init_admin()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="EasyImporter", version="0.1.0", lifespan=lifespan)
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_middleware(CORSMiddleware, allow_origins=[], allow_credentials=True, allow_methods=["*"],
                       allow_headers=["*"])
    for module in (auth, workspaces, datasources, templates, imports):
        app.include_router(module.router, prefix=API_PREFIX)
    app.add_api_route(f"{API_PREFIX}/health", _health, methods=["GET"])
    return app


def _health() -> dict:
    return {"status": "ok"}


def _validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={
        "code": "VALIDATION_FAILED", "message": "请求参数不合法",
        "params": {"errors": exc.errors()},
    })


app = create_app()
