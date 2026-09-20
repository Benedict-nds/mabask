from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.models import User
from app.core.schemas import LoginRequest, RefreshRequest, TokenPair, UserOut
from app.modules.auth import service as auth_svc

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=dict)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else None
    tokens, user = auth_svc.login(db, body.email, body.password, ip=ip)
    return {"tokens": tokens, "user": user}


@router.post("/refresh", response_model=TokenPair)
def refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    return auth_svc.refresh_tokens(db, body.refresh_token)


@router.post("/logout")
def logout(body: RefreshRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    auth_svc.logout(db, body.refresh_token, user)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return auth_svc.to_user_out(user)
