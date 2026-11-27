"""SQLite access and the versioned migration runner (A12).

- PRAGMA user_version holds the schema version; migrations/NNN_*.sql run in order, once each.
- Every connection: WAL journal, foreign keys ON (needed for ON DELETE CASCADE), 5 s busy timeout.
Pitfall: SQLite turns foreign keys OFF by default per connection, so cascade silently does
nothing unless the PRAGMA is set on every connection, not just once.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .config import settings

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrations() -> list[tuple[int, Path]]:
    found = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        m = re.match(r"(\d+)_", path.name)
        if m:
            found.append((int(m.group(1)), path))
    return found


def schema_version() -> int:
    with db() as conn:
        return conn.execute("PRAGMA user_version").fetchone()[0]


def migrate() -> int:
    """Apply pending migrations. Returns the resulting schema version."""
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path)
    try:
        current = conn.execute("PRAGMA user_version").fetchone()[0]
        # Table rebuilds drop referenced tables, so FKs must be off while migrating.
        conn.execute("PRAGMA foreign_keys=OFF")
        for version, path in migrations():
            if version <= current:
                continue
            conn.executescript("BEGIN;" + path.read_text(encoding="utf-8") + f";PRAGMA user_version={version};COMMIT;")
            current = version
        return current
    finally:
        conn.close()


def insert(conn: sqlite3.Connection, table: str, row: dict) -> None:
    """Named-column insert (A12). Table and column names come from code, never from users."""
    cols = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", tuple(row.values()))


def update(conn: sqlite3.Connection, table: str, key: dict, fields: dict, allowed: set[str]) -> int:
    """Whitelist-based UPDATE (A12): refuses any column not in `allowed`."""
    bad = set(fields) - allowed
    if bad:
        raise ValueError(f"not updatable: {sorted(bad)}")
    if not fields:
        return 0
    sets = ", ".join(f"{k} = ?" for k in fields)
    where = " AND ".join(f"{k} = ?" for k in key)
    cur = conn.execute(f"UPDATE {table} SET {sets} WHERE {where}", (*fields.values(), *key.values()))
    return cur.rowcount


def get_setting(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value)
    )
