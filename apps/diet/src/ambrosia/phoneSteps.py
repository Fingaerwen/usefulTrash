"""The phone database's numbered steps (plan 14c): step N brings the phone's database to schema N, matching cloud
upgrade N. Ambrosia's database holds its own tables and copies of the three Talon tables it reads, so each step
creates what that upgrade added of those (step 2 is empty: upgrade 002 added only Talon's settings). A new phone
runs all three at once.

Frozen once released: a later change is a new step, never an edit to an old one, because phones that already ran
a step never run it again. A test checks that running every step builds exactly the tables in ambrosia/tables.py,
and that there's one step per cloud upgrade.

How values are kept (usefulShared.tables): UUIDs, text, dates, moments and JSON as text. Whole numbers and
booleans as integers. Decimals as real numbers. The cloud's stamp may be empty on the phone. SQLite lets a text
primary key be empty unless it says "not null", so every id does.
"""

phoneSteps: tuple[tuple[str, ...], ...] = (
    # Step 1 (cloud 001): the Talon tables Ambrosia reads, and the phone-only outbox, syncState and meta.
    (
        """create table "plans" (
            "id" text not null primary key, "userId" text not null, "updatedAt" text not null,
            "deleted" integer not null, "cloudUpdatedAt" text,
            "importedAt" text not null, "effectiveDate" text not null, "startStep" integer not null,
            "planJson" text not null, "archived" integer not null)""",
        """create table "exerciseLogs" (
            "id" text not null primary key, "userId" text not null, "updatedAt" text not null,
            "deleted" integer not null, "cloudUpdatedAt" text,
            "date" text not null, "exerciseId" text not null, "targetReps" integer, "targetWeightKg" real,
            "sets" text not null, "minutes" integer, "skipped" integer not null,
            "declinedSuggestion" integer not null)""",
        """create table "bodyWeight" (
            "id" text not null primary key, "userId" text not null, "updatedAt" text not null,
            "deleted" integer not null, "cloudUpdatedAt" text,
            "date" text not null, "weightKg" real not null)""",
        # Changes waiting to be sent: one entry per row, holding the edit time of its newest unsent edit.
        # queuedAt stays the time of the oldest unsent edit. refusedReason: the cloud refused it. It's not sent
        # again until it's edited or retried. Ambrosia never edits Talon's tables, so they never get one.
        """create table "outbox" (
            "tableName" text not null, "rowId" text not null, "updatedAt" text not null,
            "queuedAt" text not null, "refusedReason" text,
            primary key ("tableName", "rowId"))""",
        # How far fetching has got in each table: the newest cloud stamp seen (plan 14b).
        """create table "syncState" ("tableName" text not null primary key, "cloudUpdatedAt" text not null)""",
        # Small facts about this database, such as whose data it holds.
        """create table "meta" ("key" text not null primary key, "value" text not null)""",
    ),
    # Step 2 (cloud 002): nothing Ambrosia keeps.
    (),
    # Step 3 (cloud 003): Ambrosia's own tables (4e), and the time of today's weigh-in (AM6.3).
    (
        """alter table "bodyWeight" add column "weighedAt" text""",
        """create table "foods" (
            "id" text not null primary key, "userId" text not null, "updatedAt" text not null,
            "deleted" integer not null, "cloudUpdatedAt" text,
            "source" text not null, "barcode" text, "usdaId" integer, "name" text not null, "brand" text,
            "unit" text not null, "kcal" real not null, "proteinG" real not null, "fatG" real not null,
            "carbsG" real not null, "servingG" real, "packG" real)""",
        """create table "foodLogs" (
            "id" text not null primary key, "userId" text not null, "updatedAt" text not null,
            "deleted" integer not null, "cloudUpdatedAt" text,
            "date" text not null, "meal" text not null, "loggedAt" text not null, "foodId" text not null,
            "portion" text not null, "portionCount" real, "grams" real not null, "name" text not null,
            "brand" text, "unit" text not null, "kcal" real not null, "proteinG" real not null,
            "fatG" real not null, "carbsG" real not null)""",
        """create table "water" (
            "id" text not null primary key, "userId" text not null, "updatedAt" text not null,
            "deleted" integer not null, "cloudUpdatedAt" text,
            "date" text not null, "ml" integer not null)""",
        """create table "dietTargets" (
            "id" text not null primary key, "userId" text not null, "updatedAt" text not null,
            "deleted" integer not null, "cloudUpdatedAt" text,
            "importedAt" text not null, "effectiveDate" text not null, "targetsJson" text not null)""",
        """create table "targetChanges" (
            "id" text not null primary key, "userId" text not null, "updatedAt" text not null,
            "deleted" integer not null, "cloudUpdatedAt" text,
            "checkDate" text not null, "fromDate" text not null, "targetsImportId" text not null,
            "reason" text not null, "kcalChange" integer not null, "macro" text not null,
            "macroChangeG" integer not null, "blockAvgKg" real not null, "blockWeighIns" integer not null,
            "comparedStart" text not null, "comparedAvgKg" real not null, "comparedWeighIns" integer not null,
            "rateKgPerWeek" real)""",
        """create table "dietBackups" (
            "id" text not null primary key, "userId" text not null, "updatedAt" text not null,
            "deleted" integer not null, "cloudUpdatedAt" text,
            "madeAt" text not null, "fileName" text not null, "driveFileId" text, "sizeBytes" integer,
            "schemaVersion" integer not null, "madeBy" text not null)""",
    ),
)
