from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from app.config import get_settings
from app.database import async_session_factory, close_db, init_db
from app.handlers import setup_routers
from app.middlewares import AccessMiddleware, DbSessionMiddleware
from app.models import User, UserSettings
from app.scheduler import SchedulerService
from app.services.ai import GeminiService
from app.utils.logging import get_logger, setup_logging
from sqlalchemy import select
from sqlalchemy.orm import selectinload


BOT_COMMANDS = [
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="menu", description="Открыть меню"),
    BotCommand(command="stopwatch", description="Секундомер"),
    BotCommand(command="settings", description="Настройки"),
]


async def ensure_admin_user() -> None:
    settings = get_settings()
    async with async_session_factory() as session:
        result = await session.execute(
            select(User)
            .where(User.telegram_id == settings.admin_id)
            .options(selectinload(User.settings))
        )
        user = result.scalar_one_or_none()
        if user is None:
            session.add(
                User(
                    telegram_id=settings.admin_id,
                    first_name="Admin",
                    settings=UserSettings(
                        calendar_mode="auto",
                        height_cm=settings.height_cm,
                        weight_goal_min=settings.weight_goal_min_kg,
                        weight_goal_max=settings.weight_goal_max_kg,
                    ),
                )
            )
        elif user.settings and user.settings.calendar_mode == "term":
            # Переводим на авто: летом это каникулы
            user.settings.calendar_mode = "auto"
        await session.commit()


async def ensure_motivation_pool() -> None:
    from app.services import quotes as quotes_svc

    async with async_session_factory() as session:
        added = await quotes_svc.ensure_seeded(session)
        stats = await quotes_svc.pool_stats(session)
        await session.commit()
        get_logger(__name__).info(
            "motivation_pool_ready", seeded=added, **stats
        )


async def main() -> None:
    setup_logging()
    logger = get_logger(__name__)
    settings = get_settings()

    await init_db()
    await ensure_admin_user()
    await ensure_motivation_pool()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    gemini = GeminiService(settings.gemini_keys(), settings.gemini_model)
    dp["gemini"] = gemini

    dp.update.middleware(DbSessionMiddleware())
    dp.update.middleware(AccessMiddleware())
    dp.include_router(setup_routers())

    scheduler = SchedulerService(bot, gemini)

    @dp.startup()
    async def _startup() -> None:
        await bot.set_my_commands(BOT_COMMANDS)
        scheduler.start()
        me = await bot.get_me()
        logger.info(
            "bot_started",
            username=me.username,
            admin_id=settings.admin_id,
            gemini_keys=len(settings.gemini_keys()),
        )

    @dp.shutdown()
    async def _shutdown() -> None:
        scheduler.shutdown()
        await close_db()
        logger.info("bot_stopped")

    logger.info("polling_start")
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
