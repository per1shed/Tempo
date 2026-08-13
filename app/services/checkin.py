from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import StateCheckin
from app.services import charts
from app.utils.custom_emoji import ce
from app.utils.datetime_utils import now, today, weekday_ru

PERIOD_MORNING = "morning"
PERIOD_EVENING = "evening"

PERIOD_LABEL = {
    PERIOD_MORNING: "Утро",
    PERIOD_EVENING: "Вечер",
}

SCORE_LABEL = {
    1: "Плохо",
    2: "Так себе",
    3: "Нормально",
    4: "Хорошо",
    5: "Отлично",
}


def resolve_period(at=None) -> str:
    """До 15:00 — утро, иначе вечер."""
    h = (at or now()).hour
    return PERIOD_MORNING if 5 <= h < 15 else PERIOD_EVENING


def clamp_score(value: int) -> int:
    return max(1, min(5, int(value)))


def format_score(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{value}/5 · {SCORE_LABEL.get(value, '')}"


async def get_latest_checkin(
    session: AsyncSession,
    user_id: int,
    *,
    day: date | None = None,
    period: str,
) -> StateCheckin | None:
    """Последняя запись за день/слот (для экрана «сегодня»)."""
    day = day or today()
    result = await session.execute(
        select(StateCheckin)
        .where(
            StateCheckin.user_id == user_id,
            StateCheckin.logged_on == day,
            StateCheckin.period == period,
        )
        .order_by(StateCheckin.created_at.desc(), StateCheckin.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


# совместимость со старым именем
get_checkin = get_latest_checkin


async def count_today(
    session: AsyncSession,
    user_id: int,
    *,
    day: date | None = None,
    period: str | None = None,
) -> int:
    day = day or today()
    stmt = select(func.count()).where(
        StateCheckin.user_id == user_id,
        StateCheckin.logged_on == day,
    )
    if period is not None:
        stmt = stmt.where(StateCheckin.period == period)
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def create_checkin(
    session: AsyncSession,
    user_id: int,
    *,
    period: str,
    day: date | None = None,
    physical: int | None = None,
    moral: int | None = None,
) -> StateCheckin:
    """Всегда новая строка — история не затирается."""
    day = day or today()
    row = StateCheckin(
        user_id=user_id,
        logged_on=day,
        period=period,
        physical=clamp_score(physical) if physical is not None else None,
        moral=clamp_score(moral) if moral is not None else None,
    )
    session.add(row)
    await session.flush()
    return row


async def set_moral_on(
    session: AsyncSession,
    user_id: int,
    checkin_id: int,
    *,
    moral: int,
) -> StateCheckin | None:
    """Дописывает моральное к уже созданной записи полного опроса."""
    result = await session.execute(
        select(StateCheckin).where(
            StateCheckin.id == checkin_id,
            StateCheckin.user_id == user_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    row.moral = clamp_score(moral)
    await session.flush()
    return row


async def list_recent(
    session: AsyncSession,
    user_id: int,
    *,
    days: int = 14,
) -> list[StateCheckin]:
    start = today() - timedelta(days=days - 1)
    result = await session.execute(
        select(StateCheckin)
        .where(
            StateCheckin.user_id == user_id,
            StateCheckin.logged_on >= start,
        )
        .order_by(StateCheckin.logged_on.asc(), StateCheckin.created_at.asc())
    )
    return list(result.scalars().all())


def _daily_averages(
    rows: list[StateCheckin],
    *,
    days: int = 14,
) -> tuple[
    list[tuple[str, float]],
    list[tuple[str, float]],
    list[tuple[str, float]],
    list[tuple[str, float]],
]:
    """Средние и все сырые отметки физ/мораль по дням."""
    by_day: dict[date, dict[str, list[int]]] = {}
    for r in rows:
        bucket = by_day.setdefault(r.logged_on, {"physical": [], "moral": []})
        if r.physical is not None:
            bucket["physical"].append(r.physical)
        if r.moral is not None:
            bucket["moral"].append(r.moral)

    phys_avg: list[tuple[str, float]] = []
    moral_avg: list[tuple[str, float]] = []
    phys_raw: list[tuple[str, float]] = []
    moral_raw: list[tuple[str, float]] = []
    start = today() - timedelta(days=days - 1)
    for i in range(days):
        d = start + timedelta(days=i)
        label = d.strftime("%d.%m")
        bucket = by_day.get(d)
        if not bucket:
            continue
        for v in bucket["physical"]:
            phys_raw.append((label, float(v)))
        for v in bucket["moral"]:
            moral_raw.append((label, float(v)))
        if bucket["physical"]:
            phys_avg.append(
                (label, sum(bucket["physical"]) / len(bucket["physical"]))
            )
        if bucket["moral"]:
            moral_avg.append(
                (label, sum(bucket["moral"]) / len(bucket["moral"]))
            )
    return phys_avg, moral_avg, phys_raw, moral_raw


def chart_png(rows: list[StateCheckin], *, days: int = 14) -> bytes:
    phys_avg, moral_avg, phys_raw, moral_raw = _daily_averages(rows, days=days)
    period = "14 дней" if days == 14 else f"{days} дней"
    return charts.render_dual_line_chart(
        series=[
            ("Физическое · среднее", phys_avg, charts.ACCENT_GREEN),
            ("Моральное · среднее", moral_avg, charts.ACCENT_BLUE),
        ],
        raw_series=[
            ("physical", phys_raw, charts.ACCENT_GREEN),
            ("moral", moral_raw, charts.ACCENT_BLUE),
        ],
        title="Самочувствие",
        subtitle=f"Линия — среднее за день, точки — все отметки · {period}",
        y_min=1,
        y_max=5,
    )


async def list_for_month(
    session: AsyncSession,
    user_id: int,
    *,
    year: int,
    month: int,
) -> list[StateCheckin]:
    import calendar as cal_mod

    start = date(year, month, 1)
    last = cal_mod.monthrange(year, month)[1]
    end = date(year, month, last)
    result = await session.execute(
        select(StateCheckin)
        .where(
            StateCheckin.user_id == user_id,
            StateCheckin.logged_on >= start,
            StateCheckin.logged_on <= end,
        )
        .order_by(StateCheckin.logged_on.asc(), StateCheckin.created_at.asc())
    )
    return list(result.scalars().all())


def month_series(
    rows: list[StateCheckin],
    *,
    year: int,
    month: int,
) -> tuple[dict[int, float], dict[int, float]]:
    """День месяца → среднее физ / мораль (1–5)."""
    by_day: dict[date, dict[str, list[int]]] = {}
    for r in rows:
        if r.logged_on.year != year or r.logged_on.month != month:
            continue
        bucket = by_day.setdefault(r.logged_on, {"physical": [], "moral": []})
        if r.physical is not None:
            bucket["physical"].append(r.physical)
        if r.moral is not None:
            bucket["moral"].append(r.moral)

    phys: dict[int, float] = {}
    moral: dict[int, float] = {}
    for d, bucket in by_day.items():
        if bucket["physical"]:
            phys[d.day] = sum(bucket["physical"]) / len(bucket["physical"])
        if bucket["moral"]:
            moral[d.day] = sum(bucket["moral"]) / len(bucket["moral"])
    return phys, moral


def month_dashboard_png(
    rows: list[StateCheckin],
    *,
    year: int,
    month: int,
    phys_delta: float | None = None,
    moral_delta: float | None = None,
    balance_delta: float | None = None,
    header_day: int | None = None,
) -> bytes:
    phys, moral = month_series(rows, year=year, month=month)
    return charts.render_state_dashboard_b2(
        year=year,
        month=month,
        phys_by_day=phys,
        moral_by_day=moral,
        phys_delta=phys_delta,
        moral_delta=moral_delta,
        balance_delta=balance_delta,
        header_day=header_day,
    )


def hub_text(
    *,
    morning: StateCheckin | None,
    evening: StateCheckin | None,
    recent: list[StateCheckin],
    morning_count: int = 0,
    evening_count: int = 0,
) -> str:
    d = today()
    lines = [
        f"{ce('stats')}<b>Состояние</b>",
        f"{weekday_ru(d).capitalize()}, {d.strftime('%d.%m.%Y')}",
        "",
        f"{ce('sun')}<b>Утро</b> · записей: {morning_count}",
        f"Последнее физ.: {format_score(morning.physical if morning else None)}",
        f"Последнее мор.: {format_score(morning.moral if morning else None)}",
        "",
        f"{ce('moon')}<b>Вечер</b> · записей: {evening_count}",
        f"Последнее физ.: {format_score(evening.physical if evening else None)}",
        f"Последнее мор.: {format_score(evening.moral if evening else None)}",
    ]

    phys_vals = [r.physical for r in recent if r.physical is not None]
    moral_vals = [r.moral for r in recent if r.moral is not None]
    if phys_vals or moral_vals:
        lines.append("")
        lines.append(f"{ce('chart')}<b>Среднее · 14 дней</b>")
        if phys_vals:
            avg_p = sum(phys_vals) / len(phys_vals)
            lines.append(f"Физическое: {avg_p:.1f}/5 ({len(phys_vals)} отм.)")
        if moral_vals:
            avg_m = sum(moral_vals) / len(moral_vals)
            lines.append(f"Моральное: {avg_m:.1f}/5 ({len(moral_vals)} отм.)")
    return "\n".join(lines)


def prompt_choose_text(period: str) -> str:
    label = PERIOD_LABEL.get(period, period)
    icon = "sun" if period == PERIOD_MORNING else "moon"
    return (
        f"{ce(icon)}<b>{label} · отметить</b>\n\n"
        "Что хочешь оценить?"
    )


def prompt_physical_text(period: str) -> str:
    label = PERIOD_LABEL.get(period, period)
    icon = "sun" if period == PERIOD_MORNING else "moon"
    return (
        f"{ce(icon)}<b>{label} · самочувствие</b>\n\n"
        f"{ce('gym')}Как <b>физическое</b> состояние?\n"
        "1 — плохо · 5 — отлично"
    )


def prompt_moral_text(period: str, *, physical: int | None = None) -> str:
    label = PERIOD_LABEL.get(period, period)
    icon = "sun" if period == PERIOD_MORNING else "moon"
    lines = [f"{ce(icon)}<b>{label} · самочувствие</b>", ""]
    if physical is not None:
        lines.append(f"Физическое: <b>{format_score(physical)}</b>")
        lines.append("")
    lines.append(f"{ce('star')}Как <b>моральное</b> состояние?")
    lines.append("1 — плохо · 5 — отлично")
    return "\n".join(lines)


def prompt_physical_only_text(period: str) -> str:
    label = PERIOD_LABEL.get(period, period)
    return (
        f"{ce('gym')}<b>Физическое · {label.lower()}</b>\n\n"
        "Оцени от 1 до 5\n"
        "1 — плохо · 5 — отлично"
    )


def prompt_moral_only_text(period: str) -> str:
    label = PERIOD_LABEL.get(period, period)
    return (
        f"{ce('star')}<b>Моральное · {label.lower()}</b>\n\n"
        "Оцени от 1 до 5\n"
        "1 — плохо · 5 — отлично"
    )


def saved_text(row: StateCheckin) -> str:
    label = PERIOD_LABEL.get(row.period, row.period)
    return (
        f"{ce('check')}<b>Сохранено · {label.lower()}</b>\n\n"
        f"{ce('gym')}Физическое: <b>{format_score(row.physical)}</b>\n"
        f"{ce('star')}Моральное: <b>{format_score(row.moral)}</b>\n\n"
        "Каждая отметка сохраняется в историю."
    )


def saved_dim_text(*, kind: str, period: str, score: int) -> str:
    label = PERIOD_LABEL.get(period, period)
    if kind == "physical":
        return (
            f"{ce('check')}<b>Физическое сохранено</b> · {label.lower()}\n\n"
            f"{ce('gym')}{format_score(score)}\n\n"
            "Добавлено в историю (предыдущие отметки на месте)."
        )
    return (
        f"{ce('check')}<b>Моральное сохранено</b> · {label.lower()}\n\n"
        f"{ce('star')}{format_score(score)}\n\n"
        "Добавлено в историю (предыдущие отметки на месте)."
    )
