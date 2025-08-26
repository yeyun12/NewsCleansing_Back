# # app/api/news/category_models.py

# from sqlmodel import SQLModel, Field
# from typing import Optional
# from datetime import datetime

# class NewsBase(SQLModel):
#     title: str
#     content: str
#     published_at: Optional[datetime] = None

# # 테이블별 모델
# class EcoNews(NewsBase, table=True):
#     __tablename__ = "eco"
#     id: str = Field(primary_key=True)

# class PolNews(NewsBase, table=True):
#     __tablename__ = "pol"
#     id: str = Field(primary_key=True)

# class ItNews(NewsBase, table=True):
#     __tablename__ = "it"
#     id: str = Field(primary_key=True)

# class LifNews(NewsBase, table=True):
#     __tablename__ = "lif"
#     id: str = Field(primary_key=True)

# class SocNews(NewsBase, table=True):
#     __tablename__ = "soc"
#     id: str = Field(primary_key=True)

# class WorNews(NewsBase, table=True):
#     __tablename__ = "wor"
#     id: str = Field(primary_key=True)
# app/api/news/category_models.py
# (필요 시 확장) 카테고리 정규화/표시 순서 유틸
DISPLAY_CATEGORIES = ["경제", "정치", "사회", "문화", "세계", "과학"]

def normalize_category(article_id: str, category: str | None) -> str:
    if article_id.startswith("eco"): return "경제"
    if article_id.startswith("pol"): return "정치"
    if article_id.startswith("soc"): return "사회"
    if article_id.startswith("lif"): return "문화"
    if article_id.startswith("sci"): return "과학"
    if article_id.startswith("int"): return "세계"
    if category in ("생활/문화",): return "문화"
    if category in ("IT/과학", "IT"): return "과학"
    if category in ("국제",): return "세계"
    return category or "기타"
