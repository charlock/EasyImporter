"""会话认证。

会话 id 是 256 位随机数，Cookie 只带明文 id，数据库存它的 SHA-256。
写操作校验 X-CSRF-Token。会话 8 小时无操作过期。
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Cookie, Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.config import get_settings
from app.core.db import get_session
from app.core.errors import ApiError
from app.models.entities import ADMIN, Session, User, WorkspaceMember

COOKIE_NAME = "ei_session"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_session(db: DbSession, user: User) -> tuple[Session, str]:
    token = secrets.token_hex(32)
    record = Session(
        token_hash=hash_token(token),
        user_id=user.id,
        csrf_token=secrets.token_hex(24),
        expires_at=datetime.now(UTC) + timedelta(hours=get_settings().session_idle_hours),
    )
    db.add(record)
    db.flush()
    return record, token


def _load(db: DbSession, token: str | None) -> tuple[Session, User]:
    if not token:
        raise ApiError("UNAUTHORIZED")
    record = db.scalar(select(Session).where(Session.token_hash == hash_token(token)))
    now = datetime.now(UTC)
    if record is None or record.expires_at.replace(tzinfo=UTC) <= now:
        raise ApiError("UNAUTHORIZED")
    user = db.get(User, record.user_id)
    if user is None or not user.is_active:
        raise ApiError("USER_DISABLED")
    record.last_seen_at = now
    record.expires_at = now + timedelta(hours=get_settings().session_idle_hours)
    return record, user


def current_user(
    db: DbSession = Depends(get_session),
    ei_session: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> User:
    _, user = _load(db, ei_session)
    db.commit()
    return user


def current_session(
    db: DbSession = Depends(get_session),
    ei_session: str | None = Cookie(default=None, alias=COOKIE_NAME),
    x_csrf_token: str | None = Header(default=None),
) -> User:
    record, user = _load(db, ei_session)
    if not x_csrf_token or not secrets.compare_digest(x_csrf_token, record.csrf_token):
        raise ApiError("CSRF_INVALID")
    db.commit()
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != ADMIN:
        raise ApiError("FORBIDDEN")
    return user


def require_admin_write(user: User = Depends(current_session)) -> User:
    if user.role != ADMIN:
        raise ApiError("FORBIDDEN")
    return user


def member_workspace_ids(db: DbSession, user: User) -> list[int]:
    if user.role == ADMIN:
        from app.models.entities import Workspace

        return list(db.scalars(select(Workspace.id)))
    return list(db.scalars(select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user.id)))


def ensure_member(db: DbSession, user: User, workspace_id: int) -> None:
    if workspace_id not in member_workspace_ids(db, user):
        raise ApiError("FORBIDDEN")
