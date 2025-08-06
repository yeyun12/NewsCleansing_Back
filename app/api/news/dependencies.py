from typing import Annotated
from fastapi import Depends
from .service import NewsService
from app.db.session import SessionDep

"""
Annotated는 타입에 추가 메타데이터를 붙이는 Python 표준 기능입니다.

기본 문법:
Annotated[타입, 메타데이터1, 메타데이터2, ...]

예시:
- Annotated[int, "사용자 ID"]
- Annotated[str, Field(min_length=1)]
- Annotated[Session, Depends(get_db)]
"""

async def get_news_service(session: SessionDep) -> NewsService:
    """NewsService 의존성 주입"""
    return NewsService(session)

NewsServiceDep = Annotated[NewsService, Depends(get_news_service)]