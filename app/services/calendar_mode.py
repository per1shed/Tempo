"""Учебное время / каникулы — авто по сезону + ручной override."""

from __future__ import annotations

from datetime import date

from app.utils.datetime_utils import today

# auto | term | holiday
CALENDAR_MODES = ("auto", "term", "holiday")


def seasonal_mode(d: date | None = None) -> str:
    """
    Типичный учебный год РФ:
    - летние каникулы: июнь–август
    - зимние каникулы: январь
    - остальное — учебное время
    """
    d = d or today()
    if d.month in (6, 7, 8) or d.month == 1:
        return "holiday"
    return "term"


def effective_calendar_mode(stored: str, d: date | None = None) -> str:
    """Что реально применять в расписании."""
    if stored == "auto":
        return seasonal_mode(d)
    if stored in ("term", "holiday"):
        return stored
    return seasonal_mode(d)


def next_calendar_mode(current: str) -> str:
    order = list(CALENDAR_MODES)
    try:
        i = order.index(current)
    except ValueError:
        return "auto"
    return order[(i + 1) % len(order)]


def calendar_mode_label(stored: str, d: date | None = None) -> str:
    eff = effective_calendar_mode(stored, d)
    eff_ru = "учебное время" if eff == "term" else "каникулы"
    if stored == "auto":
        return f"авто → {eff_ru}"
    if stored == "term":
        return "учебное время (вручную)"
    return "каникулы (вручную)"


def calendar_button_label(stored: str) -> str:
    if stored == "auto":
        return "Календарь: авто"
    if stored == "term":
        return "Календарь: учёба"
    return "Календарь: каникулы"
