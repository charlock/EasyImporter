"""认证接口。"""

from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session
from app.core.errors import ApiError
from app.core.security import (
    COOKIE_NAME,
    current_session,
    current_user,
    member_workspace_ids,
    new_session,
)
from app.models.entities import Session as SessionRecord
from app.models.entities import User
from app.schemas.dto import LoginRequest, MeOut, PasswordChange, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])
hasher = PasswordHasher()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


@router.post("/login", response_model=MeOut)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_session)):
    user = db.scalar(select(User).where(User.username == payload.username))
    now = datetime.now(UTC)
    if user and user.locked_until and user.locked_until.replace(tzinfo=UTC) > now:
        raise ApiError("LOGIN_LOCKED", {"until": user.locked_until.isoformat()})
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        if user is not None:
            user.failed_login_count += 1
            if user.failed_login_count >= get_settings().login_max_failures:
                user.locked_until = now + timedelta(minutes=get_settings().login_lock_minutes)
                user.failed_login_count = 0
            db.commit()
        raise ApiError("LOGIN_FAILED")
    user.failed_login_count = 0
    user.locked_until = None
    record, token = new_session(db, user)
    db.commit()
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax",
                        secure=get_settings().cookie_secure, path="/")
    return _me(db, user, record.csrf_token)


@router.post("/logout")
def logout(user: User = Depends(current_session), db: Session = Depends(get_session)):
    db.query(SessionRecord).filter(SessionRecord.user_id == user.id).delete()
    db.commit()
    return {"ok": True}


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(current_user), db: Session = Depends(get_session)):
    record = db.scalar(select(SessionRecord).where(SessionRecord.user_id == user.id)
                       .order_by(SessionRecord.id.desc()))
    return _me(db, user, record.csrf_token if record else "")


@router.post("/password", response_model=UserOut)
def change_password(payload: PasswordChange, user: User = Depends(current_session),
                    db: Session = Depends(get_session)):
    if not verify_password(payload.old_password, user.password_hash):
        raise ApiError("LOGIN_FAILED")
    user.password_hash = hasher.hash(payload.new_password)
    user.must_change_password = False
    db.query(SessionRecord).filter(SessionRecord.user_id == user.id).delete()
    db.commit()
    return user


def _me(db: Session, user: User, csrf_token: str) -> MeOut:
    return MeOut(id=user.id, username=user.username, role=user.role, is_active=user.is_active,
                 must_change_password=user.must_change_password,
                 workspace_ids=member_workspace_ids(db, user), csrf_token=csrf_token)
