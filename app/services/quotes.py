from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MotivationQuote
from app.utils.datetime_utils import now
from app.utils.logging import get_logger

logger = get_logger(__name__)

SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "motivation_seed.json"

# Ночная ротация пула (без AI)
NIGHTLY_RETIRE = 8
NIGHTLY_REACTIVATE = 6
MIN_ACTIVE_BY_KIND = {"morning": 60, "hourly": 50, "rest": 40}

HARD_FALLBACK = {
    "morning": "Дисциплина сегодня = свобода завтра.",
    "hourly": "Сейчас только этот блок. Всё остальное подождёт.",
    "rest": (
        "Отдых — не пауза в прогрессе, а его топливо. "
        "Сегодня восстановишься — завтра будешь сильнее."
    ),
}

# Темы цитат по типу блока расписания (приоритет слева направо).
BLOCK_THEME_MAP: dict[str, list[str]] = {
    "routine_morning": ["routine_morning", "discipline", "drive"],
    "routine_evening": ["routine_evening", "discipline", "focus"],
    "university": ["university", "study", "focus"],
    "study": ["study", "it", "focus"],
    "english": ["english", "study", "focus"],
    "gym": ["sport", "drive", "discipline"],
    "it": ["it", "focus", "excellence"],
    "recovery": ["recovery", "rest"],
    "sleep": ["sleep", "rest", "recovery"],
    "free": ["focus", "drive", "discipline"],
}

THEME_FALLBACK = {
    "sport": "Зал — это час, где ты выбираешь себя сильнее.",
    "it": "Сейчас только задача перед тобой. Остальное — шум.",
    "english": "Практика сегодня — уверенность завтра.",
    "university": "Учёба любит ритм: пришёл, включился, зафиксировал.",
    "study": "Одна законченная тема сильнее десяти начатых.",
    "routine_morning": "Утро задаёт тон. Сделай первые действия чётко.",
    "routine_evening": "Закрой день аккуратно — завтра начнётся чище.",
    "sleep": "Сон — не награда. Это часть системы.",
    "recovery": "Recovery — не лень. Это стратегия на длинной дистанции.",
}


def themes_for_block(block_kind: str | object | None) -> list[str]:
    if block_kind is None:
        return []
    key = getattr(block_kind, "value", None) or str(block_kind)
    return list(BLOCK_THEME_MAP.get(key, []))


def _normalize(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _hash_text(text: str, *, kind: str = "") -> str:
    payload = f"{kind}:{_normalize(text).lower()}" if kind else _normalize(text).lower()
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def ensure_seeded(session: AsyncSession) -> int:
    """Добавляет недостающие seed-цитаты (идемпотентно по kind+text_hash)."""
    if not SEED_PATH.exists():
        logger.warning("motivation_seed_missing", path=str(SEED_PATH))
        return 0

    raw = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    result = await session.execute(select(MotivationQuote.text_hash))
    existing = {row[0] for row in result.all()}

    added = 0
    seen: set[str] = set()
    for row in raw:
        text = _normalize(row.get("text", ""))
        kind = (row.get("kind") or "morning").strip()
        theme = (row.get("theme") or "general").strip()
        if not text or kind not in {"morning", "hourly", "rest"}:
            continue
        h = _hash_text(text, kind=kind)
        if h in seen or h in existing:
            continue
        seen.add(h)
        session.add(
            MotivationQuote(
                kind=kind,
                theme=theme,
                text=text,
                text_hash=h,
                source="seed",
                is_active=True,
            )
        )
        added += 1
    if added:
        await session.flush()
        logger.info("motivation_seed_loaded", added=added)
    return added


async def pick_quote(
    session: AsyncSession,
    *,
    kind: str,
    themes: list[str] | None = None,
    mark_used: bool = True,
) -> str:
    """
    Берёт наименее изношенную активную цитату нужного типа.
    Если переданы themes — сначала ищет среди них (по порядку приоритета),
    иначе / при пустом результате — любую цитату этого kind.
    """
    kind = kind if kind in HARD_FALLBACK else "morning"
    theme_list = [t for t in (themes or []) if t]

    async def _candidates(*, theme: str | None = None, limit: int = 12):
        clauses = [
            MotivationQuote.kind == kind,
            MotivationQuote.is_active.is_(True),
        ]
        if theme:
            clauses.append(MotivationQuote.theme == theme)
        result = await session.execute(
            select(MotivationQuote)
            .where(*clauses)
            .order_by(
                MotivationQuote.last_used_at.asc().nulls_first(),
                MotivationQuote.use_count.asc(),
                func.random(),
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    candidates: list[MotivationQuote] = []
    for theme in theme_list:
        candidates = await _candidates(theme=theme)
        if candidates:
            break

    if not candidates:
        candidates = await _candidates(theme=None)

    if not candidates:
        result = await session.execute(
            select(MotivationQuote)
            .where(MotivationQuote.is_active.is_(True))
            .order_by(MotivationQuote.last_used_at.asc().nulls_first())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is None:
            if theme_list and theme_list[0] in THEME_FALLBACK:
                return THEME_FALLBACK[theme_list[0]]
            return HARD_FALLBACK[kind]
        candidates = [row]

    quote = random.choice(candidates[:5]) if len(candidates) > 1 else candidates[0]
    if mark_used:
        quote.use_count = int(quote.use_count or 0) + 1
        quote.last_used_at = now()
        await session.flush()
    return quote.text


async def nightly_partial_refresh(session: AsyncSession) -> dict[str, int]:
    """
    Частичная ротация базы в 23:00:
    1) утомлённые цитаты временно выключаются
    2) давно выключенные снова включаются
    """
    stats = {"retired": 0, "reactivated": 0}

    result = await session.execute(
        select(MotivationQuote)
        .where(
            MotivationQuote.is_active.is_(True),
            MotivationQuote.use_count >= 2,
        )
        .order_by(
            MotivationQuote.use_count.desc(),
            MotivationQuote.last_used_at.desc().nulls_last(),
        )
        .limit(NIGHTLY_RETIRE)
    )
    for row in result.scalars().all():
        cnt = await session.execute(
            select(func.count()).where(
                MotivationQuote.kind == row.kind,
                MotivationQuote.is_active.is_(True),
            )
        )
        active_n = int(cnt.scalar_one() or 0)
        if active_n <= MIN_ACTIVE_BY_KIND.get(row.kind, 30):
            continue
        row.is_active = False
        stats["retired"] += 1
    await session.flush()

    result = await session.execute(
        select(MotivationQuote)
        .where(MotivationQuote.is_active.is_(False))
        .order_by(
            MotivationQuote.use_count.asc(),
            MotivationQuote.updated_at.asc(),
        )
        .limit(NIGHTLY_REACTIVATE * 3)
    )
    reactivated = 0
    for row in result.scalars().all():
        if reactivated >= NIGHTLY_REACTIVATE:
            break
        row.is_active = True
        row.use_count = max(0, int(row.use_count or 0) // 2)
        reactivated += 1
    stats["reactivated"] = reactivated
    await session.flush()

    logger.info("motivation_pool_refreshed", **stats)
    return stats


async def pool_stats(session: AsyncSession) -> dict[str, int]:
    result = await session.execute(
        select(
            MotivationQuote.kind,
            MotivationQuote.is_active,
            func.count(),
        ).group_by(MotivationQuote.kind, MotivationQuote.is_active)
    )
    out: dict[str, int] = {}
    for kind, active, cnt in result.all():
        key = f"{kind}_{'active' if active else 'idle'}"
        out[key] = int(cnt)
    return out
