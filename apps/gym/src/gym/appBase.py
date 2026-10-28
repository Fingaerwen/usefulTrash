"""What the phone app and the PC view share (plan 3b): the model, Today's actions, the Problems page and
plan import. Each mode adds where rows come from and go to (phoneApp.py, pcApp.py)."""

import datetime as dt
from collections.abc import Callable, Sequence
from typing import Any

import flet as ft

from gym.actions import ActionRefused, GymActions
from gym.model import AppModel, LogFacts, SyncFacts, problemsReport
from gym.planImporter import answerQuestions, askSwitch, finishImport, startImport, switchBack
from gym.rules.stats import summaryBanner, weighInBanner
from gym.rules.today import ExerciseLine, SetDone, TodayView
from gym.state import GymState, PlanEntry
from gym.tables import appSchema
from usefulShared.backup.backupJob import lastBackupText
from usefulShared.platform.appLog import AppLog


class AppBase:
    """The shared part of both controllers."""

    mode = "phone"  # or "pc": which main screen and ⋮ menu the screens show
    menuItems: tuple[str, ...] = ("problems", "history", "deload", "importPlan", "signOut")
    stepsDaysBack: int | None = 7  # Week's calendar: how far back steps can be entered (SC4.1). None = any day

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
        self._summarySeen: dt.date | None = None  # see summarySeenFor

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
        self._refreshChart()
        self.model.weight = self.state.weightView(today, self.model.weightRange)
        self._refreshHistory()
        self.afterRefresh()
        self.model.banners = (*self.model.banners, *self.state.banners(today, self.summarySeenFor()))

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

    # Today's actions. History's day editor passes its own day's view (HI1.1).

    async def check(self, line: ExerciseLine, view: TodayView | None = None) -> None:
        if await self._act(self.actions.checkExercise(view or self.model.today, line)):
            await self._restAfter(line, view)

    async def saveSets(self, line: ExerciseLine, sets: list[SetDone], minutes: int | None = None,
                       view: TodayView | None = None) -> None:
        if await self._act(self.actions.saveSets(view or self.model.today, line, sets, minutes)):
            await self._restAfter(line, view)

    # The rest timer (RT1.1): logging one of today's exercises starts its rest, unless nothing is left to do.
    # its rest time on Today starts it between sets. The phone also sets an alert for when it's over.

    async def _restAfter(self, line: ExerciseLine, view: TodayView | None) -> None:
        today = self.model.today
        if (view is not None or line.status == "done" or not line.exercise.restSec
                or today is None or not any(other.status == "todo" for other in today.exercises)):
            return
        await self.startRest(line.exercise.restSec, line.exercise.name)

    async def startRest(self, seconds: int, name: str) -> None:
        self.model.restSeconds, self.model.restName = seconds, name
        self.model.restUntil = self.clock() + dt.timedelta(seconds=seconds)
        await self.restAlert(seconds)

    async def addRest(self, seconds: int = 30) -> None:
        """+30 s: from what's left, or from now once it's over."""
        if self.model.restUntil is None:
            return
        now = self.clock()
        left = max(0.0, (self.model.restUntil - now).total_seconds()) + seconds
        self.model.restSeconds = max(self.model.restSeconds, round(left))
        self.model.restUntil = now + dt.timedelta(seconds=left)
        await self.restAlert(round(left))

    async def stopRest(self) -> None:
        self.model.restUntil = None
        await self.restAlert(None)

    async def restAlert(self, seconds: int | None) -> None:
        """The phone sets (or with None, cancels) its alert for when the rest is over. The PC view has none."""

    async def skip(self, line: ExerciseLine, view: TodayView | None = None) -> None:
        await self._act(self.actions.skipExercise(view or self.model.today, line))

    async def declineSuggestion(self, line: ExerciseLine, declined: bool) -> None:
        await self._act(self.actions.declineSuggestion(self.model.today, line, declined))

    async def finish(self) -> None:
        await self._act(self.actions.finishWorkout(self.model.today))

    async def setSteps(self, steps: int | None) -> None:
        await self._act(self.actions.setSteps(self.localToday(), steps))

    async def setStepsOn(self, date: dt.date, steps: int | None) -> None:
        """Steps for a day in Week's calendar (SC4.1): on the phone for the last 7 days, on the PC any day."""
        today = self.localToday()
        if date > today or (self.stepsDaysBack is not None and (today - date).days >= self.stepsDaysBack):
            self.model.notice = "Steps can be entered here for the last 7 days, the PC view takes any day."
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
        """◂ ▸: earlier weeks, never past this one. Seeing last week's counts as seeing its summary (BN1.1)."""
        self.model.weekOffset = max(0, offset)
        self._refreshWeek()
        if self.model.weekOffset == 1 and self.model.week is not None:
            self.markSummarySeen(self.model.week.monday)
            self.refresh()

    # --- Charts and Weight (SC8.1, SC5.1) and the day's banners (18.4a) ------------------------

    def _refreshChart(self) -> None:
        choices = [line.exercise.exerciseId for line in (*self.model.progress, *self.model.pastProgress)]
        exerciseId = self.model.chartExercise if self.model.chartExercise in choices else (choices or [""])[0]
        self.model.chart = self.state.chart(exerciseId, self.localToday(), self.model.chartRange) if exerciseId else None

    def showChart(self, exerciseId: str) -> None:
        self.model.chartExercise = exerciseId
        self._refreshChart()

    def showChartRange(self, chartRange: str) -> None:
        self.model.chartRange = chartRange
        self._refreshChart()

    def showWeightRange(self, chartRange: str) -> None:
        self.model.weightRange = chartRange
        self.model.weight = self.state.weightView(self.localToday(), chartRange)

    async def setBodyWeight(self, date: dt.date, weightKg: float | None) -> None:
        await self._act(self.actions.setBodyWeight(date, self.localToday(), weightKg))

    def summarySeenFor(self) -> dt.date | None:
        """The Monday of the last week whose summary you've looked at (BN1.1). The PC view keeps it in memory."""
        return self._summarySeen

    def markSummarySeen(self, monday: dt.date) -> None:
        self._summarySeen = monday

    # --- History: days to edit and the monthly diary (HI1.1, DI1.1) ---------------------------

    def historyDates(self) -> list[dt.date]:
        """The days History lists: every day of the month shown, up to today (HI1.2). The phone edits only its
        last 7 (19.1f-1) and shows older ones read-only."""
        today = self.localToday()
        month = self.model.historyMonth or today.replace(day=1)
        days = (month.replace(month=month.month % 12 + 1, year=month.year + month.month // 12) - month).days
        return [month + dt.timedelta(days=offset) for offset in range(days) if month + dt.timedelta(days=offset) <= today]

    def canEditDay(self, date: dt.date) -> bool:
        return self.canEnterStepsOn(date)

    def _refreshHistory(self) -> None:
        today = self.localToday()
        self.model.historyDays = self.state.historyDays(self.historyDates(), today)
        day = self.model.historyDay
        self.model.historyView = self.state.today(day) if day is not None else None
        self.model.diary = self.state.diary(self.model.historyMonth or today.replace(day=1), today)

    def openHistory(self) -> None:
        """The phone's ⋮ → History (HI1.1)."""
        self.model.historyDay = None
        self._refreshHistory()
        self.model.screen = "history"

    def closeHistory(self) -> None:
        self.model.historyDay, self.model.historyView = None, None
        self.model.screen = "main"

    def showHistoryMode(self, mode: str) -> None:
        self.model.historyMode = mode
        self.model.historyDay, self.model.historyView = None, None

    def showHistoryMonth(self, months: int) -> None:
        """◂ ▸: another month, never past this one nor before the first with a plan or anything logged."""
        thisMonth = self.localToday().replace(day=1)
        month = self.model.historyMonth or thisMonth
        index = month.year * 12 + month.month - 1 + months
        chosen = dt.date(index // 12, index % 12 + 1, 1)
        self.model.historyMonth = max(min(chosen, thisMonth), self.firstHistoryMonth())
        self._refreshHistory()

    def firstHistoryMonth(self) -> dt.date:
        """The earliest month History goes back to: the first plan's, or the first with anything logged."""
        thisMonth = self.localToday().replace(day=1)
        starts = [imported.start.effectiveDate.replace(day=1) for imported in self.state.plans]
        diaryFirst = self.model.diary.firstMonth if self.model.diary else thisMonth
        return min([*starts, diaryFirst, thisMonth])

    def editDay(self, date: dt.date) -> None:
        """Opens a day: to edit it, or to look at it if it's too far back to edit here (HI1.2)."""
        if date <= self.localToday():
            self.model.historyDay = date
            self._refreshHistory()

    def closeDay(self) -> None:
        self.model.historyDay, self.model.historyView = None, None
        self._refreshHistory()

    async def deleteWorkout(self, date: dt.date) -> None:
        await self._act(self.actions.deleteWorkout(date))

    def _live(self, tableName: str) -> list[dict[str, Any]]:
        return [row for row in self.state.rows.get(tableName, {}).values() if not row["deleted"]]

    def openBanner(self, banner: str) -> None:
        """A banner tapped: the summary opens last week on Week, the weigh-in the Weight tab (18.4a)."""
        if banner == summaryBanner:
            self.model.tab = "week"
            self.showWeek(1)
        elif banner == weighInBanner:
            self.model.tab = "weight"

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

    async def _act(self, action) -> bool:
        """Runs an action. A refused entry shows why, anything unexpected goes to the log. True if it worked."""
        try:
            await action
            return True
        except ActionRefused as refused:
            self.model.notice = str(refused)
        except Exception as problem:
            notice = self.describeFailure(problem)
            if notice is None:
                self.log.crash(problem, "today")
                notice = "That didn't work. Details are on the Problems page."
            self.model.notice = notice
        return False

    def describeFailure(self, problem: Exception) -> str | None:
        """Plain words for an expected failure (the PC view's refused writes). None = unexpected."""
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
                              self.clock(), len(self.state.unreadablePlans),
                              lastBackup=lastBackupText(self._live("backups"), self.clock()), startedIn=self.startedIn)

    # --- Plan import (PC view, the phone's fallback, G2b-2) -----------------------------------

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

    # --- Switching back to an earlier plan and archiving (PC view, SW1.1, SW1.2) --------------

    def askSwitch(self, entry: PlanEntry) -> None:
        """Switch first asks, since it changes what Today shows."""
        workoutToday = self.model.today is not None and self.model.today.workoutExists
        self.model.planSwitch = askSwitch(entry.rowId, entry.name, self.localToday(), workoutToday)
        self.model.notice = ""

    def cancelSwitch(self) -> None:
        self.model.planSwitch = None

    async def confirmSwitch(self) -> None:
        asked, self.model.planSwitch = self.model.planSwitch, None
        source = self.state.row("plans", asked.rowId) if asked else None
        if source is None:
            return
        row = switchBack(source, self.session.userId(), self.clock(), asked.takesEffect)
        if await self._act(self.saveRows([("plans", row)])):
            when = "today" if asked.takesEffect == self.localToday() else "tomorrow"
            self.model.notice = f"Switched to {asked.name}. It takes effect {when}."

    async def setArchived(self, entry: PlanEntry, archived: bool) -> None:
        """Archive hides an earlier plan in the Archived list, Unarchive brings it back. Nothing else changes."""
        row = self.state.row("plans", entry.rowId)
        if row is not None and bool(row.get("archived")) != archived:
            await self._act(self.saveRows([("plans", dict(row, archived=archived))]))
