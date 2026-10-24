"""The Charts tab (SC8.1), as chosen:

    Charts                                       ⋮
    Lat pulldown ▾                   3M · 1Y · All
    kg/side
     30  ┤                 ●───●
    27.5 ┤         ●───●───●
     25  ┤ ●───●───●
    reps
     12  ┤             ┃       ┃
     10  ┤     ┃   ┃   ┃   ┃   ┃
      8  ┤ ┃   ┃   ┃       ┃
          26 Oct    9 Nov    23 Nov
    12 Nov · 10 · 10 · 9 @ 27.5 kg/side

One exercise at a time: its kg as logged as a line, and under it each session's reps as a bar from the
lowest to the highest set, on the same dates. Deload sessions are drawn hollow. Tapping a chart writes
the nearest session out underneath. Drawn with Flet's canvas: no chart package, black and white (LK1.1).
"""

import flet as ft
import flet.canvas as cv

from gym.rules.stats import chartRanges, kgText
from gym.screens.common import Banners, Menu, Notice
from gym.screens.look import gap, quiet, title

chartHeight = 120  # each chart's height, in logical pixels
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


def lineShapes(values: list[float], deloads: list[bool], width: float, picked: int | None) -> list[cv.Shape]:
    """The kg (or minutes) line: a segment between sessions, a dot on each, hollow for a deload, bigger when
    picked."""
    xs, low, high = xPositions(len(values), width), min(values), max(values)
    points = [(x, yPosition(value, low, high)) for x, value in zip(xs, values)]
    line = ft.Paint(color=ft.Colors.ON_SURFACE, stroke_width=2)
    shapes: list[cv.Shape] = [cv.Line(x1, y1, x2, y2, paint=line) for (x1, y1), (x2, y2) in zip(points, points[1:])]
    for index, ((x, y), deload) in enumerate(zip(points, deloads)):
        style = ft.PaintingStyle.STROKE if deload else ft.PaintingStyle.FILL
        shapes.append(cv.Circle(x, y, 6 if index == picked else 4,
                                paint=ft.Paint(color=ft.Colors.ON_SURFACE, style=style, stroke_width=2)))
    return shapes


def barShapes(lows: list[int], highs: list[int], deloads: list[bool], width: float,
              picked: int | None) -> list[cv.Shape]:
    """Each session's reps: a bar from the lowest to the highest set, hollow for a deload, wider when picked."""
    xs, low, high = xPositions(len(lows), width), min(lows), max(highs)
    shapes: list[cv.Shape] = []
    for index, (x, lowest, highest, deload) in enumerate(zip(xs, lows, highs, deloads)):
        top, bottom = yPosition(highest, low, high), yPosition(lowest, low, high)
        half = 5 if index == picked else 3
        style = ft.PaintingStyle.STROKE if deload else ft.PaintingStyle.FILL
        shapes.append(cv.Rect(x - half, top - 1, 2 * half, max(bottom - top, 0) + 2,
                              paint=ft.Paint(color=ft.Colors.ON_SURFACE, style=style, stroke_width=1.5)))
    return shapes


def nearest(x: float, count: int, width: float) -> int:
    """The session whose x is nearest to a tap."""
    xs = xPositions(count, width)
    return min(range(count), key=lambda index: abs(xs[index] - x))


def numberText(value: float) -> str:
    return kgText(value)


@ft.component
def ChartsTab(app, model):
    choices = [line.exercise for line in (*model.progress, *model.pastProgress)]
    header = ft.Row([ft.Container(title("Charts"), expand=True), Menu(app, app.menuItems)])
    if not choices or model.chart is None:
        return ft.Column([header, Banners(app, model), Notice(app, model), ft.Divider(),
                          quiet("Nothing here yet: import your plan, and its exercises show up.")], spacing=gap)
    view = model.chart
    picker = ft.Dropdown(value=view.exercise.exerciseId, expand=True, label="Exercise",
                         options=[ft.DropdownOption(key=exercise.exerciseId, text=exercise.name) for exercise in choices],
                         on_select=lambda e: app.showChart(e.control.value))
    ranges = ft.Row([ft.TextButton(name, on_click=lambda e, name=name: app.showChartRange(name),
                                   style=ft.ButtonStyle(text_style=ft.TextStyle(
                                       weight=ft.FontWeight.BOLD if name == view.chartRange else None)))
                     for name in chartRanges], spacing=0)
    body = (ExerciseChart(view, key=f"{view.exercise.exerciseId}{view.chartRange}") if view.sessions
            else quiet("Nothing logged in this span yet."))
    return ft.Column([header, Banners(app, model), Notice(app, model), ft.Divider(),
                      ft.Row([picker, ranges], wrap=True), body],
                     spacing=gap, scroll=ft.ScrollMode.AUTO, expand=True)


@ft.component
def ExerciseChart(view):
    """The kg line and the reps bars of one exercise, sharing the dates; a tap picks the nearest session."""
    width, setWidth = ft.use_state(300.0)  # the canvas's real width arrives with its first resize
    picked, setPicked = ft.use_state(None)
    sessions = view.sessions
    deloads = [session.deload for session in sessions]

    def pick(e):
        setPicked(nearest(e.local_position.x, len(sessions), width))

    def resize(e):
        if abs(e.width - width) > 0.5:
            setWidth(e.width)

    def panel(label: str, shapes: list[cv.Shape], low: float, high: float) -> list[ft.Control]:
        axis = ft.Column([quiet(numberText(high)), quiet(numberText(low))], width=labelWidth, height=chartHeight,
                         alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        canvas = cv.Canvas(shapes=shapes, height=chartHeight, expand=True, on_resize=resize)
        return [quiet(label), ft.Row([axis, ft.GestureDetector(content=canvas, on_tap_down=pick, expand=True)],
                                     spacing=0)]

    parts: list[ft.Control] = []
    if view.exercise.isCardio:
        minutes = [session.minutes or 0 for session in sessions]
        parts += panel("min", lineShapes(minutes, deloads, width, picked), min(minutes), max(minutes))
    else:
        weights = [session.weightKg for session in sessions]
        if all(weight is not None for weight in weights):
            parts += panel(view.unit, lineShapes(weights, deloads, width, picked), min(weights), max(weights))
        lows = [session.lowReps or 0 for session in sessions]
        highs = [session.highReps or 0 for session in sessions]
        parts += panel("reps", barShapes(lows, highs, deloads, width, picked), min(lows), max(highs))
    first, last = sessions[0].date, sessions[-1].date
    parts.append(ft.Row([ft.Container(width=labelWidth),
                         ft.Row([quiet(f"{first.day} {first:%b}"), quiet(f"{last.day} {last:%b}")],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN, expand=True)], spacing=0))
    parts.append(ft.Text(sessions[picked].text) if picked is not None and picked < len(sessions)
                 else quiet("Tap a chart to see that session."))
    return ft.Column(parts, spacing=4)
