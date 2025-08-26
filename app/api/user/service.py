from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from .models import User, UserSession

KST = "Asia/Seoul"


class UserService:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ---------- Users ----------
    async def create_user(self, name: str, email: str, password: str) -> User:
        user = User(name=name, email=email, password=password)
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def get_users(self) -> List[User]:
        result = await self.session.execute(select(User))
        return list(result.scalars().all())

    async def update_user(self, user_id: int, name: str, email: str, password: Optional[str] = None) -> Optional[User]:
        user = (await self.session.execute(select(User).where(User.id == user_id))).scalars().one_or_none()
        if not user:
            return None
        user.name = name
        user.email = email
        if password is not None:
            user.password = password
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def delete_user(self, user_id: int) -> bool:
        user = (await self.session.execute(select(User).where(User.id == user_id))).scalars().one_or_none()
        if not user:
            return False
        await self.session.delete(user)
        await self.session.commit()
        return True

    async def login(self, email: str, password: str) -> Optional[User]:
        user = (await self.session.execute(select(User).where(User.email == email))).scalars().one_or_none()
        if not user or user.password != password:
            return None
        return user

    # ---------- Sessions ----------
    async def start_session(self, user_id: int) -> int:
        # 컬럼이 timestamp(naive)이므로 UTC now에서 tz를 제거해 저장(= naive UTC)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        row = UserSession(user_id=user_id, started_at=now)
        self.session.add(row)
        await self.session.flush()  # id 확보
        sid = row.id
        await self.session.commit()
        return sid

    async def end_session(self, session_id: int, user_id: int) -> int:
        row = (
            await self.session.execute(
                select(UserSession).where(
                    UserSession.id == session_id,
                    UserSession.user_id == user_id,
                )
            )
        ).scalars().one_or_none()
        if not row:
            return -1

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if row.ended_at is None:
            row.ended_at = now

        seconds = 0
        if row.started_at is not None:
            seconds = max(0, int((row.ended_at - row.started_at).total_seconds()))
        await self.session.commit()
        return seconds

    # ---------- Usage: hourly bins (KST 기준, 시간 경계로 분할 집계) ----------
    async def usage_hourly(self, user_id: int, *, mode: str = "day", days: int = 1) -> List[int]:
        """
        저장: started_at/ended_at = naive UTC(timestamp)
        집계: KST 로컬 기준. 세션을 시간 경계(…:00~…:59)로 쪼개 각 시간대 교집합만 합산.
        mode: "day"(오늘 0~24 KST) | "week"(이번 주 KST) | "rolling"(최근 N일 KST)
        반환: 길이 24의 '분' 단위 합계
        """
        sql = text(
            """
WITH bounds AS (
  SELECT
    CASE
      WHEN :mode = 'day'
        THEN date_trunc('day', (now() AT TIME ZONE :tz))
      WHEN :mode = 'week'
        THEN date_trunc('week', (now() AT TIME ZONE :tz))
      WHEN :mode = 'rolling'
        THEN (now() AT TIME ZONE :tz) - make_interval(days => :days)
      ELSE
        date_trunc('day', (now() AT TIME ZONE :tz))
    END AS start_local,
    CASE
      WHEN :mode = 'day'
        THEN date_trunc('day', (now() AT TIME ZONE :tz)) + interval '1 day'
      WHEN :mode = 'week'
        THEN date_trunc('week', (now() AT TIME ZONE :tz)) + interval '7 days'
      WHEN :mode = 'rolling'
        THEN (now() AT TIME ZONE :tz)
      ELSE
        date_trunc('day', (now() AT TIME ZONE :tz)) + interval '1 day'
    END AS end_local
),
-- 1) naive UTC(timestamp) -> UTC timestamptz -> KST 로컬 timestamp 로 변환
sessions_local AS (
  SELECT
    ((u.started_at AT TIME ZONE 'UTC') AT TIME ZONE :tz) AS start_local,
    ((COALESCE(u.ended_at, (now() AT TIME ZONE 'UTC')::timestamp) AT TIME ZONE 'UTC') AT TIME ZONE :tz) AS end_local
  FROM user_sessions u
  WHERE u.user_id = :user_id
),
-- 2) KST 집계 윈도우와 겹치는 구간만 남김
clipped AS (
  SELECT
    GREATEST(s.start_local, b.start_local) AS s_start,
    LEAST(s.end_local,   b.end_local)     AS s_end
  FROM sessions_local s
  CROSS JOIN bounds b
  WHERE s.end_local > b.start_local
    AND s.start_local < b.end_local
),
-- 3) 세션을 시간 단위로 분할(0분 경계 기준) 후, 각 시간대 교집합 길이 계산
expanded AS (
  SELECT
    h AS bucket_start,
    LEAST(c.s_end, h + interval '1 hour') AS bucket_end,
    GREATEST(c.s_start, h)                 AS bucket_real_start
  FROM clipped c
  JOIN LATERAL generate_series(
        date_trunc('hour', c.s_start),
        date_trunc('hour', c.s_end - interval '1 second'),
        interval '1 hour'
      ) AS h ON TRUE
),
agg AS (
  SELECT
    EXTRACT(HOUR FROM bucket_start)::int AS hour,
    SUM(GREATEST(EXTRACT(EPOCH FROM (bucket_end - bucket_real_start)), 0))::bigint AS seconds
  FROM expanded
  GROUP BY 1
)
SELECT hour, seconds
FROM agg
ORDER BY hour;
            """
        )

        params = {
            "user_id": user_id,
            "tz": KST,
            "mode": mode if mode in ("day", "week", "rolling") else "day",
            "days": int(days) if days and days > 0 else 1,
        }

        rows = (await self.session.execute(sql, params)).all()

        bins = [0] * 24
        for h, sec in rows:
            hour = int(h)
            seconds = int(sec or 0)
            bins[hour] = max(0, round(seconds / 60.0))  # 분 단위
        return bins
