from __future__ import annotations

import hashlib
import json
import random
import re
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MotivationQuote
from app.services.ai import GeminiService
from app.utils.datetime_utils import now
from app.utils.logging import get_logger

logger = get_logger(__name__)

SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "motivation_seed.json"

# Ночное обновление
NIGHTLY_ADD = 12
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
    mark_used: bool = True,
) -> str:
    """
    Берёт наименее изношенную активную цитату нужного типа.
    Приоритет: давно не использовалась → мало использовалась → случайность.
    """
    kind = kind if kind in HARD_FALLBACK else "morning"
    result = await session.execute(
        select(MotivationQuote)
        .where(MotivationQuote.kind == kind, MotivationQuote.is_active.is_(True))
        .order_by(
            MotivationQuote.last_used_at.asc().nulls_first(),
            MotivationQuote.use_count.asc(),
            func.random(),
        )
        .limit(12)
    )
    candidates = list(result.scalars().all())
    if not candidates:
        # fallback: любой kind, потом hard
        result = await session.execute(
            select(MotivationQuote)
            .where(MotivationQuote.is_active.is_(True))
            .order_by(MotivationQuote.last_used_at.asc().nulls_first())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return HARD_FALLBACK[kind]
        candidates = [row]

    quote = random.choice(candidates[:5]) if len(candidates) > 1 else candidates[0]
    if mark_used:
        quote.use_count = int(quote.use_count or 0) + 1
        quote.last_used_at = now()
        await session.flush()
    return quote.text


async def save_quote_if_new(
    session: AsyncSession,
    *,
    text: str,
    kind: str,
    theme: str = "ai",
    source: str = "ai_saved",
) -> bool:
    """Сохраняет удачный AI-текст в пул (без дублей)."""
    text = _normalize(text)
    if len(text) < 25 or len(text) > 1200:
        return False
    if kind not in {"morning", "hourly", "rest"}:
        return False
    h = _hash_text(text, kind=kind)
    exists = await session.execute(
        select(MotivationQuote.id).where(MotivationQuote.text_hash == h).limit(1)
    )
    if exists.scalar_one_or_none() is not None:
        return False
    session.add(
        MotivationQuote(
            kind=kind,
            theme=theme,
            text=text,
            text_hash=h,
            source=source,
            is_active=True,
        )
    )
    await session.flush()
    return True


def _parse_ai_quote_list(raw: str) -> list[str]:
    """Достаёт список цитат из ответа модели."""
    text = (raw or "").strip()
    if not text:
        return []
    # JSON array
    try:
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            data = json.loads(text[start : end + 1])
            if isinstance(data, list):
                return [_normalize(str(x)) for x in data if _normalize(str(x))]
    except json.JSONDecodeError:
        pass
    # numbered / bulleted lines
    lines: list[str] = []
    for line in text.splitlines():
        line = re.sub(r"^\s*[-•*\d]+[.)]\s*", "", line).strip().strip("«»\"'")
        if len(line) >= 25:
            lines.append(_normalize(line))
    return lines


async def nightly_partial_refresh(
    session: AsyncSession,
    gemini: GeminiService,
) -> dict[str, int]:
    """
    Частичное обновление базы в 23:00:
    1) AI добавляет новые цитаты по видам
    2) утомлённые цитаты временно выключаются
    3) давно выключенные seed снова включаются
    """
    stats = {"added": 0, "retired": 0, "reactivated": 0, "ai_batches": 0}

    # 1. Добавление новых через AI
    batches = [
        (
            "morning",
            "Сгенерируй 5 коротких мотивационных цитат на русском "
            "(1–2 предложения каждая) на темы: учёба, деньги, будущее, "
            "дисциплина, совершенство, фокус. Без клише и эмодзи. "
            "Верни ТОЛЬКО JSON-массив строк.",
        ),
        (
            "hourly",
            "Сгенерируй 4 короткие мотивационные фразы на русском "
            "(1 предложение) для почасового пуша: действие, фокус, дожим. "
            "Без клише и эмодзи. Верни ТОЛЬКО JSON-массив строк.",
        ),
        (
            "rest",
            "Сгенерируй 3 качественные цитаты на русском о ценности отдыха "
            "и восстановления (Recovery day), 1–3 предложения. "
            "Без клише и эмодзи. Верни ТОЛЬКО JSON-массив строк.",
        ),
    ]

    if gemini.available:
        for kind, prompt in batches:
            try:
                raw = await gemini.generate_text(
                    prompt=prompt,
                    system=(
                        "Ты редактор мотивационных текстов на русском. "
                        "Пиши сильно, коротко, без воды. Только JSON-массив строк."
                    ),
                    timeout=22.0,
                    max_attempts=2,
                    temperature=1.0,
                )
                quotes = _parse_ai_quote_list(raw)[:NIGHTLY_ADD]
                stats["ai_batches"] += 1
                for q in quotes:
                    if await save_quote_if_new(
                        session, text=q, kind=kind, theme="nightly", source="ai"
                    ):
                        stats["added"] += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("nightly_ai_batch_failed", kind=kind, error=str(exc))

    # 2. Retire перегретых активных (много использований + недавно)
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
        # не роняем пул ниже минимума по kind
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

    # 3. Reactivate старых неактивных (предпочтительно seed)
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
        # лёгкий сброс «усталости», чтобы снова участвовать в ротации
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
