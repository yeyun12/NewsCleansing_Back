# app/db/session.py
import os
from typing import AsyncGenerator, Annotated

from dotenv import load_dotenv
from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

load_dotenv()

# ---------------------------------------------------------------------
# ENV
# ---------------------------------------------------------------------
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres.mzwydodxpnejiaxcktfu:jaksal2025@"
    "aws-0-ap-northeast-2.pooler.supabase.com:5432/postgres",
)

SQL_ECHO = os.getenv("SQL_ECHO", "0") in ("1", "true", "True", "YES", "yes")
POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "300"))

# Supabase pgbouncer(pooler) 사용 시 애플리케이션 풀은 끄는 게 안전
USE_NULLPOOL = (
    "pooler.supabase.com" in DATABASE_URL
    or os.getenv("DB_USE_NULLPOOL", "1") in ("1", "true", "True", "YES", "yes")
)

# ---------------------------------------------------------------------
# ENGINE
# ---------------------------------------------------------------------
engine_kwargs = dict(
    echo=SQL_ECHO,
    future=True,
    pool_pre_ping=True,
)

if USE_NULLPOOL:
    # PgBouncer 앞단에서는 SQLAlchemy 풀을 쓰지 않는 것이 안전
    engine_kwargs["poolclass"] = NullPool
else:
    engine_kwargs["pool_recycle"] = POOL_RECYCLE

engine = create_async_engine(DATABASE_URL, **engine_kwargs)

# ---------------------------------------------------------------------
# SESSION FACTORY
# ---------------------------------------------------------------------
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

# ---------------------------------------------------------------------
# DEPENDENCY
# ---------------------------------------------------------------------
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# ---------------------------------------------------------------------
# OPTIONAL: DDL (필요할 때만 호출)
# ---------------------------------------------------------------------
async def create_db_and_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

async def dispose_engine() -> None:
    await engine.dispose()
