import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlmodel import SQLModel
from dotenv import load_dotenv
from typing import AsyncGenerator, Annotated, List
from fastapi import Depends
from dotenv import load_dotenv

load_dotenv()

# 데이터베이스 URL (환경변수 또는 직접 설정)
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql+asyncpg://postgres.vgeplpvvcmvmqldxtoec:[유저비밀번호]@aws-0-ap-northeast-2.pooler.supabase.com:5432/postgres"
)

# 비동기 엔진 생성
engine = create_async_engine(
    DATABASE_URL,
    echo=True,  # SQL 쿼리 로깅
    future=True,  # SQLAlchemy 2.0 스타일 사용
    # PgBouncer 사용 시 필요한 설정
    pool_pre_ping=True,  # 연결 상태 확인
    pool_recycle=300,    # 5분마다 연결 재생성
)

# 비동기 세션 팩토리 생성
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False
)

# 테이블 생성 함수
async def create_db_and_tables():
    """앱 시작 시 데이터베이스 테이블 생성"""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

# 데이터베이스 세션 의존성 함수
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 의존성 주입용 데이터베이스 세션"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

# 엔진 정리 함수
async def dispose_engine():
    """앱 종료 시 엔진 정리"""
    await engine.dispose()

SessionDep = Annotated[AsyncSession, Depends(get_session)]