from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_session  # 프로젝트 경로에 맞게

router = APIRouter()

@router.get("/z")
async def healthz(db: AsyncSession = Depends(get_session)):
    try:
        await db.execute(select(1))
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
