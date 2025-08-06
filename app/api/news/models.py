from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime

class NewsBase(SQLModel):
    """뉴스 기본 스키마"""
    title: str = Field(index=True, min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=5000)
    author: str = Field(min_length=1, max_length=100)
    category: Optional[str] = Field(default=None, max_length=50)
    source_url: Optional[str] = Field(default=None, max_length=500)

class News(NewsBase, table=True):
    """뉴스 데이터베이스 모델"""
    __tablename__ = "news"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    is_active: bool = Field(default=True)
    is_published: bool = Field(default=False)

class NewsCreate(NewsBase):
    """뉴스 생성 요청 스키마"""
    pass

class NewsUpdate(SQLModel):
    """뉴스 업데이트 요청 스키마"""
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    content: Optional[str] = Field(default=None, min_length=1, max_length=5000)
    author: Optional[str] = Field(default=None, min_length=1, max_length=100)
    category: Optional[str] = Field(default=None, max_length=50)
    source_url: Optional[str] = Field(default=None, max_length=500)
    is_active: Optional[bool] = None
    is_published: Optional[bool] = None

class NewsResponse(NewsBase):
    """뉴스 응답 스키마"""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    is_active: bool
    is_published: bool
    
    class Config:
        from_attributes = True