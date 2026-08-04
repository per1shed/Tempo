from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.keyboards import main_menu_kb
from app.services.day import home_chart_png, home_text
from app.utils.telegram_ui import send_home_card

router = Router(name="start")


async def deliver_home(
    bot: Bot,
    chat_id: int,
    *,
    db_user,
    user_settings,
    session=None,
    tip: str | None = None,
) -> Message:
    caption = home_text(user_settings, db_user.first_name)
    if tip:
        caption = f"{caption}\n\n{tip}"
    if len(caption) > 1000:
        caption = caption[:990] + "…"

    png = home_chart_png(user_settings)
    return await send_home_card(
        bot,
        chat_id,
        caption=caption,
        png=png,
        reply_markup=main_menu_kb(),
        user_settings=user_settings,
    )


@router.message(CommandStart())
@router.message(Command("menu"))
async def cmd_start(
    message: Message, session, db_user, user_settings, state: FSMContext
) -> None:
    await state.clear()
    await deliver_home(
        message.bot,
        message.chat.id,
        db_user=db_user,
        user_settings=user_settings,
        session=session,
    )


@router.callback_query(F.data == "menu:home")
async def cb_home(
    callback: CallbackQuery, session, db_user, user_settings, state: FSMContext
) -> None:
    await state.clear()
    await callback.answer()
    await deliver_home(
        callback.bot,
        callback.message.chat.id,
        db_user=db_user,
        user_settings=user_settings,
        session=session,
    )
