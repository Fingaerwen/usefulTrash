"""Ambrosia's tables (apps/diet/docs/plan.md 4e) and the cloud upgrade it's built for (plan 14c).

Its own six tables, and three of Talon's it reads but never writes: the plans (training and rest days, AM3.2),
the exercises you logged (whether you trained) and your weigh-ins (the bulk check). A test runs the cloud scripts
in a local Postgres and checks these definitions match the real tables exactly. Rows are plain dicts, with the
values usefulShared.tables describes.
"""

from usefulShared.tables import Column, Table, backups, bodyWeight, exerciseLogs, moment, plans, table

# The last cloud upgrade (cloud/NNN_*.sql) this app is built for. Before each sync the app reads cloudInfo and
# syncs only if minAppSchema <= appSchema <= schemaVersion (plan 14b, UP1.1).
appSchema = 3

# A food you've used: your copy, so Recent works offline and a label typed once is found again (4d). Its ID
# comes from its barcode or its USDA number, so the phone and the PC view saving it make one row.
foods = table(
    "foods",
    Column("source", "text"),  # openFoodFacts, usda or label
    Column("barcode", "text", required=False),  # digits. Empty for a USDA food or a label typed without one
    Column("usdaId", "integer", required=False),  # FoodData Central's number, for a USDA food
    Column("name", "text"),
    Column("brand", "text", required=False),
    Column("unit", "text"),  # g, or ml for a drink (its values are per 100 ml)
    Column("kcal", "numeric(4,1)"),  # per 100 g or ml, like the three below
    Column("proteinG", "numeric(5,2)"),
    Column("fatG", "numeric(5,2)"),
    Column("carbsG", "numeric(5,2)"),
    Column("servingG", "numeric(6,1)", required=False),
    Column("packG", "numeric(6,1)", required=False),
)

# Something you ate, with copies of the food's name and values at the time, so a later edit to the food never
# rewrites a past day.
foodLogs = table(
    "foodLogs",
    Column("date", "date"),
    Column("meal", "text"),  # breakfast, lunch, dinner or snacks
    Column("loggedAt", moment),  # its place in the meal
    Column("foodId", "uuid"),
    Column("portion", "text"),  # grams, servings or pack
    Column("portionCount", "numeric(8,2)", required=False),  # 1, 0.5 and so on. Empty for grams
    Column("grams", "numeric(6,1)"),  # the amount, worked out when logged (ml for a drink)
    Column("name", "text"),
    Column("brand", "text", required=False),
    Column("unit", "text"),
    Column("kcal", "numeric(4,1)"),
    Column("proteinG", "numeric(5,2)"),
    Column("fatG", "numeric(5,2)"),
    Column("carbsG", "numeric(5,2)"),
)

# A day's water: its total, one row per day (two devices adding at once keep the newer total).
water = table("water", Column("date", "date"), Column("ml", "integer"), dayKey=("date",))

# A targets file as imported (4f): it applies from the day you import it.
dietTargets = table(
    "dietTargets",
    Column("importedAt", moment),  # orders imports on the same day
    Column("effectiveDate", "date"),
    Column("targetsJson", "jsonb"),  # the file as imported
)

# A bulk-check change you applied (4g). Its ID comes from the check's Sunday, so a check makes one change at most.
# Undoing it deletes the row. The check's numbers are kept with it, for the record.
targetChanges = table(
    "targetChanges",
    Column("checkDate", "date"),
    Column("fromDate", "date"),  # the day you applied it: it counts from then
    Column("targetsImportId", "uuid"),  # the import it changes
    Column("reason", "text"),  # rate, bigMissLow or bigMissHigh
    Column("kcalChange", "integer"),
    Column("macro", "text"),  # carbs or fat: the macro that takes it
    Column("macroChangeG", "integer"),
    Column("blockAvgKg", "numeric(5,2)"),
    Column("blockWeighIns", "integer"),
    Column("comparedStart", "date"),  # the Monday of the block it was compared with
    Column("comparedAvgKg", "numeric(5,2)"),
    Column("comparedWeighIns", "integer"),
    Column("rateKgPerWeek", "numeric(5,2)", required=False),  # empty for a big miss
    dayKey=("checkDate",),
)

# Ambrosia's backups (AM5.6): the same columns as Talon's, in a table of their own, since Talon decides its own
# backup is due from the newest row in backups.
dietBackups = Table("dietBackups", backups.columns)

dietTables = (foods, foodLogs, water, dietTargets, targetChanges, dietBackups)
talonTables = (plans, exerciseLogs, bodyWeight)  # read, never written (4e)
appTables = dietTables + talonTables  # everything this app syncs
tablesByName = {table.name: table for table in appTables}
