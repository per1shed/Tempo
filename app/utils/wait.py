from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

from app.utils.custom_emoji import ce


DEFAULT_WAIT = f"{ce('timer')}Подождите, обрабатываю…"
CHART_WAIT = f"{ce('chart')}Строю график…"


@asynccontextmanager
async def wait_message(
    bot: Bot,
    chat_id: int,
    text: str = DEFAULT_WAIT,
) -> AsyncIterator[Message | None]:
    """Показывает временное сообщение и удаляет его после выхода из блока."""
    msg: Message | None = None
    try:
        msg = await bot.send_message(chat_id, text)
        yield msg
    finally:
        if msg is not None:
            try:
                await bot.delete_message(chat_id, msg.message_id)
            except TelegramBadRequest:
                pass
