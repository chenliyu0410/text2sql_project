import sqlite3

import pytest

from text2sql.db import ReadOnlySQLite


def test_readonly_sqlite_executes_select_and_rejects_writes(tmp_path) -> None:
    database = tmp_path / "sample.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE sample (value TEXT)")
        connection.execute("INSERT INTO sample VALUES ('ok')")

    executor = ReadOnlySQLite(database)
    columns, rows = executor.execute("SELECT value FROM sample LIMIT 1", ())
    assert columns == ["value"]
    assert rows == [("ok",)]
    with pytest.raises(sqlite3.OperationalError):
        executor.execute("DELETE FROM sample", ())
