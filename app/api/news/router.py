# app/api/news/router.py
from typing import Optional, Dict, Any, List, Literal, Tuple
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.config import settings

# 스키마
from .schemas import (
    ArticleOpenRequest,
    ArticleCloseRequest,
    EventsIngestRequest,
    MoodEventRequest,
)

from . import service

router = APIRouter(prefix="/news", tags=["news"])

# ------------------------------
# 내부 유틸: 외부 추천 API 호출(팀원 서버)
#  - 에러가 나면 빈 결과로 폴백(절대 예외를 밖으로 던지지 않음)
# ------------------------------
async def _fetch_recommendations(
    article_id: str, similar_limit: int, related_limit: int
) -> Dict[str, Any]:
    base = getattr(settings, "EXTERNAL_API_BASE_URL", None)
    if not base:
        return {"similar_articles": [], "related_topics": []}

    url = f"{base}/api/recommendations/complete/{article_id}"
    params = {"similar_limit": similar_limit, "related_limit": related_limit}

    try:
        async with httpx.AsyncClient(
            timeout=getattr(settings, "RECO_API_TIMEOUT", 5.0)
        ) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            return r.json()
    except Exception:
        # 타임아웃/HTTP 오류/네트워크 오류 모두 폴백
        return {"similar_articles": [], "related_topics": []}


# ------------------------------
# 추천 아이템에 태도 필드 주입 (중첩 구조까지 안전 처리)
# ------------------------------
async def _attach_attitudes_per_item(db: AsyncSession, items: Any) -> Any:
    """
    items가 다음과 같은 다양한 형태를 모두 지원:
      - 리스트 자체가 아이템 배열인 경우: [ {...}, ... ] 또는 ["eco0001", ...]
      - {"recommendations": [ ... ]}
      - {"recommendations": {"recommendations": [ ... ]}}
      - {"related_topics": [ ... ]}
      - {"related_topics": {"related_topics": [ ... ]}}
      - 레거시: {"similar_articles": [ ... ]}, {"articles": [ ... ]}, {"items": [ ... ]}
    내부 배열의 각 원소에 DB에서 가져온 attitude/attitude_confidence를 주입.
    """
    def locate_array(container) -> Tuple[Optional[dict], Optional[str], Optional[list]]:
        if isinstance(container, list):
            return None, None, container
        if not isinstance(container, dict):
            return None, None, None

        # 1차 키 바로 배열
        for key in ("recommendations", "related_topics", "similar_articles", "articles", "items"):
            val = container.get(key)
            if isinstance(val, list):
                return container, key, val

        # 2차 키(동일 키 중첩)
        for key in ("recommendations", "related_topics"):
            val = container.get(key)
            if isinstance(val, dict):
                inner = val.get(key)
                if isinstance(inner, list):
                    return val, key, inner

        return None, None, None

    if items is None:
        return items

    parent, key, arr = locate_array(items)
    if arr is None:
        # 배열이 아니라면 그대로 반환
        return items

    # 요소 정규화 + ID 수집
    normalized: List[Dict[str, Any]] = []
    ids: List[str] = []
    for it in arr:
        obj = {"article_id": it} if isinstance(it, str) else dict(it)
        aid = obj.get("article_id") or obj.get("id")
        if isinstance(aid, str):
            ids.append(aid)
        normalized.append(obj)

    # DB 조회로 태도 맵 구성
    attitude_map: Dict[str, Tuple[Optional[str], Optional[int]]] = {}
    for aid in ids:
        try:
            art = await service.get_article(db, aid)
            if art:
                attitude_map[aid] = (art.get("attitude"), art.get("attitude_confidence"))
        except Exception:
            # 개별 실패는 무시
            pass

    # 주입
    for obj in normalized:
        aid = obj.get("article_id") or obj.get("id")
        if aid and aid in attitude_map:
            att, conf = attitude_map[aid]
            obj["attitude"] = att
            obj["attitude_confidence"] = conf

    # 원 위치에 되돌려 넣기
    if parent is None:
        return normalized  # 루트가 리스트였던 경우
    parent[key] = normalized
    return items


# ------------------------------
# 목록
# ------------------------------
@router.get("", summary="뉴스 목록 조회", description="뉴스 목록을 조회합니다. 필터링, 페이징 기능을 지원")
async def list_news(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    category: Optional[str] = None,
    press: Optional[str] = None,
    q: Optional[str] = None,
    db: AsyncSession = Depends(get_session),
):
    items, total = await service.list_articles(
        db, limit=limit, offset=offset, category=category, press=press, q=q
    )
    return {"items": items, "limit": limit, "offset": offset, "total": total}


# ------------------------------
# 상세
# ------------------------------
@router.get("/{article_id}", summary="뉴스 상세 조회", description="특정 뉴스 기사의 상세 정보를 조회합니다.")
async def get_news(article_id: str, db: AsyncSession = Depends(get_session)):
    try:
        item = await service.get_article(db, article_id)
    except Exception as e:
        raise HTTPException(500, f"failed to load article: {e}")

    if not item:
        raise HTTPException(404, "article not found")
    return item


# ------------------------------
# 상세+추천 통합
# ------------------------------
@router.get(
    "/{article_id}/complete",
    summary="뉴스 상세+추천 통합 조회",
    description="특정 뉴스 기사의 상세와 추천을 한 번에 반환합니다.",
)
async def get_news_complete(
    article_id: str,
    similar_limit: int = Query(5, ge=1, le=12),
    related_limit: int = Query(6, ge=1, le=20),
    db: AsyncSession = Depends(get_session),
):
    # 1) 상세
    try:
        item = await service.get_article(db, article_id)
    except Exception as e:
        raise HTTPException(500, f"failed to load article: {e}")
    if not item:
        raise HTTPException(404, "article not found")

    # 2) 추천 (에러가 나도 빈 값으로 폴백)
    reco = await _fetch_recommendations(article_id, similar_limit, related_limit)

    # 외부 응답의 다양한 키 지원 (유연 매핑)
    raw_similar = reco.get("similar") or reco.get("similar_articles") or {}
    raw_topics = reco.get("topics") or reco.get("related_topics") or {}

    # 내부 리스트를 찾아 attitude 주입 (형태 보존)
    similar_with_att = await _attach_attitudes_per_item(db, raw_similar)
    topics_with_att = await _attach_attitudes_per_item(db, raw_topics)

    return {
        "article": item,
        "recommendations": {
            # 프론트는 객체/중첩을 그대로 받되, 아이템들만 태도 필드가 추가된 형태
            "similar": similar_with_att,
            "topics": topics_with_att,
        },
    }


# ------------------------------
# 번들/세션/통계
# ------------------------------
@router.get("/{article_id}/bundle", summary="뉴스 번들 조회", description="특정 뉴스 기사의 번들(관련 기사) 정보를 조회합니다.")
async def get_bundle(
    article_id: str, user_id: str, db: AsyncSession = Depends(get_session)
):
    return await service.bundle_article(db, article_id, user_id)


@router.post(
    "/{article_id}/open",
    status_code=status.HTTP_201_CREATED,
    summary="기사 열람 시작",
    description="특정 기사(article_id)를 열람 시작합니다.",
)
async def open_article(
    article_id: str, body: ArticleOpenRequest, db: AsyncSession = Depends(get_session)
):
    read_id = await service.open_read(db, article_id, body.user_id)
    return {"read_id": read_id}


@router.post(
    "/{article_id}/close",
    summary="기사 열람 종료",
    description="열람 세션 종료 및 체류시간 기록",
)
async def close_article(
    article_id: str,
    body: ArticleCloseRequest,
    db: AsyncSession = Depends(get_session),
):
    try:
        dwell = await service.close_read(db, article_id, body.user_id, body.read_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="read_id must be an integer string")

    if dwell < 0:
        raise HTTPException(status_code=404, detail="read session not found")

    return {
        "ok": True,
        "article_id": article_id,
        "read_id": body.read_id,
        "dwell_seconds": dwell,
    }


@router.post("/events", status_code=status.HTTP_201_CREATED, summary="유저 이벤트 수집")
async def ingest_events(
    body: EventsIngestRequest, db: AsyncSession = Depends(get_session)
):
    payloads: List[Dict[str, Any]] = [
        (e.model_dump() if hasattr(e, "model_dump") else e.dict())
        for e in body.events
    ]
    inserted = await service.ingest_events(db, payloads)
    return {"inserted": inserted}


@router.get("/{article_id}/stats", summary="기사 통계", description="세션 수/총·평균 체류시간")
async def article_stats(article_id: str, db: AsyncSession = Depends(get_session)):
    return await service.get_article_stats(db, article_id)


# ------------------------------
# User 통계/히스토리
# ------------------------------
@router.get("/user/{user_id}/today", summary="사용자 오늘 요약", description="오늘 세션 수/총 체류시간")
async def user_today(user_id: str, db: AsyncSession = Depends(get_session)):
    return await service.get_user_today(db, user_id)


@router.get("/user/{user_id}/reads/today", summary="사용자 오늘 읽기 히스토리")
async def user_reads_today(
    user_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_session),
):
    return await service.list_user_reads_today(
        db, user_id, limit=limit, offset=offset
    )


@router.get("/user/{user_id}/reads/week", summary="사용자 이번 주 읽기 히스토리")
async def user_reads_week(
    user_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_session),
):
    return await service.list_user_reads_week(db, user_id, limit=limit, offset=offset)


@router.get(
    "/user/{user_id}/field-stats",
    summary="사용자 분야별 소비 통계",
    description="표시 카테고리: 경제/정치/사회/문화/세계/과학 (항상 6개 반환, 0 포함)",
)
async def user_field_stats(
    user_id: str,
    metric: Literal["reads", "dwell"] = Query("reads"),
    mode: Literal["rolling", "week", "day"] = Query("day"),
    days: int = Query(1, ge=1, le=30),
    db: AsyncSession = Depends(get_session),
):
    # ✅ 더 이상 day를 rolling으로 바꾸지 않음
    normalized_mode = mode
    return await service.get_user_field_stats(
        db, user_id, days=days, metric=metric, mode=normalized_mode
    )


@router.get(
    "/user/{user_id}/hourly-activity",
    summary="사용자 접속 시간대(0~23시) 히스토그램",
    description="최근 N일(rolling) 또는 이번주(week) 동안 KST 기준 접속 시간대 분포를 반환합니다.",
)
async def user_hourly_activity(
    user_id: str,
    days: int = Query(7, ge=1, le=60),
    mode: Literal["rolling", "week"] = Query("rolling"),
    db: AsyncSession = Depends(get_session),
):
    return await service.get_user_hourly_activity(db, user_id, days=days, mode=mode)


# ------------------------------
# Home Feed
# ------------------------------
@router.get(
    "/user/{user_id}/feed/home",
    summary="홈 피드 생성(카테고리 관심도 반영)",
    description="오늘 읽음 수 기준으로 카테고리별 3~6개 샘플링하여 섹션을 반환합니다. exclude_read=true면 오늘 읽은 기사는 제외.",
)
async def news_home_feed(
    user_id: str,
    exclude_read: bool = Query(True),
    db: AsyncSession = Depends(get_session),
):
    return await service.get_home_feed(db, user_id, exclude_read=exclude_read)


# ------------------------------
# Mood (스트레스) 관련
# ------------------------------
@router.post("/mood/event", status_code=status.HTTP_201_CREATED, summary="스트레스 이벤트 기록")
async def mood_event(body: MoodEventRequest, db: AsyncSession = Depends(get_session)):
    inserted_id = await service.record_mood_event(
        db,
        user_id=body.user_id,
        delta=body.delta,
        reason=body.reason,
        attitude=body.attitude,
        article_id=body.article_id,
        ts=body.ts,
    )
    return {"inserted": inserted_id}


@router.get(
    "/mood/user/{user_id}/snapshot",
    summary="사용자 스트레스 스냅샷(오늘 점수/최근 N일/주간패턴)",
)
async def mood_snapshot(
    user_id: str,
    days: int = Query(7, ge=1, le=30),
    db: AsyncSession = Depends(get_session),
):
    return await service.get_user_mood_snapshot(db, user_id, days=days)
