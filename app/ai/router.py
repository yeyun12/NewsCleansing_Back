from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_session
from app.ai.sentiment_model import analyze_sentiment
from app.api.news.category_models import (
    EcoNews, PolNews, ItNews, LifNews, SocNews, WorNews
)

router = APIRouter()

# 요청 바디 스키마
class ArticleAnalyzeRequest(BaseModel):
    article_id: str

# 감정 분석 라우터
@router.post("/analyze")
async def analyze_article_by_id(
    request: ArticleAnalyzeRequest,
    db: AsyncSession = Depends(get_session)
):
    article_id = request.article_id

    # 모든 테이블 클래스 순회하며 해당 ID를 가진 기사 찾기
    category_models = [EcoNews, PolNews, ItNews, LifNews, SocNews, WorNews]
    found_article = None
    found_model = None

    for model in category_models:
        result = await db.execute(select(model).where(model.id == article_id))
        article = result.scalar_one_or_none()
        if article:
            found_article = article
            found_model = model
            break

    if not found_article:
        raise HTTPException(status_code=404, detail="해당 기사 ID를 가진 뉴스가 없습니다.")

    # 감정 분석 수행
    sentiment_result = analyze_sentiment(found_article.content)

    return {
        "article_id": found_article.id,
        "title": found_article.title,
        "category_table": found_model.__tablename__,  # 어디서 찾았는지 알려줌
        "analysis": sentiment_result["analysis"],
        "inference_time_sec": sentiment_result["inference_time_sec"]
    }
