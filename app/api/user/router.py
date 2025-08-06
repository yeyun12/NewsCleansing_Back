from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.db.session import get_session
from .service import UserService, LogService

router = APIRouter(prefix="/user", tags=["user"])

@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_user(
    name: str,
    email: str,
    password: str,
    db: AsyncSession = Depends(get_session)
):
    """새로운 유저 생성"""
    service = UserService(db)
    user = await service.create_user(name, email, password)
    return {"id": user.id, "email": user.email}

@router.get("/", response_model=List[dict])
async def get_users(
    db: AsyncSession = Depends(get_session)
):
    """유저 목록 조회"""
    service = UserService(db)
    users = await service.get_users()
    return [{"id": u.id, "email": u.email} for u in users]

@router.put("/{user_id}", response_model=dict)
async def update_user(
    user_id: int,
    name: str,
    email: str,
    password: Optional[str] = None,
    db: AsyncSession = Depends(get_session)
):
    """유저 업데이트"""
    service = UserService(db)
    user = await service.update_user(user_id, name, email, password)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": user.id, "email": user.email}

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db: AsyncSession = Depends(get_session)):
    """유저 삭제"""
    service = UserService(db)
    success = await service.delete_user(user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")

@router.post("/log", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_log(user_id: int, action: str, db: AsyncSession = Depends(get_session)):
    """유저 로그 생성"""
    service = LogService(db)
    log = await service.create_log(user_id, action)
    return {"id": log.id, "user_id": log.user_id, "action": log.action, "timestamp": log.timestamp}

@router.get("/log", response_model=List[dict])
async def get_logs(user_id: Optional[int] = None, db: AsyncSession = Depends(get_session)):
    """유저 로그 조회"""
    service = LogService(db)
    logs = await service.get_logs(user_id)
    return [{"id": l.id, "user_id": l.user_id, "action": l.action, "timestamp": l.timestamp} for l in logs]
