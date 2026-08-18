from __future__ import annotations

from datetime import date

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from app.keyboards import (
    finance_cancel_kb,
    finance_choose_kb,
    finance_month_kb,
    finance_skip_kb,
)
from app.services import checkin as ci_svc
from app.services import finance as fin_svc
from app.utils.custom_emoji import ce
from app.utils.datetime_utils import today
from app.utils.telegram_ui import clear_keyboard, remember_keyboard, show_screen
from app.utils.wait import CHART_WAIT, wait_message

router = Router(name="finance")


class FinanceForm(StatesGroup):
    waiting_cash = State()
    waiting_debt = State()


async def _hub_text(session, db_user, user_settings) -> str:
    balance = await fin_svc.get_balance(session, db_user.id, user_settings)
    today_row = await fin_svc.get_today(session, db_user.id)
    return fin_svc.hub_text(balance, today_logged=today_row is not None)


async def start_finance_prompt(
    *,
    bot,
    chat_id: int,
    user_settings,
    state: FSMContext,
    text: str,
    allow_skip: bool = False,
    source: str = "manual",
    physical: int | None = None,
    moral: int | None = None,
) -> Message:
    await state.clear()
    await state.update_data(
        fin_source=source,
        fin_physical=physical,
        fin_moral=moral,
        fin_allow_skip=allow_skip,
    )
    await clear_keyboard(bot, chat_id, user_settings.last_kb_message_id)
    sent = await bot.send_message(
        chat_id, text, reply_markup=finance_choose_kb(allow_skip=allow_skip)
    )
    await remember_keyboard(user_settings, sent, bot=bot)
    return sent


async def _send_finance_chart(
    *,
    bot,
    chat_id: int,
    session,
    db_user,
    user_settings,
    year: int,
    month: int,
    caption: str,
) -> Message:
    async with wait_message(bot, chat_id, CHART_WAIT):
        balance = await fin_svc.get_balance(session, db_user.id, user_settings)
        logs = await fin_svc.list_for_month(session, db_user.id, year=year, month=month)
        prior = await fin_svc.get_log_before(
            session, db_user.id, before=date(year, month, 1)
        )
        cash_by, debt_by = fin_svc.month_series_filled(
            logs, year=year, month=month, prior=prior, balance=balance
        )
        png = fin_svc.month_dashboard_png(
            year=year,
            month=month,
            cash_by_day=cash_by,
            debt_by_day=debt_by,
            balance=balance,
        )
        await clear_keyboard(bot, chat_id, user_settings.last_kb_message_id)
        sent = await bot.send_photo(
            chat_id,
            BufferedInputFile(png, filename="finance.png"),
            caption=caption,
            reply_markup=finance_month_kb(year, month),
        )
        await remember_keyboard(user_settings, sent, bot=bot)
        return sent


async def _after_save(
    message: Message,
    session,
    db_user,
    user_settings,
    state: FSMContext,
    *,
    cash: float,
    debt: float,
    source: str,
    physical: int | None,
    moral: int | None,
) -> None:
    await state.clear()
    ref = today()
    caption = (
        f"{fin_svc.saved_text(cash=cash, debt=debt)}\n\n"
        f"{ce('chart')}<b>Финансы</b> · {ref.month:02d}.{ref.year}"
    )
    await _send_finance_chart(
        bot=message.bot,
        chat_id=message.chat.id,
        session=session,
        db_user=db_user,
        user_settings=user_settings,
        year=ref.year,
        month=ref.month,
        caption=caption,
    )


@router.callback_query(F.data == "fin:hub")
async def cb_hub(
    callback: CallbackQuery, session, db_user, user_settings, state: FSMContext
) -> None:
    await state.clear()
    await callback.answer()
    ref = today()
    caption = await _hub_text(session, db_user, user_settings)
    await _send_finance_chart(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        session=session,
        db_user=db_user,
        user_settings=user_settings,
        year=ref.year,
        month=ref.month,
        caption=caption,
    )


@router.callback_query(F.data == "fin:update")
async def cb_update(
    callback: CallbackQuery, session, db_user, user_settings, state: FSMContext
) -> None:
    await callback.answer()
    balance = await fin_svc.get_balance(session, db_user.id, user_settings)
    await state.clear()
    await state.update_data(fin_source="manual", fin_allow_skip=False)
    await show_screen(
        callback,
        fin_svc.prompt_choose_text(balance=balance),
        finance_choose_kb(allow_skip=False),
        user_settings=user_settings,
    )


@router.callback_query(F.data == "fin:choose")
async def cb_choose(
    callback: CallbackQuery, session, db_user, user_settings, state: FSMContext
) -> None:
    await callback.answer()
    data = await state.get_data()
    allow_skip = bool(data.get("fin_allow_skip"))
    await state.set_state(None)
    balance = await fin_svc.get_balance(session, db_user.id, user_settings)
    if data.get("fin_source") == "evening":
        text = fin_svc.prompt_evening_intro_text(
            physical=data.get("fin_physical"),
            moral=data.get("fin_moral"),
            balance=balance,
        )
    else:
        text = fin_svc.prompt_choose_text(balance=balance)
    await show_screen(
        callback,
        text,
        finance_choose_kb(allow_skip=allow_skip),
        user_settings=user_settings,
    )


@router.callback_query(F.data == "fin:edit:cash")
async def cb_edit_cash(
    callback: CallbackQuery, session, db_user, user_settings, state: FSMContext
) -> None:
    await callback.answer()
    data = await state.get_data()
    allow_skip = bool(data.get("fin_allow_skip"))
    await state.set_state(FinanceForm.waiting_cash)
    balance = await fin_svc.get_balance(session, db_user.id, user_settings)
    kb = finance_skip_kb() if allow_skip else finance_cancel_kb()
    await show_screen(
        callback,
        fin_svc.prompt_cash_text(balance=balance),
        kb,
        user_settings=user_settings,
    )


@router.callback_query(F.data == "fin:edit:debt")
async def cb_edit_debt(
    callback: CallbackQuery, session, db_user, user_settings, state: FSMContext
) -> None:
    await callback.answer()
    data = await state.get_data()
    allow_skip = bool(data.get("fin_allow_skip"))
    await state.set_state(FinanceForm.waiting_debt)
    balance = await fin_svc.get_balance(session, db_user.id, user_settings)
    kb = finance_skip_kb() if allow_skip else finance_cancel_kb()
    await show_screen(
        callback,
        fin_svc.prompt_debt_text(debt=balance.debt if balance else None),
        kb,
        user_settings=user_settings,
    )


@router.callback_query(F.data == "fin:skip")
async def cb_skip(
    callback: CallbackQuery, session, db_user, user_settings, state: FSMContext
) -> None:
    data = await state.get_data()
    source = data.get("fin_source", "manual")
    physical = data.get("fin_physical")
    moral = data.get("fin_moral")
    await state.clear()
    await callback.answer("Пропущено")
    ref = today()
    if source == "evening":
        from app.handlers.checkin import _send_month_dashboard

        await _send_month_dashboard(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            session=session,
            db_user=db_user,
            user_settings=user_settings,
            caption=(
                f"{ce('check')}<b>Сохранено · вечер</b>\n\n"
                f"{ce('gym')}Физическое: <b>{ci_svc.format_score(physical)}</b>\n"
                f"{ce('star')}Моральное: <b>{ci_svc.format_score(moral)}</b>\n\n"
                f"Финансы пропущены.\n\n"
                f"{ce('chart')}<b>Самочувствие</b> · {ref.month:02d}.{ref.year}"
            ),
            year=ref.year,
            month=ref.month,
        )
    else:
        ref = today()
        caption = await _hub_text(session, db_user, user_settings)
        await _send_finance_chart(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            session=session,
            db_user=db_user,
            user_settings=user_settings,
            year=ref.year,
            month=ref.month,
            caption=caption,
        )


@router.callback_query(
    F.data.regexp(r"^fin:chart:month(?::(\d{4})-(\d{2}))?(?::(prev|next))?$")
)
async def cb_chart_month(
    callback: CallbackQuery, session, db_user, user_settings, state: FSMContext
) -> None:
    await state.clear()
    await callback.answer()
    parts = callback.data.split(":")
    ref = today()
    year, month = ref.year, ref.month
    if len(parts) >= 4 and parts[3]:
        year_s, month_s = parts[3].split("-")
        year, month = int(year_s), int(month_s)
    action = parts[4] if len(parts) >= 5 else None
    if action == "prev":
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    elif action == "next":
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)

    await _send_finance_chart(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        session=session,
        db_user=db_user,
        user_settings=user_settings,
        year=year,
        month=month,
        caption=await _hub_text(session, db_user, user_settings),
    )


@router.message(StateFilter(FinanceForm.waiting_cash), F.text)
async def on_cash(
    message: Message, session, db_user, user_settings, state: FSMContext
) -> None:
    pair = fin_svc.parse_pair(message.text or "")
    current = await fin_svc.get_balance(session, db_user.id, user_settings)
    if pair is not None:
        cash, debt = pair
    else:
        cash = fin_svc.parse_amount(message.text or "")
        if cash is None:
            await message.answer(
                "Не разобрал сумму. Пример: <code>45 000</code>."
            )
            return
        debt = current.debt if current else 0.0

    await fin_svc.save_balance(
        session, db_user.id, cash=cash, debt=debt, settings=user_settings
    )
    data = await state.get_data()
    await _after_save(
        message,
        session,
        db_user,
        user_settings,
        state,
        cash=cash,
        debt=debt,
        source=data.get("fin_source", "manual"),
        physical=data.get("fin_physical"),
        moral=data.get("fin_moral"),
    )


@router.message(StateFilter(FinanceForm.waiting_debt), F.text)
async def on_debt(
    message: Message, session, db_user, user_settings, state: FSMContext
) -> None:
    debt = fin_svc.parse_amount(message.text or "")
    if debt is None:
        await message.answer(
            "Не разобрал сумму долга. Пример: <code>12 000</code> или <code>0</code>."
        )
        return
    current = await fin_svc.get_balance(session, db_user.id, user_settings)
    cash = current.cash if current else 0.0
    debt = max(0.0, debt)
    await fin_svc.save_balance(
        session, db_user.id, cash=cash, debt=debt, settings=user_settings
    )
    data = await state.get_data()
    await _after_save(
        message,
        session,
        db_user,
        user_settings,
        state,
        cash=cash,
        debt=debt,
        source=data.get("fin_source", "manual"),
        physical=data.get("fin_physical"),
        moral=data.get("fin_moral"),
    )
