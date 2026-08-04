from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.utils.custom_emoji import icon_id


def _btn(text: str, callback_data: str, icon: str | None = None) -> InlineKeyboardButton:
    kwargs: dict = {"text": text, "callback_data": callback_data}
    if icon:
        kwargs["icon_custom_emoji_id"] = icon_id(icon)
    return InlineKeyboardButton(**kwargs)


def main_menu_kb() -> InlineKeyboardMarkup | None:
    """Главный экран без inline-кнопок — секундомер только через /stopwatch."""
    return None


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
