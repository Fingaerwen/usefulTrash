"""Draws the app's screens in tests, without a phone or a display.

Each component's body is rendered the way Flet itself does it (Component.before_update), with a
stand-in page session, so tests can read the texts and press the buttons of the real screens. This
leans on Flet 1.0.3's internals (the version is pinned); a Flet upgrade re-checks this kit first.
Not a test file itself: pytest only collects test*.py.
"""

import asyncio
import dataclasses
import inspect
from typing import Any

from flet.components.component import Component, Renderer
from flet.controls.base_control import BaseControl
from flet.controls.context import _context_page


class _Session:
    """What components ask of a page session; redraws and effects are left to the test."""

    def schedule_update(self, component) -> None:
        pass

    def schedule_effect(self, hook, is_cleanup) -> None:
        pass

    def patch_control(self, **kwargs) -> None:
        pass


class _Page:
    session = _Session()


class Event:
    """What a handler gets: the control it came from (handlers read e.control.value and the like)."""

    def __init__(self, control: BaseControl):
        self.control = control
        self.data = None


def draw(componentFn, *args) -> BaseControl:
    """Renders a component and everything under it; returns the root."""
    token = _context_page.set(_Page())
    try:
        root = Renderer().render(componentFn, *args)
        redraw(root)
        return root
    finally:
        _context_page.reset(token)


def redraw(control: BaseControl) -> None:
    """Renders a component again with its own state kept (children start fresh)."""
    token = _context_page.set(_Page())
    try:
        _expand(control)
    finally:
        _context_page.reset(token)


def _expand(control: BaseControl) -> None:
    if isinstance(control, Component):
        control.before_update()
        for child in _asList(control._b):
            _expand(child)
        return
    for child in _children(control):
        _expand(child)


def _asList(value: Any) -> list:
    return value if isinstance(value, list) else [] if value is None else [value]


def _children(control: BaseControl) -> list[BaseControl]:
    found = []
    for field in dataclasses.fields(control):
        if field.name.startswith("_"):
            continue
        value = getattr(control, field.name, None)
        if isinstance(value, BaseControl):
            found.append(value)
        elif isinstance(value, list):
            found += [item for item in value if isinstance(item, BaseControl)]
    return found


def walk(control: BaseControl) -> list[BaseControl]:
    """Every control drawn, in order, component bodies included."""
    found = [control]
    children = _asList(control._b) if isinstance(control, Component) else _children(control)
    for child in children:
        found += walk(child)
    return found


def label(control: BaseControl) -> str:
    """The text a control shows: a Text's value, a button's words, a field's label, a tooltip."""
    for name in ("value", "content", "label", "text", "tooltip"):
        value = getattr(control, name, None)
        if isinstance(value, str) and value:
            return value
    return ""


def visibleTexts(root: BaseControl) -> list[str]:
    """Every text shown, skipping hidden parts."""
    texts = []

    def collect(control: BaseControl, hidden: bool) -> None:
        hidden = hidden or getattr(control, "visible", True) is False
        if not hidden and type(control).__name__ == "Text" and control.value:
            texts.append(control.value)
        children = _asList(control._b) if isinstance(control, Component) else _children(control)
        for child in children:
            collect(child, hidden)

    collect(root, False)
    return texts


def find(root: BaseControl, text: str, kind: str | None = None) -> BaseControl:
    """The one control showing `text` (optionally of a kind, like "Button"); fails if not exactly one."""
    matches = [control for control in walk(root) if label(control) == text and
               (kind is None or type(control).__name__ == kind)]
    assert len(matches) == 1, f"{len(matches)} controls show {text!r}"
    return matches[0]


def press(control: BaseControl, handler: str = "on_click") -> None:
    """Calls a control's handler as Flet would, waiting for it if it's async."""
    callback = getattr(control, handler)
    assert callback is not None, f"{label(control)!r} has no {handler}"
    result = callback(Event(control))
    if inspect.isawaitable(result):
        _run(result)


def type_(control: BaseControl, value: str) -> None:
    """Types into a field: sets its value and calls on_change."""
    control.value = value
    press(control, "on_change")


_loop: asyncio.AbstractEventLoop | None = None


def useLoop(loop: asyncio.AbstractEventLoop) -> None:
    """Async handlers run on this loop (the test's app loop), so the app's tasks keep working."""
    global _loop
    _loop = loop


def _run(awaitable) -> None:
    if _loop is None:
        asyncio.run(awaitable)
    else:
        _loop.run_until_complete(awaitable)
