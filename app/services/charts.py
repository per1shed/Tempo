from __future__ import annotations

import math
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BG = (242, 242, 247)
CARD = (255, 255, 255)
TITLE = (28, 28, 30)
SECONDARY = (142, 142, 147)
GRID = (229, 229, 234)
ACCENT_BLUE = (10, 132, 255)
ACCENT_GREEN = (48, 209, 88)
ACCENT_ORANGE = (255, 159, 10)


def _load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    names = (
        ["DejaVuSans-Bold.ttf", "Arial Bold.ttf", "Helvetica.ttc"]
        if bold
        else ["DejaVuSans.ttf", "Arial.ttf", "Helvetica.ttc"]
    )
    roots = [
        Path("/usr/share/fonts/truetype/dejavu"),
        Path("/System/Library/Fonts/Supplemental"),
        Path("/Library/Fonts"),
        Path("/System/Library/Fonts"),
    ]
    for root in roots:
        for name in names:
            path = root / name
            if path.exists():
                try:
                    return ImageFont.truetype(str(path), size=size)
                except OSError:
                    continue
    return ImageFont.load_default()


def _base(width: int, height: int, title: str, subtitle: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    scale = 2
    w, h = width * scale, height * scale
    img = Image.new("RGB", (w, h), BG)
    draw = ImageDraw.Draw(img)
    pad = 40 * scale
    draw.rounded_rectangle((pad, pad, w - pad, h - pad), radius=36 * scale, fill=CARD)
    draw.text((pad * 2, pad * 1.6), title, font=_load_font(28 * scale, True), fill=TITLE)
    draw.text((pad * 2, pad * 1.6 + 44 * scale), subtitle, font=_load_font(16 * scale), fill=SECONDARY)
    return img, draw


def render_line_chart(
    points: list[tuple[str, float]],
    *,
    title: str,
    subtitle: str,
    color: tuple[int, int, int] = ACCENT_BLUE,
    y_unit: str = "",
) -> bytes:
    scale = 2
    width, height = 780, 520
    img, draw = _base(width, height, title, subtitle)
    w, h = img.size
    pad = 40 * scale
    chart_left = pad * 2
    chart_right = w - pad * 2
    chart_top = 140 * scale
    chart_bottom = h - 100 * scale

    if len(points) < 1:
        draw.text(
            (chart_left, (chart_top + chart_bottom) // 2),
            "Недостаточно данных",
            font=_load_font(18 * scale),
            fill=SECONDARY,
        )
        return _to_png(img)

    values = [v for _, v in points]
    vmin, vmax = min(values), max(values)
    if abs(vmax - vmin) < 1e-6:
        vmin -= 1
        vmax += 1
    span = vmax - vmin

    # grid
    for i in range(5):
        y = chart_top + (chart_bottom - chart_top) * i / 4
        draw.line((chart_left, y, chart_right, y), fill=GRID, width=2)
        val = vmax - span * i / 4
        label = f"{val:.1f}{y_unit}"
        draw.text((chart_left, y - 18 * scale), label, font=_load_font(12 * scale), fill=SECONDARY)

    coords = []
    n = len(points)
    for i, (label, val) in enumerate(points):
        x = chart_left if n == 1 else chart_left + (chart_right - chart_left) * i / (n - 1)
        y = chart_bottom - (val - vmin) / span * (chart_bottom - chart_top)
        coords.append((x, y, label))

    if len(coords) >= 2:
        draw.line([(x, y) for x, y, _ in coords], fill=color, width=5 * scale)
    for x, y, label in coords:
        r = 6 * scale
        draw.ellipse((x - r, y - r, x + r, y + r), fill=color)
        draw.text((x - 16 * scale, chart_bottom + 12 * scale), label, font=_load_font(11 * scale), fill=SECONDARY)

    return _to_png(img)


def render_bar_chart(
    points: list[tuple[str, float]],
    *,
    title: str,
    subtitle: str,
    color: tuple[int, int, int] = ACCENT_GREEN,
) -> bytes:
    scale = 2
    width, height = 780, 520
    img, draw = _base(width, height, title, subtitle)
    w, h = img.size
    pad = 40 * scale
    chart_left = pad * 2
    chart_right = w - pad * 2
    chart_top = 140 * scale
    chart_bottom = h - 100 * scale

    if not points:
        draw.text(
            (chart_left, (chart_top + chart_bottom) // 2),
            "Недостаточно данных",
            font=_load_font(18 * scale),
            fill=SECONDARY,
        )
        return _to_png(img)

    vmax = max(max(v for _, v in points), 1.0)
    n = len(points)
    gap = 12 * scale
    bar_w = max(10 * scale, (chart_right - chart_left - gap * (n + 1)) / n)

    for i, (label, val) in enumerate(points):
        x0 = chart_left + gap + i * (bar_w + gap)
        bar_h = (val / vmax) * (chart_bottom - chart_top)
        y0 = chart_bottom - bar_h
        draw.rounded_rectangle((x0, y0, x0 + bar_w, chart_bottom), radius=8 * scale, fill=color)
        draw.text(
            (x0, chart_bottom + 12 * scale),
            label,
            font=_load_font(11 * scale),
            fill=SECONDARY,
        )

    return _to_png(img)


def render_dual_line_chart(
    *,
    series: list[tuple[str, list[tuple[str, float]], tuple[int, int, int]]],
    title: str,
    subtitle: str,
    y_min: float | None = None,
    y_max: float | None = None,
    raw_series: list[tuple[str, list[tuple[str, float]], tuple[int, int, int]]]
    | None = None,
) -> bytes:
    """
    Линии — средние за день.
    raw_series — все отдельные отметки точками на тех же днях.
    """
    scale = 2
    width, height = 780, 560
    img, draw = _base(width, height, title, subtitle)
    w, h = img.size
    pad = 40 * scale
    chart_left = pad * 2
    chart_right = w - pad * 2
    chart_top = 150 * scale
    chart_bottom = h - 120 * scale

    all_vals = [v for _, pts, _ in series for _, v in pts]
    if raw_series:
        all_vals.extend(v for _, pts, _ in raw_series for _, v in pts)
    if not all_vals:
        draw.text(
            (chart_left, (chart_top + chart_bottom) // 2),
            "Недостаточно данных",
            font=_load_font(18 * scale),
            fill=SECONDARY,
        )
        return _to_png(img)

    vmin = y_min if y_min is not None else min(all_vals)
    vmax = y_max if y_max is not None else max(all_vals)
    if abs(vmax - vmin) < 1e-6:
        vmin -= 1
        vmax += 1
    span = vmax - vmin

    for i in range(5):
        y = chart_top + (chart_bottom - chart_top) * i / 4
        draw.line((chart_left, y, chart_right, y), fill=GRID, width=2)
        val = vmax - span * i / 4
        draw.text(
            (chart_left, y - 18 * scale),
            f"{val:.0f}",
            font=_load_font(12 * scale),
            fill=SECONDARY,
        )

    labels: list[str] = []
    seen: set[str] = set()
    for group in (raw_series or []) + series:
        for lab, _ in group[1]:
            if lab not in seen:
                seen.add(lab)
                labels.append(lab)
    n = max(len(labels), 1)
    x_of = {
        lab: (
            chart_left
            if n == 1
            else chart_left + (chart_right - chart_left) * i / (n - 1)
        )
        for i, lab in enumerate(labels)
    }
    day_width = (chart_right - chart_left) / max(n - 1, 1) if n > 1 else 40 * scale

    def _y(val: float) -> float:
        return chart_bottom - (val - vmin) / span * (chart_bottom - chart_top)

    # Сначала все сырые отметки (полупрозрачные / светлее)
    if raw_series:
        for _, pts, color in raw_series:
            by_lab: dict[str, list[float]] = {}
            for lab, val in pts:
                by_lab.setdefault(lab, []).append(val)
            soft = tuple(min(255, c + 90) for c in color)
            for lab, vals in by_lab.items():
                base_x = x_of[lab]
                k = len(vals)
                for j, val in enumerate(vals):
                    # лёгкий разброс по X, если в день несколько отметок
                    jitter = (j - (k - 1) / 2) * min(10 * scale, day_width * 0.12)
                    x = base_x + jitter
                    y = _y(val)
                    r = 4 * scale
                    draw.ellipse(
                        (x - r, y - r, x + r, y + r),
                        fill=soft,
                        outline=color,
                        width=max(1, scale // 2),
                    )

    legend_x = chart_left
    legend_y = chart_bottom + 48 * scale
    for name, pts, color in series:
        coords = []
        for lab, val in pts:
            if lab not in x_of:
                continue
            x = x_of[lab]
            y = _y(val)
            coords.append((x, y))
        if len(coords) >= 2:
            draw.line(coords, fill=color, width=5 * scale)
        point_r = 5 * scale if n > 16 else 7 * scale
        for x, y in coords:
            r = point_r
            draw.ellipse((x - r, y - r, x + r, y + r), fill=color)
            # белая обводка — средняя точка заметнее сырых
            draw.ellipse(
                (x - r, y - r, x + r, y + r),
                outline=CARD,
                width=max(2, scale),
            )
            draw.ellipse((x - r + scale, y - r + scale, x + r - scale, y + r - scale), fill=color)
        draw.rounded_rectangle(
            (legend_x, legend_y, legend_x + 18 * scale, legend_y + 18 * scale),
            radius=4 * scale,
            fill=color,
        )
        draw.text(
            (legend_x + 26 * scale, legend_y - 2 * scale),
            name,
            font=_load_font(13 * scale),
            fill=TITLE,
        )
        legend_x += 200 * scale

    if n <= 10:
        label_step = 1
    elif n <= 16:
        label_step = 2
    else:
        label_step = max(3, n // 8)
    for i, lab in enumerate(labels):
        if i % label_step != 0 and i != n - 1:
            continue
        x = x_of[lab]
        draw.text(
            (x - 16 * scale, chart_bottom + 12 * scale),
            lab,
            font=_load_font(10 * scale if n > 16 else 11 * scale),
            fill=SECONDARY,
        )

    return _to_png(img)


def _to_png(img: Image.Image) -> bytes:
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def render_focus_blocks(
    *,
    blocks: list | None = None,
    previous=None,
    current=None,
    upcoming=None,
    following=None,
    title: str = "Сейчас",
    subtitle: str = "",
    now_label: str = "",
    now_time=None,
) -> bytes:
    """
    Карточка со всеми блоками плана на день.
    Только текущий выделен синей рамкой и меткой «СЕЙЧАС».
    """
    scale = 2
    width = 780
    current_key = getattr(current, "key", None) if current else None

    if blocks is not None:
        plan = list(blocks)
    else:
        plan = []
        seen: set[str] = set()
        for b in (previous, current, upcoming, following):
            if b is None:
                continue
            k = getattr(b, "key", None)
            if k and k in seen:
                continue
            if k:
                seen.add(k)
            plan.append(b)

    display = list(plan)
    if current is not None and getattr(getattr(current, "kind", None), "value", "") == "free":
        insert_at = sum(1 for b in plan if b.end <= current.start)
        display.insert(insert_at, current)

    slots: list[tuple[object, bool]] = []
    for block in display:
        is_cur = bool(
            current is not None
            and (
                block is current
                or (current_key and getattr(block, "key", None) == current_key)
            )
        )
        slots.append((block, is_cur))

    row_cur = 100
    row_other = 78
    rows_h = sum(row_cur if is_cur else row_other for _, is_cur in slots)
    gaps = 10 * max(len(slots) - 1, 0)
    height = max(520, 140 + rows_h + gaps + 36)

    img = Image.new("RGB", (width * scale, height * scale), BG)
    draw = ImageDraw.Draw(img)
    w, h = img.size
    pad = 36 * scale

    draw.rounded_rectangle(
        (pad, pad, w - pad, h - pad),
        radius=36 * scale,
        fill=CARD,
    )

    font_title = _load_font(28 * scale, True)
    font_sub = _load_font(14 * scale)
    font_role = _load_font(11 * scale, True)
    font_name = _load_font(20 * scale, True)
    font_time = _load_font(14 * scale)

    title_y = pad * 1.4
    sub_y = title_y + 42 * scale
    draw.text((pad * 1.8, title_y), title, font=font_title, fill=TITLE)
    if subtitle:
        draw.text(
            (pad * 1.8, sub_y),
            subtitle,
            font=font_sub,
            fill=SECONDARY,
        )
    if now_label:
        # Дата по высоте: верх = «Вторник», низ = «Без зала · …»
        sub_box = font_sub.getbbox(subtitle or "А")
        sub_h = sub_box[3] - sub_box[1]
        date_top = title_y
        date_bottom = sub_y + sub_h
        date_h = max(date_bottom - date_top, 1)

        # Подбираем кегль под высоту блока заголовка
        date_size = max(18 * scale, int(date_h * 0.72))
        font_date = _load_font(date_size, True)
        tw = draw.textlength(now_label, font=font_date)
        tb = font_date.getbbox(now_label)
        text_h = tb[3] - tb[1]

        pad_x = 18 * scale
        px1 = w - pad * 1.8
        px0 = px1 - tw - pad_x * 2
        py0 = date_top
        py1 = date_bottom
        draw.rounded_rectangle(
            (px0, py0, px1, py1),
            radius=14 * scale,
            fill=(232, 240, 255),
        )
        text_x = px0 + pad_x
        text_y = py0 + (py1 - py0 - text_h) / 2 - tb[1]
        draw.text(
            (text_x, text_y),
            now_label,
            font=font_date,
            fill=ACCENT_BLUE,
        )

    card_left = pad * 1.8
    card_right = w - pad * 1.8
    y = 130 * scale

    for block, is_current in slots:
        row_h = (row_cur if is_current else row_other) * scale

        if is_current:
            bg_fill = (245, 248, 255)
            border = ACCENT_BLUE
            border_w = 3 * scale
        else:
            bg_fill = (248, 248, 250)
            border = GRID
            border_w = 2

        draw.rounded_rectangle(
            (card_left, y, card_right, y + row_h),
            radius=20 * scale,
            fill=bg_fill,
            outline=border,
            width=border_w,
        )

        accent = _hex_to_rgb(getattr(block, "color", "#8E8E93"))
        bar_w = 8 * scale
        draw.rounded_rectangle(
            (
                card_left + 14 * scale,
                y + 14 * scale,
                card_left + 14 * scale + bar_w,
                y + row_h - 14 * scale,
            ),
            radius=5 * scale,
            fill=accent,
        )

        text_x = card_left + 36 * scale
        if is_current:
            draw.text(
                (text_x, y + 12 * scale),
                "СЕЙЧАС",
                font=font_role,
                fill=ACCENT_BLUE,
            )
            name_y = y + 32 * scale
            name_color = TITLE
        else:
            name_y = y + 16 * scale
            name_color = (60, 60, 67)

        draw.text((text_x, name_y), block.title, font=font_name, fill=name_color)

        kind_val = getattr(getattr(block, "kind", None), "value", "")
        if kind_val == "sleep" or block.end < block.start:
            time_range = f"{block.start.strftime('%H:%M')} → {block.end.strftime('%H:%M')}"
        else:
            time_range = f"{block.start.strftime('%H:%M')}–{block.end.strftime('%H:%M')}"
        draw.text(
            (text_x, name_y + 28 * scale),
            time_range,
            font=font_time,
            fill=SECONDARY,
        )

        y += row_h + 10 * scale

    return _to_png(img)


def render_day_timeline(
    blocks: list,
    *,
    now_time=None,
    title: str = "Сегодня",
    subtitle: str = "",
    previous=None,
    current=None,
    upcoming=None,
) -> bytes:
    """Карточка со всеми блоками дня."""
    from datetime import datetime as dt

    from app.services.schedule import active_block

    at = dt.combine(dt.today().date(), now_time) if now_time else dt.now()
    cur = current if current is not None else active_block(blocks, at)
    return render_focus_blocks(
        blocks=blocks,
        current=cur,
        title=title,
        subtitle=subtitle,
        now_label=at.strftime("%d.%m"),
        now_time=now_time if hasattr(now_time, "hour") else at.time(),
    )


# --- B2 dashboard — exact Apple reference layout --------------------------------

CAL_RED = (255, 59, 48)  # выходные на оси самочувствия
# P2 · голубая шкала календаря
CAL_LOW = (186, 212, 245)
CAL_MID = (90, 200, 250)
CAL_HIGH = (10, 132, 255)  # = LINE_BLUE
CAL_EMPTY = (229, 229, 234)
WD_SHORT = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
LINE_GREEN = (52, 199, 89)      # Apple green
LINE_BLUE = (10, 132, 255)      # Apple blue
MONTHS_RU = (
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)


def score_to_100(score: float) -> float:
    return max(0.0, min(100.0, (float(score) - 1.0) / 4.0 * 100.0))


def calendar_level_color(overall: float | None) -> tuple[int, int, int] | None:
    if overall is None:
        return None
    if overall < 2.5:
        return CAL_LOW
    if overall < 3.5:
        return CAL_MID
    return CAL_HIGH


def _calendar_num_fill(col: tuple[int, int, int]) -> tuple[int, int, int]:
    """Тёмный текст на бледных кружках, белый на насыщенных."""
    if col == CAL_EMPTY:
        return SECONDARY
    luminance = 0.299 * col[0] + 0.587 * col[1] + 0.114 * col[2]
    return TITLE if luminance > 160 else (255, 255, 255)


def _load_sf_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = (
        [
            "/System/Library/Fonts/SFNS.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/Library/Fonts/Arial Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
        if bold
        else [
            "/System/Library/Fonts/SFNS.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/Library/Fonts/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
    )
    for path_s in candidates:
        p = Path(path_s)
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size=size)
            except OSError:
                continue
    return _load_font(size, bold=bold)


def _polyline(
    points: list[tuple[float, float]], *, steps_per_seg: int = 8
) -> list[tuple[float, float]]:
    """Прямые отрезки между точками."""
    if len(points) < 2:
        return list(points)
    out: list[tuple[float, float]] = []
    for i in range(len(points) - 1):
        x0, y0 = points[i]
        x1, y1 = points[i + 1]
        for j in range(steps_per_seg):
            t = j / steps_per_seg
            out.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    out.append(points[-1])
    return out


def _smooth_clamped(
    points: list[tuple[float, float]], *, steps_per_seg: int = 48
) -> list[tuple[float, float]]:
    """Плавные скруглённые кубические Безье через точки без перелёта по Y.

    Горизонтальные касательные на концах сегмента → ease-in-out скругление.
    Контрольные точки лежат на той же Y, что и вершины, поэтому по выпуклой
    оболочке кривая остаётся строго между соседними точками (без overshoot).
    """
    if len(points) < 2:
        return list(points)
    if len(points) == 2:
        return _polyline(points, steps_per_seg=steps_per_seg)

    # Доля сегмента до контрольной точки: больше → мягче/круглее переход.
    pull = 0.42

    out: list[tuple[float, float]] = []
    for i in range(len(points) - 1):
        x0, y0 = points[i]
        x1, y1 = points[i + 1]
        dx = x1 - x0
        c1x = x0 + dx * pull
        c2x = x1 - dx * pull
        # горизонтальные касательные: максимальное скругление без выхода за Y
        c1y, c2y = y0, y1

        for j in range(steps_per_seg):
            t = j / steps_per_seg
            u = 1.0 - t
            x = (
                u * u * u * x0
                + 3 * u * u * t * c1x
                + 3 * u * t * t * c2x
                + t * t * t * x1
            )
            y = (
                u * u * u * y0
                + 3 * u * u * t * c1y
                + 3 * u * t * t * c2y
                + t * t * t * y1
            )
            out.append((x, y))
    out.append(points[-1])
    return out


def _fill_series_gaps(
    by_day: dict[int, float], days_in_month: int
) -> list[tuple[int, float]]:
    known = sorted((d, v) for d, v in by_day.items() if 1 <= d <= days_in_month)
    if not known:
        return []
    if len(known) == 1:
        _, v0 = known[0]
        return [(d, v0) for d in range(1, days_in_month + 1)]
    out: list[tuple[int, float]] = []
    for day in range(1, days_in_month + 1):
        if day in by_day:
            out.append((day, by_day[day]))
            continue
        prev = next(((d, v) for d, v in reversed(known) if d < day), None)
        nxt = next(((d, v) for d, v in known if d > day), None)
        if prev and nxt:
            t = (day - prev[0]) / (nxt[0] - prev[0])
            out.append((day, prev[1] + (nxt[1] - prev[1]) * t))
        elif prev:
            out.append((day, prev[1]))
        elif nxt:
            out.append((day, nxt[1]))
    return out


def _draw_elegant_line(
    base: Image.Image,
    coords: list[tuple[float, float]],
    *,
    color: tuple[int, int, int],
    bottom: float,
    stroke: int,
    fill_alpha: int = 38,
    fill_power: float = 2.0,
) -> None:
    """Максимально плавная скруглённая линия без перелёта за точки + заливка."""
    if len(coords) < 2:
        return
    smooth = _smooth_clamped(coords, steps_per_seg=48)
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    bands = 28
    for i in range(bands):
        t0 = i / bands
        t1 = (i + 1) / bands
        a = int(fill_alpha * (1.0 - t0) ** fill_power)
        if a < 1:
            continue
        top_e = [(x, y + (bottom - y) * t0) for x, y in smooth]
        bot_e = [(x, y + (bottom - y) * t1) for x, y in reversed(smooth)]
        od.polygon(top_e + bot_e, fill=(*color, a))
    od.line(smooth, fill=(*color, 90), width=stroke + 2, joint="curve")
    od.line(smooth, fill=(*color, 255), width=stroke, joint="curve")
    base.alpha_composite(overlay)


def _ring(
    base: Image.Image,
    *,
    cx: float,
    cy: float,
    radius: float,
    width: float,
    fraction: float,
    color: tuple[int, int, int],
) -> None:
    """Кольцо прогресса: цветная дуга ровно по серому треку, концы скруглены."""
    import math
    from PIL import ImageChops

    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)

    half = width / 2.0
    ro, ri = radius + half, max(0.5, radius - half)
    track = (229, 229, 234, 255)

    def _full_annulus(draw, fill) -> None:
        n = 180
        pts: list[tuple[float, float]] = []
        for i in range(n + 1):
            a = -math.pi / 2 + 2 * math.pi * i / n
            pts.append((cx + ro * math.cos(a), cy + ro * math.sin(a)))
        for i in range(n + 1):
            a = -math.pi / 2 + 2 * math.pi * (1.0 - i / n)
            pts.append((cx + ri * math.cos(a), cy + ri * math.sin(a)))
        draw.polygon(pts, fill=fill)

    # серый трек
    _full_annulus(od, track)

    frac = max(0.0, min(1.0, fraction))
    if frac <= 0.001:
        base.alpha_composite(overlay)
        return

    if frac >= 0.999:
        _full_annulus(od, (*color, 255))
        base.alpha_composite(overlay)
        return

    # цвет — тот же annulus, обрезанный по сектору (без смещения относительно трека)
    ann = Image.new("L", base.size, 0)
    _full_annulus(ImageDraw.Draw(ann), 255)

    start = -math.pi / 2
    span = 2 * math.pi * frac
    end = start + span
    sector = Image.new("L", base.size, 0)
    sd = ImageDraw.Draw(sector)
    pie = [(cx, cy)]
    n = max(64, int(abs(span) / (2 * math.pi) * 180))
    for i in range(n + 1):
        a = start + span * i / n
        pie.append((cx + (ro + 2) * math.cos(a), cy + (ro + 2) * math.sin(a)))
    sd.polygon(pie, fill=255)
    # скруглённые концы линии (в пределах трека)
    for a in (start, end):
        x = cx + radius * math.cos(a)
        y = cy + radius * math.sin(a)
        sd.ellipse((x - half, y - half, x + half, y + half), fill=255)

    mask = ImageChops.multiply(ann, sector)
    colored = Image.new("RGBA", base.size, (*color, 0))
    colored.putalpha(mask)
    overlay.alpha_composite(colored)
    base.alpha_composite(overlay)


def _card(img: Image.Image, box, *, radius: float) -> None:
    x0, y0, x1, y1 = box
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(sh)
    for i, a in enumerate((10, 6, 3)):
        o = i + 1
        sd.rounded_rectangle(
            (x0, y0 + o * 2, x1, y1 + o * 2),
            radius=radius,
            fill=(0, 0, 0, a),
        )
    img.alpha_composite(sh)
    ImageDraw.Draw(img).rounded_rectangle(box, radius=radius, fill=(*CARD, 255))


def render_state_dashboard_b2(
    *,
    year: int,
    month: int,
    phys_by_day: dict[int, float],
    moral_by_day: dict[int, float],
    phys_delta: float | None = None,
    moral_delta: float | None = None,
    balance_delta: float | None = None,
    header_day: int | None = None,
) -> bytes:
    """
    Макет H2 (горизонталь):
    Самочувствие | Календарь
    Физическое | Моральное | Баланс
    """
    import calendar as cal_mod

    scale = 2
    W, H = 1180, 720
    img = Image.new("RGBA", (W * scale, H * scale), (*BG, 255))
    draw = ImageDraw.Draw(img)
    w, h = img.size
    pad = 24 * scale
    gap = 14 * scale
    rad = 22 * scale

    f_title = _load_sf_font(22 * scale, True)
    f_label = _load_sf_font(14 * scale)
    f_axis = _load_sf_font(11 * scale)
    f_wd = _load_sf_font(11 * scale)
    f_day = _load_sf_font(12 * scale, True)
    f_leg = _load_sf_font(12 * scale)
    f_bal = _load_sf_font(36 * scale, True)
    f_metric_score = _load_sf_font(36 * scale, True)
    f_metric_unit = _load_sf_font(16 * scale)

    days_n = cal_mod.monthrange(year, month)[1]
    p_vals = [phys_by_day[d] for d in range(1, days_n + 1) if d in phys_by_day]
    m_vals = [moral_by_day[d] for d in range(1, days_n + 1) if d in moral_by_day]
    p_avg = sum(p_vals) / len(p_vals) if p_vals else None
    m_avg = sum(m_vals) / len(m_vals) if m_vals else None
    p100 = score_to_100(p_avg) if p_avg is not None else 0.0
    m100 = score_to_100(m_avg) if m_avg is not None else 0.0
    if p_avg is not None and m_avg is not None:
        b100 = (p100 + m100) / 2
    else:
        b100 = p100 or m100

    left, right = pad, w - pad
    top, bottom = pad, h - pad
    content_h = bottom - top
    top_h = content_h * 0.60
    bot_h = content_h - top_h - gap
    sam_w = (right - left - gap) * 0.58
    col_w = (right - left - 2 * gap) / 3

    def xy(day: int, v100: float, box):
        cl, ct, cr, cb = box
        return (
            cl + (day - 1) / max(days_n - 1, 1) * (cr - cl),
            cb - v100 / 100.0 * (cb - ct),
        )

    p_series = _fill_series_gaps(phys_by_day, days_n)
    m_series = _fill_series_gaps(moral_by_day, days_n)

    # ===== TOP-LEFT: Самочувствие =====
    sx0, sy0 = left, top
    sx1, sy1 = left + sam_w, top + top_h
    _card(img, (sx0, sy0, sx1, sy1), radius=rad)
    draw = ImageDraw.Draw(img)
    draw.text((sx0 + 22 * scale, sy0 + 16 * scale), "Самочувствие", font=f_title, fill=TITLE)

    date_label = f"{header_day or days_n} {MONTHS_RU[month]} {year}"
    tw_date = draw.textlength(date_label, font=f_leg)
    icon_s = 18 * scale
    gap_i = 6 * scale
    ix1 = sx1 - 20 * scale
    tx = ix1 - tw_date
    ix0 = tx - gap_i - icon_s
    iy0 = sy0 + 18 * scale
    draw.rounded_rectangle(
        (ix0, iy0, ix0 + icon_s, iy0 + icon_s),
        radius=4 * scale,
        outline=SECONDARY,
        width=max(2, scale),
    )
    draw.rectangle((ix0, iy0, ix0 + icon_s, iy0 + 6 * scale), fill=SECONDARY)
    for col in range(3):
        for row in range(2):
            cx = ix0 + (3 + col * 5) * scale
            cy = iy0 + (8 + row * 5) * scale
            draw.ellipse((cx, cy, cx + 2 * scale, cy + 2 * scale), fill=GRID)
    draw.text((tx, sy0 + 20 * scale), date_label, font=f_leg, fill=SECONDARY)

    lx, ly = sx0 + 22 * scale, sy0 + 46 * scale
    for name, col in (("Физическое", LINE_GREEN), ("Моральное", LINE_BLUE)):
        draw.rounded_rectangle((lx, ly + 6 * scale, lx + 16 * scale, ly + 10 * scale), radius=2, fill=col)
        draw.text((lx + 22 * scale, ly), name, font=f_leg, fill=SECONDARY)
        lx += 140 * scale

    box = (sx0 + 42 * scale, sy0 + 78 * scale, sx1 - 20 * scale, sy1 - 56 * scale)
    cl, ct, cr, cb = box
    day_span = (cr - cl) / max(days_n - 1, 1)

    for day in range(1, days_n + 1):
        if date(year, month, day).weekday() < 5:
            continue
        x = cl + (day - 1) * day_span
        draw.rectangle(
            (x - day_span * 0.45, ct, x + day_span * 0.45, cb),
            fill=(236, 236, 240, 255),
        )

    for i in range(5):
        gy = ct + (cb - ct) * i / 4
        x = cl
        while x < cr:
            draw.line((x, gy, min(x + 4 * scale, cr), gy), fill=GRID, width=max(1, scale // 2))
            x += 8 * scale
        lab = f"{100 - 25 * i}"
        tw = draw.textlength(lab, font=f_axis)
        draw.text((cl - tw - 8 * scale, gy - 7 * scale), lab, font=f_axis, fill=SECONDARY)

    p_bends = _series_bends(p_series)
    m_bends = _series_bends(m_series)
    p_coords = [xy(d, score_to_100(v), box) for d, v in p_bends]
    m_coords = [xy(d, score_to_100(v), box) for d, v in m_bends]
    stroke = max(3, int(2.4 * scale))
    if p_coords:
        _draw_elegant_line(img, p_coords, color=LINE_GREEN, bottom=cb, stroke=stroke, fill_alpha=32)
    if m_coords:
        _draw_elegant_line(img, m_coords, color=LINE_BLUE, bottom=cb, stroke=stroke, fill_alpha=28)

    def _mark_points(coords, color):
        if not coords:
            return
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        r = max(4, int(1.8 * scale))
        ring = max(2, int(0.8 * scale))
        for x, yy in coords:
            od.ellipse(
                (x - r - ring, yy - r - ring, x + r + ring, yy + r + ring),
                fill=(255, 255, 255, 255),
            )
            od.ellipse((x - r, yy - r, x + r, yy + r), fill=(*color, 255))
        img.alpha_composite(overlay)

    _mark_points(p_coords, LINE_GREEN)
    _mark_points(m_coords, LINE_BLUE)

    draw = ImageDraw.Draw(img)
    for day in range(1, days_n + 1):
        x = cl + (day - 1) * day_span
        lab = str(day)
        wd = WD_SHORT[date(year, month, day).weekday()]
        is_weekend = date(year, month, day).weekday() >= 5
        label_fill = CAL_RED if is_weekend else SECONDARY
        wd_fill = CAL_RED if is_weekend else (174, 174, 178)
        tw = draw.textlength(lab, font=f_axis)
        draw.text((x - tw / 2, cb + 8 * scale), lab, font=f_axis, fill=label_fill)
        tw2 = draw.textlength(wd, font=f_wd)
        draw.text((x - tw2 / 2, cb + 22 * scale), wd, font=f_wd, fill=wd_fill)

    # ===== TOP-RIGHT: Календарь =====
    cx0, cy0 = left + sam_w + gap, top
    cx1, cy1 = right, top + top_h
    _card(img, (cx0, cy0, cx1, cy1), radius=rad)
    draw = ImageDraw.Draw(img)
    draw.text((cx0 + 18 * scale, cy0 + 14 * scale), "Календарь", font=f_title, fill=TITLE)

    gl, gr = cx0 + 14 * scale, cx1 - 14 * scale
    head_y = cy0 + 48 * scale
    cell_w = (gr - gl) / 7
    for i, wd in enumerate(WD_SHORT):
        tw = draw.textlength(wd, font=f_wd)
        draw.text((gl + i * cell_w + (cell_w - tw) / 2, head_y), wd, font=f_wd, fill=SECONDARY)

    weeks = cal_mod.Calendar(firstweekday=0).monthdayscalendar(year, month)
    gtop = head_y + 24 * scale
    gbot = cy1 - 44 * scale
    row_h = (gbot - gtop) / max(len(weeks), 1)
    cr_ = min(cell_w, row_h) * 0.34

    for ri, week in enumerate(weeks):
        for ci, day in enumerate(week):
            if day == 0:
                continue
            cx = gl + ci * cell_w + cell_w / 2
            cy = gtop + ri * row_h + row_h / 2
            pv, mv = phys_by_day.get(day), moral_by_day.get(day)
            if pv is not None and mv is not None:
                ov = (pv + mv) / 2
            else:
                ov = pv if pv is not None else mv
            col = calendar_level_color(ov) or CAL_EMPTY
            draw.ellipse((cx - cr_, cy - cr_, cx + cr_, cy + cr_), fill=col)
            num = str(day)
            tw = draw.textlength(num, font=f_day)
            tb = f_day.getbbox(num)
            th = tb[3] - tb[1]
            fill = _calendar_num_fill(col)
            draw.text((cx - tw / 2, cy - th / 2 - tb[1]), num, font=f_day, fill=fill)

    items = ((CAL_LOW, "Низкое"), (CAL_MID, "Среднее"), (CAL_HIGH, "Высокое"))
    widths = [12 * scale + 5 * scale + draw.textlength(lab, font=f_leg) for _, lab in items]
    total = sum(widths) + 14 * scale * 2
    lx = cx0 + (cx1 - cx0 - total) / 2
    leg_y = cy1 - 28 * scale
    for (col, lab), iw in zip(items, widths):
        r = 5 * scale
        draw.ellipse((lx, leg_y, lx + 2 * r, leg_y + 2 * r), fill=col)
        draw.text((lx + 2 * r + 5 * scale, leg_y - 2 * scale), lab, font=f_leg, fill=SECONDARY)
        lx += iw + 14 * scale

    # ===== BOTTOM ROW: Физ | Мор | Баланс =====
    by0 = top + top_h + gap
    by1 = bottom

    def metric(box_, title, score, color, series):
        _card(img, box_, radius=rad)
        d = ImageDraw.Draw(img)
        x0, y0, x1, y1 = box_
        d.text((x0 + 18 * scale, y0 + 14 * scale), title, font=f_label, fill=TITLE)
        if score is None:
            d.text((x0 + 18 * scale, y0 + 40 * scale), "—/100", font=f_metric_score, fill=SECONDARY)
        else:
            main = f"{score:.0f}"
            d.text((x0 + 18 * scale, y0 + 36 * scale), main, font=f_metric_score, fill=color)
            tw = d.textlength(main, font=f_metric_score)
            d.text(
                (x0 + 18 * scale + tw + 5 * scale, y0 + 52 * scale),
                "/100",
                font=f_metric_unit,
                fill=SECONDARY,
            )
        spark = (x0 + 16 * scale, y0 + 92 * scale, x1 - 16 * scale, y1 - 16 * scale)
        if series:
            coords = [
                xy(dd, score_to_100(vv), spark) for dd, vv in _series_bends(series)
            ]
            _draw_elegant_line(
                img,
                coords,
                color=color,
                bottom=spark[3],
                stroke=max(3, int(2.0 * scale)),
                fill_alpha=88,
                fill_power=0.75,
            )

    metric(
        (left, by0, left + col_w, by1),
        "Физическое",
        p100 if p_avg is not None else None,
        LINE_GREEN,
        p_series,
    )
    metric(
        (left + col_w + gap, by0, left + 2 * col_w + gap, by1),
        "Моральное",
        m100 if m_avg is not None else None,
        LINE_BLUE,
        m_series,
    )

    # Баланс
    bx0 = left + 2 * (col_w + gap)
    bx1 = right
    _card(img, (bx0, by0, bx1, by1), radius=rad)
    draw = ImageDraw.Draw(img)
    draw.text((bx0 + 18 * scale, by0 + 14 * scale), "Баланс", font=f_title, fill=TITLE)

    # слева снизу — физ/мораль столбиком; справа — кольцо на весь остаток
    leg_x = bx0 + 16 * scale
    f_bal_lab = _load_sf_font(12 * scale)
    f_bal_val = _load_sf_font(22 * scale, True)
    leg_items = [
        (LINE_GREEN, "Физическое", p100 if p_avg is not None else None),
        (LINE_BLUE, "Моральное", m100 if m_avg is not None else None),
    ]
    leg_col_w = 0.0
    for col, lab, val in leg_items:
        txt = f"{val:.0f}/100" if val is not None else "—/100"
        leg_col_w = max(
            leg_col_w,
            12 * scale + 8 * scale + draw.textlength(lab, font=f_bal_lab),
            18 * scale + draw.textlength(txt, font=f_bal_val),
        )
    leg_col_w = max(leg_col_w, 100 * scale)

    row_h = 48 * scale
    ly = by1 - 14 * scale - row_h * 2
    for col, lab, val in leg_items:
        draw.ellipse((leg_x, ly + 3 * scale, leg_x + 10 * scale, ly + 13 * scale), fill=col)
        draw.text((leg_x + 16 * scale, ly - 1 * scale), lab, font=f_bal_lab, fill=SECONDARY)
        txt = f"{val:.0f}/100" if val is not None else "—/100"
        draw.text((leg_x + 16 * scale, ly + 18 * scale), txt, font=f_bal_val, fill=col)
        ly += row_h

    # кольцо справа максимально: на всю высоту под заголовком
    ring_left = bx0 + leg_col_w + 12 * scale
    ring_right = bx1 - 10 * scale
    ring_top = by0 + 42 * scale
    ring_bot = by1 - 10 * scale
    ring_cx = (ring_left + ring_right) / 2
    ring_cy = (ring_top + ring_bot) / 2
    half = min(ring_right - ring_left, ring_bot - ring_top) / 2
    rw = max(11 * scale, half * 0.20)
    r_out = half - rw / 2 - 1 * scale
    r_in = r_out - rw * 1.2
    if r_in < rw * 1.15:
        r_in = r_out * 0.60

    _ring(
        img,
        cx=ring_cx,
        cy=ring_cy,
        radius=r_out,
        width=rw,
        fraction=p100 / 100.0 if p_avg is not None else 0,
        color=LINE_GREEN,
    )
    _ring(
        img,
        cx=ring_cx,
        cy=ring_cy,
        radius=r_in,
        width=rw,
        fraction=m100 / 100.0 if m_avg is not None else 0,
        color=LINE_BLUE,
    )

    draw = ImageDraw.Draw(img)
    f_bal_center = _load_sf_font(max(30, int(r_in * 0.75)), True)
    bt = f"{b100:.0f}"
    tw = draw.textlength(bt, font=f_bal_center)
    tb = f_bal_center.getbbox(bt)
    draw.text(
        (ring_cx - tw / 2, ring_cy - (tb[3] - tb[1]) / 2 - tb[1]),
        bt,
        font=f_bal_center,
        fill=TITLE,
    )

    rgb = Image.new("RGB", img.size, BG)
    rgb.paste(img, mask=img.split()[3])
    return _to_png(rgb)


LINE_CASH = (52, 199, 89)
LINE_DEBT = (255, 69, 58)
LINE_NET = (10, 132, 255)


def _fmt_axis_money(v: float) -> str:
    if abs(v) < 0.5:
        return "0"
    av = abs(v)
    sign = "−" if v < 0 else ""
    if av >= 1_000_000:
        body = f"{av / 1_000_000:.1f}M".replace(".0M", "M")
        return f"{sign}{body}"
    if av >= 1000:
        return f"{sign}{av / 1000:.0f}k"
    return f"{sign}{av:.0f}"


def _money_axis_ticks(vmin: float, vmax: float, *, max_ticks: int = 6) -> list[float]:
    """Деления оси Y с обязательным нулём, если он в диапазоне."""
    span = vmax - vmin
    if span <= 0:
        return [0.0]
    raw = span / max(max_ticks - 1, 1)
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1.0
    step = mag * 10
    for m in (1, 2, 2.5, 5, 10):
        cand = m * mag
        if span / cand <= max_ticks - 1:
            step = cand
            break
    start = math.floor(vmin / step) * step
    ticks: list[float] = []
    v = start
    while v <= vmax + step * 0.01:
        ticks.append(round(v, 8))
        v += step
    if vmin <= 0 <= vmax and all(abs(t) >= 0.5 for t in ticks):
        ticks.append(0.0)
        ticks = sorted(ticks)
    # убрать почти-дубли
    cleaned: list[float] = []
    for t in ticks:
        if not cleaned or abs(t - cleaned[-1]) > step * 0.15:
            cleaned.append(t)
    if vmin <= 0 <= vmax and all(abs(t) >= 0.5 for t in cleaned):
        cleaned.append(0.0)
        cleaned.sort()
    return cleaned


def _series_bends(series: list[tuple[int, float]]) -> list[tuple[int, float]]:
    """Вершины, где линия меняет наклон (плато, пики, первый и последний)."""
    if len(series) <= 2:
        return list(series)
    out = [series[0]]
    for i in range(1, len(series) - 1):
        y0 = series[i - 1][1]
        y1 = series[i][1]
        y2 = series[i + 1][1]
        if abs((y1 - y0) - (y2 - y1)) > 1e-6:
            out.append(series[i])
    if out[-1] != series[-1]:
        out.append(series[-1])
    return out


def render_finance_dashboard(
    *,
    year: int,
    month: int,
    cash_by_day: dict[int, float],
    debt_by_day: dict[int, float],
    latest_cash: float | None = None,
    latest_debt: float | None = None,
) -> bytes:
    """Карточка финансов в формате самочувствия: выходные, дни недели, точки на изгибах."""
    import calendar as cal

    scale = 2
    width, height = 900, 680
    w, h = width * scale, height * scale
    img = Image.new("RGBA", (w, h), (*BG, 255))
    draw = ImageDraw.Draw(img)
    pad = 28 * scale
    rad = 28 * scale

    draw.rounded_rectangle(
        (pad, pad, w - pad, h - pad),
        radius=rad,
        fill=(*CARD, 255),
    )

    ru_months = (
        "Январь",
        "Февраль",
        "Март",
        "Апрель",
        "Май",
        "Июнь",
        "Июль",
        "Август",
        "Сентябрь",
        "Октябрь",
        "Ноябрь",
        "Декабрь",
    )
    f_title = _load_sf_font(26 * scale, True)
    f_sub = _load_sf_font(14 * scale)
    f_card_t = _load_sf_font(13 * scale)
    f_card_v = _load_sf_font(22 * scale, True)
    f_axis = _load_sf_font(11 * scale)
    f_wd = _load_sf_font(11 * scale)

    x0 = pad + 22 * scale
    y0 = pad + 18 * scale
    draw.text((x0, y0), "Финансы", font=f_title, fill=TITLE)
    draw.text((x0, y0 + 36 * scale), f"{ru_months[month - 1]} {year}", font=f_sub, fill=SECONDARY)

    days = cal.monthrange(year, month)[1]
    cash_now = latest_cash
    debt_now = latest_debt
    net_now = (
        None if cash_now is None or debt_now is None else cash_now - debt_now
    )
    show_net_now = (
        cash_now is not None
        and net_now is not None
        and abs(cash_now - net_now) >= 0.5
    )

    def _money_label(v: float | None) -> str:
        if v is None:
            return "—"
        n = int(round(v))
        sign = "−" if n < 0 else ""
        return f"{sign}{abs(n):,}".replace(",", " ") + " ₽"

    cards = [
        ("Баланс", _money_label(cash_now), LINE_CASH),
        ("Долги", _money_label(debt_now), LINE_DEBT),
    ]
    if show_net_now:
        cards.append(("Баланс с учётом долгов", _money_label(net_now), LINE_NET))
    card_y = y0 + 70 * scale
    card_h = 80 * scale
    gap = 12 * scale
    inner_w = w - 2 * pad - 44 * scale
    card_w = (inner_w - gap * (len(cards) - 1)) / len(cards)
    for i, (lab, val, col) in enumerate(cards):
        cx = x0 + i * (card_w + gap)
        draw.rounded_rectangle(
            (cx, card_y, cx + card_w, card_y + card_h),
            radius=16 * scale,
            fill=(248, 248, 250, 255),
            outline=GRID,
            width=2,
        )
        draw.rounded_rectangle(
            (
                cx + 12 * scale,
                card_y + 14 * scale,
                cx + 12 * scale + 6 * scale,
                card_y + card_h - 14 * scale,
            ),
            radius=4 * scale,
            fill=col,
        )
        tx = cx + 28 * scale
        max_lab_w = card_w - 40 * scale
        words = lab.split()
        wrapped: list[str] = []
        cur = ""
        for word in words:
            trial = f"{cur} {word}".strip()
            if draw.textlength(trial, font=f_card_t) <= max_lab_w or not cur:
                cur = trial
            else:
                wrapped.append(cur)
                cur = word
        if cur:
            wrapped.append(cur)
        ly = card_y + 10 * scale
        for line in wrapped:
            draw.text((tx, ly), line, font=f_card_t, fill=SECONDARY)
            ly += 16 * scale
        draw.text((tx, card_y + 44 * scale), val, font=f_card_v, fill=TITLE)

    chart_top = card_y + card_h + 16 * scale
    chart_bottom = h - pad - 72 * scale
    chart_left = x0 + 40 * scale
    chart_right = w - pad - 22 * scale

    net_by_day: dict[int, float] = {}
    for day in set(cash_by_day) | set(debt_by_day):
        cash_v = cash_by_day.get(day)
        debt_v = debt_by_day.get(day, 0.0 if cash_v is not None else None)
        if cash_v is None:
            continue
        net_v = cash_v - float(debt_v or 0.0)
        if abs(cash_v - net_v) >= 0.5:
            net_by_day[day] = net_v

    values = list(cash_by_day.values()) + list(debt_by_day.values()) + list(net_by_day.values())
    day_span = (chart_right - chart_left) / max(days - 1, 1)

    for day in range(1, days + 1):
        if date(year, month, day).weekday() < 5:
            continue
        x = chart_left + (day - 1) * day_span
        draw.rectangle(
            (x - day_span * 0.45, chart_top, x + day_span * 0.45, chart_bottom),
            fill=(236, 236, 240, 255),
        )

    if not values:
        draw.text(
            ((chart_left + chart_right) / 2 - 80 * scale, (chart_top + chart_bottom) / 2),
            "Пока нет данных",
            font=_load_sf_font(18 * scale),
            fill=SECONDARY,
        )
    else:
        data_min = min(values)
        data_max = max(values)
        vmin = min(0.0, data_min)
        vmax = max(0.0, data_max)
        if abs(vmax - vmin) < 1:
            vmax = vmin + 1
        pad_v = (vmax - vmin) * 0.08
        vmax += pad_v
        if vmin < 0:
            vmin -= pad_v
        span = vmax - vmin

        ticks = _money_axis_ticks(vmin, vmax)
        for val in ticks:
            gy = chart_bottom - (val - vmin) / span * (chart_bottom - chart_top)
            x = chart_left
            is_zero = abs(val) < 0.5
            line_fill = (174, 174, 178) if is_zero else GRID
            line_w = max(2, scale) if is_zero else max(1, scale // 2)
            while x < chart_right:
                draw.line(
                    (x, gy, min(x + (6 * scale if is_zero else 4 * scale), chart_right), gy),
                    fill=line_fill,
                    width=line_w,
                )
                x += 8 * scale
            lab = _fmt_axis_money(val)
            tw = draw.textlength(lab, font=f_axis)
            draw.text((chart_left - tw - 8 * scale, gy - 7 * scale), lab, font=f_axis, fill=TITLE if is_zero else SECONDARY)

        def _to_xy(series: list[tuple[int, float]]) -> list[tuple[float, float]]:
            pts: list[tuple[float, float]] = []
            for day, val in series:
                x = chart_left + (day - 1) * day_span
                y = chart_bottom - (val - vmin) / span * (chart_bottom - chart_top)
                pts.append((x, y))
            return pts

        def _daily(by_day: dict[int, float]) -> list[tuple[int, float]]:
            return [(d, by_day[d]) for d in sorted(by_day)]

        def _draw_series(by_day: dict[int, float], color: tuple[int, int, int], fill_alpha: int) -> None:
            daily = _daily(by_day)
            if not daily:
                return
            bends = _series_bends(daily)
            coords = _to_xy(bends)
            if len(coords) >= 2:
                _draw_elegant_line(
                    img,
                    coords,
                    color=color,
                    bottom=chart_bottom,
                    stroke=max(3, int(2.4 * scale)),
                    fill_alpha=fill_alpha,
                )
            overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
            od = ImageDraw.Draw(overlay)
            r = max(4, int(1.8 * scale))
            ring = max(2, int(0.8 * scale))
            for x, y in coords:
                od.ellipse(
                    (x - r - ring, y - r - ring, x + r + ring, y + r + ring),
                    fill=(255, 255, 255, 255),
                )
                od.ellipse((x - r, y - r, x + r, y + r), fill=(*color, 255))
            img.alpha_composite(overlay)

        _draw_series(cash_by_day, LINE_CASH, 28)
        _draw_series(debt_by_day, LINE_DEBT, 20)
        _draw_series(net_by_day, LINE_NET, 22)

    draw = ImageDraw.Draw(img)
    for day in range(1, days + 1):
        x = chart_left + (day - 1) * day_span
        lab = str(day)
        wd = WD_SHORT[date(year, month, day).weekday()]
        is_weekend = date(year, month, day).weekday() >= 5
        label_fill = CAL_RED if is_weekend else SECONDARY
        wd_fill = CAL_RED if is_weekend else (174, 174, 178)
        tw = draw.textlength(lab, font=f_axis)
        draw.text((x - tw / 2, chart_bottom + 8 * scale), lab, font=f_axis, fill=label_fill)
        tw2 = draw.textlength(wd, font=f_wd)
        draw.text((x - tw2 / 2, chart_bottom + 22 * scale), wd, font=f_wd, fill=wd_fill)

    rgb = Image.new("RGB", img.size, BG)
    rgb.paste(img, mask=img.split()[3] if img.mode == "RGBA" else None)
    return _to_png(rgb)
