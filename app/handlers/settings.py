from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.keyboards import (
    counter_detail_kb,
    counters_cancel_kb,
    counters_hub_kb,
    counters_mode_kb,
    settings_kb,
)
from app.services import counters as cnt_svc
from app.services.calendar_mode import (
    calendar_mode_label,
    next_calendar_mode,
)
from app.utils.custom_emoji import ce
from app.utils.telegram_ui import clear_keyboard, remember_keyboard, show_screen

router = Router(name="settings")


class CounterForm(StatesGroup):
    waiting_name = State()
    waiting_date = State()


def _text(settings, *, counters_count: int = 0) -> str:
    lines = [
        f"{ce('settings')}<b>Настройки</b>",
        "",
        f"Расписание: <b>{calendar_mode_label(settings.calendar_mode)}</b>",
    ]
    if counters_count:
        lines.append(f"Даты: <b>{counters_count}</b>")
    return "\n".join(lines)


def _kb(settings, *, counters_count: int = 0):
    return settings_kb(
        settings.calendar_mode,
        counters_count=counters_count,
    )


async def _counters_payload(session, db_user):
    counters = await cnt_svc.list_counters(session, db_user.id)
    return cnt_svc.hub_text(counters), counters_hub_kb(counters), counters


async def _show_counters(callback, session, db_user, user_settings, state: FSMContext):
    await state.clear()
    text, kb, _ = await _counters_payload(session, db_user)
    await show_screen(callback, text, kb, user_settings=user_settings)


@router.message(Command("settings"))
async def cmd_settings(
    message: Message, session, db_user, user_settings, state: FSMContext
) -> None:
    await state.clear()
    counters = await cnt_svc.list_counters(session, db_user.id)
    await clear_keyboard(
        message.bot, message.chat.id, user_settings.last_kb_message_id
    )
    sent = await message.answer(
        _text(user_settings, counters_count=len(counters)),
        reply_markup=_kb(user_settings, counters_count=len(counters)),
    )
    await remember_keyboard(user_settings, sent, bot=message.bot)


@router.callback_query(F.data == "menu:settings")
async def cb_settings(
    callback: CallbackQuery, session, db_user, user_settings, state: FSMContext
) -> None:
    await state.clear()
    await callback.answer()
    counters = await cnt_svc.list_counters(session, db_user.id)
    await show_screen(
        callback,
        _text(user_settings, counters_count=len(counters)),
        _kb(user_settings, counters_count=len(counters)),
        user_settings=user_settings,
    )


@router.callback_query(F.data == "settings:toggle_mode")
async def cb_toggle_mode(
    callback: CallbackQuery, session, db_user, user_settings
) -> None:
    user_settings.calendar_mode = next_calendar_mode(user_settings.calendar_mode)
    await callback.answer(calendar_mode_label(user_settings.calendar_mode))
    counters = await cnt_svc.list_counters(session, db_user.id)
    await callback.message.edit_text(
        _text(user_settings, counters_count=len(counters)),
        reply_markup=_kb(user_settings, counters_count=len(counters)),
    )


@router.callback_query(F.data == "settings:counters")
async def cb_counters_hub(
    callback: CallbackQuery, session, db_user, user_settings, state: FSMContext
) -> None:
    await callback.answer()
    await _show_counters(callback, session, db_user, user_settings, state)


@router.callback_query(F.data == "cnt:add")
async def cb_counter_add(
    callback: CallbackQuery, user_settings, state: FSMContext
) -> None:
    await state.set_state(CounterForm.waiting_name)
    await callback.answer()
    await show_screen(
        callback,
        cnt_svc.prompt_name_text(),
        counters_cancel_kb(),
        user_settings=user_settings,
    )


@router.callback_query(F.data.regexp(r"^cnt:mode:(until|since|date)$"))
async def cb_counter_mode(
    callback: CallbackQuery, user_settings, state: FSMContext
) -> None:
    mode = callback.data.rsplit(":", 1)[-1]
    data = await state.get_data()
    name = data.get("cnt_name")
    if not name:
        await callback.answer("Сначала название", show_alert=True)
        return
    await state.update_data(cnt_mode=mode)
    await state.set_state(CounterForm.waiting_date)
    await callback.answer()
    await show_screen(
        callback,
        cnt_svc.prompt_date_text(name, mode),
        counters_cancel_kb(),
        user_settings=user_settings,
    )


@router.callback_query(F.data.regexp(r"^cnt:open:(\d+)$"))
async def cb_counter_open(
    callback: CallbackQuery, session, db_user, user_settings
) -> None:
    counter_id = int(callback.data.rsplit(":", 1)[-1])
    counter = await cnt_svc.get_counter(session, db_user.id, counter_id)
    if not counter:
        await callback.answer("Не найдено", show_alert=True)
        return
    await callback.answer()
    await show_screen(
        callback,
        f"{ce('calendar')}\n{cnt_svc.counter_line(counter)}",
        counter_detail_kb(counter.id),
        user_settings=user_settings,
    )


@router.callback_query(F.data.regexp(r"^cnt:del:(\d+)$"))
async def cb_counter_del(
    callback: CallbackQuery, session, db_user, user_settings, state: FSMContext
) -> None:
    counter_id = int(callback.data.rsplit(":", 1)[-1])
    if not await cnt_svc.delete_counter(session, db_user.id, counter_id):
        await callback.answer("Не найдено", show_alert=True)
        return
    await callback.answer("Удалено")
    await _show_counters(callback, session, db_user, user_settings, state)


@router.message(StateFilter(CounterForm.waiting_name), F.text)
async def on_counter_name(
    message: Message, user_settings, state: FSMContext
) -> None:
    name = " ".join((message.text or "").split()).strip()
    if not name:
        await message.answer("Напишите название.")
        return
    if len(name) > cnt_svc.MAX_NAME_LEN:
        await message.answer(f"Короче — до {cnt_svc.MAX_NAME_LEN} символов.")
        return
    await state.update_data(cnt_name=name)
    await state.set_state(None)
    await clear_keyboard(
        message.bot, message.chat.id, user_settings.last_kb_message_id
    )
    sent = await message.answer(
        cnt_svc.prompt_mode_text(name),
        reply_markup=counters_mode_kb(),
    )
    await remember_keyboard(user_settings, sent, bot=message.bot)


@router.message(StateFilter(CounterForm.waiting_date), F.text)
async def on_counter_date(
    message: Message, session, db_user, user_settings, state: FSMContext
) -> None:
    data = await state.get_data()
    name = data.get("cnt_name")
    mode = data.get("cnt_mode")
    if not name or not mode:
        await state.clear()
        await message.answer("Настройки → Даты.")
        return
    target = cnt_svc.parse_date(message.text or "")
    if target is None:
        await message.answer(
            "Не разобрал дату. Пример: <code>31.12.2026</code>."
        )
        return
    result = await cnt_svc.create_counter(
        session,
        db_user.id,
        name=name,
        mode=mode,
        target_on=target,
    )
    if isinstance(result, str):
        await message.answer(result)
        return
    await state.clear()
    await clear_keyboard(
        message.bot, message.chat.id, user_settings.last_kb_message_id
    )
    text, kb, _ = await _counters_payload(session, db_user)
    sent = await message.answer(
        f"{ce('check')}«{result.name}» добавлено.\n\n{text}",
        reply_markup=kb,
    )
    await remember_keyboard(user_settings, sent, bot=message.bot)
