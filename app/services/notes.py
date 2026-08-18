from __future__ import annotations

import html
from datetime import date, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Note, NoteCategory
from app.utils.custom_emoji import ce
from app.utils.datetime_utils import now, to_local, today

MAX_CATEGORIES = 16
MAX_NOTE_LEN = 3500
MAX_CAT_NAME = 40
PAGE_SIZE = 8

_MONTHS = (
    "янв",
    "фев",
    "мар",
    "апр",
    "мая",
    "июн",
    "июл",
    "авг",
    "сен",
    "окт",
    "ноя",
    "дек",
)


def split_title_body(text: str) -> tuple[str, str]:
    raw = (text or "").strip()
    if not raw:
        return "Без названия", ""
    lines = raw.splitlines()
    title = lines[0].strip() or "Без названия"
    body = "\n".join(lines[1:]).strip()
    return title, body


def format_when(dt: datetime | date | None) -> str:
    if dt is None:
        return ""
    if isinstance(dt, datetime):
        local = to_local(dt)
        d = local.date()
        time_s = local.strftime("%H:%M")
    else:
        d = dt
        time_s = ""
    ref = today()
    if d == ref:
        return f"сегодня, {time_s}" if time_s else "сегодня"
    if d == ref - timedelta(days=1):
        return "вчера"
    if d.year == ref.year:
        return f"{d.day} {_MONTHS[d.month - 1]}"
    return d.strftime("%d.%m.%Y")


def note_btn_label(note: Note) -> str:
    title, _ = split_title_body(note.text)
    encoded = title.encode("utf-8")
    if len(encoded) <= 48:
        return title
    cut = title
    while cut and len(cut.encode("utf-8")) > 45:
        cut = cut[:-1]
    return cut + "…"


ORPHAN_FOLDER = "Входящие"


async def _put_orphans_in_folder(session: AsyncSession, user_id: int) -> None:
    """Старые заметки без папки кладём во «Входящие»."""
    orphan_count = await session.scalar(
        select(func.count()).where(
            Note.user_id == user_id, Note.category_id.is_(None)
        )
    )
    if not orphan_count:
        return
    result = await session.execute(
        select(NoteCategory)
        .where(NoteCategory.user_id == user_id)
        .order_by(NoteCategory.id.asc())
    )
    cats = list(result.scalars().all())
    inbox = next((c for c in cats if c.name.lower() == ORPHAN_FOLDER.lower()), None)
    if inbox is None:
        inbox = NoteCategory(user_id=user_id, name=ORPHAN_FOLDER, is_default=False)
        session.add(inbox)
        await session.flush()
    await session.execute(
        update(Note)
        .where(Note.user_id == user_id, Note.category_id.is_(None))
        .values(category_id=inbox.id)
    )
    await session.flush()


async def list_categories(
    session: AsyncSession, user_id: int
) -> list[NoteCategory]:
    await _put_orphans_in_folder(session, user_id)
    result = await session.execute(
        select(NoteCategory)
        .where(NoteCategory.user_id == user_id)
        .order_by(NoteCategory.name.asc())
    )
    return list(result.scalars().all())


async def get_category(
    session: AsyncSession, user_id: int, category_id: int
) -> NoteCategory | None:
    result = await session.execute(
        select(NoteCategory).where(
            NoteCategory.id == category_id,
            NoteCategory.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def create_category(
    session: AsyncSession, user_id: int, name: str
) -> NoteCategory | str:
    clean = " ".join((name or "").split()).strip()[:MAX_CAT_NAME]
    if not clean:
        return "Пустое имя"
    cats = await list_categories(session, user_id)
    if len(cats) >= MAX_CATEGORIES:
        return f"Лимит папок: {MAX_CATEGORIES}"
    if any(c.name.lower() == clean.lower() for c in cats):
        return "Такая папка уже есть"
    row = NoteCategory(user_id=user_id, name=clean, is_default=False)
    session.add(row)
    await session.flush()
    return row


async def delete_category(
    session: AsyncSession, user_id: int, category_id: int
) -> str | None:
    cat = await get_category(session, user_id, category_id)
    if not cat:
        return "Папка не найдена"
    await session.delete(cat)
    await session.flush()
    return None


async def create_note(
    session: AsyncSession,
    user_id: int,
    *,
    text: str,
    category_id: int,
) -> Note | str:
    clean = (text or "").strip()
    if not clean:
        return "Пустая заметка"
    clean = clean[:MAX_NOTE_LEN]
    cat = await get_category(session, user_id, category_id)
    if not cat:
        return "Папка не найдена"
    row = Note(
        user_id=user_id,
        category_id=cat.id,
        text=clean,
        is_done=False,
        is_pinned=False,
        created_on=today(),
        updated_at=now(),
    )
    session.add(row)
    await session.flush()
    return row


async def append_note_text(
    session: AsyncSession,
    user_id: int,
    note_id: int,
    text: str,
) -> Note | str:
    add = (text or "").strip()
    if not add:
        return "Пустая заметка"
    note = await get_note(session, user_id, note_id)
    if not note:
        return "Не найдено"
    merged = (note.text.rstrip() + "\n" + add).strip()
    note.text = merged[:MAX_NOTE_LEN]
    note.updated_at = now()
    await session.flush()
    return note


async def replace_note_text(
    session: AsyncSession,
    user_id: int,
    note_id: int,
    text: str,
) -> Note | str:
    clean = (text or "").strip()
    if not clean:
        return "Пустая заметка"
    note = await get_note(session, user_id, note_id)
    if not note:
        return "Не найдено"
    note.text = clean[:MAX_NOTE_LEN]
    note.updated_at = now()
    await session.flush()
    return note


async def get_note(
    session: AsyncSession, user_id: int, note_id: int
) -> Note | None:
    result = await session.execute(
        select(Note)
        .where(Note.id == note_id, Note.user_id == user_id)
        .options(selectinload(Note.category))
    )
    return result.scalar_one_or_none()


def _notes_order():
    return (Note.updated_at.desc(), Note.id.desc())


async def list_notes(
    session: AsyncSession,
    user_id: int,
    *,
    category_id: int,
    limit: int = 30,
    offset: int = 0,
) -> list[Note]:
    result = await session.execute(
        select(Note)
        .where(Note.user_id == user_id, Note.category_id == category_id)
        .options(selectinload(Note.category))
        .order_by(*_notes_order())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all())


async def count_notes(
    session: AsyncSession,
    user_id: int,
    *,
    category_id: int,
) -> int:
    result = await session.execute(
        select(func.count()).where(
            Note.user_id == user_id, Note.category_id == category_id
        )
    )
    return int(result.scalar_one() or 0)


async def move_note(
    session: AsyncSession,
    user_id: int,
    note_id: int,
    category_id: int,
) -> Note | str:
    note = await get_note(session, user_id, note_id)
    if not note:
        return "Не найдено"
    cat = await get_category(session, user_id, category_id)
    if not cat:
        return "Папка не найдена"
    note.category_id = cat.id
    note.updated_at = now()
    await session.flush()
    await session.refresh(note, attribute_names=["category"])
    return note


async def delete_note(
    session: AsyncSession, user_id: int, note_id: int
) -> bool:
    note = await get_note(session, user_id, note_id)
    if not note:
        return False
    await session.delete(note)
    await session.flush()
    return True


async def category_counts(
    session: AsyncSession, user_id: int
) -> dict[int, int]:
    result = await session.execute(
        select(Note.category_id, func.count())
        .where(Note.user_id == user_id)
        .group_by(Note.category_id)
    )
    return {
        int(cat_id): int(cnt or 0)
        for cat_id, cnt in result.all()
        if cat_id is not None
    }


def folders_text(*, categories: list[NoteCategory]) -> str:
    lines = [f"{ce('book')}<b>Заметки</b>", ""]
    if categories:
        lines.append("Откройте папку или напишите название новой.")
    else:
        lines.append("Пока нет папок. Напишите название — создам первую.")
    return "\n".join(lines)


def list_text(
    *,
    heading: str,
    total: int,
    page: int,
    pages: int,
) -> str:
    lines = [f"{ce('book')}<b>{html.escape(heading)}</b>"]
    if total:
        extra = f" · {page + 1}/{pages}" if pages > 1 else ""
        lines.append(f"{total} {_notes_word(total)}{extra}")
        lines += ["", "Напишите — новая заметка."]
    else:
        lines += ["", "Пусто. Напишите — создам заметку."]
    return "\n".join(lines)


def _notes_word(n: int) -> str:
    n_abs = abs(n) % 100
    n1 = n_abs % 10
    if 11 <= n_abs <= 14:
        return "заметок"
    if n1 == 1:
        return "заметка"
    if 2 <= n1 <= 4:
        return "заметки"
    return "заметок"


def _display_cells(text: str) -> float:
    """Приблизительная ширина строки в «клетках» Telegram."""
    cells = 0.0
    for ch in text:
        cp = ord(ch)
        if cp in (0x200B, 0x200C, 0x200D, 0xFEFF) or 0xFE00 <= cp <= 0xFE0F:
            continue
        if cp >= 0x1F300 or 0x2600 <= cp <= 0x27BF:
            cells += _CHARS_PER_STICKER
        else:
            cells += 1.0
    return cells


# 24 стикера чуть вылезали за пузырь; 12 были короче длинной строки
_DIVIDER_MAX = 22
_DIVIDER_MIN = 6
_CHARS_PER_STICKER = 2.55
_TITLE_ICON_CELLS = 2.55


def _divider_for_note(title: str, body: str, when: str) -> str:
    widest = _TITLE_ICON_CELLS + _display_cells(title)
    for raw in (body, when, "Напишите — допишу."):
        for line in (raw or "").splitlines():
            t = line.strip()
            if t:
                extra = _TITLE_ICON_CELLS if t == when else 0.0
                widest = max(widest, extra + _display_cells(t))
    n = int(widest / _CHARS_PER_STICKER + 0.5)
    n = max(_DIVIDER_MIN, min(_DIVIDER_MAX, n))
    return ce("line") * n


def note_detail_text(note: Note) -> str:
    title, body = split_title_body(note.text)
    when = format_when(note.updated_at or note.created_on)
    lines = [f"{ce('book')}<b>{html.escape(title)}</b>"]
    if body:
        lines += ["", html.escape(body)]
    if when:
        lines += [
            _divider_for_note(title, body, when),
            f"{ce('clock')}{html.escape(when)}",
        ]
    lines += ["", "Напишите — допишу."]
    text = "\n".join(lines)
    if len(text) > 3900:
        return text[:3897] + "…"
    return text


def prompt_edit_text(note: Note) -> str:
    raw = (note.text or "").strip()
    body = html.escape(raw)
    if len(body) > 3000:
        body = body[:2997] + "…"
    return (
        f"{ce('mark')}<b>Изменить</b>\n\n"
        "Скопируйте текст, поправьте и отправьте.\n\n"
        f"<pre>{body}</pre>"
    )


def confirm_delete_note_text(note: Note) -> str:
    title, _ = split_title_body(note.text)
    return (
        f"{ce('trash')}<b>Удалить заметку?</b>\n\n"
        f"«{html.escape(title)}» исчезнет."
    )


def confirm_delete_folder_text(cat: NoteCategory, count: int) -> str:
    extra = (
        f" Вместе с ней удалятся {count} {_notes_word(count)}."
        if count
        else ""
    )
    return (
        f"{ce('trash')}<b>Удалить папку?</b>\n\n"
        f"«{html.escape(cat.name)}» исчезнет.{extra}"
    )
