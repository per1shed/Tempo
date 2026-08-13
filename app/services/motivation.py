from __future__ import annotations

import html

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import quotes as quotes_svc
from app.utils.custom_emoji import block_ce, ce


async def generate_morning_motivation(
    session: AsyncSession,
    *,
    saturday: bool,
) -> str:
    """Утренняя мотивация из пула цитат."""
    kind = "rest" if saturday else "morning"
    body = await quotes_svc.pick_quote(session, kind=kind)
    title = "Recovery day" if saturday else "Доброе утро"
    return f"{ce('sun')}<b>{title}</b>\n\n{html.escape(body)}"


async def generate_hourly_motivation(
    session: AsyncSession,
    *,
    block_title: str | None = None,
    block_kind: str | object | None = None,
) -> str:
    """Короткая мотивация из пула цитат."""
    _ = block_title  # контекст блока больше не уходит в AI
    body = await quotes_svc.pick_quote(session, kind="hourly")
    icon = block_ce(block_kind) if block_kind is not None else ce("fire")
    return f"{icon}{html.escape(body)}"
