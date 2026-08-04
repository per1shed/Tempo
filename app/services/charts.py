from __future__ import annotations

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
    Только текущий выделен синей рамкой и меткой «СЕЙЧАС» — без галочек.
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
