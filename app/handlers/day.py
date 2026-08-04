from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.keyboards import back_menu_kb
from app.utils.custom_emoji import ce
from app.utils.datetime_utils import new_year_label
from app.utils.telegram_ui import show_screen

router = Router(name="day")


@router.callback_query(F.data == "menu:newyear")
async def cb_newyear(callback: CallbackQuery, user_settings) -> None:
    await callback.answer()
    text = (
        f"{ce('party')}<b>Новый год</b>\n\n"
        f"{ce('timer')}{new_year_label(short=True)}\n\n"
        f"Отсчёт всегда в шапке главного меню."
    )
    await show_screen(callback, text, back_menu_kb(), user_settings=user_settings)
