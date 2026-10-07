"""SQLite state store.

Contract
--------
* `connect()` returns a connection with `Row` factory, WAL, foreign keys on.
* All timestamps are ISO-8601 strings with a local UTC offset (see `now_iso`).
* Concurrency correctness lives in `concurrency.py`; this module only owns the
  schema, connections and simple CRUD.
* Migrations are append-only: add a new file under `sql/` and extend `migrate()`.
"""

import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from .errors import TaskproofError

SCHEMA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sql")

DEFAULT_DB_NAME = "taskproof.db"


def now_iso() -> str:
    """Current time, ISO-8601 with the local offset (matches the old ledger format)."""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def db_path(workspace: str) -> str:
    return os.path.join(workspace, DEFAULT_DB_NAME)


def connect(path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    """Apply `sql/schema.sql` (idempotent — every statement is IF NOT EXISTS)."""
    with open(os.path.join(SCHEMA_DIR, "schema.sql"), encoding="utf-8") as fh:
        conn.executescript(fh.read())
    row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
    if row is None or row["v"] is None:
        conn.execute(
            "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
            (1, now_iso()),
        )


# --------------------------------------------------------------------------
# Implementation cards fill the bodies below. Signatures and semantics are the
# contract; raise NotImplementedError until then.
# --------------------------------------------------------------------------


def insert_task(conn: sqlite3.Connection, task) -> None:
    """Insert a new task row (status queued). Raises on duplicate id."""
    raise NotImplementedError("card: storage-crud")


def update_task(conn: sqlite3.Connection, task_id: str, **fields) -> None:
    """Patch the given columns of one task. Unknown field names are a bug."""
    raise NotImplementedError("card: storage-crud")


def get_task(conn: sqlite3.Connection, task_id: str) -> Optional[sqlite3.Row]:
    raise NotImplementedError("card: storage-crud")


def list_tasks(conn, *, status=None, project=None, limit=50):
    """Most recent first. `status` may be a single value or an iterable."""
    raise NotImplementedError("card: storage-crud")


def next_task_id(conn: sqlite3.Connection, *, prefix_date: str) -> str:
    """Allocate `t-<yyyymmdd>-<nnn>`; must be safe under concurrent dispatch."""
    raise NotImplementedError("card: storage-crud")


def append_event(conn: sqlite3.Connection, task_id: Optional[str], event: str, payload=None) -> None:
    """Append to BOTH the `events` table and the JSONL audit stream (see ledger.py)."""
    raise NotImplementedError("card: storage-crud")


def list_events(conn: sqlite3.Connection, task_id: str):
    raise NotImplementedError("card: storage-crud")
