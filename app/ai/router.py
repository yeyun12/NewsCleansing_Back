from fastapi import APIRouter
from pydantic import BaseModel
from app.ai.sentiment_model import analyze_sentiment


router = APIRouter()

class ArticleRequest(BaseModel):
    content: str

@router.post("/analyze")
async def analyze_article(request: ArticleRequest):
    return analyze_sentiment(request.content)
