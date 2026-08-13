from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.keyboards import stopwatch_kb
from app.services import stopwatch as sw_svc
from app.utils.telegram_ui import clear_keyboard, remember_keyboard

router = Router(name="stopwatch")


async def _render(message: Message, session, db_user, user_settings) -> Message:
    state = await sw_svc.get_or_create(session, db_user.id)
    text = sw_svc.screen_text(state)
    kb = stopwatch_kb(state.status)
    await clear_keyboard(
        message.bot, message.chat.id, user_settings.last_kb_message_id
    )
    sent = await message.answer(text, reply_markup=kb)
    await remember_keyboard(user_settings, sent, bot=message.bot)
    return sent


async def _edit(callback: CallbackQuery, session, db_user) -> None:
    state = await sw_svc.get_or_create(session, db_user.id)
    text = sw_svc.screen_text(state)
    kb = stopwatch_kb(state.status)
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


@router.message(Command("stopwatch", "sw"))
async def cmd_stopwatch(message: Message, session, db_user, user_settings) -> None:
    await _render(message, session, db_user, user_settings)


@router.callback_query(F.data == "menu:stopwatch")
async def cb_menu_stopwatch(
    callback: CallbackQuery, session, db_user, user_settings
) -> None:
    await callback.answer()
    await _render(callback.message, session, db_user, user_settings)


@router.callback_query(F.data == "sw:start")
async def cb_start(callback: CallbackQuery, session, db_user) -> None:
    state = await sw_svc.get_or_create(session, db_user.id)
    await sw_svc.start(session, state)
    await callback.answer("Старт")
    await _edit(callback, session, db_user)


@router.callback_query(F.data == "sw:pause")
async def cb_pause(callback: CallbackQuery, session, db_user) -> None:
    state = await sw_svc.get_or_create(session, db_user.id)
    await sw_svc.pause(session, state)
    await callback.answer("Пауза")
    await _edit(callback, session, db_user)


@router.callback_query(F.data == "sw:reset")
async def cb_reset(callback: CallbackQuery, session, db_user) -> None:
    state = await sw_svc.get_or_create(session, db_user.id)
    await sw_svc.reset(session, state)
    await callback.answer("Сброшено")
    await _edit(callback, session, db_user)


@router.callback_query(F.data == "sw:lap")
async def cb_lap(callback: CallbackQuery, session, db_user) -> None:
    state = await sw_svc.get_or_create(session, db_user.id)
    if state.status != "running":
        await callback.answer("Секундомер не запущен", show_alert=True)
        return
    await sw_svc.lap(session, state)
    await callback.answer("Круг")
    await _edit(callback, session, db_user)


@router.callback_query(F.data == "sw:refresh")
async def cb_refresh(callback: CallbackQuery, session, db_user) -> None:
    await callback.answer()
    await _edit(callback, session, db_user)
