from __future__ import annotations
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
import httpx
from app.db.session import get_session
from .service import UserService
from .schemas import (
    UserCreate,
    UserResponse,
    LoginBody,
    SessionStartBody,
    SessionEndBody,
    SessionStartResponse,
    SessionEndResponse,
    UsageHourlyResponse,
)
import os
from fastapi import APIRouter
import requests

router = APIRouter()
router = APIRouter(prefix="/user", tags=["users"])
EXTERNAL_API_BASE_URL = os.getenv("EXTERNAL_API_BASE_URL")

# ---------------- Users ----------------
@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    name: str = Query(...),
    email: str = Query(...),
    password: str = Query(...),
    db: AsyncSession = Depends(get_session),
):
    svc = UserService(db)
    u = await svc.create_user(name, email, password)
    return UserResponse(id=u.id, name=u.name, email=u.email, created_at=u.created_at)

@router.get("/", response_model=List[UserResponse])
async def get_users(db: AsyncSession = Depends(get_session)):
    svc = UserService(db)
    rows = await svc.get_users()
    return [UserResponse(id=u.id, name=u.name, email=u.email, created_at=u.created_at) for u in rows]

@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    name: str = Query(...),
    email: str = Query(...),
    password: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_session),
):
    svc = UserService(db)
    u = await svc.update_user(user_id, name, email, password)
    if not u:
        raise HTTPException(404, "User not found")
    return UserResponse(id=u.id, name=u.name, email=u.email, created_at=u.created_at)

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db: AsyncSession = Depends(get_session)):
    svc = UserService(db)
    ok = await svc.delete_user(user_id)
    if not ok:
        raise HTTPException(404, "User not found")

# ---------------- Auth ----------------
@router.post("/login", response_model=UserResponse)
async def login(
    email: Optional[str] = Query(None),
    password: Optional[str] = Query(None),
    body: Optional[LoginBody] = Body(None),
    db: AsyncSession = Depends(get_session),
):
    em = email if email is not None else (body.email if body else None)
    pw = password if password is not None else (body.password if body else None)
    if not em or not pw:
        raise HTTPException(status_code=400, detail="email and password are required")

    svc = UserService(db)
    user = await svc.login(em, pw)
    if not user:
        raise HTTPException(status_code=401, detail="잘못된 이메일 또는 비밀번호입니다.")
    return UserResponse(id=user.id, name=user.name, email=user.email, created_at=user.created_at)

@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    name: str = Query(...),
    email: str = Query(...),
    password: str = Query(...),
    db: AsyncSession = Depends(get_session),
):
    svc = UserService(db)
    u = await svc.create_user(name, email, password)
    return UserResponse(id=u.id, name=u.name, email=u.email, created_at=u.created_at)

# ---------------- Sessions ----------------
@router.post("/session/start", response_model=SessionStartResponse, status_code=status.HTTP_201_CREATED)
async def session_start(
    user_id: Optional[int] = Query(None),
    body: Optional[SessionStartBody] = Body(None),
    db: AsyncSession = Depends(get_session),
):
    uid = user_id if user_id is not None else (body.user_id if body else None)
    if uid is None:
        raise HTTPException(400, detail="user_id is required")

    svc = UserService(db)
    sid = await svc.start_session(uid)
    return SessionStartResponse(session_id=sid)

@router.post("/session/end", response_model=SessionEndResponse)
async def session_end(
    user_id: Optional[int] = Query(None),
    session_id: Optional[int] = Query(None),
    body: Optional[SessionEndBody] = Body(None),
    db: AsyncSession = Depends(get_session),
):
    uid = user_id if user_id is not None else (body.user_id if body else None)
    sid = session_id if session_id is not None else (body.session_id if body else None)
    if uid is None or sid is None:
        raise HTTPException(400, detail="user_id and session_id are required")

    svc = UserService(db)
    seconds = await svc.end_session(session_id=sid, user_id=uid)
    if seconds < 0:
        raise HTTPException(404, detail="session not found")
    return SessionEndResponse(ok=True, seconds=seconds)

# ---------------- Usage (hourly) ----------------
@router.get("/sessions/hours", response_model=UsageHourlyResponse)
async def session_hours(
    user_id: int = Query(...),
    mode: str = Query("day"),        # "day" | "week" | "rolling"
    days: int = Query(1, ge=1, le=31),
    db: AsyncSession = Depends(get_session),
):
    svc = UserService(db)
    bins = await svc.usage_hourly(user_id, mode=mode, days=days)
    return UsageHourlyResponse(labels=list(range(24)), bins=bins)



