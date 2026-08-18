from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.utils.custom_emoji import icon_id, icon_label


def _btn(
    text: str,
    callback_data: str,
    icon: str | None = None,
    *,
    tight: bool = False,
) -> InlineKeyboardButton:
    if icon and tight:
        return InlineKeyboardButton(text=icon_label(icon, text), callback_data=callback_data)
    if icon:
        return InlineKeyboardButton(
            text=text,
            callback_data=callback_data,
            icon_custom_emoji_id=icon_id(icon),
        )
    return InlineKeyboardButton(text=text, callback_data=callback_data)


def _append_home(b: InlineKeyboardBuilder) -> None:
    b.row(_btn("Главное меню", "menu:home", "home"))


def _append_main_nav(b: InlineKeyboardBuilder) -> None:
    """Разделы только для главного меню."""
    b.row(_btn("Состояние", "ci:hub", "stats"))
    b.row(_btn("Финансы", "fin:hub", "money"))
    b.row(_btn("Секундомер", "menu:stopwatch", "timer"))


def main_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    _append_main_nav(b)
    return b.as_markup()


def back_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    _append_home(b)
    return b.as_markup()


def stopwatch_kb(status: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if status == "running":
        b.row(
            _btn("Пауза", "sw:pause", "sw_pause"),
            _btn("Круг", "sw:lap", "sw_lap"),
        )
        b.row(
            _btn("Обновить", "sw:refresh", "sw_refresh"),
            _btn("Сброс", "sw:reset", "sw_reset"),
        )
    elif status == "paused":
        b.row(_btn("Продолжить", "sw:start", "sw_continue"))
        b.row(_btn("Сброс", "sw:reset", "sw_reset"))
    else:
        b.row(_btn("Старт", "sw:start", "sw_start"))
    _append_home(b)
    return b.as_markup()


def settings_kb(
    calendar_mode: str,
    *,
    counters_count: int = 0,
) -> InlineKeyboardMarkup:
    from app.services.calendar_mode import calendar_button_label

    b = InlineKeyboardBuilder()
    b.row(_btn(calendar_button_label(calendar_mode), "settings:toggle_mode", "uni"))
    label = f"Даты · {counters_count}" if counters_count else "Даты"
    b.row(_btn(label, "settings:counters", "calendar"))
    _append_home(b)
    return b.as_markup()


def counters_hub_kb(counters: list) -> InlineKeyboardMarkup:
    from app.services.counters import counter_btn_label

    b = InlineKeyboardBuilder()
    b.row(_btn("Добавить", "cnt:add", "plus"))
    for c in counters[:10]:
        icon = "calendar" if getattr(c, "mode", "") == "date" else "timer"
        b.row(_btn(counter_btn_label(c), f"cnt:open:{c.id}", icon))
    b.row(_btn("« Назад", "menu:settings", "settings"))
    return b.as_markup()


def counters_mode_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(_btn("Осталось", "cnt:mode:until", "calendar"))
    b.row(_btn("Прошло", "cnt:mode:since", "timer"))
    b.row(_btn("Дата", "cnt:mode:date", "check"))
    b.row(_btn("Отмена", "settings:counters", "cross"))
    return b.as_markup()


def counters_cancel_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(_btn("Отмена", "settings:counters", "cross"))
    return b.as_markup()


def counter_detail_kb(counter_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(_btn("Удалить", f"cnt:del:{counter_id}", "trash"))
    b.row(_btn("« Назад", "settings:counters", "calendar"))
    return b.as_markup()


def checkin_hub_kb() -> InlineKeyboardMarkup:
    """Устарело: хаб сразу шлёт график. Оставлено для совместимости."""
    b = InlineKeyboardBuilder()
    b.row(_btn("Отметить состояние", "ci:ask:now", "refresh"))
    b.row(_btn("Главное меню", "menu:home", "home"))
    return b.as_markup()


def checkin_choose_kb() -> InlineKeyboardMarkup:
    """После «Отметить сейчас» — выбор измерения."""
    b = InlineKeyboardBuilder()
    b.row(_btn("Физическое", "ci:ask:phys", "phys"))
    b.row(_btn("Моральное", "ci:ask:moral", "star"))
    b.row(_btn("« Назад", "ci:hub", "home"))
    _append_home(b)
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
    _append_home(b)
    return b.as_markup()


def checkin_done_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(_btn("Отметить состояние", "ci:ask:now", "refresh"))
    _append_home(b)
    return b.as_markup()


def checkin_month_kb(year: int, month: int) -> InlineKeyboardMarkup:
    """Навигация по месяцам: ◀ ▶ + отметить состояние / главное меню."""
    b = InlineKeyboardBuilder()
    b.row(
        _btn("◀", f"ci:chart:month:{year:04d}-{month:02d}:prev"),
        _btn(f"{month:02d}.{year}", f"ci:chart:month:{year:04d}-{month:02d}"),
        _btn("▶", f"ci:chart:month:{year:04d}-{month:02d}:next"),
    )
    b.row(_btn("Отметить состояние", "ci:ask:now", "refresh"))
    b.row(_btn("Главное меню", "menu:home", "home"))
    return b.as_markup()


def finance_hub_kb() -> InlineKeyboardMarkup:
    """Устарело: хаб сразу шлёт график. Оставлено для совместимости."""
    b = InlineKeyboardBuilder()
    b.row(_btn("Обновить баланс", "fin:update", "refresh"))
    b.row(_btn("Главное меню", "menu:home", "home"))
    return b.as_markup()


def finance_skip_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(_btn("Назад", "fin:choose", "home"))
    b.row(_btn("Пропустить", "fin:skip", "cross"))
    return b.as_markup()


def finance_cancel_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(_btn("Назад", "fin:choose", "home"))
    b.row(_btn("Отмена", "fin:hub", "cross"))
    return b.as_markup()


def finance_choose_kb(*, allow_skip: bool = False) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(_btn("Изменить деньги", "fin:edit:cash", "money"))
    b.row(_btn("Изменить долги", "fin:edit:debt", "money"))
    if allow_skip:
        b.row(_btn("Пропустить", "fin:skip", "cross"))
    else:
        b.row(_btn("Отмена", "fin:hub", "cross"))
    return b.as_markup()


def finance_month_kb(year: int, month: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        _btn("◀", f"fin:chart:month:{year:04d}-{month:02d}:prev"),
        _btn(f"{month:02d}.{year}", f"fin:chart:month:{year:04d}-{month:02d}"),
        _btn("▶", f"fin:chart:month:{year:04d}-{month:02d}:next"),
    )
    b.row(_btn("Обновить баланс", "fin:update", "refresh"))
    b.row(_btn("Главное меню", "menu:home", "home"))
    return b.as_markup()

