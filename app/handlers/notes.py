from __future__ import annotations

import math

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.keyboards import (
    notes_confirm_kb,
    notes_edit_kb,
    notes_folders_kb,
    notes_list_kb,
    notes_move_kb,
    notes_note_kb,
)
from app.services import notes as notes_svc
from app.utils.custom_emoji import ce
from app.utils.telegram_ui import clear_keyboard, remember_keyboard, show_screen

router = Router(name="notes")


class NotesForm(StatesGroup):
    browsing = State()
    viewing = State()
    editing = State()


def _folder_back(folder_id: int, page: int) -> str:
    return f"notes:f:{folder_id}:{page}" if page else f"notes:f:{folder_id}"


async def _reply(target, text: str, kb, user_settings) -> None:
    if isinstance(target, CallbackQuery):
        await show_screen(target, text, kb, user_settings=user_settings)
        return
    await clear_keyboard(target.bot, target.chat.id, user_settings.last_kb_message_id)
    sent = await target.answer(text, reply_markup=kb)
    await remember_keyboard(user_settings, sent, bot=target.bot)


async def _show_folders(
    target,
    session,
    db_user,
    user_settings,
    state: FSMContext,
) -> None:
    await state.set_state(NotesForm.browsing)
    await state.update_data(
        notes_folder_id=None, notes_list_page=0, notes_screen="folders"
    )
    cats = await notes_svc.list_categories(session, db_user.id)
    counts = await notes_svc.category_counts(session, db_user.id)
    text = notes_svc.folders_text(categories=cats)
    kb = notes_folders_kb(cats, counts)
    await _reply(target, text, kb, user_settings)


async def _show_list(
    target,
    session,
    db_user,
    user_settings,
    state: FSMContext,
    *,
    folder_id: int,
    page: int = 0,
) -> None:
    cat = await notes_svc.get_category(session, db_user.id, folder_id)
    if not cat:
        await _show_folders(target, session, db_user, user_settings, state)
        return
    total = await notes_svc.count_notes(
        session, db_user.id, category_id=folder_id
    )
    pages = max(1, math.ceil(total / notes_svc.PAGE_SIZE))
    page = max(0, min(page, pages - 1))
    notes = await notes_svc.list_notes(
        session,
        db_user.id,
        category_id=folder_id,
        limit=notes_svc.PAGE_SIZE,
        offset=page * notes_svc.PAGE_SIZE,
    )
    await state.set_state(NotesForm.browsing)
    await state.update_data(
        notes_folder_id=folder_id, notes_list_page=page, notes_screen="list"
    )
    text = notes_svc.list_text(
        heading=cat.name, total=total, page=page, pages=pages
    )
    kb = notes_list_kb(notes, folder_id=folder_id, page=page, pages=pages)
    await _reply(target, text, kb, user_settings)


async def _show_note(
    target,
    note,
    user_settings,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    folder_id = data.get("notes_folder_id") or note.category_id
    page = int(data.get("notes_list_page") or 0)
    await state.set_state(NotesForm.viewing)
    await state.update_data(
        note_view_id=note.id, notes_folder_id=folder_id, notes_list_page=page
    )
    text = notes_svc.note_detail_text(note)
    kb = notes_note_kb(note.id, list_back=_folder_back(int(folder_id), page))
    await _reply(target, text, kb, user_settings)


@router.callback_query(F.data == "notes:hub")
@router.callback_query(F.data.regexp(r"^notes:hub:(\d+)$"))
@router.callback_query(F.data == "notes:folders")
@router.callback_query(F.data == "notes:all")
@router.callback_query(F.data.regexp(r"^notes:all:(\d+)$"))
async def cb_hub(
    callback: CallbackQuery, session, db_user, user_settings, state: FSMContext
) -> None:
    await callback.answer()
    await _show_folders(callback, session, db_user, user_settings, state)


@router.callback_query(F.data == "notes:add_folder")
async def cb_add_folder(
    callback: CallbackQuery, session, db_user, user_settings, state: FSMContext
) -> None:
    await callback.answer("Напишите название папки")
    await _show_folders(callback, session, db_user, user_settings, state)


@router.callback_query(F.data.regexp(r"^notes:f:(\d+)(?::(\d+))?$"))
@router.callback_query(F.data.regexp(r"^notes:cat:(\d+)$"))
async def cb_folder(
    callback: CallbackQuery, session, db_user, user_settings, state: FSMContext
) -> None:
    parts = callback.data.split(":")
    folder_id = int(parts[2])
    page = int(parts[3]) if len(parts) >= 4 else 0
    cat = await notes_svc.get_category(session, db_user.id, folder_id)
    if not cat:
        await callback.answer("Папка не найдена", show_alert=True)
        await _show_folders(callback, session, db_user, user_settings, state)
        return
    await callback.answer()
    await _show_list(
        callback,
        session,
        db_user,
        user_settings,
        state,
        folder_id=folder_id,
        page=page,
    )


@router.callback_query(F.data.regexp(r"^notes:rmf:(\d+)$"))
async def cb_rm_folder(
    callback: CallbackQuery, session, db_user, user_settings
) -> None:
    cat_id = int(callback.data.rsplit(":", 1)[-1])
    cat = await notes_svc.get_category(session, db_user.id, cat_id)
    if not cat:
        await callback.answer("Папка не найдена", show_alert=True)
        return
    count = await notes_svc.count_notes(session, db_user.id, category_id=cat.id)
    await callback.answer()
    await show_screen(
        callback,
        notes_svc.confirm_delete_folder_text(cat, count),
        notes_confirm_kb(f"notes:rmfok:{cat.id}", "notes:hub"),
        user_settings=user_settings,
    )


@router.callback_query(F.data.regexp(r"^notes:rmfok:(\d+)$"))
async def cb_rm_folder_ok(
    callback: CallbackQuery, session, db_user, user_settings, state: FSMContext
) -> None:
    cat_id = int(callback.data.rsplit(":", 1)[-1])
    err = await notes_svc.delete_category(session, db_user.id, cat_id)
    if err:
        await callback.answer(err, show_alert=True)
        return
    await callback.answer("Папка удалена")
    await _show_folders(callback, session, db_user, user_settings, state)


@router.callback_query(F.data.regexp(r"^notes:open:(\d+)$"))
async def cb_open_note(
    callback: CallbackQuery, session, db_user, user_settings, state: FSMContext
) -> None:
    note_id = int(callback.data.rsplit(":", 1)[-1])
    note = await notes_svc.get_note(session, db_user.id, note_id)
    if not note or note.category_id is None:
        await callback.answer("Не найдено", show_alert=True)
        return
    await callback.answer()
    await _show_note(callback, note, user_settings, state)


@router.callback_query(F.data.regexp(r"^notes:edit:(\d+)$"))
async def cb_edit_note(
    callback: CallbackQuery, session, db_user, user_settings, state: FSMContext
) -> None:
    note_id = int(callback.data.rsplit(":", 1)[-1])
    note = await notes_svc.get_note(session, db_user.id, note_id)
    if not note:
        await callback.answer("Не найдено", show_alert=True)
        return
    await state.set_state(NotesForm.editing)
    await state.update_data(note_view_id=note.id)
    await callback.answer()
    await show_screen(
        callback,
        notes_svc.prompt_edit_text(note),
        notes_edit_kb(note.id),
        user_settings=user_settings,
    )


@router.callback_query(F.data.regexp(r"^notes:move:(\d+)$"))
async def cb_move(
    callback: CallbackQuery, session, db_user, user_settings, state: FSMContext
) -> None:
    note_id = int(callback.data.rsplit(":", 1)[-1])
    note = await notes_svc.get_note(session, db_user.id, note_id)
    if not note:
        await callback.answer("Не найдено", show_alert=True)
        return
    cats = await notes_svc.list_categories(session, db_user.id)
    others = [c for c in cats if c.id != note.category_id]
    if not others:
        await callback.answer("Нет других папок", show_alert=True)
        return
    await state.set_state(NotesForm.viewing)
    await state.update_data(note_view_id=note.id)
    await callback.answer()
    await show_screen(
        callback,
        f"{ce('folder')}<b>В папку</b>\n\nКуда перенести?",
        notes_move_kb(note.id, cats, current_id=note.category_id),
        user_settings=user_settings,
    )


@router.callback_query(F.data.regexp(r"^notes:to:(\d+):(\d+)$"))
async def cb_move_to(
    callback: CallbackQuery, session, db_user, user_settings, state: FSMContext
) -> None:
    _, _, note_id_s, cat_id_s = callback.data.split(":")
    result = await notes_svc.move_note(
        session, db_user.id, int(note_id_s), int(cat_id_s)
    )
    if isinstance(result, str):
        await callback.answer(result, show_alert=True)
        return
    await callback.answer("Готово")
    await state.update_data(notes_folder_id=result.category_id, notes_list_page=0)
    note = await notes_svc.get_note(session, db_user.id, result.id)
    await _show_note(callback, note, user_settings, state)


@router.callback_query(F.data.regexp(r"^notes:del:(\d+)$"))
async def cb_del_note(
    callback: CallbackQuery, session, db_user, user_settings
) -> None:
    note_id = int(callback.data.rsplit(":", 1)[-1])
    note = await notes_svc.get_note(session, db_user.id, note_id)
    if not note:
        await callback.answer("Не найдено", show_alert=True)
        return
    await callback.answer()
    await show_screen(
        callback,
        notes_svc.confirm_delete_note_text(note),
        notes_confirm_kb(f"notes:delok:{note.id}", f"notes:open:{note.id}"),
        user_settings=user_settings,
    )


@router.callback_query(F.data.regexp(r"^notes:delok:(\d+)$"))
async def cb_del_note_ok(
    callback: CallbackQuery, session, db_user, user_settings, state: FSMContext
) -> None:
    note_id = int(callback.data.rsplit(":", 1)[-1])
    data = await state.get_data()
    folder_id = data.get("notes_folder_id")
    page = int(data.get("notes_list_page") or 0)
    note = await notes_svc.get_note(session, db_user.id, note_id)
    if note and folder_id is None:
        folder_id = note.category_id
    if not await notes_svc.delete_note(session, db_user.id, note_id):
        await callback.answer("Не найдено", show_alert=True)
        return
    await callback.answer("Удалено")
    if folder_id is None:
        await _show_folders(callback, session, db_user, user_settings, state)
        return
    await _show_list(
        callback,
        session,
        db_user,
        user_settings,
        state,
        folder_id=int(folder_id),
        page=page,
    )


@router.message(StateFilter(NotesForm.browsing), F.text)
async def on_browsing_text(
    message: Message, session, db_user, user_settings, state: FSMContext
) -> None:
    data = await state.get_data()
    screen = data.get("notes_screen")
    if screen == "list":
        folder_id = data.get("notes_folder_id")
        if folder_id is None:
            await _show_folders(message, session, db_user, user_settings, state)
            return
        result = await notes_svc.create_note(
            session,
            db_user.id,
            text=notes_svc.message_html(message),
            category_id=int(folder_id),
        )
        if isinstance(result, str):
            await message.answer(result)
            return
        note = await notes_svc.get_note(session, db_user.id, result.id)
        await _show_note(message, note, user_settings, state)
        return

    result = await notes_svc.create_category(session, db_user.id, message.text or "")
    if isinstance(result, str):
        await message.answer(result)
        return
    await _show_list(
        message,
        session,
        db_user,
        user_settings,
        state,
        folder_id=result.id,
        page=0,
    )


@router.message(StateFilter(NotesForm.viewing), F.text)
async def on_viewing_append(
    message: Message, session, db_user, user_settings, state: FSMContext
) -> None:
    data = await state.get_data()
    note_id = data.get("note_view_id")
    if not note_id:
        await state.clear()
        return
    result = await notes_svc.append_note_text(
        session, db_user.id, int(note_id), notes_svc.message_html(message)
    )
    if isinstance(result, str):
        await message.answer(result)
        return
    note = await notes_svc.get_note(session, db_user.id, result.id)
    await _show_note(message, note, user_settings, state)


@router.message(StateFilter(NotesForm.editing), F.text)
async def on_editing_replace(
    message: Message, session, db_user, user_settings, state: FSMContext
) -> None:
    data = await state.get_data()
    note_id = data.get("note_view_id")
    if not note_id:
        await state.clear()
        return
    result = await notes_svc.replace_note_text(
        session, db_user.id, int(note_id), notes_svc.message_html(message)
    )
    if isinstance(result, str):
        await message.answer(result)
        return
    note = await notes_svc.get_note(session, db_user.id, result.id)
    await _show_note(message, note, user_settings, state)
