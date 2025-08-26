from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel

# ---- Users ----
class UserCreate(BaseModel):
    name: str
    email: str  # EmailStr 제거(외부 패키지 불필요)
    password: str

class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    created_at: datetime | None = None

# ---- Auth/Login body (선택) ----
class LoginBody(BaseModel):
    email: str
    password: str

# ---- Sessions ----
class SessionStartBody(BaseModel):
    user_id: int

class SessionEndBody(BaseModel):
    user_id: int
    session_id: int

class SessionStartResponse(BaseModel):
    session_id: int

class SessionEndResponse(BaseModel):
    ok: bool
    seconds: int

# ---- Usage (hourly bins) ----
class UsageHourlyResponse(BaseModel):
    labels: list[int]   # 0~23
    bins: list[int]     # 각 시간대 사용 분(min)
