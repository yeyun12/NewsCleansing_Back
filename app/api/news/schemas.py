# app/api/news/schemas.py
from typing import Optional, Dict, List, Union
from datetime import datetime, timezone
from pydantic import BaseModel

# --- Pydantic v1/v2 호환 데코레이터 준비 -------------------------------------
try:
    # v2
    from pydantic import field_validator as _field_validator  # type: ignore
    PydV2 = True
except Exception:
    # v1 fallback
    from pydantic import validator as _v1_validator  # type: ignore
    PydV2 = False

    def _field_validator(field_name):
        # v1에서는 pre=True, allow_reuse=True 권장
        return _v1_validator(field_name, pre=True, allow_reuse=True)


UserId = Union[str, int]


# -----------------------------
# 요청 스키마들
# -----------------------------
class ArticleOpenRequest(BaseModel):
    user_id: UserId

    if PydV2:
        @_field_validator("user_id")
        @classmethod
        def _to_str(cls, v):
            return str(v)
    else:
        @_field_validator("user_id")
        def _to_str(cls, v):
            return str(v)


class ArticleCloseRequest(BaseModel):
    user_id: UserId
    read_id: str

    if PydV2:
        @_field_validator("user_id")
        @classmethod
        def _to_str(cls, v):
            return str(v)
    else:
        @_field_validator("user_id")
        def _to_str(cls, v):
            return str(v)


class EventItem(BaseModel):
    user_id: UserId
    event_type: str
    article_id: Optional[str] = None
    metadata: Optional[Dict] = None
    ts: Optional[datetime] = None

    if PydV2:
        @_field_validator("user_id")
        @classmethod
        def _uid_to_str(cls, v):
            return str(v)

        @_field_validator("ts")
        @classmethod
        def _default_ts(cls, v):
            return v or datetime.now(timezone.utc)
    else:
        @_field_validator("user_id")
        def _uid_to_str(cls, v):
            return str(v)

        @_field_validator("ts")
        def _default_ts(cls, v):
            return v or datetime.now(timezone.utc)


class EventsIngestRequest(BaseModel):
    events: List[EventItem]

# -----------------------------
# 기분(스트레스) 관련
class MoodEventRequest(BaseModel):
    user_id: str
    delta: int                    # 가/감 스트레스(+6, -4 등)
    reason: str                   # 'read' | 'cleanseOn' 등
    attitude: Optional[str] = None  # '우호적'|'중립적'|'비판적' 등 (있으면)
    article_id: Optional[str] = None
    ts: Optional[datetime] = None  # 없으면 서버 now()