from __future__ import annotations

import html

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import quotes as quotes_svc
from app.utils.custom_emoji import block_ce, ce


async def generate_morning_motivation(
    session: AsyncSession,
    *,
    saturday: bool,
    block_kind: str | object | None = None,
) -> str:
    """Утренняя / recovery-мотивация из пула цитат (с учётом блока)."""
    kind = "rest" if saturday else "morning"
    themes = quotes_svc.themes_for_block(block_kind)
    if not themes:
        themes = ["recovery", "rest"] if saturday else ["routine_morning", "discipline"]
    body = await quotes_svc.pick_quote(session, kind=kind, themes=themes)
    title = "Recovery day" if saturday else "Доброе утро"
    return f"{ce('sun')}<b>{title}</b>\n\n{html.escape(body)}"


async def generate_hourly_motivation(
    session: AsyncSession,
    *,
    block_title: str | None = None,
    block_kind: str | object | None = None,
) -> str:
    """Короткая мотивация из пула — тема под текущий блок."""
    _ = block_title
    themes = quotes_svc.themes_for_block(block_kind)
    key = getattr(block_kind, "value", None) or str(block_kind or "")
    # Сон: предпочитаем rest-пул со sleep/recovery, иначе hourly
    if key == "sleep":
        body = await quotes_svc.pick_quote(session, kind="rest", themes=themes)
    else:
        body = await quotes_svc.pick_quote(session, kind="hourly", themes=themes)
    icon = block_ce(block_kind) if block_kind is not None else ce("fire")
    return f"{icon}{html.escape(body)}"
