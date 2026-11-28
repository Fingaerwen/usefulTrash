"""Steps and calories from Health Connect (gym/rules/health.py, plan HC1.1 to HC1.4)."""

import datetime as dt

from gym.rules.health import HealthDay, StoredDay, changedDays, kcalText, readHealthDays, readWindow

today = dt.date(2026, 11, 28)


def testTheFirstReadGoes30DaysBackThen7():
    assert readWindow([], today) == (today - dt.timedelta(days=29), today)
    assert readWindow([today - dt.timedelta(days=3)], today) == (today - dt.timedelta(days=6), today)


def testReadingsBecomeDaysWithWholeKcal():
    raw = [{"date": "2026-11-27", "steps": 9500, "activeKcal": 411.6, "totalKcal": 2310.2},
           {"date": "2026-11-26", "steps": None, "activeKcal": 120.0, "totalKcal": None},  # calories, no steps
           {"date": "2026-11-25", "steps": None, "activeKcal": None, "totalKcal": None},  # nothing: left out
           {"date": "2026-11-29", "steps": 10, "activeKcal": None, "totalKcal": None},  # after today: left out
           {"date": "2026-11-24", "steps": 900000, "activeKcal": None, "totalKcal": None},  # no phone counts that
           {"date": "soon"}, "x"]
    days, skipped = readHealthDays(raw, today)
    assert days == [HealthDay(dt.date(2026, 11, 27), 9500, 412, 2310), HealthDay(dt.date(2026, 11, 26), 0, 120, None)]
    assert len(skipped) == 3


def testOnlyChangedOrTypedDaysAreWritten():
    """HC1.2, HC1.3: a late OHealth sync changes a day, and Health Connect replaces typed steps."""
    same = HealthDay(dt.date(2026, 11, 26), 8000, 300, 2200)
    later = HealthDay(dt.date(2026, 11, 27), 9500, 412, 2310)
    typed = HealthDay(dt.date(2026, 11, 28), 4000, 150, 1200)
    stored = {same.date: StoredDay(8000, 300, 2200, True), later.date: StoredDay(7000, 300, 2100, True),
              typed.date: StoredDay(4000, None, None, False)}
    assert changedDays([same, later, typed], stored) == [later, typed]


def testKcalText():
    assert kcalText(412, 2310) == "Active 412 kcal · Total 2,310 kcal"
    assert kcalText(None, 2310) == "Total 2,310 kcal" and kcalText(None, None) == ""
