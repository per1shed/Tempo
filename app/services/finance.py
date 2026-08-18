from __future__ import annotations

import calendar
import re
from datetime import date
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FinanceLog, UserSettings
from app.services import charts
from app.utils.custom_emoji import ce
from app.utils.datetime_utils import today


class Balance(NamedTuple):
    cash: float
    debt: float
    updated_on: date | None


def format_money(amount: float | None, *, empty: str = "—") -> str:
    if amount is None:
        return empty
    n = int(round(amount))
    sign = "−" if n < 0 else ""
    body = f"{abs(n):,}".replace(",", " ")
    return f"{sign}{body} ₽"


def parse_amount(text: str) -> float | None:
    """Разбор суммы: 45000, 45 000, 45.5к, 12,5 тыс."""
    raw = (text or "").strip().lower()
    if not raw:
        return None
    raw = (
        raw.replace("₽", " ")
        .replace("руб.", " ")
        .replace("руб", " ")
        .replace("rur", " ")
        .replace("rub", " ")
    )
    mult = 1.0
    if re.search(r"(тыс|тысяч|k|к)\b", raw):
        mult = 1000.0
        raw = re.sub(r"(тыс|тысяч|k|к)\b", " ", raw)
    raw = raw.replace(" ", "").replace("\u00a0", "")
    raw = raw.replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", raw)
    if not m:
        return None
    try:
        return float(m.group(0)) * mult
    except ValueError:
        return None


def parse_pair(text: str) -> tuple[float, float] | None:
    """Два числа в одном сообщении: деньги и долг."""
    raw = (text or "").strip()
    if not raw:
        return None
    lines = [ln.strip() for ln in raw.replace(";", "\n").splitlines() if ln.strip()]
    if len(lines) >= 2:
        a, b = parse_amount(lines[0]), parse_amount(lines[1])
        if a is not None and b is not None:
            return a, max(0.0, b)
    parts = re.split(r"[/\s]+", raw)
    nums: list[float] = []
    for p in parts:
        v = parse_amount(p)
        if v is not None:
            nums.append(v)
    if len(nums) >= 2:
        return nums[0], max(0.0, nums[1])
    return None


async def get_latest_log(session: AsyncSession, user_id: int) -> FinanceLog | None:
    result = await session.execute(
        select(FinanceLog)
        .where(FinanceLog.user_id == user_id)
        .order_by(FinanceLog.logged_on.desc(), FinanceLog.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_balance(
    session: AsyncSession, user_id: int, settings: UserSettings | None = None
) -> Balance | None:
    """Текущий баланс — всегда из настроек (с подхватом из истории при первом чтении)."""
    if settings is not None and settings.finance_cash is not None:
        return Balance(
            cash=float(settings.finance_cash),
            debt=float(settings.finance_debt or 0.0),
            updated_on=settings.finance_updated_on,
        )
    latest = await get_latest_log(session, user_id)
    if latest is None:
        return None
    if settings is not None:
        settings.finance_cash = float(latest.cash)
        settings.finance_debt = float(latest.debt)
        settings.finance_updated_on = latest.logged_on
        await session.flush()
    return Balance(
        cash=float(latest.cash),
        debt=float(latest.debt),
        updated_on=latest.logged_on,
    )


async def save_balance(
    session: AsyncSession,
    user_id: int,
    *,
    cash: float,
    debt: float,
    settings: UserSettings | None = None,
    logged_on: date | None = None,
) -> FinanceLog:
    """
    Обновляет постоянный баланс и пишет точку в историю для графика.
    Баланс не привязан к месяцу — месяц нужен только графику.
    """
    day = logged_on or today()
    cash_f = float(cash)
    debt_f = max(0.0, float(debt))

    if settings is not None:
        settings.finance_cash = cash_f
        settings.finance_debt = debt_f
        settings.finance_updated_on = day

    # одна точка на день: обновляем сегодняшнюю, иначе создаём
    result = await session.execute(
        select(FinanceLog)
        .where(FinanceLog.user_id == user_id, FinanceLog.logged_on == day)
        .order_by(FinanceLog.id.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row:
        row.cash = cash_f
        row.debt = debt_f
    else:
        row = FinanceLog(
            user_id=user_id,
            logged_on=day,
            cash=cash_f,
            debt=debt_f,
        )
        session.add(row)
    await session.flush()
    return row


async def get_today(session: AsyncSession, user_id: int) -> FinanceLog | None:
    d = today()
    result = await session.execute(
        select(FinanceLog)
        .where(FinanceLog.user_id == user_id, FinanceLog.logged_on == d)
        .order_by(FinanceLog.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_log_before(
    session: AsyncSession, user_id: int, before: date
) -> FinanceLog | None:
    result = await session.execute(
        select(FinanceLog)
        .where(FinanceLog.user_id == user_id, FinanceLog.logged_on < before)
        .order_by(FinanceLog.logged_on.desc(), FinanceLog.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def list_for_month(
    session: AsyncSession, user_id: int, *, year: int, month: int
) -> list[FinanceLog]:
    days = calendar.monthrange(year, month)[1]
    start = date(year, month, 1)
    end = date(year, month, days)
    result = await session.execute(
        select(FinanceLog)
        .where(
            FinanceLog.user_id == user_id,
            FinanceLog.logged_on >= start,
            FinanceLog.logged_on <= end,
        )
        .order_by(FinanceLog.logged_on.asc(), FinanceLog.id.asc())
    )
    return list(result.scalars().all())


def month_series_filled(
    logs: list[FinanceLog],
    *,
    year: int,
    month: int,
    prior: FinanceLog | None = None,
    balance: Balance | None = None,
) -> tuple[dict[int, float], dict[int, float]]:
    """
    День → cash/debt с переносом последнего известного значения.
    Так график месяца продолжает баланс из прошлого.
    """
    days = calendar.monthrange(year, month)[1]
    by_day: dict[int, tuple[float, float]] = {}
    for row in logs:
        if row.logged_on.year == year and row.logged_on.month == month:
            by_day[row.logged_on.day] = (float(row.cash), float(row.debt))

    if prior is not None:
        cash, debt = float(prior.cash), float(prior.debt)
    elif balance is not None and not by_day:
        # нет точек в месяце, но баланс есть — горизонталь на конец/сегодня
        cash, debt = balance.cash, balance.debt
    else:
        cash = debt = None  # type: ignore[assignment]

    ref = today()
    last_day = days
    if (year, month) == (ref.year, ref.month):
        last_day = ref.day
    elif date(year, month, 1) > ref:
        return {}, {}

    cash_by: dict[int, float] = {}
    debt_by: dict[int, float] = {}
    for day in range(1, last_day + 1):
        if day in by_day:
            cash, debt = by_day[day]
        if cash is None:
            continue
        cash_by[day] = cash
        debt_by[day] = debt if debt is not None else 0.0
    return cash_by, debt_by


def _balance_summary_lines(cash: float, debt: float) -> list[str]:
    lines = [
        f"Баланс: <b>{format_money(cash)}</b>",
        f"Долги: <b>{format_money(debt)}</b>",
    ]
    net = cash - debt
    if abs(cash - net) >= 0.5:
        lines.append(f"Баланс с учётом долгов: <b>{format_money(net)}</b>")
    return lines


def hub_text(balance: Balance | None, *, today_logged: bool) -> str:
    lines = [
        f"{ce('money')}<b>Финансы</b>",
        "",
    ]
    if balance:
        lines.extend(_balance_summary_lines(balance.cash, balance.debt))
        if balance.updated_on:
            lines.append(f"Обновлено: {balance.updated_on.strftime('%d.%m.%Y')}")
    else:
        lines.append("Пока нет записей. Отметьте вечерний опрос или обновите вручную.")

    if today_logged:
        lines.append("")
        lines.append("Сегодняшняя отметка уже сохранена.")

    lines.extend(
        [
            "",
            "Вечером после самочувствия бот спросит баланс и долги.",
        ]
    )
    return "\n".join(lines)


def prompt_evening_intro_text(
    *,
    physical: int | None = None,
    moral: int | None = None,
    balance: Balance | None = None,
) -> str:
    from app.services.checkin import format_score

    lines = [
        f"{ce('moon')}<b>Вечер · финансы</b>",
        "",
    ]
    if physical is not None or moral is not None:
        lines.append("Самочувствие сохранено.")
        if physical is not None:
            lines.append(f"{ce('gym')}Физическое: <b>{format_score(physical)}</b>")
        if moral is not None:
            lines.append(f"{ce('star')}Моральное: <b>{format_score(moral)}</b>")
        lines.append("")
    if balance:
        lines.append(
            f"Сейчас: баланс {format_money(balance.cash)} · долги {format_money(balance.debt)}"
        )
        lines.append("")
    lines.extend(
        [
            "Коротко зафиксируем финансовое положение на конец дня.",
            "Что изменить?",
        ]
    )
    return "\n".join(lines)


def prompt_choose_text(*, balance: Balance | None = None) -> str:
    lines = [
        f"{ce('money')}<b>Финансы · обновить</b>",
        "",
    ]
    if balance:
        lines.extend(_balance_summary_lines(balance.cash, balance.debt))
        lines.append("")
    lines.append("Что изменить?")
    return "\n".join(lines)


def prompt_cash_text(*, balance: Balance | None = None) -> str:
    lines = [
        f"{ce('money')}<b>Финансы · баланс</b>",
        "",
    ]
    if balance:
        lines.append(f"Сейчас: <b>{format_money(balance.cash)}</b>")
        lines.append("")
    lines.extend(
        [
            "Какой сейчас <b>баланс</b> (наличные + счета)?",
            "",
            "Пример: <code>45 000</code>",
        ]
    )
    return "\n".join(lines)


def prompt_debt_text(*, cash: float | None = None, debt: float | None = None) -> str:
    lines = [
        f"{ce('money')}<b>Финансы · долги</b>",
        "",
    ]
    if debt is not None:
        lines.append(f"Сейчас: <b>{format_money(debt)}</b>")
        lines.append("")
    elif cash is not None:
        lines.append(f"Баланс: <b>{format_money(cash)}</b>")
        lines.append("")
    lines.extend(
        [
            "Какая сейчас <b>сумма долгов</b>?",
            "Кредиты, займы — одной цифрой.",
            "Если долгов нет — отправьте <code>0</code>.",
        ]
    )
    return "\n".join(lines)


def saved_text(*, cash: float, debt: float) -> str:
    lines = [
        f"{ce('check')}<b>Финансы сохранены</b>",
        "",
        *_balance_summary_lines(cash, debt),
        "",
        "Баланс обновлён в постоянной памяти.",
    ]
    return "\n".join(lines)


def month_dashboard_png(
    *,
    year: int,
    month: int,
    cash_by_day: dict[int, float],
    debt_by_day: dict[int, float],
    balance: Balance | None = None,
) -> bytes:
    return charts.render_finance_dashboard(
        year=year,
        month=month,
        cash_by_day=cash_by_day,
        debt_by_day=debt_by_day,
        latest_cash=balance.cash if balance else None,
        latest_debt=balance.debt if balance else None,
    )


# совместимость со старыми именами
async def get_latest(session: AsyncSession, user_id: int) -> FinanceLog | None:
    return await get_latest_log(session, user_id)


async def create_log(
    session: AsyncSession,
    user_id: int,
    *,
    cash: float,
    debt: float,
    logged_on: date | None = None,
    settings: UserSettings | None = None,
) -> FinanceLog:
    return await save_balance(
        session,
        user_id,
        cash=cash,
        debt=debt,
        settings=settings,
        logged_on=logged_on,
    )
