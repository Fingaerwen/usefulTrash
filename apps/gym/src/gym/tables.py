"""The gym app's tables (plan 14) and the cloud upgrade it's built for (14c).

The tables Ambrosia reads too (plans, exercise logs, body weight) and the other shared ones (daily steps,
backups) come from usefulShared.tables. A test runs the cloud scripts in a local Postgres and checks these
definitions match the real tables exactly.
"""

from usefulShared.tables import Column, exerciseLogs, moment, plans, sharedTables, table

# The last cloud upgrade (cloud/NNN_*.sql) this app is built for. Before each sync the app reads
# cloudInfo and syncs only if minAppSchema <= appSchema <= schemaVersion (14b, UP1.1).
appSchema = 3

# Workouts: one per day (DT1.1), each recording which plan step it was.
sessions = table(
    "sessions",
    Column("date", "date"),
    Column("planImportId", "uuid"),
    Column("stepIndex", "integer"),
    Column("finishedAt", moment, required=False),  # empty until you tap Finish
    dayKey=("date",),
)

# A weight you set in the app for one exercise on one day (WD2.1): from fromDate on, that day's target
# starts again from it (WD3.7). Every change is its own row, so a later one never rewrites what an
# earlier one did to your progression.
exerciseWeights = table(
    "exerciseWeights",
    Column("exerciseId", "text"),
    Column("weekday", "integer"),  # 0 = Monday
    Column("weightKg", "numeric(6,2)"),
    Column("fromDate", "date"),
)

# A weight step you set in the app (WD2.1): from fromDate on, it replaces the plan's incrementKg. Every
# change is its own row, so sessions before it keep the step they had.
exerciseSteps = table(
    "exerciseSteps",
    Column("exerciseId", "text"),
    Column("incrementKg", "numeric(5,2)"),
    Column("fromDate", "date"),
)

# A deload you started by hand (WD2.4): 7 days from startDate. Stopping it deletes the row.
deloads = table(
    "deloads",
    Column("startDate", "date"),
)

gymTables = (plans, sessions, exerciseLogs, exerciseWeights, exerciseSteps, deloads)
appTables = gymTables + sharedTables  # everything this app syncs
tablesByName = {table.name: table for table in appTables}
