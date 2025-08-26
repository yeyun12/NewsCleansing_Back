# app/api/news/service.py
import os
import hashlib
import json
import html
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, date, timedelta
from sqlalchemy.dialects.postgresql import JSONB
import httpx
from sqlalchemy import select, desc, and_, func, text, case, cast, Integer
from sqlalchemy.ext.asyncio import AsyncSession
from dotenv import load_dotenv
from sqlalchemy.types import Numeric
load_dotenv()

FEED_LOOKBACK_DAYS = int(os.getenv("FEED_LOOKBACK_DAYS", "60"))
BASELINE_STRESS = 50

from .models import Article, ArticleRead, UserEvent

KST = "Asia/Seoul"

def _to_kst(col):
    """
    컬럼이 UTC 기반 timestamp WITHOUT time zone으로 저장되어 있을 때,
    KST 벽시계 시각으로 안전 변환:
      col AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Seoul'
    (만약 DB가 timestamptz라면 첫 'UTC' 변환은 생략 가능하지만,
     현재 스키마에 안전하게 맞춘 형태)
    """
    return col.op("AT TIME ZONE")("UTC").op("AT TIME ZONE")(KST)

def _now_kst():
    # now()는 timestamptz → timezone(KST, now())는 KST 벽시계(naive) 반환
    return func.timezone(KST, func.now())


# ------------------------------------------------------------------------------ #
# Config
# ------------------------------------------------------------------------------ #
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "3.0"))
SENTI_URL = os.getenv("SENTI_URL")
CLEANSE_URL = os.getenv("CLEANSE_URL")
RECO_URL = os.getenv("RECO_URL")
KST = "Asia/Seoul"

DISPLAY_CATEGORIES = ["경제", "정치", "사회", "문화", "세계", "과학"]

# ------------------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------------------ #
def _row_to_dict(row) -> Dict[str, Any]:
    if isinstance(row, Article):
        a = row
        return {
            "id": a.id,
            "url": a.url,
            "category": a.category,
            "published_at": a.published_at,
            "title": a.title,
            "content": a.content,
            "thumbnail_url": a.thumbnail_url,
            "reporter": a.reporter,
            "press": a.press,
            "keywords": a.keywords,
            "scraped_at": a.scraped_at,
        }
    return dict(row._mapping)


def _read_row_to_dict(m) -> dict:
    return {
        "read_id": m["read_id"],
        "opened_at": m["opened_at"],
        "closed_at": m["closed_at"],
        "dwell_seconds": m["dwell_seconds"] or 0,
        "article": {
            "id": m["article_id"],
            "title": m["title"],
            "category": m["category"],
            "press": m["press"],
            "published_at": m["published_at"],
            "thumbnail_url": m["thumbnail_url"],
        },
    }


def _kst_today_window():
    now_kst_local = func.timezone(KST, func.now())
    start_kst_local = func.date_trunc("day", now_kst_local)
    end_kst_local = start_kst_local + text("interval '1 day'")
    return start_kst_local, end_kst_local


def _daily_seed(user_id: int, d: date) -> str:
    return hashlib.sha1(f"{user_id}:{d.isoformat()}".encode()).hexdigest()[:8]


def _as_list(v) -> List[str]:
    """문자열/JSON/리스트를 안전하게 리스트로 변환"""
    if v is None:
        return []
    if isinstance(v, list):
        return v
    s = str(v).strip()
    if not s:
        return []
    try:
        return json.loads(s)
    except Exception:
        try:
            return json.loads(s.replace("'", '"'))
        except Exception:
            return []


def _build_highlight_html(content: str, evidences: List[str]) -> Optional[str]:
    """원문에서 evidence 문장을 찾아 하이라이트 HTML 생성."""
    if not content or not evidences:
        return None

    txt = content
    # 긴 문장부터 매칭하면 겹침이 줄어듦
    evs = sorted(set([e for e in evidences if e]), key=len, reverse=True)
    ranges: List[tuple[int, int]] = []

    def overlaps(a, b):
        return not (a[1] <= b[0] or b[1] <= a[0])

    for ev in evs:
        start = 0
        while True:
            i = txt.find(ev, start)
            if i == -1:
                break
            j = i + len(ev)
            if any(overlaps((i, j), r) for r in ranges):
                start = i + 1
                continue
            ranges.append((i, j))
            start = j

    if not ranges:
        return None

    ranges.sort()
    out: List[str] = []
    cur = 0
    for s, e in ranges:
        if cur < s:
            out.append(html.escape(txt[cur:s]))
        out.append(f'<mark class="nc-negative">{html.escape(txt[s:e])}</mark>')
        cur = e
    if cur < len(txt):
        out.append(html.escape(txt[cur:]))

    return "".join(out)

# sentiment_articles의 선택 컬럼 프로빙(요약/하이라이트/근거문장)
_SENTI_COLS_CHECKED = False
_HAS_SUMMARY_HTML = False
_HAS_HIGHLIGHT_HTML = False
_HAS_EVIDENCE = False

async def _probe_sentiment_optional_columns(session: AsyncSession) -> None:
    """sentiment_articles에 선택 컬럼이 존재하는지 1회만 점검"""
    global _SENTI_COLS_CHECKED, _HAS_SUMMARY_HTML, _HAS_HIGHLIGHT_HTML, _HAS_EVIDENCE
    if _SENTI_COLS_CHECKED:
        return
    sql = text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'sentiment_articles'
          AND column_name IN ('summary_html','highlight_html','evidence_sentences')
    """)
    rows = (await session.execute(sql)).all()
    names = {r[0] for r in rows}
    _HAS_SUMMARY_HTML   = 'summary_html' in names
    _HAS_HIGHLIGHT_HTML = 'highlight_html' in names
    _HAS_EVIDENCE       = 'evidence_sentences' in names
    _SENTI_COLS_CHECKED = True


# ------------------------------------------------------------------------------ #
# Article list / search  (★ 감정 조인 포함)
# ------------------------------------------------------------------------------ #
ATTITUDE_CASE_SQL = """
    COALESCE(
      CASE
        WHEN sa.sentiment_classification IS NULL THEN NULL
        -- 우호적
        WHEN LOWER(TRIM(sa.sentiment_classification)) IN ('우호', '우호적', '긍정', '긍정적', 'positive', 'pos')
          OR LOWER(TRIM(sa.sentiment_classification)) LIKE 'pos%%'
          OR LOWER(TRIM(sa.sentiment_classification)) LIKE '긍정%%'
          OR LOWER(TRIM(sa.sentiment_classification)) LIKE '우호%%'
        THEN '우호적'
        -- 비판적
        WHEN LOWER(TRIM(sa.sentiment_classification)) IN ('비판', '비판적', '부정', '부정적', 'negative', 'neg')
          OR LOWER(TRIM(sa.sentiment_classification)) LIKE 'neg%%'
          OR LOWER(TRIM(sa.sentiment_classification)) LIKE '부정%%'
          OR LOWER(TRIM(sa.sentiment_classification)) LIKE '비판%%'
        THEN '비판적'
        -- 중립적
        WHEN LOWER(TRIM(sa.sentiment_classification)) IN ('중립', '중립적', 'neutral', 'neu')
          OR LOWER(TRIM(sa.sentiment_classification)) LIKE 'neu%%'
          OR LOWER(TRIM(sa.sentiment_classification)) LIKE '중립%%'
        THEN '중립적'
        ELSE NULL
      END,
      '중립적'
    )
"""

async def list_articles(
    session: AsyncSession,
    *,
    limit: int = 20,
    offset: int = 0,
    category: Optional[str] = None,
    press: Optional[str] = None,
    q: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    conds = ["1=1"]
    params: Dict[str, Any] = {"limit": int(limit), "offset": int(offset)}
    if category:
        conds.append("a.category = :category")
        params["category"] = category
    if press:
        conds.append("a.press = :press")
        params["press"] = press
    if q:
        conds.append("(a.title ILIKE :like OR a.content ILIKE :like OR a.keywords ILIKE :like)")
        params["like"] = f"%{q}%"

    sql = text(f"""
        SELECT
            a.id, a.url, a.category, a.published_at, a.title,
            a.content, a.thumbnail_url, a.reporter, a.press,
            a.keywords, a.scraped_at,
            {ATTITUDE_CASE_SQL} AS attitude,
            sa.confidence   AS attitude_confidence
        FROM original_article a
        LEFT JOIN sentiment_articles sa
          ON sa.original_article_id = a.id
        WHERE {' AND '.join(conds)}
        ORDER BY a.published_at DESC NULLS LAST, a.id DESC
        OFFSET :offset
        LIMIT :limit
    """)
    rows = (await session.execute(sql, params)).mappings().all()

    items: List[Dict[str, Any]] = []
    for r in rows:
        items.append({
            "id": r["id"],
            "url": r.get("url"),
            "category": r.get("category"),
            "published_at": r.get("published_at"),
            "title": r.get("title"),
            "content": r.get("content"),
            "thumbnail_url": r.get("thumbnail_url"),
            "reporter": r.get("reporter"),
            "press": r.get("press"),
            "keywords": r.get("keywords"),
            "scraped_at": r.get("scraped_at"),
            "attitude": r.get("attitude") or "중립적",
            "attitude_confidence": r.get("attitude_confidence"),
        })

    total_sql = text(f"""
        SELECT COUNT(*) AS cnt
        FROM original_article a
        WHERE {' AND '.join(conds)}
    """)
    total = (await session.execute(total_sql, params)).scalar_one()
    return items, int(total)


async def get_article(session: AsyncSession, article_id: str) -> Dict[str, Any]:
    """
    단건 조회 + sentiment_articles(감정/증거문장) + summarized_articles(요약) 조인.
    """
    attitude_case = """
        COALESCE(
          CASE
            WHEN sa.sentiment_classification IS NULL THEN NULL
            WHEN LOWER(TRIM(sa.sentiment_classification)) IN ('우호','우호적','긍정','긍정적','positive','pos')
              OR LOWER(TRIM(sa.sentiment_classification)) LIKE 'pos%%'
              OR LOWER(TRIM(sa.sentiment_classification)) LIKE '긍정%%'
              OR LOWER(TRIM(sa.sentiment_classification)) LIKE '우호%%'
            THEN '우호적'
            WHEN LOWER(TRIM(sa.sentiment_classification)) IN ('비판','비판적','부정','부정적','negative','neg')
              OR LOWER(TRIM(sa.sentiment_classification)) LIKE 'neg%%'
              OR LOWER(TRIM(sa.sentiment_classification)) LIKE '부정%%'
              OR LOWER(TRIM(sa.sentiment_classification)) LIKE '비판%%'
            THEN '비판적'
            WHEN LOWER(TRIM(sa.sentiment_classification)) IN ('중립','중립적','neutral','neu')
              OR LOWER(TRIM(sa.sentiment_classification)) LIKE 'neu%%'
              OR LOWER(TRIM(sa.sentiment_classification)) LIKE '중립%%'
            THEN '중립적'
            ELSE NULL
          END,
          '중립적'
        )
    """

    sql = text(f"""
        SELECT
            a.id, a.url, a.category, a.published_at, a.title,
            a.content, a.thumbnail_url, a.reporter, a.press,
            a.keywords, a.scraped_at,

            {attitude_case}  AS attitude,
            sa.confidence    AS attitude_confidence,
            sa.evidence_sentences AS evidence_sentences,

            sm.summary_content AS summary_json
        FROM original_article a
        LEFT JOIN sentiment_articles sa
          ON sa.original_article_id = a.id
        LEFT JOIN LATERAL (
            SELECT summary_content
            FROM summarized_articles s
            WHERE s.original_article_id = a.id
            ORDER BY s.summarized_at DESC
            LIMIT 1
        ) sm ON TRUE
        WHERE a.id = :aid
        LIMIT 1
    """)
    row = (await session.execute(sql, {"aid": article_id})).mappings().first()
    if not row:
        raise KeyError("article not found")

    # evidence_sentences 정규화
    evidence_items: List[str] = []
    ev = row.get("evidence_sentences")
    if isinstance(ev, (list, tuple)):
        evidence_items = [str(x).strip() for x in ev if str(x).strip()]
    elif isinstance(ev, str):
        s = ev.strip()
        if s.startswith("{") and s.endswith("}"):
            s = s[1:-1]
            parts = []
            buf = ""
            in_quote = False
            i = 0
            while i < len(s):
                ch = s[i]
                if ch == '"':
                    in_quote = not in_quote
                elif ch == "," and not in_quote:
                    parts.append(buf)
                    buf = ""
                else:
                    buf += ch
                i += 1
            if buf:
                parts.append(buf)
            evidence_items = [p.replace('""', '"').strip().strip('"') for p in parts if p.strip().strip('"')]
        else:
            if s:
                evidence_items = [s]

    # summary_content(JSON) → summary_items(list[str])
    summary_items: List[str] = []
    raw = row.get("summary_json")
    if raw:
        try:
            obj = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(obj, dict) and "summary" in obj:
                val = obj["summary"]
            else:
                val = obj
            if isinstance(val, list):
                summary_items = [str(x).strip() for x in val if str(x).strip()]
            elif isinstance(val, str) and val.strip():
                summary_items = [val.strip()]
        except Exception:
            pass

    return {
        "id": row["id"],
        "url": row.get("url"),
        "category": row.get("category"),
        "published_at": row.get("published_at"),
        "title": row.get("title"),
        "content": row.get("content"),
        "thumbnail_url": row.get("thumbnail_url"),
        "reporter": row.get("reporter"),
        "press": row.get("press"),
        "keywords": row.get("keywords"),
        "scraped_at": row.get("scraped_at"),
        "attitude": row.get("attitude"),
        "attitude_confidence": row.get("attitude_confidence"),
        "evidence_sentences": evidence_items,
        "summary_items": summary_items,
    }

# ------------------------------------------------------------------------------ #
# Bundle (article + optional sentiment/cleanse/reco)
# ------------------------------------------------------------------------------ #
async def _fallback_reco(
    session: AsyncSession, article_id: str, category: str, n: int = 5
) -> Dict[str, Any]:
    stmt = (
        select(
            Article.id,
            Article.title,
            Article.category,
            Article.press,
            Article.published_at,
            Article.thumbnail_url,
        )
        .where(Article.id != article_id)
        .order_by(desc(Article.published_at))
        .limit(n)
    )
    if category:
        stmt = stmt.where(Article.category == category)

    rows = (await session.execute(stmt)).all()
    return {
        "items": [_row_to_dict(r) for r in rows],
        "model_version": "fallback-category-latest",
    }


async def bundle_article(
    session: AsyncSession, article_id: str, user_id: str
) -> Dict[str, Any]:
    art = await get_article(session, article_id)
    payload = {"article_id": article_id, "text": art.get("content", "")}

    senti = clnz = reco = None
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        if SENTI_URL:
            try:
                r = await client.post(f"{SENTI_URL}/analyze", json=payload)
                r.raise_for_status()
                senti = r.json()
            except Exception:
                senti = None

        if CLEANSE_URL:
            try:
                r = await client.post(f"{CLEANSE_URL}/cleanse", json=payload)
                r.raise_for_status()
                clnz = r.json()
            except Exception:
                clnz = None

        if RECO_URL:
            try:
                r = await client.get(
                    f"{RECO_URL}/recommend",
                    params={"article_id": article_id, "user_id": user_id},
                )
                r.raise_for_status()
                reco = r.json()
            except Exception:
                reco = None

    if not reco:
        reco = await _fallback_reco(session, article_id, art.get("category", ""))

    return {
        "article": {
            "id": art["id"],
            "url": art.get("url"),
            "title": art.get("title"),
            "category": art.get("category"),
            "press": art.get("press"),
            "published_at": art.get("published_at"),
            "thumbnail_url": art.get("thumbnail_url"),
            "reporter": art.get("reporter"),
            "keywords": art.get("keywords"),
            "content": art.get("content"),
            "summary": (clnz or {}).get("summary"),
            "cleaned_html": (clnz or {}).get("cleaned_html"),
            "attitude": art.get("attitude"),
            "attitude_confidence": art.get("attitude_confidence"),
        },
        "analysis": {"sentiment": senti},
        "recommendations": reco.get("items", []),
    }


# ------------------------------------------------------------------------------ #
# Read open/close
# ------------------------------------------------------------------------------ #
async def open_read(session: AsyncSession, article_id: str, user_id: str) -> str:
    now = datetime.utcnow()

    existing = (
        await session.execute(
            select(ArticleRead)
            .where(
                and_(
                    ArticleRead.user_id == int(user_id),
                    ArticleRead.article_id == article_id,
                    ArticleRead.closed_at.is_(None),
                )
            )
            .order_by(desc(ArticleRead.opened_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing:
        return str(existing.id)

    row = ArticleRead(
        user_id=int(user_id),
        article_id=article_id,
        opened_at=now,
    )
    session.add(row)
    await session.flush()
    read_id = row.id

    session.add(
        UserEvent(
            user_id=int(user_id),
            event_type="article_open",
            article_id=article_id,
            meta={},
            ts=now,
        )
    )
    await session.commit()
    return str(read_id)


async def close_read(
    session: AsyncSession, article_id: str, user_id: str, read_id: str
) -> int:
    row = (
        await session.execute(
            select(ArticleRead).where(
                ArticleRead.id == int(read_id),
                ArticleRead.user_id == int(user_id),
                ArticleRead.article_id == article_id,
            )
        )
    ).scalar_one_or_none()
    if not row:
        return -1

    now = datetime.utcnow()
    opened_at = row.opened_at or now

    row.closed_at = now
    row.dwell_seconds = max(0, int((now - opened_at).total_seconds()))

    session.add(
        UserEvent(
            user_id=int(user_id),
            event_type="article_close",
            article_id=article_id,
            meta={"dwell_seconds": row.dwell_seconds},
            ts=now,
        )
    )
    await session.commit()
    return row.dwell_seconds


# ------------------------------------------------------------------------------ #
# Events ingest (batch)
# ------------------------------------------------------------------------------ #
async def ingest_events(session: AsyncSession, items: List[Dict[str, Any]]) -> int:
    now = datetime.utcnow()
    objs: List[UserEvent] = []

    for e in items:
        try:
            uid = int(e.get("user_id"))
        except Exception:
            continue
        objs.append(
            UserEvent(
                user_id=uid,
                event_type=str(e.get("event_type")),
                article_id=e.get("article_id"),
                meta=e.get("metadata") or e.get("meta") or {},
                ts=e.get("ts") or now,
            )
        )

    if objs:
        session.add_all(objs)
        await session.commit()
    return len(objs)


# ------------------------------------------------------------------------------ #
# Analytics (stats)
# ------------------------------------------------------------------------------ #
async def get_article_stats(session: AsyncSession, article_id: str) -> dict:
    q = select(
        func.count().label("readers"),
        func.coalesce(func.sum(ArticleRead.dwell_seconds), 0).label("total_dwell"),
        func.coalesce(func.avg(ArticleRead.dwell_seconds), 0).label("avg_dwell"),
    ).where(ArticleRead.article_id == article_id)
    r = (await session.execute(q)).one()
    return {
        "readers": int(r.readers),
        "total_dwell": int(r.total_dwell),
        "avg_dwell": int(r.avg_dwell),
    }


# ------------------------------------------------------------------------------ #
# User today / week (KST)
# ------------------------------------------------------------------------------ #
async def get_user_today(session: AsyncSession, user_id: str) -> dict:
    start_kst, end_kst = _kst_today_window()

    q = select(
        func.count().label("reads"),
        func.coalesce(func.sum(ArticleRead.dwell_seconds), 0).label("total_dwell"),
    ).where(
        ArticleRead.user_id == int(user_id),
        ArticleRead.opened_at >= start_kst,
        ArticleRead.opened_at < end_kst,
    )
    r = (await session.execute(q)).one()
    return {"reads": int(r.reads), "total_dwell": int(r.total_dwell)}


async def list_user_reads_today(
    session: AsyncSession, user_id: str, *, limit: int = 50, offset: int = 0
) -> dict:
    start_kst, end_kst = _kst_today_window()

    base = (
        select(
            ArticleRead.id.label("read_id"),
            ArticleRead.opened_at,
            ArticleRead.closed_at,
            ArticleRead.dwell_seconds,
            Article.id.label("article_id"),
            Article.title,
            Article.category,
            Article.press,
            Article.published_at,
            Article.thumbnail_url,
        )
        .join(Article, Article.id == ArticleRead.article_id)
        .where(
            ArticleRead.user_id == int(user_id),
            ArticleRead.opened_at >= start_kst,
            ArticleRead.opened_at < end_kst,
        )
        .order_by(desc(ArticleRead.opened_at))
    )

    rows = (await session.execute(base.offset(offset).limit(limit))).all()
    items = [_read_row_to_dict(r._mapping) for r in rows]

    total = (
        await session.execute(
            select(func.count())
            .select_from(ArticleRead)
            .where(
                ArticleRead.user_id == int(user_id),
                ArticleRead.opened_at >= start_kst,
                ArticleRead.opened_at < end_kst,
            )
        )
    ).scalar_one()

    return {"items": items, "limit": limit, "offset": offset, "total": int(total)}


async def list_user_reads_week(
    session: AsyncSession, user_id: str, *, limit: int = 50, offset: int = 0
) -> dict:
    seoul_opened = func.timezone(KST, ArticleRead.opened_at)
    seoul_now = func.timezone(KST, func.now())

    base = (
        select(
            ArticleRead.id.label("read_id"),
            ArticleRead.opened_at,
            ArticleRead.closed_at,
            ArticleRead.dwell_seconds,
            Article.id.label("article_id"),
            Article.title,
            Article.category,
            Article.press,
            Article.published_at,
            Article.thumbnail_url,
        )
        .join(Article, Article.id == ArticleRead.article_id)
        .where(
            ArticleRead.user_id == int(user_id),
            func.date_trunc("week", seoul_opened)
            == func.date_trunc("week", seoul_now),
        )
        .order_by(desc(ArticleRead.opened_at))
    )

    rows = (await session.execute(base.offset(offset).limit(limit))).all()
    items = [_read_row_to_dict(r._mapping) for r in rows]

    total = (
        await session.execute(
            select(func.count())
            .select_from(ArticleRead)
            .where(
                ArticleRead.user_id == int(user_id),
                func.date_trunc("week", seoul_opened)
                == func.date_trunc("week", seoul_now),
            )
        )
    ).scalar_one()

    return {"items": items, "limit": limit, "offset": offset, "total": int(total)}


# ------------------------------------------------------------------------------ #
# Field stats
# ------------------------------------------------------------------------------ #
async def get_user_field_stats(
    session: AsyncSession,
    user_id: str,
    *,
    days: int = 7,
    metric: str = "reads",
    mode: str = "rolling",
) -> Dict[str, Any]:
    value_col = (
        func.count().label("value")
        if metric != "dwell"
        else func.coalesce(func.sum(ArticleRead.dwell_seconds), 0).label("value")
    )

    cat_norm = case(
        (Article.category.in_(["문화", "생활/문화"]), "문화"),
        (Article.category.in_(["과학", "IT/과학", "IT"]), "과학"),
        (Article.category.in_(["국제", "세계"]), "세계"),
        (Article.category == "경제", "경제"),
        (Article.category == "정치", "정치"),
        (Article.category == "사회", "사회"),
        else_=func.coalesce(Article.category, "기타"),
    )

    label_expr = case(
        (Article.id.ilike("eco%"), "경제"),
        (Article.id.ilike("pol%"), "정치"),
        (Article.id.ilike("soc%"), "사회"),
        (Article.id.ilike("lif%"), "문화"),
        (Article.id.ilike("sci%"), "과학"),
        (Article.id.ilike("int%"), "세계"),
        else_=cat_norm,
    ).label("label")

    base = (
        select(label_expr, value_col)
        .select_from(ArticleRead)
        .join(Article, Article.id == ArticleRead.article_id)
        .where(ArticleRead.user_id == int(user_id))
    )

    # ✅ opened_at을 KST 벽시계로 변환
    opened_kst = _to_kst(ArticleRead.opened_at)
    now_kst = _now_kst()

    if mode == "day":
        # 오늘 00:00 ~ 내일 00:00 (KST)
        start = func.date_trunc("day", now_kst)
        end = start + text("interval '1 day'")
        base = base.where(opened_kst >= start, opened_kst < end)
    elif mode == "week":
        base = base.where(
            func.date_trunc("week", opened_kst) == func.date_trunc("week", now_kst)
        )
    else:  # rolling
        base = base.where(
            opened_kst >= (now_kst - text(f"interval '{int(days)} day'"))
        )

    q = base.group_by(label_expr).order_by(desc("value"))
    rows = (await session.execute(q)).all()

    counts: Dict[str, int] = {}
    for r in rows:
        label = (r.label or "기타")
        counts[label] = int(r.value)

    stats = []
    for cat in DISPLAY_CATEGORIES:
        c = counts.get(cat, 0)
        stats.append({"label": cat, "value": c, "count": c})

    max_value = max([s["value"] for s in stats]) if stats else 0

    return {
        "field_stats": stats,
        "max_value": max_value,
        "metric": metric,
        "mode": mode,
        "days": days,
    }


# ------------------------------------------------------------------------------ #
# Hourly activity
# ------------------------------------------------------------------------------ #
async def get_user_hourly_activity(
    session: AsyncSession,
    user_id: str,
    *,
    days: int = 7,
    mode: str = "rolling",
) -> Dict[str, Any]:
    hour_expr = func.extract("hour", func.timezone(KST, ArticleRead.opened_at)).label("hour")

    base = (
        select(hour_expr, func.count().label("cnt"))
        .select_from(ArticleRead)
        .where(ArticleRead.user_id == int(user_id))
    )

    if mode == "week":
        seoul_opened = func.timezone(KST, ArticleRead.opened_at)
        seoul_now = func.timezone(KST, func.now())
        base = base.where(
            func.date_trunc("week", seoul_opened) == func.date_trunc("week", seoul_now)
        )
    else:
        base = base.where(
            ArticleRead.opened_at >= (func.now() - text(f"interval '{int(days)} days'"))
        )

    q = base.group_by(hour_expr).order_by(hour_expr.asc())
    rows = (await session.execute(q)).all()

    m = {int(r.hour): int(r.cnt) for r in rows}
    bins = [{"hour": h, "count": m.get(h, 0)} for h in range(24)]
    total = sum(m.values())
    return {"bins": bins, "total": int(total)}


# ------------------------------------------------------------------------------ #
# Home Feed
# ------------------------------------------------------------------------------ #
async def get_home_feed(
    session: AsyncSession,
    user_id: str,
    *,
    exclude_read: bool = True,
) -> Dict[str, Any]:
    uid = int(user_id)
    seed = _daily_seed(uid, date.today())
    days_back = FEED_LOOKBACK_DAYS

    counts_sql = text("""
    SELECT
      COALESCE(
        CASE
          WHEN r.article_id ILIKE 'eco%%' THEN '경제'
          WHEN r.article_id ILIKE 'pol%%' THEN '정치'
          WHEN r.article_id ILIKE 'soc%%' THEN '사회'
          WHEN r.article_id ILIKE 'lif%%' THEN '문화'
          WHEN r.article_id ILIKE 'sci%%' THEN '과학'
          WHEN r.article_id ILIKE 'int%%' THEN '세계'
          ELSE NULL
        END,
        CASE
          WHEN a.category IN ('문화','생활/문화') THEN '문화'
          WHEN a.category IN ('과학','IT/과학','IT') THEN '과학'
          WHEN a.category IN ('국제','세계') THEN '세계'
          WHEN a.category = '경제' THEN '경제'
          WHEN a.category = '정치' THEN '정치'
          WHEN a.category = '사회' THEN '사회'
          ELSE NULL
        END
      ) AS label,
      COUNT(*) AS cnt
    FROM article_reads r
    LEFT JOIN original_article a ON a.id = r.article_id
    WHERE r.user_id = :uid
      AND r.opened_at >= (now() - interval '1 day')
    GROUP BY label
    """)
    cnt_rows = (await session.execute(counts_sql, {"uid": uid})).all()
    read_counts: Dict[str, int] = {row.label: int(row.cnt) for row in cnt_rows if row.label}
    read_counts = {c: read_counts.get(c, 0) for c in DISPLAY_CATEGORIES}

    limits: Dict[str, int] = {}
    for c in DISPLAY_CATEGORIES:
        rc = read_counts.get(c, 0)
        limits[c] = 6 if rc >= 10 else (5 if rc >= 5 else 3)
    max_limit = max(limits.values()) if limits else 6

    date_clause = """
      AND COALESCE(a.published_at, a.scraped_at)
          >= CURRENT_DATE - (:days * interval '1 day')
    """
    label_allow = "('경제','정치','사회','문화','세계','과학')"

    exclude_clause = ""
    if exclude_read:
        exclude_clause = """
        AND NOT EXISTS (
            SELECT 1
            FROM article_reads r
            WHERE r.user_id = :uid
              AND r.article_id = a.id
              AND r.opened_at >= (now() - interval '1 day')
        )
        """

    label_case = """
        CASE
          WHEN a.id ILIKE 'eco%' THEN '경제'
          WHEN a.id ILIKE 'pol%' THEN '정치'
          WHEN a.id ILIKE 'soc%' THEN '사회'
          WHEN a.id ILIKE 'lif%' THEN '문화'
          WHEN a.id ILIKE 'sci%' THEN '과학'
          WHEN a.id ILIKE 'int%' THEN '세계'
          WHEN a.category IN ('문화','생활/문화') THEN '문화'
          WHEN a.category IN ('과학','IT/과학','IT') THEN '과학'
          WHEN a.category IN ('국제','세계') THEN '세계'
          WHEN a.category='경제' THEN '경제'
          WHEN a.category='정치' THEN '정치'
          WHEN a.category='사회' THEN '사회'
          ELSE COALESCE(a.category,'기타')
        END
    """

    # 감정/신뢰도 포함
    base_sql_tmpl = f"""
    WITH base AS (
      SELECT
        a.id, a.title, a.press, a.category, a.thumbnail_url,
        a.published_at, a.scraped_at,
        {label_case} AS label,
        {ATTITUDE_CASE_SQL} AS attitude,
        sa.confidence AS attitude_confidence
      FROM original_article a
      LEFT JOIN sentiment_articles sa
        ON sa.original_article_id = a.id
      WHERE 1=1
        {{date_clause}}
        AND ({label_case}) IN {label_allow}
        {{exclude_clause}}
    ),
    ranked AS (
      SELECT
        id, title, press, category, thumbnail_url, published_at, label,
        attitude, attitude_confidence,
        ROW_NUMBER() OVER (PARTITION BY label ORDER BY md5(id::text || :seed)) AS rn
      FROM base
    )
    SELECT id, title, press, category, thumbnail_url, published_at, label,
           attitude, attitude_confidence, rn
    FROM ranked
    WHERE rn <= :max_limit
    """
    sql_1 = text(base_sql_tmpl.format(date_clause=date_clause, exclude_clause=exclude_clause))
    params_1 = {"uid": uid, "seed": seed, "days": int(days_back), "max_limit": int(max_limit)}
    rows = (await session.execute(sql_1, params_1)).mappings().all()

    bucket: Dict[str, List[Dict[str, Any]]] = {c: [] for c in DISPLAY_CATEGORIES}
    for r in rows:
        c = r["label"]
        if c in bucket and len(bucket[c]) < limits[c]:
            bucket[c].append({
                "id": r["id"],
                "title": r["title"],
                "category": r["category"],
                "press": r["press"],
                "published_at": r["published_at"],
                "thumbnail_url": r["thumbnail_url"],
                "attitude": r.get("attitude"),
                "attitude_confidence": r.get("attitude_confidence"),
            })

    def shortages() -> Dict[str, int]:
        return {c: (limits[c] - len(bucket[c])) for c in DISPLAY_CATEGORIES if len(bucket[c]) < limits[c]}

    short = shortages()

    if short:
        sql_2 = text(base_sql_tmpl.format(date_clause="", exclude_clause=exclude_clause))
        params_2 = {"uid": uid, "seed": seed, "max_limit": int(max_limit)}
        rows2 = (await session.execute(sql_2, params_2)).mappings().all()
        for r in rows2:
            c = r["label"]
            if c in bucket and len(bucket[c]) < limits[c]:
                bucket[c].append({
                    "id": r["id"],
                    "title": r["title"],
                    "category": r["category"],
                    "press": r["press"],
                    "published_at": r["published_at"],
                    "thumbnail_url": r["thumbnail_url"],
                    "attitude": r.get("attitude"),
                    "attitude_confidence": r.get("attitude_confidence"),
                })
        short = shortages()

    if short:
        max_need = max(short.values())
        fill_sql = text(f"""
        WITH base AS (
          SELECT
            a.id, a.title, a.press, a.category, a.thumbnail_url,
            a.published_at, a.scraped_at,
            {label_case} AS label,
            {ATTITUDE_CASE_SQL} AS attitude,
            sa.confidence AS attitude_confidence,
            COALESCE(a.published_at, a.scraped_at) AS ts
          FROM original_article a
          LEFT JOIN sentiment_articles sa
            ON sa.original_article_id = a.id
          WHERE ({label_case}) IN {label_allow}
        ),
        ranked AS (
          SELECT
            id, title, press, category, thumbnail_url, published_at, label, ts,
            attitude, attitude_confidence,
            ROW_NUMBER() OVER (PARTITION BY label ORDER BY ts DESC NULLS LAST, id DESC) AS rn
          FROM base
        )
        SELECT id, title, press, category, thumbnail_url, published_at, label,
               attitude, attitude_confidence, rn
        FROM ranked
        WHERE rn <= :max_need
        """)
        rows3 = (await session.execute(fill_sql, {"max_need": int(max_need)})).mappings().all()
        for r in rows3:
            c = r["label"]
            if c in bucket and len(bucket[c]) < limits[c]:
                bucket[c].append({
                    "id": r["id"],
                    "title": r["title"],
                    "category": r["category"],
                    "press": r["press"],
                    "published_at": r["published_at"],
                    "thumbnail_url": r["thumbnail_url"],
                    "attitude": r.get("attitude"),
                    "attitude_confidence": r.get("attitude_confidence"),
                })

    order_for_all = sorted(DISPLAY_CATEGORIES, key=lambda c: (-read_counts.get(c, 0), c))

    sections = [
        {
            "category": c,
            "read_today": read_counts.get(c, 0),
            "limit": limits[c],
            "pinned": limits[c] > 3,
            "articles": bucket[c],
        }
        for c in order_for_all
    ]

    return {
        "date": date.today().isoformat(),
        "seed": seed,
        "order_for_all": order_for_all,
        "sections": sections,
    }

# ------------------------------------------------------------------------------ #
# Mood: 기록/스냅샷
# ------------------------------------------------------------------------------ #
async def record_mood_event(
    session: AsyncSession,
    user_id: str,
    delta: int,
    reason: str,
    attitude: Optional[str] = None,
    article_id: Optional[str] = None,
    ts: Optional[datetime] = None,
) -> int:
    """user_events에 event_type='mood' 로 한 줄 기록"""
    now = ts or datetime.utcnow()
    obj = UserEvent(
        user_id=int(user_id),
        event_type="mood",
        article_id=article_id,
        meta={"delta": int(delta), "reason": reason, "attitude": attitude},
        ts=now,
    )
    session.add(obj)
    await session.flush()
    await session.commit()
    return int(obj.id)



async def get_user_mood_snapshot(session: AsyncSession, user_id: str, *, days: int = 7) -> Dict[str, Any]:
    days = 7

    # ✅ KST now / event ts(KST)
    seoul_now = _now_kst()
    seoul_ts = _to_kst(UserEvent.ts)

    day_str = func.to_char(func.date_trunc("day", seoul_ts), "YYYY-MM-DD").label("day")

    delta_text = func.jsonb_extract_path_text(UserEvent.meta.cast(JSONB), 'delta')
    sum_delta = func.coalesce(
        func.sum(
            case(
                (delta_text.op('~')('^-?[0-9]+(\\.[0-9]+)?$'), cast(delta_text, Numeric())),
                else_=0.0,
            )
        ),
        0.0,
    ).label("sum_delta")

    window_start = seoul_now - text(f"interval '{int(days)} day'")

    q = (
        select(day_str, sum_delta)
        .where(
            UserEvent.user_id == int(user_id),
            UserEvent.event_type.in_(["mood", "stress_delta"]),
            seoul_ts >= window_start,
        )
        .group_by(day_str)
        .order_by(day_str.asc())
    )
    rows = (await session.execute(q)).all()
    m = {r.day: float(r.sum_delta or 0.0) for r in rows}

    today_str = (
        await session.execute(
            select(func.to_char(func.date_trunc("day", seoul_now), "YYYY-MM-DD"))
        )
    ).scalar_one()

    today_date = datetime.strptime(today_str, "%Y-%m-%d").date()
    days_list = []
    for i in range(days - 1, -1, -1):
        d = (today_date - timedelta(days=i)).isoformat()
        score = BASELINE_STRESS + m.get(d, 0.0)
        days_list.append({"date": d, "score": int(round(score))})

    today_score = days_list[-1]["score"] if days_list else BASELINE_STRESS

    s = today_score
    if s <= 20:   emoji, word = "😌", "매우 안정"
    elif s <= 40: emoji, word = "😊", "안정"
    elif s <= 60: emoji, word = "🙂", "평온"
    elif s <= 80: emoji, word = "😟", "긴장"
    else:         emoji, word = "😣", "불안"

    week_bins = [{"dow": i, "cnt": 0, "sum": 0, "avg": None} for i in range(7)]
    for d in days_list:
        dt = datetime.strptime(d["date"], "%Y-%m-%d").date()
        dow = (dt.weekday() + 1) % 7
        week_bins[dow]["cnt"] += 1
        week_bins[dow]["sum"] += d["score"]
    for b in week_bins:
        if b["cnt"]:
            b["avg"] = int(round(b["sum"] / b["cnt"]))

    return {
        "date": today_str,
        "score": int(today_score),
        "emoji": emoji,
        "word": word,
        "days": days_list,
        "week": [{"dow": b["dow"], "avg": b["avg"], "cnt": b["cnt"]} for b in week_bins],
        "baseline": BASELINE_STRESS,
    }
