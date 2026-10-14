"""What the phone app and the PC view share (plan 3b): the model, Today's actions, the Problems page and
plan import. Each mode adds where rows come from and go to (phoneApp.py, pcApp.py)."""

import datetime as dt
from collections.abc import Callable, Sequence
from typing import Any

import flet as ft

from gym.actions import ActionRefused, GymActions
from gym.model import AppModel, LogFacts, SyncFacts, problemsReport
from gym.planImporter import answerQuestions, finishImport, startImport
from gym.rules.today import ExerciseLine, SetDone
from gym.state import GymState
from gym.tables import appSchema
from usefulShared.platform.appLog import AppLog


class AppBase:
    """The shared part of both controllers."""

    mode = "phone"  # or "pc": which main screen and ⋮ menu the screens show
    menuItems: tuple[str, ...] = ("problems", "importPlan", "signOut")

    def __init__(self, config: dict[str, str], services: Any, log: AppLog, clock: Callable[[], dt.datetime],
                 localToday: Callable[[], dt.date]):
        self.config = config  # the public identifiers only (K2a)
        self.services = services
        self.log = log
        self.clock = clock
        self.localToday = localToday  # this device's calendar date (16.4c)
        self.model = AppModel()
        self.state = GymState()
        self.session = None  # usefulShared.signIn.sessionKeeper.SessionKeeper once started
        self.actions: GymActions | None = None
        self._trainAnywayOn: dt.date | None = None  # Train anyway applies to the day it was pressed

    def hasCloudSettings(self) -> bool:
        return all(self.config.get(name) for name in ("supabaseUrl", "supabasePublishableKey", "googleWebClientId"))

    def _fail(self, why: str) -> None:
        self.model.failure = why
        self.model.screen = "failed"

    # --- What each mode provides -------------------------------------------------------------

    def rowsByTable(self) -> dict[str, list[dict[str, Any]]] | None:
        raise NotImplementedError

    async def saveRows(self, edits: Sequence[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
        """The RowStore actions save through: save, then redraw."""
        raise NotImplementedError

    def syncFacts(self) -> SyncFacts:
        raise NotImplementedError

    def extraLogFiles(self) -> list[str]:
        return []

    def afterRefresh(self) -> None:
        """Anything a mode adds to the model after the facts are worked out again."""

    def onResume(self) -> None:
        """Back on screen."""

    # --- The facts and Today -----------------------------------------------------------------

    def refresh(self) -> None:
        """Works out the facts again and redraws what changed."""
        rows = self.rowsByTable()
        if rows is None:
            return
        self.state.load(rows)
        today = self.localToday()
        if self._trainAnywayOn != today:
            self._trainAnywayOn, self.model.trainAnyway = None, False
        self.model.today = self.state.today(today, self.model.trainAnyway)
        self.afterRefresh()

    def startActions(self) -> None:
        self.actions = GymActions(self, self.state, self.session.userId(), self.clock)

    def trainAnyway(self) -> None:
        """Rest day: show the next workout instead (19.1c-2). Nothing is saved until something is logged."""
        self._trainAnywayOn, self.model.trainAnyway = self.localToday(), True
        self.refresh()

    async def check(self, line: ExerciseLine) -> None:
        await self._act(self.actions.checkExercise(self.model.today, line))

    async def saveSets(self, line: ExerciseLine, sets: list[SetDone], minutes: int | None = None) -> None:
        await self._act(self.actions.saveSets(self.model.today, line, sets, minutes))

    async def skip(self, line: ExerciseLine) -> None:
        await self._act(self.actions.skipExercise(self.model.today, line))

    async def finish(self) -> None:
        await self._act(self.actions.finishWorkout(self.model.today))

    async def setSteps(self, steps: int | None) -> None:
        await self._act(self.actions.setSteps(self.localToday(), steps))

    async def _act(self, action) -> None:
        """Runs an action; a refused entry shows why, anything unexpected goes to the log."""
        try:
            await action
        except ActionRefused as refused:
            self.model.notice = str(refused)
        except Exception as problem:
            notice = self.describeFailure(problem)
            if notice is None:
                self.log.crash(problem, "today")
                notice = "That didn't work. Details are on the Problems page."
            self.model.notice = notice

    def describeFailure(self, problem: Exception) -> str | None:
        """Plain words for an expected failure (the PC view's refused writes); None = unexpected."""
        return None

    # --- Problems page (12d) -----------------------------------------------------------------

    def openProblems(self) -> None:
        self.model.problems = self.problemsLines()
        self.model.screen = "problems"

    def closeProblems(self) -> None:
        self.model.screen = "main" if self.session is not None and self.session.isSignedIn() else "signIn"

    async def copyProblems(self) -> None:
        await self.services.clipboard.set("\n".join(self.model.problems))
        self.model.notice = "Copied."

    def clearProblems(self) -> None:
        self.log.clear()
        self.model.problems = self.problemsLines()

    def problemsLines(self) -> tuple[str, ...]:
        check = self.log.check(self.extraLogFiles())
        recent = tuple((entry.at, entry.area, entry.plainWords, entry.technical) for entry in self.log.entries(limit=20))
        return problemsReport(appSchema, self.syncFacts(), LogFacts(check.lines, check.tokenShapedStrings,
                                                                     check.knownSecretsFound, recent),
                              self.clock(), len(self.state.unreadablePlans))

    # --- Plan import (PC view; the phone's fallback, G2b-2) -----------------------------------

    async def pickPlanFile(self) -> None:
        files = await self.services.filePicker.pick_files(file_type=ft.FilePickerFileType.CUSTOM,
                                                          allowed_extensions=["json"], with_data=True)
        if not files:
            return
        picked = files[0]
        workoutToday = self.model.today is not None and self.model.today.workoutExists
        self.model.planImport = startImport(picked.name, picked.bytes or b"", self.state.known, self.localToday(),
                                            workoutLoggedToday=workoutToday)
        self.model.screen = "importPlan"

    def answerPlanQuestions(self, sameAs: list[bool]) -> None:
        self.model.planImport = answerQuestions(self.model.planImport, sameAs)

    async def finishPlanImport(self, startStep: int) -> None:
        flow = self.model.planImport
        row = finishImport(flow, startStep, self.session.userId(), self.clock())
        self.model.notice = ""
        await self._act(self.saveRows([("plans", row)]))
        if self.model.notice:  # the save failed and says why: stay on the import
            return
        when = "today" if flow.takesEffect == self.localToday() else "tomorrow"
        self.model.notice = f"Plan imported. It takes effect {when}."
        self.closePlanImport()

    def closePlanImport(self) -> None:
        self.model.planImport = None
        self.model.screen = "main"
