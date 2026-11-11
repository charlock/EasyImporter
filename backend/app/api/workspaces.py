"""工作区与用户管理。"""

from argon2 import PasswordHasher
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.errors import ApiError
from app.core.security import (
    current_user,
    ensure_member,
    require_admin,
    require_admin_write,
)
from app.models.entities import (
    ADMIN,
    IMPORTER,
    ImportTask,
    Template,
    User,
    Workspace,
    WorkspaceMember,
)
from app.schemas.dto import (
    MembersIn,
    UserCreate,
    UserOut,
    UserUpdate,
    WorkspaceIn,
    WorkspaceOut,
)

router = APIRouter(tags=["admin"])
hasher = PasswordHasher()


@router.get("/workspaces", response_model=list[WorkspaceOut])
def list_workspaces(user: User = Depends(current_user), db: Session = Depends(get_session)):
    query = select(Workspace)
    if user.role != ADMIN:
        query = query.join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id).where(
            WorkspaceMember.user_id == user.id
        )
    workspaces = db.scalars(query.order_by(Workspace.id)).all()
    counts = dict(db.execute(select(WorkspaceMember.workspace_id, func.count()).group_by(
        WorkspaceMember.workspace_id)).all())
    return [WorkspaceOut(id=item.id, name=item.name, description=item.description,
                         member_count=counts.get(item.id, 0)) for item in workspaces]


@router.post("/workspaces", response_model=WorkspaceOut)
def create_workspace(payload: WorkspaceIn, _: User = Depends(require_admin_write),
                     db: Session = Depends(get_session)):
    workspace = Workspace(name=payload.name, description=payload.description)
    db.add(workspace)
    db.commit()
    return WorkspaceOut(id=workspace.id, name=workspace.name, description=workspace.description)


@router.put("/workspaces/{workspace_id}", response_model=WorkspaceOut)
def update_workspace(workspace_id: int, payload: WorkspaceIn, _: User = Depends(require_admin_write),
                     db: Session = Depends(get_session)):
    workspace = _workspace(db, workspace_id)
    workspace.name = payload.name
    workspace.description = payload.description
    db.commit()
    return WorkspaceOut(id=workspace.id, name=workspace.name, description=workspace.description)


@router.delete("/workspaces/{workspace_id}")
def delete_workspace(workspace_id: int, _: User = Depends(require_admin_write),
                     db: Session = Depends(get_session)):
    _workspace(db, workspace_id)
    has_templates = db.scalar(select(Template.id).where(Template.workspace_id == workspace_id).limit(1))
    has_imports = db.scalar(select(ImportTask.id).where(ImportTask.workspace_id == workspace_id).limit(1))
    if has_templates or has_imports:
        raise ApiError("WORKSPACE_NOT_EMPTY")
    db.query(WorkspaceMember).filter(WorkspaceMember.workspace_id == workspace_id).delete()
    db.query(Workspace).filter(Workspace.id == workspace_id).delete()
    db.commit()
    return {"ok": True}


@router.get("/workspaces/{workspace_id}/members", response_model=list[UserOut])
def list_members(workspace_id: int, user: User = Depends(current_user), db: Session = Depends(get_session)):
    ensure_member(db, user, workspace_id)
    return db.scalars(select(User).join(WorkspaceMember, WorkspaceMember.user_id == User.id).where(
        WorkspaceMember.workspace_id == workspace_id).order_by(User.id)).all()


@router.put("/workspaces/{workspace_id}/members", response_model=list[UserOut])
def set_members(workspace_id: int, payload: MembersIn, _: User = Depends(require_admin_write),
                db: Session = Depends(get_session)):
    _workspace(db, workspace_id)
    users = db.scalars(select(User).where(User.id.in_(payload.user_ids))).all() if payload.user_ids else []
    if len(users) != len(set(payload.user_ids)):
        raise ApiError("MEMBER_NOT_FOUND")
    db.query(WorkspaceMember).filter(WorkspaceMember.workspace_id == workspace_id).delete()
    for member_id in payload.user_ids:
        db.add(WorkspaceMember(workspace_id=workspace_id, user_id=member_id))
    db.commit()
    return users


@router.get("/users", response_model=list[UserOut])
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_session)):
    return db.scalars(select(User).order_by(User.id)).all()


@router.post("/users", response_model=UserOut)
def create_user(payload: UserCreate, _: User = Depends(require_admin_write),
                db: Session = Depends(get_session)):
    if payload.role not in {ADMIN, IMPORTER}:
        raise ApiError("VALIDATION_FAILED", {"field": "role"})
    if db.scalar(select(User.id).where(User.username == payload.username)):
        raise ApiError("USERNAME_TAKEN")
    user = User(username=payload.username, password_hash=hasher.hash(payload.password), role=payload.role,
                must_change_password=True)
    db.add(user)
    db.commit()
    return user


@router.put("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, _: User = Depends(require_admin_write),
                db: Session = Depends(get_session)):
    user = db.get(User, user_id)
    if user is None:
        raise ApiError("NOT_FOUND")
    if payload.role is not None:
        if payload.role not in {ADMIN, IMPORTER}:
            raise ApiError("VALIDATION_FAILED", {"field": "role"})
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
        if not payload.is_active:
            from app.models.entities import Session as SessionRecord

            db.query(SessionRecord).filter(SessionRecord.user_id == user.id).delete()
    if payload.password:
        user.password_hash = hasher.hash(payload.password)
        user.must_change_password = True
    db.commit()
    return user


def _workspace(db: Session, workspace_id: int) -> Workspace:
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise ApiError("NOT_FOUND")
    return workspace
