from __future__ import annotations

import html

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai import GeminiService
from app.services import quotes as quotes_svc
from app.utils.custom_emoji import block_ce, ce
from app.utils.logging import get_logger

logger = get_logger(__name__)

SYSTEM = (
    "Ты сильный мотивационный автор на русском. "
    "Пиши живо, без клише вроде «поверь в себя» и без воды. "
    "Без markdown, без HTML, без кавычек-обёрток, без эмодзи. "
    "Тон серьёзный, взрослый, для амбициозного человека."
)


async def generate_morning_motivation(
    session: AsyncSession,
    gemini: GeminiService,
    *,
    saturday: bool,
) -> str:
    """Утренняя мотивация: AI → иначе цитата из БД."""
    kind = "rest" if saturday else "morning"
    if saturday:
        prompt = (
            "Напиши утреннюю мотивацию на субботу (Recovery day) на русском. "
            "Обязательно раскрой ценность отдыха и восстановления: "
            "почему отдых нужен для роста, дисциплины и результатов, "
            "а не «простой день без дела». "
            "Формат: либо сильная цитата (1–2 предложения), "
            "либо короткий мотивационный рассказ (4–7 предложений). "
            "Темы: восстановление, энергия, ясность ума, устойчивость."
        )
    else:
        prompt = (
            "Напиши качественную утреннюю мотивацию на русском. "
            "Формат: либо сильная цитата (1–2 предложения), "
            "либо короткий мотивационный рассказ (4–7 предложений). "
            "Темы на выбор: учёба, деньги, будущее, дисциплина, "
            "совершенство, путь к №1. Без банальностей."
        )

    text = ""
    if gemini.available:
        try:
            text = await gemini.generate_text(
                prompt=prompt,
                system=SYSTEM,
                timeout=18.0,
                max_attempts=2,
                temperature=0.95,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("morning_motivation_ai_failed", error=str(exc))
            text = ""

    if text and len(text.strip()) >= 25:
        body = text.strip()
        # короткие AI-ответы кладём в пул для ротации
        if len(body) <= 500:
            try:
                await quotes_svc.save_quote_if_new(
                    session, text=body, kind=kind, theme="live", source="ai_saved"
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("save_ai_quote_failed", error=str(exc))
    else:
        body = await quotes_svc.pick_quote(session, kind=kind)

    title = "Recovery day" if saturday else "Доброе утро"
    return f"{ce('sun')}<b>{title}</b>\n\n{html.escape(body)}"


async def generate_hourly_motivation(
    session: AsyncSession,
    gemini: GeminiService,
    *,
    block_title: str | None,
    block_kind: str | object | None = None,
) -> str:
    """Короткая мотивация: AI → иначе цитата из БД."""
    context = f"Текущий блок дня: {block_title}." if block_title else "Блок дня неизвестен."
    prompt = (
        f"{context}\n"
        "Напиши одну короткую мотивационную фразу или мини-абзац "
        "(1–3 предложения) на русском: подтолкни к действию в этом блоке. "
        "Темы: фокус, учёба, деньги, будущее, дисциплина. Без воды."
    )
    text = ""
    if gemini.available:
        try:
            text = await gemini.generate_text(
                prompt=prompt,
                system=SYSTEM,
                timeout=12.0,
                max_attempts=1,
                temperature=0.9,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("hourly_motivation_ai_failed", error=str(exc))
            text = ""

    if text and len(text.strip()) >= 20:
        body = text.strip()
        if len(body) <= 400:
            try:
                await quotes_svc.save_quote_if_new(
                    session, text=body, kind="hourly", theme="live", source="ai_saved"
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("save_ai_quote_failed", error=str(exc))
    else:
        body = await quotes_svc.pick_quote(session, kind="hourly")

    icon = block_ce(block_kind) if block_kind is not None else ce("fire")
    return f"{icon}{html.escape(body)}"
