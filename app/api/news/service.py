from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import NoResultFound 
from .models import News, NewsCreate, NewsUpdate
from typing import List, Optional

class NewsService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_news(self, news_data: NewsCreate) -> News:
        """새 뉴스 생성"""
        news = News(**news_data.dict())
        self.session.add(news)
        await self.session.commit()
        await self.session.refresh(news)
        return news

    async def get_news(self, news_id: int) -> Optional[News]:
        """ID로 뉴스 조회"""
        statement = select(News).where(News.id == news_id)
        # ✅ .execute() 사용 + .scalar_one_or_none()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_news_list(
        self, 
        skip: int = 0, 
        limit: int = 100,
        active_only: bool = True,
        published_only: bool = False
    ) -> List[News]:
        """뉴스 목록 조회"""
        statement = select(News)
        
        if active_only:
            statement = statement.where(News.is_active == True)
        
        if published_only:
            statement = statement.where(News.is_published == True)
        
        statement = statement.offset(skip).limit(limit).order_by(News.created_at.desc())
        
        # ✅ .execute() 사용 + .scalars().all()
        result = await self.session.execute(statement)
        return result.scalars().all()

    async def update_news(self, news_id: int, news_data: NewsUpdate) -> Optional[News]:
        """뉴스 업데이트"""
        # 먼저 뉴스 조회
        statement = select(News).where(News.id == news_id)
        result = await self.session.execute(statement)
        news = result.scalar_one_or_none()
        
        if not news:
            return None

        # 업데이트 적용
        update_data = news_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(news, field, value)
        
        from datetime import datetime
        news.updated_at = datetime.now()
        
        # 발행 상태가 True로 변경되면 발행 시간 설정
        if news_data.is_published and not news.published_at:
            news.published_at = datetime.now()
        
        await self.session.commit()
        await self.session.refresh(news)
        return news

    async def delete_news(self, news_id: int) -> bool:
        """뉴스 소프트 삭제"""
        statement = select(News).where(News.id == news_id)
        result = await self.session.execute(statement)
        news = result.scalar_one_or_none()
        
        if not news:
            return False

        from datetime import datetime
        news.is_active = False
        news.updated_at = datetime.now()
        
        await self.session.commit()
        return True

    async def search_news(self, query: str) -> List[News]:
        """뉴스 검색"""
        statement = (
            select(News)
            .where(
                News.is_active == True,
                News.title.ilike(f"%{query}%")
            )
            .order_by(News.created_at.desc())
        )
        
        result = await self.session.execute(statement)
        return result.scalars().all()

    async def get_news_by_category(self, category: str) -> List[News]:
        """카테고리별 뉴스 조회"""
        statement = (
            select(News)
            .where(
                News.is_active == True,
                News.is_published == True,
                News.category == category
            )
            .order_by(News.published_at.desc())
        )
        
        result = await self.session.execute(statement)
        return result.scalars().all()

    async def publish_news(self, news_id: int) -> Optional[News]:
        """뉴스 발행"""
        statement = select(News).where(News.id == news_id)
        result = await self.session.execute(statement)
        news = result.scalar_one_or_none()
        
        if not news:
            return None

        from datetime import datetime
        news.is_published = True
        news.published_at = datetime.now()
        news.updated_at = datetime.now()
        
        await self.session.commit()
        await self.session.refresh(news)
        return news