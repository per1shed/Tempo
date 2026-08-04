from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import StopwatchState
from app.utils.custom_emoji import ce
from app.utils.datetime_utils import now, to_local


STATUS_LABEL = {
    "idle": "остановлен",
    "running": "идёт",
    "paused": "пауза",
}


async def get_or_create(session: AsyncSession, user_id: int) -> StopwatchState:
    result = await session.execute(
        select(StopwatchState).where(StopwatchState.user_id == user_id)
    )
    state = result.scalar_one_or_none()
    if state is not None:
        return state
    state = StopwatchState(user_id=user_id)
    session.add(state)
    await session.flush()
    return state


def elapsed_seconds(state: StopwatchState) -> float:
    total = float(state.elapsed_before or 0.0)
    if state.status == "running" and state.segment_started_at is not None:
        started = to_local(state.segment_started_at)
        total += max(0.0, (now() - started).total_seconds())
    return total


def format_elapsed(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    ms = total_ms % 1000
    total_sec = total_ms // 1000
    h, rem = divmod(total_sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}.{ms // 100}"
    return f"{m:02d}:{s:02d}.{ms // 100}"


def get_laps(state: StopwatchState) -> list[float]:
    try:
        data = json.loads(state.laps_json or "[]")
        if isinstance(data, list):
            return [float(x) for x in data]
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    return []


def _set_laps(state: StopwatchState, laps: list[float]) -> None:
    state.laps_json = json.dumps(laps)


async def start(session: AsyncSession, state: StopwatchState) -> StopwatchState:
    if state.status == "running":
        return state
    state.status = "running"
    state.segment_started_at = now()
    await session.flush()
    return state


async def pause(session: AsyncSession, state: StopwatchState) -> StopwatchState:
    if state.status != "running":
        return state
    state.elapsed_before = elapsed_seconds(state)
    state.segment_started_at = None
    state.status = "paused"
    await session.flush()
    return state


async def reset(session: AsyncSession, state: StopwatchState) -> StopwatchState:
    state.status = "idle"
    state.segment_started_at = None
    state.elapsed_before = 0.0
    _set_laps(state, [])
    await session.flush()
    return state


async def lap(session: AsyncSession, state: StopwatchState) -> StopwatchState:
    if state.status != "running":
        return state
    laps = get_laps(state)
    laps.append(elapsed_seconds(state))
    _set_laps(state, laps)
    await session.flush()
    return state


def screen_text(state: StopwatchState) -> str:
    elapsed = elapsed_seconds(state)
    status = STATUS_LABEL.get(state.status, state.status)
    lines = [
        f"{ce('timer')}<b>Секундомер</b>",
        "",
        f"<code>{format_elapsed(elapsed)}</code>",
        f"Статус: <b>{status}</b>",
    ]
    laps = get_laps(state)
    if laps:
        lines.append("")
        lines.append("<b>Круги</b>")
        prev = 0.0
        for i, total in enumerate(laps, start=1):
            split = total - prev
            lines.append(
                f"{i}. {format_elapsed(total)}"
                f"  <i>(+{format_elapsed(split)})</i>"
            )
            prev = total
    if state.status == "running":
        lines.append("")
        lines.append("Нажми «Обновить», чтобы увидеть актуальное время.")
    return "\n".join(lines)
