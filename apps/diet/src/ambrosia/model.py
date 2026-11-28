"""What Ambrosia's screens draw (plan 3b: declarative screens): one observable model. The controller
(appBase.py) changes it. Every screen that shows a changed field redraws by itself."""

import datetime as dt
from dataclasses import dataclass, field

import flet as ft

from ambrosia.rules.foods import Food, LoggedFood
from ambrosia.rules.shake import ShakeValues, placeholder
from ambrosia.rules.targets import FileCheck
from ambrosia.rules.today import DayView
from ambrosia.rules.week import WeekView
from ambrosia.sources.openFoodFacts import Product
from ambrosia.state import BulkCheckView, HistoryDay, TargetsView

appName = "Ambrosia"
appVersion = "0.2-alpha"


@dataclass(frozen=True, slots=True)
class Found:
    """One search result: a food, where it's from or how often you've had it, and for a packaged food without all
    four values the product, to type the rest from its label (AM2.3)."""

    food: Food | None
    title: str
    detail: str
    product: Product | None = None
    last: LoggedFood | None = None  # Recent: the last time you had it, to have it again in one tap (4a)


@dataclass(frozen=True, slots=True)
class SearchResults:
    words: str
    yours: tuple[Found, ...] = ()
    generic: tuple[Found, ...] = ()
    packaged: tuple[Found, ...] = ()
    packagedNote: str = ""  # "Searching…", a problem in plain words, or "" when done


@dataclass(frozen=True, slots=True)
class Picked:
    """The food whose amount you're choosing (the How much screen), for which meal and day. Also something you
    logged, opened from its meal to change the amount or the meal, or delete it (AM12.2)."""

    food: Food
    meal: str
    date: dt.date
    portion: str = "grams"
    count: float = 100
    weighedG: float | None = None  # a weighed pack's weight from its barcode, for the Whole pack button (AM11.1)
    logId: str | None = None  # something you logged, opened to look at or change (AM12.2). None: adding food
    readOnly: bool = False  # opened on a day the phone can't edit any more (AM5.5)


@dataclass(frozen=True, slots=True)
class ShakeDraft:
    """The protein shake screen (AM12.3): a shake being added to a meal, or one you logged, opened (AM12.2)."""

    meal: str
    date: dt.date
    proteinG: float  # this shake's protein, to start the field with
    logId: str | None = None  # an opened shake. None: adding one
    readOnly: bool = False  # opened on a day the phone can't edit any more (AM5.5)
    logged: LoggedFood | None = None  # an opened shake as logged, with its values then


@dataclass(frozen=True, slots=True)
class LabelDraft:
    """Typing a food from its label (AM2.3): what's known so far, as text for the fields."""

    why: str  # "Barcode … isn't in Open Food Facts." and so on
    barcode: str = ""
    name: str = ""
    brand: str = ""
    unit: str = "g"
    kcal: str = ""
    proteinG: str = ""
    fatG: str = ""
    carbsG: str = ""
    servingG: str = ""
    packG: str = ""
    meal: str = "lunch"
    date: dt.date | None = None
    weighedG: float | None = None  # kept for How much after the label is saved


@ft.observable
@dataclass
class AppModel:
    """Everything the screens show. Fields are replaced, never changed in place, so each change redraws."""

    screen: str = "starting"  # starting, signIn, downloading, main, add, amount, label, shake, importTargets,
    # history, problems or failed
    tab: str = "today"  # phone: today, week, targets. The PC view also history, backup
    busy: str = ""  # what's running right now ("Signing in…"). Buttons wait while it's set
    notice: str = ""  # a message shown once, like a refused entry or a sign-in problem
    failure: str = ""  # why the app can't start (screen "failed")
    downloaded: int = 0  # first download: "Downloading your data… N rows" (plan 14b)
    today: DayView | None = None
    weekDays: tuple[dt.date, ...] = ()  # Today's day strip (AM12.1): the days of this week, Monday to Sunday
    dayShown: dt.date | None = None  # the day Today shows when it isn't today, None for today
    dayView: DayView | None = None  # that day, laid out like Today
    weekOffset: int = 0
    week: WeekView | None = None
    targets: TargetsView | None = None
    banners: tuple[str, ...] = ()  # sync and backup problems, at the top of any tab
    bulkCheck: BulkCheckView | None = None  # the bulk check's newest result and suggestion (4g). None: it's off
    applyReady: bool = False  # synced today, so the suggestion's Apply can go ahead (4g)
    waiting: int = 0  # changes not sent yet: "3 waiting"
    backupStatus: str = ""  # the PC view's Backup tab: what Back up now or Export CSV just did
    # Adding food (4a): for which meal and day, how, and what was found
    addMeal: str = "lunch"
    addDate: dt.date | None = None
    addMode: str = "search"  # search, scan or recent
    searchWords: str = ""  # what's typed in the search field, kept while you look at a result
    results: SearchResults | None = None
    recent: tuple[Found, ...] = ()
    picked: Picked | None = None
    label: LabelDraft | None = None
    shake: ShakeDraft | None = None  # the protein shake screen (AM12.3)
    shakeValues: ShakeValues = placeholder  # your shake's values a serving, as set in the app
    shakeIsPlaceholder: bool = True  # they're still the placeholders: the screen asks you to set yours
    # A targets file being imported (4f)
    targetsCheck: FileCheck | None = None
    targetsData: dict | None = field(default=None, repr=False)
    # History (AM5.5)
    historyMonth: dt.date | None = None
    historyDays: tuple[HistoryDay, ...] = ()
    historyDay: DayView | None = None
    problems: tuple[str, ...] = ()
