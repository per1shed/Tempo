from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.keyboards import settings_kb
from app.services.notifications import (
    normalize_notification_flags,
    notifications_enabled,
    set_notifications,
)
from app.services.calendar_mode import (
    calendar_mode_label,
    next_calendar_mode,
    seasonal_mode,
)
from app.utils.custom_emoji import ce
from app.utils.telegram_ui import clear_keyboard, remember_keyboard, show_screen

router = Router(name="settings")


def _text(settings) -> str:
    normalize_notification_flags(settings)
    auto_now = "каникулы" if seasonal_mode() == "holiday" else "учебное время"
    pushes = "вкл" if notifications_enabled(settings) else "выкл"
    return (
        f"{ce('settings')}<b>Настройки</b>\n\n"
        f"Календарь: <b>{calendar_mode_label(settings.calendar_mode)}</b>\n"
        f"Пуши: <b>{pushes}</b>\n\n"
        f"Пуши приходят только в момент смены слота дня "
        f"(с графиком текущего блока).\n\n"
        f"{ce('uni')}В учебное время пн–пт блок 07:30–14:00 — университет.\n"
        f"На каникулах этот слот — самообучение / IT.\n\n"
        f"Режим <b>авто</b>: лето (июнь–август) и январь → каникулы, "
        f"иначе учёба. Сейчас по сезону: <b>{auto_now}</b>.\n"
        f"Суббота — Recovery day."
    )


def _kb(settings):
    normalize_notification_flags(settings)
    return settings_kb(
        settings.calendar_mode,
        notifications_enabled(settings),
    )


@router.message(Command("settings"))
async def cmd_settings(message: Message, user_settings) -> None:
    await clear_keyboard(
        message.bot, message.chat.id, user_settings.last_kb_message_id
    )
    sent = await message.answer(_text(user_settings), reply_markup=_kb(user_settings))
    await remember_keyboard(user_settings, sent, bot=message.bot)


@router.callback_query(F.data == "menu:settings")
async def cb_settings(callback: CallbackQuery, user_settings) -> None:
    await callback.answer()
    await show_screen(
        callback,
        _text(user_settings),
        _kb(user_settings),
        user_settings=user_settings,
    )


@router.callback_query(F.data == "settings:toggle_mode")
async def cb_toggle_mode(callback: CallbackQuery, user_settings) -> None:
    user_settings.calendar_mode = next_calendar_mode(user_settings.calendar_mode)
    await callback.answer(calendar_mode_label(user_settings.calendar_mode))
    await callback.message.edit_text(
        _text(user_settings),
        reply_markup=_kb(user_settings),
    )


@router.callback_query(F.data == "settings:toggle_pushes")
async def cb_toggle_pushes(callback: CallbackQuery, user_settings) -> None:
    enabled = not notifications_enabled(user_settings)
    set_notifications(user_settings, enabled)
    await callback.answer("Пуши вкл" if enabled else "Пуши выкл")
    await callback.message.edit_text(
        _text(user_settings),
        reply_markup=_kb(user_settings),
    )
