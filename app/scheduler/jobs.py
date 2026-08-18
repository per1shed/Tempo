from __future__ import annotations

import asyncio

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import BufferedInputFile
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import async_session_factory
from app.models import User
from app.services.calendar_mode import effective_calendar_mode
from app.services.day import home_chart_png
from app.services.motivation import generate_hourly_motivation, generate_morning_motivation
from app.services import quotes as quotes_svc
from app.services.schedule import (
    BlockKind,
    active_block,
    block_transition_times,
    format_block_range,
    schedule_for_day,
)
from app.keyboards import checkin_score_kb, main_menu_kb
from app.services import checkin as ci_svc
from app.utils.custom_emoji import block_ce
from app.utils.datetime_utils import now, today, tz
from app.utils.logging import get_logger
from app.utils.telegram_ui import clear_keyboard, remember_keyboard
from app.utils.wait import CHART_WAIT, wait_message

logger = get_logger(__name__)


class SchedulerService:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
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
            self.send_checkin_push,
            "cron",
            hour=7,
            minute=30,
            id="checkin_morning",
            replace_existing=True,
            kwargs={"period": ci_svc.PERIOD_MORNING},
        )
        self.scheduler.add_job(
            self.send_checkin_push,
            "cron",
            hour=22,
            minute=0,
            id="checkin_evening",
            replace_existing=True,
            kwargs={"period": ci_svc.PERIOD_EVENING},
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
            checkin_slots=["07:30", "22:00"],
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
                        session,
                        saturday=saturday,
                        block_kind=cur.kind,
                    )
                else:
                    tip = await generate_hourly_motivation(
                        session,
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

                async with wait_message(self.bot, user.telegram_id, CHART_WAIT):
                    png = home_chart_png(user.settings)
                    await clear_keyboard(
                        self.bot, user.telegram_id, user.settings.last_kb_message_id
                    )
                    sent = await self.bot.send_photo(
                        user.telegram_id,
                        BufferedInputFile(png, filename="block.png"),
                        caption=caption,
                        parse_mode=ParseMode.HTML,
                        reply_markup=main_menu_kb(),
                    )
                    await remember_keyboard(user.settings, sent, bot=self.bot)
                    await session.commit()
            except Exception as exc:  # noqa: BLE001
                await session.rollback()
                logger.warning("block_push_failed", error=str(exc))

    async def send_checkin_push(self, period: str) -> None:
        """Опрос самочувствия утром 07:30 / вечером 22:00."""
        # Утром даём block-пушу 07:30 закончиться, чтобы не снять кнопки опроса.
        if period == ci_svc.PERIOD_MORNING:
            await asyncio.sleep(8)

        async with async_session_factory() as session:
            user = await self._admin_user(session)
            if not user or not user.settings:
                return

            # Не спамим, если за этот слот уже есть полная отметка —
            # дополнительные всё равно можно добавить командами.
            existing = await ci_svc.get_latest_checkin(session, user.id, period=period)
            if (
                existing
                and existing.physical is not None
                and existing.moral is not None
            ):
                return

            period_code = "m" if period == ci_svc.PERIOD_MORNING else "e"
            text = ci_svc.prompt_physical_text(period)
            kb = checkin_score_kb(kind="p", period=period_code, allow_skip=True)
            try:
                await clear_keyboard(
                    self.bot, user.telegram_id, user.settings.last_kb_message_id
                )
                sent = await self.bot.send_message(
                    user.telegram_id,
                    text,
                    reply_markup=kb,
                    parse_mode=ParseMode.HTML,
                )
                await remember_keyboard(user.settings, sent, bot=self.bot)
                await session.commit()
            except Exception as exc:  # noqa: BLE001
                await session.rollback()
                logger.warning("checkin_push_failed", error=str(exc), period=period)

    async def refresh_quote_pool(self) -> None:
        async with async_session_factory() as session:
            try:
                stats = await quotes_svc.nightly_partial_refresh(session)
                await session.commit()
                logger.info("quote_pool_refresh_done", **stats)
            except Exception as exc:  # noqa: BLE001
                await session.rollback()
                logger.warning("quote_pool_refresh_failed", error=str(exc))
