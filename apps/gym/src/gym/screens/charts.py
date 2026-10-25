"""The Charts tab (SC8.1), as chosen, restyled (LK1.2):

    Charts                                       ⋮
    [ Lat pulldown                           v ]
    [3M] [1Y] [All]
    ┌ KG/SIDE                                     ┐
    │  30 ┤ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ●───●             │
    │  25 ┤ ●───●───●───●───●                     │
    │ REPS                                        │
    │  12 ┤             ▌       ▌                 │
    │   8 ┤ ▌   ▌   ▌   ▌   ▌   ▌                 │
    │       26 Oct                    23 Nov      │
    └ LATEST  12 Nov · 10 · 10 · 9 @ 27.5 kg/side ┘

One exercise at a time: its kg as logged as a line, and under it each session's reps as a bar from the
lowest to the highest set, on the same dates. Deload sessions are drawn hollow. The latest session is written
out underneath; tapping the chart picks another. Drawn with Flet's canvas: no chart package, in the theme's
black and greys (LK1.1, LK1.2). LineChart draws any dated line the same way (the weigh-ins, the diary's
months).
"""

import datetime as dt

import flet as ft
import flet.canvas as cv

from gym.rules.stats import chartRanges, evenlyPicked, kgText
from gym.screens.common import Banners, Menu, Notice
from gym.screens.look import card, chartFade, faint, header, label, quiet, screen, segments

chartHeight = 130  # each chart's height, in logical pixels
labelWidth = 44  # the column of axis numbers on the left
inset = 8  # keeps the marks off the canvas's edges


def xPositions(count: int, width: float) -> list[float]:
    """Each session's x, spread evenly across the width; a single one in the middle."""
    if count == 1:
        return [width / 2]
    return [inset + index * (width - 2 * inset) / (count - 1) for index in range(count)]


def yPosition(value: float, low: float, high: float) -> float:
    """A value's y: the highest at the top; all equal in the middle."""
    if high == low:
        return chartHeight / 2
    return inset + (high - value) / (high - low) * (chartHeight - 2 * inset)


def gridShapes(width: float, low: float, high: float) -> list[cv.Shape]:
    """Faint lines at the top, middle and bottom values (one in the middle when all are equal)."""
    paint = ft.Paint(color=ft.Colors.OUTLINE_VARIANT, stroke_width=1)
    values = [low] if high == low else [high, (high + low) / 2, low]
    return [cv.Line(0, y, width, y, paint=paint) for y in (yPosition(value, low, high) for value in values)]


def lineShapes(values: list[float], deloads: list[bool], width: float, picked: int | None) -> list[cv.Shape]:
    """The kg (or minutes) line over a soft fill: a dot on each session, hollow for a deload, the picked one
    bigger."""
    xs, low, high = xPositions(len(values), width), min(values), max(values)
    points = [(x, yPosition(value, low, high)) for x, value in zip(xs, values)]
    shapes: list[cv.Shape] = gridShapes(width, low, high)
    if len(points) > 1 and high > low:  # a soft fill under the line, fading downwards
        bottom = chartHeight - inset / 2
        area = [cv.Path.MoveTo(points[0][0], bottom), *[cv.Path.LineTo(x, y) for x, y in points],
                cv.Path.LineTo(points[-1][0], bottom), cv.Path.Close()]
        fade = ft.PaintLinearGradient((0, inset), (0, bottom), chartFade)
        shapes.append(cv.Path(area, paint=ft.Paint(gradient=fade, style=ft.PaintingStyle.FILL)))
    line = ft.Paint(color=ft.Colors.PRIMARY, stroke_width=2.5, stroke_cap=ft.StrokeCap.ROUND)
    shapes += [cv.Line(x1, y1, x2, y2, paint=line) for (x1, y1), (x2, y2) in zip(points, points[1:])]
    for index, ((x, y), deload) in enumerate(zip(points, deloads)):
        size = 6 if index == picked else 4
        if deload:
            shapes.append(cv.Circle(x, y, size, paint=ft.Paint(color=ft.Colors.SURFACE_CONTAINER_LOW,
                                                               style=ft.PaintingStyle.FILL)))
        shapes.append(cv.Circle(x, y, size, paint=ft.Paint(color=ft.Colors.PRIMARY, stroke_width=2,
                                                           style=ft.PaintingStyle.STROKE if deload
                                                           else ft.PaintingStyle.FILL)))
    return shapes


def barShapes(lows: list[int], highs: list[int], deloads: list[bool], width: float,
              picked: int | None) -> list[cv.Shape]:
    """Each session's reps: a rounded bar from the lowest to the highest set, hollow for a deload; grey, and
    white (black in light mode) when picked."""
    xs, low, high = xPositions(len(lows), width), min(lows), max(highs)
    shapes: list[cv.Shape] = gridShapes(width, low, high)
    for index, (x, lowest, highest, deload) in enumerate(zip(xs, lows, highs, deloads)):
        top, bottom = yPosition(highest, low, high), yPosition(lowest, low, high)
        half = 5 if index == picked else 3.5
        color = ft.Colors.PRIMARY if index == picked else ft.Colors.ON_SURFACE_VARIANT
        style = ft.PaintingStyle.STROKE if deload else ft.PaintingStyle.FILL
        shapes.append(cv.Rect(x - half, top - 3, 2 * half, max(bottom - top, 0) + 6, border_radius=half,
                              paint=ft.Paint(color=color, style=style, stroke_width=1.5)))
    return shapes


def nearest(x: float, count: int, width: float) -> int:
    """The session whose x is nearest to a tap."""
    xs = xPositions(count, width)
    return min(range(count), key=lambda index: abs(xs[index] - x))


def numberText(value: float) -> str:
    return kgText(value)


def axis(low: float, high: float) -> ft.Column:
    """The axis numbers left of a chart: the highest at the top, the lowest at the bottom."""
    if high == low:
        return ft.Column([faint(numberText(high))], width=labelWidth, height=chartHeight,
                         alignment=ft.MainAxisAlignment.CENTER)
    return ft.Column([faint(numberText(high)), faint(numberText(low))], width=labelWidth, height=chartHeight,
                     alignment=ft.MainAxisAlignment.SPACE_BETWEEN)


def datesRow(first: str, last: str) -> ft.Row:
    return ft.Row([ft.Container(width=labelWidth),
                   ft.Row([faint(first), faint(last)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, expand=True)],
                  spacing=0)


@ft.component
def ChartsTab(app, model):
    choices = [line.exercise for line in (*model.progress, *model.pastProgress)]
    top = [header("Charts", trailing=[Menu(app, app.menuItems)]), Banners(app, model), Notice(app, model)]
    if not choices or model.chart is None:
        return screen([*top, card(quiet("Nothing here yet: import your plan, and its exercises show up."))])
    view = model.chart
    picker = ft.Dropdown(value=view.exercise.exerciseId, expand=True, label="Exercise", filled=True,
                         fill_color=ft.Colors.SURFACE_CONTAINER_HIGH, border_radius=12,
                         border_color=ft.Colors.TRANSPARENT, focused_border_color=ft.Colors.OUTLINE,
                         menu_height=420,
                         options=[ft.DropdownOption(key=exercise.exerciseId, text=exercise.name) for exercise in choices],
                         on_select=lambda e: app.showChart(e.control.value))
    body = (card(ExerciseChart(view, key=f"{view.exercise.exerciseId}{view.chartRange}")) if view.sessions
            else card(quiet("Nothing logged in this span yet.")))
    return screen([*top, ft.Row([picker]),
                   segments([(name, name) for name in chartRanges], view.chartRange, app.showChartRange), body])


@ft.component
def ExerciseChart(view):
    """The kg line and the reps bars of one exercise, sharing the dates; a tap picks the nearest session."""
    width, setWidth = ft.use_state(300.0)  # the canvas's real width arrives with its first resize
    picked, setPicked = ft.use_state(None)
    sessions = view.sessions
    deloads = [session.deload for session in sessions]
    shown = picked if picked is not None and picked < len(sessions) else len(sessions) - 1

    def pick(e):
        setPicked(nearest(e.local_position.x, len(sessions), width))

    def resize(e):
        if abs(e.width - width) > 0.5:
            setWidth(e.width)

    def panel(name: str, shapes: list[cv.Shape], low: float, high: float) -> list[ft.Control]:
        canvas = cv.Canvas(shapes=shapes, height=chartHeight, expand=True, on_resize=resize)
        return [label(name), ft.Row([axis(low, high), ft.GestureDetector(content=canvas, on_tap_down=pick,
                                                                          expand=True)], spacing=0)]

    parts: list[ft.Control] = []
    if view.exercise.isCardio:
        minutes = [session.minutes or 0 for session in sessions]
        parts += panel("min", lineShapes(minutes, deloads, width, shown), min(minutes), max(minutes))
    else:
        weights = [session.weightKg for session in sessions]
        if all(weight is not None for weight in weights):
            parts += panel(view.unit, lineShapes(weights, deloads, width, shown), min(weights), max(weights))
        lows = [session.lowReps or 0 for session in sessions]
        highs = [session.highReps or 0 for session in sessions]
        parts += panel("reps", barShapes(lows, highs, deloads, width, shown), min(lows), max(highs))
    first, last = sessions[0].date, sessions[-1].date
    parts.append(datesRow(f"{first.day} {first:%b}", f"{last.day} {last:%b}"))
    parts.append(ft.Row([faint("PICKED" if picked is not None else "LATEST", size=11),
                         ft.Text(sessions[shown].text, expand=True, weight=ft.FontWeight.W_500)], spacing=10))
    if picked is None and len(sessions) > 1:
        parts.append(faint("Tap the chart to see another session."))
    return ft.Column(parts, spacing=6)


def dateLabel(date: dt.date, byDay: bool) -> str:
    """4 Oct 2026, or Oct 2026 for a month."""
    return f"{date.day} {date:%b %Y}" if byDay else f"{date:%b %Y}"


@ft.component
def LineChart(points, byDay: bool, unit: str = "kg"):
    """A line through dated values (the weigh-ins, SC5.1, DI1.2; the diary's months, DI1.1), at most 30 points,
    evenly picked and ending with the latest."""
    width, setWidth = ft.use_state(300.0)
    if not points:
        return quiet("Nothing to draw yet.")
    points = evenlyPicked(list(points))
    values = [value for _, value in points]

    def resize(e):
        if abs(e.width - width) > 0.5:
            setWidth(e.width)

    canvas = cv.Canvas(shapes=lineShapes(values, [False] * len(values), width, len(values) - 1), height=chartHeight,
                       expand=True, on_resize=resize)
    return ft.Column([
        label(unit),
        ft.Row([axis(min(values), max(values)), canvas], spacing=0),
        datesRow(dateLabel(points[0][0], byDay), dateLabel(points[-1][0], byDay)),
    ], spacing=6)
