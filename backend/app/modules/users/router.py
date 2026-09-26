from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.permissions import require_permission
from app.core.schemas import (
    PermissionInfo,
    PermissionOverridesUpdate,
    RoleOut,
    UserCreate,
    UserOut,
    UserPermissionsOut,
    UserUpdate,
)
from app.models import User
from app.modules.users import permissions as perms_svc
from app.modules.users import service as users_svc

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_permission("users.read"))):
    return users_svc.list_users(db)


@router.get("/roles", response_model=list[RoleOut])
def list_roles(_: User = Depends(require_permission("users.read"))):
    return users_svc.list_roles()


@router.get("/permission-catalog", response_model=list[PermissionInfo])
def permission_catalog(_: User = Depends(require_permission("users.read"))):
    return perms_svc.permission_catalog()


@router.get("/{user_id}/permissions", response_model=UserPermissionsOut)
def get_user_permissions(user_id: str, db: Session = Depends(get_db), actor: User = Depends(require_permission("users.read"))):
    return perms_svc.get_user_permissions(db, user_id, actor)


@router.put("/{user_id}/permissions", response_model=UserPermissionsOut)
def set_user_permissions(
    user_id: str,
    body: PermissionOverridesUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("users.update")),
):
    return perms_svc.set_user_permissions(db, user_id, body.overrides, actor)


@router.post("/{user_id}/permissions/reset", response_model=UserPermissionsOut)
def reset_user_permissions(user_id: str, db: Session = Depends(get_db), actor: User = Depends(require_permission("users.update"))):
    return perms_svc.reset_user_permissions(db, user_id, actor)


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: str, db: Session = Depends(get_db), _: User = Depends(require_permission("users.read"))):
    return users_svc.get_user(db, user_id)


@router.post("", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db), actor: User = Depends(require_permission("users.create"))):
    return users_svc.create_user(db, body, actor)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: str, body: UserUpdate, db: Session = Depends(get_db), actor: User = Depends(require_permission("users.update"))):
    return users_svc.update_user(db, user_id, body, actor)


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: str, db: Session = Depends(get_db), actor: User = Depends(require_permission("users.delete"))):
    users_svc.delete_user(db, user_id, actor)
