from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import async_session_factory
from app.models import User, UserSettings


STUB_TEXT = (
    "Tempo — персональный ассистент.\n\n"
    "Сейчас бот доступен только владельцу.\n"
    "Если это ошибка — напиши администратору."
)


class DbSessionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with async_session_factory() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise


class AccessMiddleware(BaseMiddleware):
    """Только ADMIN_ID получает полный доступ; остальным — заглушка."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        settings = get_settings()
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        if user.id != settings.admin_id:
            if isinstance(event, Message):
                await event.answer(STUB_TEXT)
            elif isinstance(event, CallbackQuery):
                await event.answer("Доступ закрыт", show_alert=True)
                if event.message:
                    await event.message.answer(STUB_TEXT)
            return None

        session = data["session"]
        db_user = await _ensure_user(session, user)
        data["db_user"] = db_user
        data["user_settings"] = db_user.settings
        return await handler(event, data)


async def _ensure_user(session, tg_user) -> User:
    result = await session.execute(
        select(User)
        .where(User.telegram_id == tg_user.id)
        .options(selectinload(User.settings))
    )
    user = result.scalar_one_or_none()
    cfg = get_settings()
    if user is None:
        user = User(
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            settings=UserSettings(
                height_cm=cfg.height_cm,
                weight_goal_min=cfg.weight_goal_min_kg,
                weight_goal_max=cfg.weight_goal_max_kg,
            ),
        )
        session.add(user)
        await session.flush()
        await session.refresh(user, attribute_names=["settings"])
        return user

    user.username = tg_user.username
    user.first_name = tg_user.first_name
    if user.settings is None:
        user.settings = UserSettings(
            height_cm=cfg.height_cm,
            weight_goal_min=cfg.weight_goal_min_kg,
            weight_goal_max=cfg.weight_goal_max_kg,
        )
        await session.flush()
    return user
