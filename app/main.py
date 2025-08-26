from contextlib import asynccontextmanager
from fastapi import FastAPI #APIRouter
from app.db.session import create_db_and_tables, dispose_engine
from app.api.news.router import router as news_router
from app.api.user.router import router as user_router
from fastapi.middleware.cors import CORSMiddleware
from app.api.health.router import router as health_router
# from app.ai.router import router as ai_router
import os
from dotenv import load_dotenv

# .env 파일 불러오기
load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 생명주기 관리"""
    # 시작 시
    print("INFO: Creating database and tables...")
    await create_db_and_tables()

    print("INFO: Database tables created successfully")

    yield
    
    # 종료 시
    print("INFO: Disposing database engine...")
    await dispose_engine()
    print("INFO: Database engine disposed")

app = FastAPI(
    title="News Main Server",
    description="FastAPI + Supabase PostgreSQL with SQLModel",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        # 배포 프론트 도메인 추가
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# 라우터 등록
app.include_router(news_router, prefix="/api")
app.include_router(user_router, prefix="/api")
app.include_router(health_router, prefix="/api/health", tags=["health"])
# app.include_router(ai_router, prefix="/api/sentiment", tags=["Sentiment"])

@app.get("/")
async def root():
    """루트 엔드포인트"""
    return {
        "message": "Item Management API",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc"
    }

