"""The gym app's tables (plan 14) and the cloud upgrade it's built for (14c).

The shared tables (body weight, daily steps, backups) come from usefulShared.tables. A test runs the
cloud scripts in a local Postgres and checks these definitions match the real tables exactly.
"""

from usefulShared.tables import Column, moment, sharedTables, table

# The last cloud upgrade (cloud/NNN_*.sql) this app is built for. Before each sync the app reads
# cloudInfo and syncs only if minAppSchema <= appSchema <= schemaVersion (14b, UP1.1).
appSchema = 1

# Plan imports: the plan as imported, when it takes effect and the starting step you chose.
plans = table(
    "plans",
    Column("importedAt", moment),  # orders imports taking effect the same day
    Column("effectiveDate", "date"),
    Column("startStep", "integer"),
    Column("planJson", "jsonb"),  # the plan file as read, with matched exercise IDs (11.3)
    Column("archived", "boolean"),
)

# Workouts: one per day (DT1.1), each recording which plan step it was.
sessions = table(
    "sessions",
    Column("date", "date"),
    Column("planImportId", "uuid"),
    Column("stepIndex", "integer"),
    Column("finishedAt", moment, required=False),  # empty until you tap Finish
    dayKey=("date",),
)

# One exercise on one workout day: what was suggested and what you did.
exerciseLogs = table(
    "exerciseLogs",
    Column("date", "date"),
    Column("exerciseId", "text"),
    Column("targetReps", "integer", required=False),  # what Today suggested
    Column("targetWeightKg", "numeric(6,2)", required=False),
    Column("sets", "jsonb"),  # [{"reps": 9, "weightKg": 82.5}, ...]
    Column("minutes", "integer", required=False),  # cardio
    Column("skipped", "boolean"),
    Column("declinedSuggestion", "boolean"),  # you pressed Undo on ↑new
    dayKey=("date", "exerciseId"),
)

gymTables = (plans, sessions, exerciseLogs)
appTables = gymTables + sharedTables  # everything this app syncs
tablesByName = {table.name: table for table in appTables}
