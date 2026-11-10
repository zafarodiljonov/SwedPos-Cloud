"""Charts drawn as SVG on the server, in the desktop app's style: brass line/area and bars, dashed previous period, values on hover."""
import math
from decimal import Decimal

from django.utils.html import escape
from django.utils.safestring import mark_safe

from .builder import short

W, H, LEFT, RIGHT, TOP, BOTTOM = 1000, 300, 70, 14, 12, 270


def nice_scale(top, lines=4):
    top = float(top)
    if top <= 0:
        return lines, 1
    raw = top / lines
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw)
    return step * lines, step


def _f(v):
    return f"{v:.1f}".rstrip("0").rstrip(".")


def _grid(top, step, y_of):
    out, v = [], 0.0
    while v <= top + 1e-9:
        y = y_of(v)
        out.append(f'<line class="grid" x1="{LEFT}" x2="{W - RIGHT}" y1="{_f(y)}" y2="{_f(y)}"/>'
                   f'<text class="axis" x="{LEFT - 8}" y="{_f(y + 4)}" text-anchor="end">{escape(short(Decimal(str(v))))}</text>')
        v += step
    return "".join(out)


def line_chart(points):
    if not points:
        return ""
    top, step = nice_scale(max(max(float(p["value"]), float(p.get("previous") or 0)) for p in points))
    n = len(points)

    def x(i):
        return (LEFT + W - RIGHT) / 2 if n <= 1 else LEFT + i * (W - LEFT - RIGHT) / (n - 1)

    def y(v):
        return BOTTOM - float(v) / top * (BOTTOM - TOP)
    slot = (W - LEFT - RIGHT) if n <= 1 else (W - LEFT - RIGHT) / (n - 1)
    path = " ".join(f"{_f(x(i))},{_f(y(p['value']))}" for i, p in enumerate(points))
    parts = [f'<svg class="chart" viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid meet" role="img">', _grid(top, step, y)]
    if any(p.get("previous") is not None for p in points):
        prev = " ".join(f"{_f(x(i))},{_f(y(p.get('previous') or 0))}" for i, p in enumerate(points))
        parts.append(f'<polyline class="prev" points="{prev}"/>')
    parts.append(f'<polygon class="area" points="{_f(x(0))},{BOTTOM} {path} {_f(x(n - 1))},{BOTTOM}"/>')
    parts.append(f'<polyline class="line" points="{path}"/>')
    for i, p in enumerate(points):
        parts.append(f'<g class="pt"><rect class="hit" x="{_f(x(i) - slot / 2)}" y="{TOP}" width="{_f(slot)}" height="{BOTTOM - TOP}"/>'
                     f'<line class="guide" x1="{_f(x(i))}" x2="{_f(x(i))}" y1="{TOP}" y2="{BOTTOM}"/>'
                     f'<rect class="dot" x="{_f(x(i) - 4)}" y="{_f(y(p["value"]) - 4)}" width="8" height="8"/>'
                     f'<title>{escape(p.get("tip") or p["label"])}</title></g>')
    every = max(1, math.ceil(n / 10))
    for i in range(0, n, every):
        parts.append(f'<text class="axis" x="{_f(x(i))}" y="{H - 6}" text-anchor="middle">{escape(points[i]["label"])}</text>')
    parts.append("</svg>")
    return mark_safe("".join(parts))


def bar_chart(points):
    if not points:
        return ""
    top_value = max(float(p["value"]) for p in points)
    top, step = nice_scale(top_value)
    n = len(points)
    slot = (W - LEFT - 8) / n
    bar = max(3, min(56, slot * 0.62))

    def y(v):
        return BOTTOM - float(v) / top * (BOTTOM - TOP)
    parts = [f'<svg class="chart" viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid meet" role="img">', _grid(top, step, y)]
    every = max(1, math.ceil(n / 16))
    for i, p in enumerate(points):
        h = float(p["value"]) / top * (BOTTOM - TOP)
        cls = "bar max" if top_value > 0 and float(p["value"]) == top_value else "bar"
        parts.append(f'<g class="{cls}"><rect class="hit" x="{_f(LEFT + i * slot)}" y="{TOP}" width="{_f(slot)}" height="{BOTTOM - TOP}"/>'
                     f'<rect class="fill" x="{_f(LEFT + i * slot + (slot - bar) / 2)}" y="{_f(BOTTOM - h)}" width="{_f(bar)}" height="{_f(max(h, 0))}"/>'
                     f'<title>{escape(p.get("tip") or p["label"])}</title></g>')
        if i % every == 0:
            parts.append(f'<text class="axis" x="{_f(LEFT + i * slot + slot / 2)}" y="{H - 6}" text-anchor="middle">{escape(p["label"])}</text>')
    parts.append("</svg>")
    return mark_safe("".join(parts))
