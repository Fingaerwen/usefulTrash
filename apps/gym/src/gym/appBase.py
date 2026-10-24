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
    menuItems: tuple[str, ...] = ("problems", "deload", "importPlan", "signOut")
    stepsDaysBack: int | None = 7  # Week's calendar: how far back steps can be entered (SC4.1); None = any day

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
        self.startedIn: float | None = None  # seconds from Python starting to the first real screen (main.py)

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
        self.model.today = self.state.today(today)
        running = self.state.training(today).deloadOn(today) is not None
        self.model.deloadAction = ("stop" if self.state.manualDeloadAt(today) else "" if running else "start")
        self.model.progress, self.model.pastProgress = self.state.progress(today)
        self._refreshDetail()
        self._refreshWeek()
        self.afterRefresh()

    def _refreshDetail(self) -> None:
        self.model.detail = (self.state.exerciseDetail(self.model.progressOpen, self.localToday(),
                                                       self.model.progressRange)
                             if self.model.progressOpen else None)

    def _refreshWeek(self) -> None:
        today = self.localToday()
        monday = today - dt.timedelta(days=today.weekday() + 7 * self.model.weekOffset)
        self.model.week = self.state.week(monday, today)

    def startActions(self) -> None:
        self.actions = GymActions(self, self.state, self.session.userId(), self.clock)

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

    async def setStepsOn(self, date: dt.date, steps: int | None) -> None:
        """Steps for a day in Week's calendar (SC4.1): on the phone for the last 7 days, on the PC any day."""
        today = self.localToday()
        if date > today or (self.stepsDaysBack is not None and (today - date).days >= self.stepsDaysBack):
            self.model.notice = "Steps can be entered here for the last 7 days; the PC view takes any day."
            return
        await self._act(self.actions.setSteps(date, steps))

    def canEnterStepsOn(self, date: dt.date) -> bool:
        today = self.localToday()
        return date <= today and (self.stepsDaysBack is None or (today - date).days < self.stepsDaysBack)

    # --- Progress and Week (SC3.1, SC4.1) ---------------------------------------------------

    def openExercise(self, exerciseId: str) -> None:
        self.model.progressOpen = exerciseId
        self._refreshDetail()

    def closeExercise(self) -> None:
        self.model.progressOpen, self.model.detail = "", None

    def showRange(self, chartRange: str) -> None:
        self.model.progressRange = chartRange
        self._refreshDetail()

    def showWeek(self, offset: int) -> None:
        """◂ ▸: earlier weeks, never past this one."""
        self.model.weekOffset = max(0, offset)
        self._refreshWeek()

    async def setWeight(self, exerciseId: str, weekday: int, weightKg: float) -> None:
        """A weight for one exercise on one day (WD2.1). If that day's session has it logged today, it applies
        from tomorrow (WD3.7)."""
        today = self.model.today
        doneToday = today is not None and any(
            line.exercise.exerciseId == exerciseId and line.trackDay == weekday and line.status == "done"
            for line in today.exercises)
        await self._act(self.actions.setWeight(exerciseId, weekday, weightKg, self.localToday(), doneToday))

    async def setStep(self, exerciseId: str, incrementKg: float) -> None:
        await self._act(self.actions.setStep(exerciseId, incrementKg, self.localToday()))

    async def startDeload(self) -> None:
        workoutToday = self.model.today is not None and self.model.today.workoutExists
        await self._act(self.actions.startDeload(self.localToday(), workoutToday))

    async def stopDeload(self) -> None:
        await self._act(self.actions.stopDeload(self.localToday()))

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
                              self.clock(), len(self.state.unreadablePlans), startedIn=self.startedIn)

    # --- Plan import (PC view; the phone's fallback, G2b-2) -----------------------------------

    async def pickPlanFile(self) -> None:
        files = await self.services.filePicker.pick_files(file_type=ft.FilePickerFileType.CUSTOM,
                                                          allowed_extensions=["json"], with_data=True)
        if not files:
            return
        picked = files[0]
        workoutToday = self.model.today is not None and self.model.today.workoutExists
        self.model.planImport = startImport(picked.name, picked.bytes or b"", self.state.known, self.localToday(),
                                            training=self.state.training(self.localToday()),
                                            workoutLoggedToday=workoutToday)
        self.model.screen = "importPlan"

    def answerPlanQuestions(self, sameAs: list[bool]) -> None:
        self.model.planImport = answerQuestions(self.model.planImport, sameAs, self.state.training(self.localToday()))

    async def finishPlanImport(self) -> None:
        flow = self.model.planImport
        row = finishImport(flow, self.session.userId(), self.clock())
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
