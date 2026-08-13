from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.utils.custom_emoji import icon_id


def _btn(text: str, callback_data: str, icon: str | None = None) -> InlineKeyboardButton:
    kwargs: dict = {"text": text, "callback_data": callback_data}
    if icon:
        kwargs["icon_custom_emoji_id"] = icon_id(icon)
    return InlineKeyboardButton(**kwargs)


def main_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(_btn("Состояние", "ci:hub", "stats"))
    b.row(_btn("Секундомер", "menu:stopwatch", "timer"))
    return b.as_markup()


def back_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(_btn("« Меню", "menu:home", "home"))
    return b.as_markup()


def stopwatch_kb(status: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if status == "running":
        b.row(
            _btn("Пауза", "sw:pause", "alarm"),
            _btn("Круг", "sw:lap", "plus"),
        )
        b.row(
            _btn("Обновить", "sw:refresh", "timer"),
            _btn("Сброс", "sw:reset", "cross"),
        )
    elif status == "paused":
        b.row(_btn("Продолжить", "sw:start", "check"))
        b.row(_btn("Сброс", "sw:reset", "cross"))
    else:
        b.row(_btn("Старт", "sw:start", "check"))
    b.row(_btn("« Меню", "menu:home", "home"))
    return b.as_markup()


def settings_kb(calendar_mode: str, pushes: bool) -> InlineKeyboardMarkup:
    from app.services.calendar_mode import calendar_button_label

    b = InlineKeyboardBuilder()
    b.row(_btn(calendar_button_label(calendar_mode), "settings:toggle_mode", "uni"))
    b.row(
        _btn(
            f"Пуши: {'вкл' if pushes else 'выкл'}",
            "settings:toggle_pushes",
            "bell",
        )
    )
    b.row(_btn("« Меню", "menu:home", "home"))
    return b.as_markup()


def checkin_hub_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(_btn("Отметить сейчас", "ci:ask:now", "check"))
    b.row(_btn("График месяца", "ci:chart:month", "chart"))
    b.row(_btn("« Меню", "menu:home", "home"))
    return b.as_markup()


def checkin_choose_kb() -> InlineKeyboardMarkup:
    """После «Отметить сейчас» — выбор измерения."""
    b = InlineKeyboardBuilder()
    b.row(
        _btn("Физическое", "ci:ask:phys", "gym"),
        _btn("Моральное", "ci:ask:moral", "star"),
    )
    b.row(_btn("« Назад", "ci:hub", "home"))
    return b.as_markup()


def checkin_score_kb(
    *,
    kind: str,
    period: str,
    prefix: str = "ci",
    checkin_id: int | None = None,
    allow_skip: bool = False,
) -> InlineKeyboardMarkup:
    """
    kind: p (physical in full flow) | m (moral in full flow) | phys | moral
    period: m | e
    checkin_id: для шага moral полного опроса
    allow_skip: кнопка «Не отмечать» (для пушей и добровольного пропуска)
    """
    b = InlineKeyboardBuilder()
    row = []
    for n in range(1, 6):
        data = f"{prefix}:{kind}:{period}:{n}"
        if checkin_id is not None:
            data = f"{data}:{checkin_id}"
        row.append(_btn(str(n), data))
    b.row(*row)
    if allow_skip:
        b.row(_btn("Не отмечать", "ci:skip", "cross"))
    # из выбора физ/мораль — назад к выбору; из пуша полного опроса — к хабу
    back = "ci:ask:now" if kind in ("phys", "moral") else "ci:hub"
    b.row(_btn("« Назад", back, "home"))
    return b.as_markup()


def checkin_done_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(_btn("График месяца", "ci:chart:month", "chart"))
    b.row(_btn("Состояние", "ci:hub", "stats"), _btn("« Меню", "menu:home", "home"))
    return b.as_markup()


def checkin_month_kb(year: int, month: int) -> InlineKeyboardMarkup:
    """Навигация по месяцам: ◀ ▶."""
    b = InlineKeyboardBuilder()
    b.row(
        _btn("◀", f"ci:chart:month:{year:04d}-{month:02d}:prev"),
        _btn(f"{month:02d}.{year}", f"ci:chart:month:{year:04d}-{month:02d}"),
        _btn("▶", f"ci:chart:month:{year:04d}-{month:02d}:next"),
    )
    b.row(_btn("Состояние", "ci:hub", "stats"), _btn("« Меню", "menu:home", "home"))
    return b.as_markup()
