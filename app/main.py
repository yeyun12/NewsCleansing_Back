# from contextlib import asynccontextmanager
# from fastapi import FastAPI #APIRouter
# from app.db.session import create_db_and_tables, dispose_engine
# from app.api.news.router import router as news_router
# from app.api.user.router import router as user_router
# from fastapi.middleware.cors import CORSMiddleware
# from app.api.health.router import router as health_router
# # from app.ai.router import router as ai_router
# import os
# from dotenv import load_dotenv

# # .env 파일 불러오기
# load_dotenv()


# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     """앱 생명주기 관리"""
#     # 시작 시
#     print("INFO: Creating database and tables...")
#     await create_db_and_tables()

#     print("INFO: Database tables created successfully")

#     yield
    
#     # 종료 시
#     print("INFO: Disposing database engine...")
#     await dispose_engine()
#     print("INFO: Database engine disposed")

# app = FastAPI(
#     title="News Main Server",
#     description="FastAPI + Supabase PostgreSQL with SQLModel",
#     version="1.0.0",
#     lifespan=lifespan
# )

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=[
#         "http://localhost:3000",
#         "http://127.0.0.1:3000",
#         # 배포 프론트 도메인 추가
#     ],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )



# # 라우터 등록
# app.include_router(news_router, prefix="/api")
# app.include_router(user_router, prefix="/api")
# app.include_router(health_router, prefix="/api/health", tags=["health"])
# # app.include_router(ai_router, prefix="/api/sentiment", tags=["Sentiment"])

# @app.get("/")
# async def root():
#     """루트 엔드포인트"""
#     return {
#         "message": "Item Management API",
#         "version": "1.0.0",
#         "docs": "/docs",
#         "redoc": "/redoc"
#     }

# app/main.py
from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.session import create_db_and_tables, dispose_engine
from app.api.news.router import router as news_router
from app.api.user.router import router as user_router
from app.api.health.router import router as health_router  # /api/health

from dotenv import load_dotenv

# .env 로드 (로컬 개발용)
load_dotenv()


def _env_true(v: str | None) -> bool:
    return str(v).lower() in {"1", "true", "yes", "y"}


# ---------------------------------------------------------------------
# Lifespan: 앱 생명주기 (부팅 시 DB 스키마 생성 / 종료 시 엔진 정리)
# ---------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 시작 시
    if not _env_true(os.getenv("SKIP_DB_INIT")):
        print("INFO: Creating database and tables...")
        await create_db_and_tables()
        print("INFO: Database tables created successfully")
    else:
        print("INFO: SKIP_DB_INIT=1 → DB 초기화 건너뜀")

    yield

    # 종료 시
    print("INFO: Disposing database engine...")
    await dispose_engine()
    print("INFO: Database engine disposed")


# ---------------------------------------------------------------------
# FastAPI 앱
# ---------------------------------------------------------------------
app = FastAPI(
    title="News Main Server",
    description="FastAPI + Supabase PostgreSQL with SQLModel",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------
# CORS 설정
#   - 배포 후에는 FRONTEND_URL 한 도메인만 허용
#   - 로컬 개발(URL)도 함께 허용
# ---------------------------------------------------------------------
frontend_url = os.getenv("FRONTEND_URL")  # 예) https://news-cleansing-front.vercel.app
allow_origins = {
    "http://localhost:3000",
    "http://127.0.0.1:3000",
}
if frontend_url:
    allow_origins.add(frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(allow_origins) if allow_origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------
# 라우터 등록
# ---------------------------------------------------------------------
app.include_router(news_router, prefix="/api")
app.include_router(user_router, prefix="/api")
app.include_router(health_router, prefix="/api/health", tags=["health"])

# Render Health Check 용 심플 엔드포인트 (설정에서 /health 로 지정 추천)
@app.get("/health")
async def health():
    return {"ok": True}

# 루트
@app.get("/")
async def root():
    return {
        "message": "Item Management API",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc",
    }
