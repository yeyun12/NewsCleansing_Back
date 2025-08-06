# app/api/news/category_models.py

from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime

class NewsBase(SQLModel):
    title: str
    content: str
    published_at: Optional[datetime] = None

# 테이블별 모델
class EcoNews(NewsBase, table=True):
    __tablename__ = "eco"
    id: str = Field(primary_key=True)

class PolNews(NewsBase, table=True):
    __tablename__ = "pol"
    id: str = Field(primary_key=True)

class ItNews(NewsBase, table=True):
    __tablename__ = "it"
    id: str = Field(primary_key=True)

class LifNews(NewsBase, table=True):
    __tablename__ = "lif"
    id: str = Field(primary_key=True)

class SocNews(NewsBase, table=True):
    __tablename__ = "soc"
    id: str = Field(primary_key=True)

class WorNews(NewsBase, table=True):
    __tablename__ = "wor"
    id: str = Field(primary_key=True)
