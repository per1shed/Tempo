from __future__ import annotations

from datetime import date, timedelta

from app.models import UserSettings
from app.services.calendar_mode import effective_calendar_mode
from app.services import charts
from app.services.schedule import (
    BlockKind,
    active_block,
    current_block,
    day_status_line,
    format_block_range,
    schedule_for_day,
)
from app.utils.datetime_utils import new_year_label, now, today, weekday_ru
from app.utils.custom_emoji import block_ce, ce


def _mode(settings: UserSettings, d=None) -> str:
    return effective_calendar_mode(settings.calendar_mode, d)


def home_text(
    settings: UserSettings,
    name: str | None = None,
    *,
    counters: list | None = None,
) -> str:
    """Главный экран: статус дня (бывший «Сейчас») + меню."""
    from app.services import counters as cnt_svc

    display_name = (name or "Pavel").strip() or "Pavel"
    at = now()
    mode = _mode(settings, at.date())
    blocks = schedule_for_day(at.date(), calendar_mode=mode)
    cur = current_block(blocks, at)

    lines = [
        f"{ce('person')}{display_name}",
        "",
        f"{ce('calendar')}{weekday_ru().capitalize()}, {today().strftime('%d.%m.%Y')}",
        f"{ce('timer')}{new_year_label(short=True)}",
    ]
    if counters:
        lines.extend(cnt_svc.home_lines(counters))
    if cur is not None and cur.kind != BlockKind.FREE:
        lines.append("")
        lines.append(
            f"{block_ce(cur.kind)}Сейчас: <b>{cur.title}</b> ({format_block_range(cur)})"
        )
    return "\n".join(lines)


def home_chart_png(settings: UserSettings) -> bytes:
    at = now()
    mode = _mode(settings, at.date())
    blocks = schedule_for_day(at.date(), calendar_mode=mode)
    cur = active_block(blocks, at)
    subtitle = day_status_line(at.date(), calendar_mode=mode)
    return charts.render_focus_blocks(
        blocks=blocks,
        current=cur,
        title=weekday_ru().capitalize(),
        subtitle=subtitle,
        now_label=at.strftime("%d.%m"),
        now_time=at.timetz().replace(tzinfo=None),
    )


def now_text(settings: UserSettings) -> str:
    return home_text(settings)


def schedule_text(settings: UserSettings, offset: int = 0) -> str:
    d = today() + timedelta(days=offset)
    mode = _mode(settings, d)
    blocks = schedule_for_day(d, calendar_mode=mode)
    status = day_status_line(d, calendar_mode=mode)
    lines = [
        f"{ce('calendar')}<b>Расписание</b> · {weekday_ru(d).capitalize()}, {d.strftime('%d.%m')}",
        status,
        "",
    ]
    for b in blocks:
        lines.append(f"• {format_block_range(b)} — {b.title}")
    return "\n".join(lines)


def hourly_push_text(settings: UserSettings) -> str:
    return home_text(settings)
