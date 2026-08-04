from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.config import get_settings


def tz() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


def now() -> datetime:
    return datetime.now(tz())


def today() -> date:
    return now().date()


def to_local(dt: datetime) -> datetime:
    """Приводит datetime к часовому поясу бота (Europe/Moscow)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz())
    return dt.astimezone(tz())


def format_local(dt: datetime | None, fmt: str = "%H:%M") -> str:
    if dt is None:
        return "—"
    return to_local(dt).strftime(fmt)


def parse_hhmm(value: str) -> time:
    hour, minute = value.strip().split(":")
    return time(int(hour), int(minute))


def combine_local(d: date, t: time) -> datetime:
    return datetime(d.year, d.month, d.day, t.hour, t.minute, tzinfo=tz())


def days_until_new_year(ref: date | None = None) -> int:
    ref = ref or today()
    target = date(ref.year + 1, 1, 1)
    if ref.month == 1 and ref.day == 1:
        return 0
    return (target - ref).days


def _days_word(days: int) -> str:
    if days % 10 == 1 and days % 100 != 11:
        return "день"
    if 2 <= days % 10 <= 4 and not (12 <= days % 100 <= 14):
        return "дня"
    return "дней"


def new_year_label(ref: date | None = None, *, short: bool = False) -> str:
    days = days_until_new_year(ref)
    if days == 0:
        return "Сегодня Новый год!"
    if short:
        return f"До НГ: {days} {_days_word(days)}"
    return f"До Нового года: {days} {_days_word(days)}"


def format_duration(hours: float | None) -> str:
    if hours is None:
        return "—"
    total_min = int(round(hours * 60))
    h, m = divmod(total_min, 60)
    return f"{h}ч {m:02d}м"


def weekday_ru(d: date | None = None) -> str:
    names = (
        "понедельник",
        "вторник",
        "среда",
        "четверг",
        "пятница",
        "суббота",
        "воскресенье",
    )
    return names[(d or today()).weekday()]
