# # app/api/news/models.py
from typing import Optional, Dict
from datetime import datetime
from sqlmodel import SQLModel, Field, Column, JSON

class Article(SQLModel, table=True):
    __tablename__ = "original_article"
    id: str = Field(primary_key=True)
    url: Optional[str] = None
    category: Optional[str] = None
    published_at: Optional[datetime] = None
    title: Optional[str] = None
    content: Optional[str] = None
    thumbnail_url: Optional[str] = None
    reporter: Optional[str] = None
    press: Optional[str] = None
    keywords: Optional[str] = None
    scraped_at: Optional[datetime] = None

class ArticleRead(SQLModel, table=True):
    __tablename__ = "article_reads"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int
    article_id: str
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    dwell_seconds: Optional[int] = 0

class UserEvent(SQLModel, table=True):
    __tablename__ = "user_events"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int
    event_type: str
    article_id: Optional[str] = None
    ts: Optional[datetime] = None
    meta: Optional[Dict] = Field(default=None, sa_column=Column(JSON))
