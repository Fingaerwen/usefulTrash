"""Notes written on the phone first and sent to Supabase later (Phase 0 check 4).

A local SQLite file in the app's private data folder. Each note gets its final ID here, when it's written,
so sending it again after a lost answer can never create a duplicate in Supabase. Not encrypted: gym data
isn't sensitive (plan T1.1). The sign-in session is stored separately, encrypted."""

import os
import sqlite3
import time
import uuid


class OfflineQueue:
    """Notes waiting to be sent, oldest first."""

    def __init__(self, folder: str):
        self.dbPath = os.path.join(folder, "offlineQueue.sqlite3")
        self._run(
            'create table if not exists "pendingNotes" '
            '("id" text primary key, "noteText" text not null, "createdAt" real not null)'
        )

    def _run(self, sql: str, params: tuple | list = ()) -> list:
        """Runs one statement in its own transaction (committed on success, rolled back on error)."""
        db = sqlite3.connect(self.dbPath)
        try:
            with db:
                return db.execute(sql, params).fetchall()
        finally:
            db.close()

    def add(self, noteText: str) -> str:
        """Stores a note on the phone and returns its ID (the same ID it will have in Supabase)."""
        noteId = str(uuid.uuid4())
        self._run('insert into "pendingNotes" ("id", "noteText", "createdAt") values (?, ?, ?)',
                  (noteId, noteText, time.time()))
        return noteId

    def pending(self) -> list[dict]:
        """All notes not sent yet, oldest first."""
        rows = self._run('select "id", "noteText" from "pendingNotes" order by "createdAt"')
        return [{"id": noteId, "noteText": noteText} for noteId, noteText in rows]

    def count(self) -> int:
        return self._run('select count(*) from "pendingNotes"')[0][0]

    def remove(self, noteIds: list[str]) -> None:
        """Forgets notes that Supabase has confirmed."""
        if noteIds:
            placeholders = ", ".join("?" for _ in noteIds)
            self._run(f'delete from "pendingNotes" where "id" in ({placeholders})', noteIds)
