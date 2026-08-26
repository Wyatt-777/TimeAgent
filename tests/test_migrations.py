import sqlite3

import pytest

from core.migrations import Migration, MigrationError, MigrationRunner


def test_runner_applies_each_migration_once() -> None:
    connection = sqlite3.connect(":memory:")
    calls: list[int] = []
    migrations = (
        Migration(2, "second", lambda _: calls.append(2)),
        Migration(1, "first", lambda _: calls.append(1)),
    )
    runner = MigrationRunner(migrations)

    assert runner.apply(connection) == 2
    assert runner.apply(connection) == 2
    assert calls == [1, 2]


@pytest.mark.parametrize(
    "migrations",
    [
        (Migration(0, "zero", lambda _: None),),
        (Migration(1, "duplicate", lambda _: None), Migration(1, "again", lambda _: None)),
        (Migration(1, "", lambda _: None),),
    ],
)
def test_runner_rejects_invalid_definitions(migrations) -> None:
    with pytest.raises(MigrationError):
        MigrationRunner(migrations)
