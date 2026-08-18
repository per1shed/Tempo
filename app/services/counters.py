from __future__ import annotations

import html
import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DateCounter
from app.utils.custom_emoji import ce
from app.utils.datetime_utils import today

MODE_UNTIL = "until"
MODE_SINCE = "since"
MODE_DATE = "date"

MODE_LABEL = {
    MODE_UNTIL: "осталось",
    MODE_SINCE: "прошло",
    MODE_DATE: "дата",
}

MODES = (MODE_UNTIL, MODE_SINCE, MODE_DATE)

MAX_COUNTERS = 10
MAX_NAME_LEN = 40


def days_word(days: int) -> str:
    n = abs(days) % 100
    n1 = n % 10
    if 11 <= n <= 14:
        return "дней"
    if n1 == 1:
        return "день"
    if 2 <= n1 <= 4:
        return "дня"
    return "дней"


def parse_date(raw: str) -> date | None:
    text = (raw or "").strip().replace(",", ".")
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%d/%m/%Y", "%d/%m/%y"):
        try:
            from datetime import datetime

            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    m = re.fullmatch(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})", text)
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100:
        y += 2000
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def counter_days(counter: DateCounter, *, ref: date | None = None) -> int:
    ref = ref or today()
    if counter.mode == MODE_DATE:
        return 0
    if counter.mode == MODE_UNTIL:
        return (counter.target_on - ref).days
    return (ref - counter.target_on).days


def format_days(counter: DateCounter, *, ref: date | None = None) -> str:
    if counter.mode == MODE_DATE:
        return counter.target_on.strftime("%d.%m.%Y")
    days = counter_days(counter, ref=ref)
    if counter.mode == MODE_UNTIL:
        if days == 0:
            return "сегодня"
        if days < 0:
            passed = abs(days)
            return f"прошло {passed} {days_word(passed)} назад"
        return f"{days} {days_word(days)}"
    if days == 0:
        return "сегодня"
    if days < 0:
        return "ещё не наступило"
    return f"{days} {days_word(days)}"


def counter_line(counter: DateCounter, *, ref: date | None = None, compact: bool = False) -> str:
    label = html.escape(counter.name)
    when = format_days(counter, ref=ref)
    date_s = counter.target_on.strftime("%d.%m.%Y")
    if compact:
        icon = "calendar" if counter.mode == MODE_DATE else "timer"
        return f"{ce(icon)}{label}: {when}"
    if counter.mode == MODE_DATE:
        return f"<b>{label}</b>\n{date_s}"
    kind = "До" if counter.mode == MODE_UNTIL else "С"
    return (
        f"<b>{label}</b>\n"
        f"{kind} {date_s} · {when}"
    )


def counter_btn_label(counter: DateCounter, *, ref: date | None = None) -> str:
    title = counter.name if len(counter.name) <= 22 else counter.name[:19] + "…"
    return f"{title} · {format_days(counter, ref=ref)}"


async def list_counters(session: AsyncSession, user_id: int) -> list[DateCounter]:
    result = await session.execute(
        select(DateCounter)
        .where(DateCounter.user_id == user_id)
        .order_by(DateCounter.id.asc())
    )
    return list(result.scalars().all())


async def get_counter(
    session: AsyncSession, user_id: int, counter_id: int
) -> DateCounter | None:
    result = await session.execute(
        select(DateCounter).where(
            DateCounter.id == counter_id,
            DateCounter.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def create_counter(
    session: AsyncSession,
    user_id: int,
    *,
    name: str,
    mode: str,
    target_on: date,
) -> DateCounter | str:
    clean = " ".join((name or "").split()).strip()[:MAX_NAME_LEN]
    if not clean:
        return "Пустое название"
    if mode not in MODES:
        return "Неверный тип"
    existing = await list_counters(session, user_id)
    if len(existing) >= MAX_COUNTERS:
        return f"Лимит: {MAX_COUNTERS}"
    row = DateCounter(
        user_id=user_id,
        name=clean,
        mode=mode,
        target_on=target_on,
    )
    session.add(row)
    await session.flush()
    return row


async def delete_counter(
    session: AsyncSession, user_id: int, counter_id: int
) -> bool:
    row = await get_counter(session, user_id, counter_id)
    if not row:
        return False
    await session.delete(row)
    await session.flush()
    return True


def hub_text(counters: list[DateCounter]) -> str:
    lines = [f"{ce('calendar')}<b>Даты</b>", ""]
    if not counters:
        lines.append("Пока пусто.")
        return "\n".join(lines)
    blocks = [counter_line(c) for c in counters]
    lines.append("\n\n".join(blocks))
    return "\n".join(lines)


def prompt_name_text() -> str:
    return (
        f"{ce('plus')}<b>Новая дата</b>\n\n"
        "Название. Пример: <code>Экзамен</code>"
    )


def prompt_mode_text(name: str) -> str:
    return (
        f"{ce('calendar')}<b>{html.escape(name)}</b>\n\n"
        "Остаток, прошедшее или просто дата?"
    )


def prompt_date_text(name: str, mode: str) -> str:
    if mode == MODE_DATE:
        kind = "какое число"
    elif mode == MODE_UNTIL:
        kind = "до какого числа"
    else:
        kind = "с какого числа"
    return (
        f"{ce('calendar')}<b>{html.escape(name)}</b> · {MODE_LABEL[mode]}\n\n"
        f"{kind.capitalize()}?\n"
        "Пример: <code>31.12.2026</code>"
    )


def home_lines(counters: list[DateCounter]) -> list[str]:
    if not counters:
        return []
    return [counter_line(c, compact=True) for c in counters]
