from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from app.keyboards import (
    checkin_choose_kb,
    checkin_month_kb,
    checkin_score_kb,
)
from app.services import checkin as ci_svc
from app.utils.custom_emoji import ce
from app.utils.datetime_utils import today
from app.utils.telegram_ui import clear_keyboard, remember_keyboard, show_screen
from app.utils.wait import CHART_WAIT, wait_message

router = Router(name="checkin")

_PERIOD_SHORT = {
    "m": ci_svc.PERIOD_MORNING,
    "e": ci_svc.PERIOD_EVENING,
    ci_svc.PERIOD_MORNING: ci_svc.PERIOD_MORNING,
    ci_svc.PERIOD_EVENING: ci_svc.PERIOD_EVENING,
}
_PERIOD_CODE = {
    ci_svc.PERIOD_MORNING: "m",
    ci_svc.PERIOD_EVENING: "e",
}


def _period_from_code(code: str) -> str:
    return _PERIOD_SHORT.get(code, ci_svc.resolve_period())


def _code(period: str) -> str:
    return _PERIOD_CODE.get(period, "m")


async def _hub_payload(session, db_user, *, year: int | None = None, month: int | None = None):
    ref = today()
    year = year or ref.year
    month = month or ref.month
    rows = await ci_svc.list_for_month(session, db_user.id, year=year, month=month)
    return ci_svc.hub_text(month_rows=rows)


async def _send_month_dashboard(
    *,
    bot,
    chat_id: int,
    session,
    db_user,
    user_settings,
    caption: str,
    year: int | None = None,
    month: int | None = None,
) -> Message:
    """Строит дашборд месяца и шлёт фото с навигацией."""
    ref = today()
    year = year or ref.year
    month = month or ref.month
    async with wait_message(bot, chat_id, CHART_WAIT):
        rows = await ci_svc.list_for_month(session, db_user.id, year=year, month=month)
        png = ci_svc.month_dashboard_png(
            rows,
            year=year,
            month=month,
            header_day=ref.day if (year, month) == (ref.year, ref.month) else None,
        )
        await clear_keyboard(bot, chat_id, user_settings.last_kb_message_id)
        sent = await bot.send_photo(
            chat_id,
            BufferedInputFile(png, filename="state_month.png"),
            caption=caption,
            reply_markup=checkin_month_kb(year, month),
        )
        await remember_keyboard(user_settings, sent, bot=bot)
        return sent


async def _open_hub(message: Message, session, db_user, user_settings) -> Message:
    ref = today()
    return await _send_month_dashboard(
        bot=message.bot,
        chat_id=message.chat.id,
        session=session,
        db_user=db_user,
        user_settings=user_settings,
        caption=await _hub_payload(session, db_user),
        year=ref.year,
        month=ref.month,
    )


async def _edit_or_answer(
    callback: CallbackQuery,
    text: str,
    kb,
    user_settings,
) -> None:
    await show_screen(callback, text, kb, user_settings=user_settings)


@router.message(Command("state", "checkin"))
async def cmd_state(message: Message, session, db_user, user_settings) -> None:
    await _open_hub(message, session, db_user, user_settings)


@router.message(Command("physical", "phys"))
async def cmd_physical(message: Message, session, db_user, user_settings) -> None:
    period = ci_svc.resolve_period()
    text = ci_svc.prompt_physical_only_text(period)
    kb = checkin_score_kb(kind="phys", period=_code(period))
    await clear_keyboard(
        message.bot, message.chat.id, user_settings.last_kb_message_id
    )
    sent = await message.answer(text, reply_markup=kb)
    await remember_keyboard(user_settings, sent, bot=message.bot)


@router.message(Command("moral", "mood"))
async def cmd_moral(message: Message, session, db_user, user_settings) -> None:
    period = ci_svc.resolve_period()
    text = ci_svc.prompt_moral_only_text(period)
    kb = checkin_score_kb(kind="moral", period=_code(period))
    await clear_keyboard(
        message.bot, message.chat.id, user_settings.last_kb_message_id
    )
    sent = await message.answer(text, reply_markup=kb)
    await remember_keyboard(user_settings, sent, bot=message.bot)


async def _safe_answer(callback: CallbackQuery, text: str | None = None, **kwargs) -> None:
    from aiogram.exceptions import TelegramBadRequest

    try:
        if text is None:
            await callback.answer(**kwargs)
        else:
            await callback.answer(text, **kwargs)
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == "ci:hub")
async def cb_hub(
    callback: CallbackQuery, session, db_user, user_settings, state: FSMContext
) -> None:
    await state.clear()
    await _safe_answer(callback)
    ref = today()
    await _send_month_dashboard(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        session=session,
        db_user=db_user,
        user_settings=user_settings,
        caption=await _hub_payload(session, db_user),
        year=ref.year,
        month=ref.month,
    )


@router.callback_query(F.data == "ci:ask:now")
async def cb_ask_now(callback: CallbackQuery, user_settings) -> None:
    await _safe_answer(callback)
    period = ci_svc.resolve_period()
    text = ci_svc.prompt_choose_text(period)
    await _edit_or_answer(callback, text, checkin_choose_kb(), user_settings)


@router.callback_query(F.data == "ci:skip")
async def cb_skip(callback: CallbackQuery, session, db_user, user_settings) -> None:
    await _safe_answer(callback, "Пропущено")
    ref = today()
    await _send_month_dashboard(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        session=session,
        db_user=db_user,
        user_settings=user_settings,
        caption=await _hub_payload(session, db_user),
        year=ref.year,
        month=ref.month,
    )


@router.callback_query(F.data == "ci:ask:phys")
async def cb_ask_phys(callback: CallbackQuery, user_settings) -> None:
    await _safe_answer(callback)
    period = ci_svc.resolve_period()
    text = ci_svc.prompt_physical_only_text(period)
    kb = checkin_score_kb(kind="phys", period=_code(period))
    await _edit_or_answer(callback, text, kb, user_settings)


@router.callback_query(F.data == "ci:ask:moral")
async def cb_ask_moral(callback: CallbackQuery, user_settings) -> None:
    await _safe_answer(callback)
    period = ci_svc.resolve_period()
    text = ci_svc.prompt_moral_only_text(period)
    kb = checkin_score_kb(kind="moral", period=_code(period))
    await _edit_or_answer(callback, text, kb, user_settings)


@router.callback_query(F.data.regexp(r"^ci:p:[me]:[1-5]$"))
async def cb_full_physical(
    callback: CallbackQuery, session, db_user, user_settings
) -> None:
    _, _, period_code, score_s = callback.data.split(":")
    period = _period_from_code(period_code)
    score = int(score_s)
    row = await ci_svc.create_checkin(
        session, db_user.id, period=period, physical=score
    )
    await _safe_answer(callback, f"Физическое: {score}")
    text = ci_svc.prompt_moral_text(period, physical=row.physical)
    kb = checkin_score_kb(
        kind="m",
        period=period_code,
        checkin_id=row.id,
        allow_skip=True,
    )
    await _edit_or_answer(callback, text, kb, user_settings)


@router.callback_query(F.data.regexp(r"^ci:m:[me]:[1-5]:\d+$"))
async def cb_full_moral(
    callback: CallbackQuery, session, db_user, user_settings, state: FSMContext
) -> None:
    _, _, period_code, score_s, checkin_id_s = callback.data.split(":")
    score = int(score_s)
    row = await ci_svc.set_moral_on(
        session, db_user.id, int(checkin_id_s), moral=score
    )
    if row is None:
        period = _period_from_code(period_code)
        row = await ci_svc.create_checkin(
            session, db_user.id, period=period, moral=score
        )
    await _safe_answer(callback, "Сохранено")

    # Вечер: после самочувствия — опрос финансов
    if period_code == "e":
        from app.handlers.finance import start_finance_prompt
        from app.services import finance as fin_svc

        balance = await fin_svc.get_balance(session, db_user.id, user_settings)
        await start_finance_prompt(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            user_settings=user_settings,
            state=state,
            text=fin_svc.prompt_evening_intro_text(
                physical=row.physical, moral=row.moral, balance=balance
            ),
            allow_skip=True,
            source="evening",
            physical=row.physical,
            moral=row.moral,
        )
        return

    ref = today()
    await _send_month_dashboard(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        session=session,
        db_user=db_user,
        user_settings=user_settings,
        caption=(
            f"{ci_svc.saved_text(row)}\n\n"
            f"{ce('chart')}<b>Самочувствие</b> · {ref.month:02d}.{ref.year}"
        ),
        year=ref.year,
        month=ref.month,
    )


@router.callback_query(F.data.regexp(r"^ci:phys:[me]:[1-5]$"))
async def cb_phys_only(
    callback: CallbackQuery, session, db_user, user_settings
) -> None:
    _, _, period_code, score_s = callback.data.split(":")
    period = _period_from_code(period_code)
    score = int(score_s)
    await ci_svc.create_checkin(session, db_user.id, period=period, physical=score)
    await _safe_answer(callback, "Сохранено")
    ref = today()
    await _send_month_dashboard(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        session=session,
        db_user=db_user,
        user_settings=user_settings,
        caption=(
            f"{ci_svc.saved_dim_text(kind='physical', period=period, score=score)}\n\n"
            f"{ce('chart')}<b>Самочувствие</b> · {ref.month:02d}.{ref.year}"
        ),
        year=ref.year,
        month=ref.month,
    )


@router.callback_query(F.data.regexp(r"^ci:moral:[me]:[1-5]$"))
async def cb_moral_only(
    callback: CallbackQuery, session, db_user, user_settings
) -> None:
    _, _, period_code, score_s = callback.data.split(":")
    period = _period_from_code(period_code)
    score = int(score_s)
    await ci_svc.create_checkin(session, db_user.id, period=period, moral=score)
    await _safe_answer(callback, "Сохранено")
    ref = today()
    await _send_month_dashboard(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        session=session,
        db_user=db_user,
        user_settings=user_settings,
        caption=(
            f"{ci_svc.saved_dim_text(kind='moral', period=period, score=score)}\n\n"
            f"{ce('chart')}<b>Самочувствие</b> · {ref.month:02d}.{ref.year}"
        ),
        year=ref.year,
        month=ref.month,
    )


@router.callback_query(F.data.regexp(r"^ci:chart:month(?::(\d{4})-(\d{2}))?(?::(prev|next))?$"))
async def cb_chart_month(
    callback: CallbackQuery, session, db_user, user_settings
) -> None:
    await _safe_answer(callback)
    parts = callback.data.split(":")
    ref = today()
    year, month = ref.year, ref.month
    if len(parts) >= 4 and parts[3]:
        year_s, month_s = parts[3].split("-")
        year, month = int(year_s), int(month_s)
    action = parts[4] if len(parts) >= 5 else None
    if action == "prev":
        if month == 1:
            year, month = year - 1, 12
        else:
            month -= 1
    elif action == "next":
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1

    await _send_month_dashboard(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        session=session,
        db_user=db_user,
        user_settings=user_settings,
        caption=await _hub_payload(session, db_user, year=year, month=month),
        year=year,
        month=month,
    )


@router.callback_query(F.data.regexp(r"^ci:chart(?::(14|30))?$"))
async def cb_chart(callback: CallbackQuery, session, db_user, user_settings) -> None:
    """Старые кнопки 14/30 → месячный дашборд."""
    await _safe_answer(callback)
    ref = today()
    await _send_month_dashboard(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        session=session,
        db_user=db_user,
        user_settings=user_settings,
        caption=await _hub_payload(session, db_user),
        year=ref.year,
        month=ref.month,
    )
