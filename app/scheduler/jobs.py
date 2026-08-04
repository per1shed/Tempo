from __future__ import annotations

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import BufferedInputFile
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import async_session_factory
from app.models import User
from app.services.ai import GeminiService
from app.services.calendar_mode import effective_calendar_mode
from app.services.day import home_chart_png
from app.services.motivation import generate_hourly_motivation, generate_morning_motivation
from app.services.notifications import notifications_enabled
from app.services import quotes as quotes_svc
from app.services.schedule import (
    BlockKind,
    active_block,
    block_transition_times,
    format_block_range,
    schedule_for_day,
)
from app.utils.custom_emoji import block_ce
from app.utils.datetime_utils import now, today, tz
from app.utils.logging import get_logger
from app.utils.telegram_ui import clear_keyboard

logger = get_logger(__name__)


class SchedulerService:
    def __init__(self, bot: Bot, gemini: GeminiService) -> None:
        self.bot = bot
        self.gemini = gemini
        self.scheduler = AsyncIOScheduler(timezone=str(tz()))
        self.settings = get_settings()

    def start(self) -> None:
        for t in block_transition_times():
            self.scheduler.add_job(
                self.send_block_push,
                "cron",
                hour=t.hour,
                minute=t.minute,
                id=f"block_{t.hour:02d}{t.minute:02d}",
                replace_existing=True,
            )

        self.scheduler.add_job(
            self.refresh_quote_pool,
            "cron",
            hour=23,
            minute=0,
            id="quote_pool_refresh",
            replace_existing=True,
        )

        self.scheduler.start()
        logger.info(
            "scheduler_started",
            block_slots=len(block_transition_times()),
        )

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    async def _admin_user(self, session) -> User | None:
        result = await session.execute(
            select(User)
            .where(User.telegram_id == self.settings.admin_id)
            .options(selectinload(User.settings))
        )
        return result.scalar_one_or_none()

    async def send_block_push(self) -> None:
        """Пуш только в момент смены слота: график дня + мотивация."""
        n = now()
        async with async_session_factory() as session:
            user = await self._admin_user(session)
            if not user or not user.settings:
                return
            if not notifications_enabled(user.settings):
                return

            mode = effective_calendar_mode(user.settings.calendar_mode)
            blocks = schedule_for_day(today(), calendar_mode=mode)
            cur = active_block(blocks, n)
            if cur is None or cur.kind == BlockKind.FREE:
                return

            # Только старт запланированного блока
            if (n.hour, n.minute) != (cur.start.hour, cur.start.minute):
                return

            # Антидубль на тот же блок
            if user.settings.last_block_key == cur.key:
                return
            user.settings.last_block_key = cur.key

            saturday = today().weekday() == 5
            use_morning = (
                cur.kind == BlockKind.ROUTINE_MORNING
                or (saturday and cur.kind == BlockKind.RECOVERY)
            )
            try:
                if use_morning:
                    tip = await generate_morning_motivation(
                        session, self.gemini, saturday=saturday
                    )
                else:
                    tip = await generate_hourly_motivation(
                        session,
                        self.gemini,
                        block_title=cur.title,
                        block_kind=cur.kind,
                    )

                icon = block_ce(cur.kind)
                block_line = (
                    f"{icon}Сейчас: <b>{cur.title}</b> ({format_block_range(cur)})"
                )
                caption = f"{tip}\n\n{block_line}"
                if len(caption) > 1000:
                    # Telegram caption limit ~1024
                    overflow = len(caption) - 990
                    tip_cut = tip[: max(0, len(tip) - overflow - 1)] + "…"
                    caption = f"{tip_cut}\n\n{block_line}"

                png = home_chart_png(user.settings)
                await clear_keyboard(
                    self.bot, user.telegram_id, user.settings.last_kb_message_id
                )
                await self.bot.send_photo(
                    user.telegram_id,
                    BufferedInputFile(png, filename="block.png"),
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                )
                user.settings.last_kb_message_id = None
                await session.commit()
            except Exception as exc:  # noqa: BLE001
                await session.rollback()
                logger.warning("block_push_failed", error=str(exc))

    async def refresh_quote_pool(self) -> None:
        async with async_session_factory() as session:
            try:
                stats = await quotes_svc.nightly_partial_refresh(session, self.gemini)
                await session.commit()
                logger.info("quote_pool_refresh_done", **stats)
            except Exception as exc:  # noqa: BLE001
                await session.rollback()
                logger.warning("quote_pool_refresh_failed", error=str(exc))
