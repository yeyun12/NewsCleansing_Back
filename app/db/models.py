from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime

class ItemBase(SQLModel):
    """아이템 기본 스키마"""
    name: str = Field(index=True, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    price: float = Field(gt=0, description="가격은 0보다 커야 합니다")
    tax: Optional[float] = Field(default=None, ge=0)

class Item(ItemBase, table=True):
    """아이템 데이터베이스 모델"""
    __tablename__ = "items"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None
    is_active: bool = Field(default=True)

class ItemCreate(ItemBase):
    """아이템 생성 요청 스키마"""
    pass

class ItemUpdate(SQLModel):
    """아이템 업데이트 요청 스키마"""
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    price: Optional[float] = Field(default=None, gt=0)
    tax: Optional[float] = Field(default=None, ge=0)
    is_active: Optional[bool] = None

class ItemResponse(ItemBase):
    """아이템 응답 스키마"""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    is_active: bool
    
    class Config:
        from_attributes = True