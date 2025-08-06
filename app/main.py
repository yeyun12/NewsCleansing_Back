from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter
from app.db.session import create_db_and_tables, dispose_engine
from app.api.news.router import router as news_router
from app.api.user.router import router as user_router
from app.ai.router import router as ai_router



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
    title="Item Management API",
    description="FastAPI + Supabase PostgreSQL with SQLModel",
    version="1.0.0",
    lifespan=lifespan
)

# 라우터 등록
app.include_router(news_router, prefix="/api")
app.include_router(user_router, prefix="/api")
app.include_router(ai_router, prefix="/api/sentiment", tags=["Sentiment"])

@app.get("/")
async def root():
    """루트 엔드포인트"""
    return {
        "message": "Item Management API",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc"
    }

@app.get("/health")
async def health_check():
    """헬스 체크 엔드포인트"""
    return {"status": "healthy"}
