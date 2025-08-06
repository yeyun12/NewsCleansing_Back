from typing import Annotated, List
from fastapi import APIRouter, Depends, HTTPException, Query, APIRouter 
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_session, SessionDep
from .models import NewsCreate, NewsUpdate, NewsResponse
from .service import NewsService
from .dependencies import NewsServiceDep

router = APIRouter(prefix="/news", tags=["news"])

@router.post("/", response_model=NewsResponse, status_code=201)
async def create_news(
    news_data: NewsCreate,
    news_service: NewsServiceDep
):
    """새로운 뉴스 생성"""
    news = await news_service.create_news(news_data)
    return NewsResponse.from_orm(news)

@router.get("/", response_model=List[NewsResponse])
async def get_news_list(
    news_service: NewsServiceDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    active_only: bool = Query(True),
    published_only: bool = Query(False)
):
    """뉴스 목록 조회"""
    news_list = await news_service.get_news_list(
        skip=skip, 
        limit=limit, 
        active_only=active_only,
        published_only=published_only
    )
    return [NewsResponse.from_orm(news) for news in news_list]

@router.get("/{news_id}", response_model=NewsResponse)
async def get_news(
    news_service: NewsServiceDep,
    news_id: int,
):
    """특정 뉴스 조회"""
    news = await news_service.get_news(news_id)
    if not news or not news.is_active:
        raise HTTPException(status_code=404, detail="News not found")
    
    return NewsResponse.from_orm(news)

@router.put("/{news_id}", response_model=NewsResponse)
async def update_news(
    news_data: NewsUpdate,
    news_service: NewsServiceDep,
    news_id: int
):
    """뉴스 업데이트"""
    news = await news_service.update_news(news_id, news_data)
    if not news:
        raise HTTPException(status_code=404, detail="News not found")
    
    return NewsResponse.from_orm(news)

@router.delete("/{news_id}", status_code=204)
async def delete_news(
    news_id: int,
    news_service: NewsServiceDep
):
    """뉴스 삭제"""
    success = await news_service.delete_news(news_id)
    if not success:
        raise HTTPException(status_code=404, detail="News not found")

@router.get("/search/{query}", response_model=List[NewsResponse])
async def search_news(
    query: str,
    news_service: NewsServiceDep
):
    """뉴스 검색"""
    news_list = await news_service.search_news(query)
    return [NewsResponse.from_orm(news) for news in news_list]

@router.get("/category/{category}", response_model=List[NewsResponse])
async def get_news_by_category(
    category: str,
    news_service: NewsServiceDep
):
    """카테고리별 뉴스 조회"""
    news_list = await news_service.get_news_by_category(category)
    return [NewsResponse.from_orm(news) for news in news_list]

@router.post("/{news_id}/publish", response_model=NewsResponse)
async def publish_news(
    news_id: int,
    news_service: NewsServiceDep
):
    """뉴스 발행"""
    news = await news_service.publish_news(news_id)
    if not news:
        raise HTTPException(status_code=404, detail="News not found")
    
    return NewsResponse.from_orm(news)