"""Read-only, time-bounded SQLite execution adapter."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from time import monotonic


class QueryTimeoutError(TimeoutError):
    """Raised when SQLite exceeds the configured execution deadline."""


class ReadOnlySQLite:
    def __init__(self, database: Path, *, timeout_seconds: float = 5.0):
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds 必須大於 0")
        self.database = database.resolve()
        self.timeout_seconds = timeout_seconds

    def execute(
        self, sql: str, params: tuple[object, ...]
    ) -> tuple[list[str], list[tuple[object, ...]]]:
        if not self.database.is_file():
            raise FileNotFoundError(self.database)

        deadline = monotonic() + self.timeout_seconds
        timed_out = False

        def within_deadline() -> int:
            nonlocal timed_out
            timed_out = monotonic() > deadline
            return int(timed_out)

        uri = f"{self.database.as_uri()}?mode=ro"
        try:
            with sqlite3.connect(uri, uri=True) as connection:
                connection.execute("PRAGMA query_only = ON")
                connection.set_progress_handler(within_deadline, 1_000)
                cursor = connection.execute(sql, params)
                columns = [item[0] for item in cursor.description or ()]
                rows = [tuple(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError as error:
            if timed_out:
                raise QueryTimeoutError(
                    f"SQLite 查詢超過 {self.timeout_seconds:g} 秒上限。"
                ) from error
            raise
        return columns, rows
