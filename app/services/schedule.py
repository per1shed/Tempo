from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum


class BlockKind(str, Enum):
    ROUTINE_MORNING = "routine_morning"
    ROUTINE_EVENING = "routine_evening"
    UNIVERSITY = "university"
    ENGLISH = "english"
    GYM = "gym"
    IT = "it"
    STUDY = "study"  # самообучение / IT вместо универа на каникулах / вс
    FREE = "free"  # синтетический зазор между блоками (не в списке расписания)
    SLEEP = "sleep"
    RECOVERY = "recovery"


@dataclass(frozen=True)
class Block:
    start: time
    end: time
    kind: BlockKind
    title: str
    color: str = "#8E8E93"

    @property
    def key(self) -> str:
        return f"{self.kind.value}_{self.start.strftime('%H%M')}"

    def contains(self, t: time) -> bool:
        if self.start <= self.end:
            return self.start <= t < self.end
        # overnight (not used now)
        return t >= self.start or t < self.end


def _t(h: int, m: int = 0) -> time:
    return time(h, m)


# Палитра по смыслу занятия (тёплое утро → холодный вечер/сон)
C = {
    "routine_morning": "#FFD60A",  # жёлтый — рассвет, подъём
    "university": "#8B7355",       # тёплый тауп — учёба, кампус
    "study": "#6C5CE7",            # индиго — глубокий фокус / самообучение
    "english": "#FF6B3D",          # коралл — речь, общение
    "gym": "#30D158",              # зелёный — тело, энергия
    "it": "#0A84FF",               # синий — код, экран
    "routine_evening": "#AF52DE",  # сирень — закат, сворачивание дня
    "sleep": "#4854A8",            # ночной индиго — сон
    "free": "#C7C7CC",             # нейтральный серый — пауза
    "recovery": "#64D2FF",         # мягкий небо-голубой — восстановление
}


def _morning_routine() -> Block:
    return Block(
        _t(6, 30),
        _t(7, 30),
        BlockKind.ROUTINE_MORNING,
        "Утренняя рутина",
        C["routine_morning"],
    )


def _evening_and_sleep() -> list[Block]:
    return [
        Block(
            _t(20, 30),
            _t(22, 30),
            BlockKind.ROUTINE_EVENING,
            "Вечерняя рутина",
            C["routine_evening"],
        ),
        Block(_t(22, 30), _t(6, 30), BlockKind.SLEEP, "Сон", C["sleep"]),
    ]


def _day_block_730_1400(*, term: bool, is_sunday: bool) -> Block:
    """Пн–пт в учебное время — университет; иначе самообучение/IT."""
    if is_sunday or not term:
        return Block(
            _t(7, 30),
            _t(14, 0),
            BlockKind.STUDY,
            "Самообучение / IT",
            C["study"],
        )
    return Block(
        _t(7, 30),
        _t(14, 0),
        BlockKind.UNIVERSITY,
        "Университет",
        C["university"],
    )


def schedule_for_day(d: date, *, calendar_mode: str = "auto") -> list[Block]:
    """
    Сжатый распорядок: только зафиксированные блоки.
    Свободные окна (14:00–14:30, 15:00–16:30 и т.п.) не заполняются.

    calendar_mode: 'term' | 'holiday' | 'auto'
    Суббота — день отдыха: один блок Recovery day на весь день + сон.
    Воскресенье — без зала, без университета.
    Пн/ср/пт — зал + IT.
    Вт/чт — IT без зала.
    """
    wd = d.weekday()  # 0=Mon ... 5=Sat 6=Sun
    if calendar_mode == "auto":
        from app.services.calendar_mode import seasonal_mode

        calendar_mode = seasonal_mode(d)
    term = calendar_mode == "term"

    if wd == 5:  # Saturday — полный день отдыха
        return [
            Block(
                _t(6, 30),
                _t(22, 30),
                BlockKind.RECOVERY,
                "Recovery day",
                C["recovery"],
            ),
            Block(_t(22, 30), _t(6, 30), BlockKind.SLEEP, "Сон", C["sleep"]),
        ]

    blocks: list[Block] = [_morning_routine()]
    blocks.append(_day_block_730_1400(term=term, is_sunday=(wd == 6)))
    # 14:00–14:30 свободно
    blocks.append(
        Block(_t(14, 30), _t(15, 0), BlockKind.ENGLISH, "Английский", C["english"])
    )
    # 15:00–16:30 свободно

    if wd in (0, 2, 4):  # Mon Wed Fri — gym
        blocks.append(Block(_t(16, 30), _t(18, 30), BlockKind.GYM, "Зал", C["gym"]))
        blocks.append(Block(_t(18, 30), _t(20, 30), BlockKind.IT, "IT", C["it"]))
    else:  # Tue Thu Sun — no gym, long IT
        blocks.append(Block(_t(16, 30), _t(20, 30), BlockKind.IT, "IT", C["it"]))

    blocks.extend(_evening_and_sleep())
    return blocks


def previous_block(blocks: list[Block], at: datetime) -> Block | None:
    t = at.timetz().replace(tzinfo=None)
    past = [b for b in blocks if b.kind != BlockKind.SLEEP and b.end <= t]
    if past:
        return max(past, key=lambda b: (b.end.hour, b.end.minute))
    return None


def current_block(blocks: list[Block], at: datetime) -> Block | None:
    t = at.timetz().replace(tzinfo=None)
    for b in blocks:
        if b.kind == BlockKind.SLEEP:
            if t >= b.start or t < _t(6, 30):
                return b
        elif b.contains(t):
            return b
    return None


def free_gap_block(blocks: list[Block], at: datetime) -> Block | None:
    """
    Если сейчас в зазоре между запланированными блоками —
    синтетический блок «Свободное время» от конца предыдущего до начала следующего.
    В список расписания не попадает.
    """
    if current_block(blocks, at) is not None:
        return None
    prev = previous_block(blocks, at)
    nxt = next_block(blocks, at)
    if not prev or not nxt:
        return None
    t = at.timetz().replace(tzinfo=None)
    if prev.end <= t < nxt.start:
        return Block(
            prev.end,
            nxt.start,
            BlockKind.FREE,
            "Свободное время",
            C["free"],
        )
    return None


def active_block(blocks: list[Block], at: datetime) -> Block | None:
    """Текущий запланированный блок или свободный зазор для плашки «СЕЙЧАС»."""
    return current_block(blocks, at) or free_gap_block(blocks, at)


def next_block(blocks: list[Block], at: datetime) -> Block | None:
    t = at.timetz().replace(tzinfo=None)
    upcoming = [b for b in blocks if b.kind != BlockKind.SLEEP and b.start > t]
    if upcoming:
        return min(upcoming, key=lambda b: b.start)
    morning = [b for b in blocks if b.kind != BlockKind.SLEEP]
    return morning[0] if morning else None


def block_after(blocks: list[Block], ref: Block | None) -> Block | None:
    """Следующий запланированный блок после указанного (без свободных зазоров)."""
    if ref is None or ref.kind == BlockKind.SLEEP:
        return None
    later = [
        b
        for b in blocks
        if b.kind != BlockKind.SLEEP and b.start >= ref.end and b.key != ref.key
    ]
    if later:
        return min(later, key=lambda b: b.start)
    return None


def format_block_range(b: Block) -> str:
    if b.kind == BlockKind.SLEEP:
        return f"{b.start.strftime('%H:%M')} → {b.end.strftime('%H:%M')}"
    return f"{b.start.strftime('%H:%M')}–{b.end.strftime('%H:%M')}"


def day_status_line(d: date, *, calendar_mode: str) -> str:
    wd = d.weekday()
    mode = "учебное время" if calendar_mode == "term" else "каникулы"
    if wd == 5:
        return f"Recovery day · {mode}"
    if wd in (0, 2, 4):
        return f"День с залом · {mode}"
    if wd == 6:
        return f"Воскресенье · без зала · {mode}"
    return f"Без зала · {mode}"


def hourly_push_times() -> list[time]:
    """Устарело: пуши теперь на смене слотов."""
    return block_transition_times()


def block_transition_times() -> list[time]:
    """
    Моменты старта запланированных блоков по всем дням недели и режимам.
    Свободные окна не учитываются.
    """
    times: set[time] = set()
    # Любая дата-якорь; weekday задаём сдвигом
    anchor = date(2026, 1, 5)  # понедельник
    for mode in ("term", "holiday"):
        for wd in range(7):
            d = anchor + timedelta(days=wd)
            blocks = schedule_for_day(d, calendar_mode=mode)
            for b in blocks:
                times.add(b.start)
    return sorted(times)


def is_push_day(d: date) -> bool:
    """Пуши на смене слотов — все дни, включая субботу."""
    return True
