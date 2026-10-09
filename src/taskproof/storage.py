"""SQLite state store.

Contract
--------
* `connect()` returns a connection with `Row` factory, WAL, foreign keys on.
* All timestamps are ISO-8601 strings with a local UTC offset (see `now_iso`).
* Concurrency correctness lives in `concurrency.py`; this module only owns the
  schema, connections and simple CRUD.
* Migrations are append-only: add a new file under `sql/` and extend `migrate()`.
"""

import json
import os
import sqlite3
import time
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


#: Schema level this build writes. Bump it whenever `migrate()` learns a new
#: step that `schema.sql` alone cannot perform on an existing database.
SCHEMA_VERSION = 2

#: Columns added after v1. `schema.sql` is all ``CREATE TABLE IF NOT EXISTS``,
#: so it can never add a column to a table that already exists — these are the
#: PRAGMA-probed ``ALTER TABLE`` steps that upgrade a pre-existing workspace.
#: (table, column, declared type); identifiers are module constants, never user
#: input, so the f-string below is safe.
_ADDED_COLUMNS = (
    ("tasks", "pgid", "INTEGER"),
    ("tasks", "queue_seq", "INTEGER"),
)


def _table_columns(conn: sqlite3.Connection, table: str) -> set:
    """Column names of `table` (empty set when the table does not exist)."""
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def migrate(conn: sqlite3.Connection) -> None:
    """Bring `conn`'s database up to the current schema (idempotent).

    `schema.sql` builds a fresh database in full; the probes below are what
    upgrade a database created before `pgid`/`queue_seq` existed. Both halves are
    safe to run any number of times, and every step either applies cleanly or is
    skipped because it is already present.
    """
    with open(os.path.join(SCHEMA_DIR, "schema.sql"), encoding="utf-8") as fh:
        conn.executescript(fh.read())

    for table, column, column_type in _ADDED_COLUMNS:
        if column not in _table_columns(conn, table):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")

    row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
    current = (row[0] if row is not None else None) or 0
    if current < 1:
        conn.execute(
            "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
            (1, now_iso()),
        )
    if current < SCHEMA_VERSION:
        # PRIMARY KEY on `version` makes the recording itself idempotent.
        conn.execute(
            "INSERT OR IGNORE INTO schema_version (version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION, now_iso()),
        )


# --------------------------------------------------------------------------
# Implementation cards fill the bodies below. Signatures and semantics are the
# contract; raise NotImplementedError until then.
# --------------------------------------------------------------------------

# Every column of the `tasks` table. This is the whitelist for the dynamically
# built SET-clause in `update_task` — caller-supplied keys are validated against
# it before they ever reach a SQL string.
TASK_COLUMNS = frozenset(
    {
        "id",
        "project",
        "group_name",
        "brief",
        "status",
        "adapter",
        "model",
        "reasoning",
        "attempt",
        "exit_code",
        "pid",
        "pgid",
        "queue_seq",
        "workdir",
        "result_path",
        "verify_cmd",
        "verify_exit",
        "files_changed",
        "created_at",
        "started_at",
        "finished_at",
    }
)


def _row_dict(task) -> dict:
    """Normalise a Task dataclass / mapping / sqlite3.Row into a plain dict."""
    if isinstance(task, dict):
        return dict(task)
    if isinstance(task, sqlite3.Row):
        return dict(task)
    if hasattr(task, "to_row"):
        return dict(task.to_row())
    return dict(vars(task))


def insert_task(conn: sqlite3.Connection, task) -> None:
    """Insert a new task row (status queued). Raises on duplicate id."""
    row = _row_dict(task)
    # The model calls the column `group`; the table calls it `group_name`.
    if "group" in row and "group_name" not in row:
        row["group_name"] = row.pop("group")
    if not row.get("status"):
        row["status"] = "queued"
    if not row.get("created_at"):
        row["created_at"] = now_iso()

    cols = [c for c in row if c in TASK_COLUMNS]
    if not cols:
        raise TaskproofError("insert_task: no insertable columns in row")
    placeholders = ", ".join("?" for _ in cols)
    conn.execute(
        f"INSERT INTO tasks ({', '.join(cols)}) VALUES ({placeholders})",
        [row[c] for c in cols],
    )


def update_task(conn: sqlite3.Connection, task_id: str, **fields) -> None:
    """Patch the given columns of one task. Unknown field names are a bug."""
    if not fields:
        return
    unknown = sorted(set(fields) - TASK_COLUMNS)
    if unknown:
        # Defence in depth: validate every key against the whitelist BEFORE it is
        # interpolated into the statement. `fields.values()` always travel as
        # bound parameters; only whitelisted identifiers are concatenated.
        raise TaskproofError(
            f"unknown task column(s): {', '.join(unknown)}",
            hint=f"allowed columns: {', '.join(sorted(TASK_COLUMNS))}",
        )
    assignments = ", ".join(f"{name} = ?" for name in fields)
    params = list(fields.values())
    params.append(task_id)
    conn.execute(f"UPDATE tasks SET {assignments} WHERE id = ?", params)


def get_task(conn: sqlite3.Connection, task_id: str) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()


def delete_task(conn: sqlite3.Connection, task_id: str) -> None:
    """Delete one task row AND its `events` rows.

    The JSONL audit stream (`events-<month>.jsonl`) is append-only history and
    is deliberately NOT touched: it is never read for logic, so leaving it
    behind keeps the audit trail intact while removing the queryable record.
    """
    conn.execute("DELETE FROM events WHERE task_id = ?", (task_id,))
    conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))


def list_tasks(conn, *, status=None, project=None, limit=50):
    """Most recent first. `status` may be a single value or an iterable."""
    clauses = []
    params = []
    if status is not None:
        statuses = [status] if isinstance(status, str) else list(status)
        if not statuses:
            return []
        placeholders = ", ".join("?" for _ in statuses)
        clauses.append(f"status IN ({placeholders})")
        params.extend(statuses)
    if project is not None:
        clauses.append("project = ?")
        params.append(project)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    return conn.execute(
        f"SELECT * FROM tasks{where} ORDER BY created_at DESC LIMIT ?", params
    ).fetchall()


#: Statuses that count as "in progress" in the project overview. These are the
#: non-terminal states: a queued task is still work the user is waiting on.
IN_PROGRESS_STATUSES = ("queued", "running", "verifying")


def project_overview(conn: sqlite3.Connection):
    """Per-project task counts — the whole overview in ONE SQL statement.

    Returns a list of dicts with ``project``, ``total``, ``in_progress``,
    ``failed`` and ``last_activity`` (the newest ``created_at`` for the
    project, or ``None`` when it has no tasks). Ordered by most recent activity
    first; projects that never ran a task sort last.
    """
    placeholders = ", ".join("?" for _ in IN_PROGRESS_STATUSES)
    rows = conn.execute(
        "SELECT project, "
        "COUNT(*) AS total, "
        f"SUM(CASE WHEN status IN ({placeholders}) THEN 1 ELSE 0 END) AS in_progress, "
        "SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) AS failed, "
        "MAX(created_at) AS last_activity "
        "FROM tasks GROUP BY project "
        "ORDER BY last_activity IS NULL, last_activity DESC, project ASC",
        (*IN_PROGRESS_STATUSES, "failed"),
    ).fetchall()
    return [dict(row) for row in rows]


def group_tasks_by_project(tasks):
    """Group task mappings by project: newest-active block first.

    Shared by the CLI and the board so the two surfaces order groups
    identically. Groups are ordered by the most recent ``created_at`` inside
    each group (desc); tasks within a group are returned newest-first too.
    """
    groups: dict = {}
    for task in tasks:
        groups.setdefault(task.get("project") or "", []).append(task)
    ordered = sorted(
        groups.items(),
        key=lambda item: max((t.get("created_at") or "") for t in item[1]),
        reverse=True,
    )
    return [
        (pid, sorted(items, key=lambda t: t.get("created_at") or "", reverse=True))
        for pid, items in ordered
    ]


def next_task_id(conn: sqlite3.Connection, *, prefix_date: str) -> str:
    """Allocate `t-<yyyymmdd>-<nnn>`; must be safe under concurrent dispatch.

    Concurrency is guaranteed by the `meta` table, not by a read-then-write
    race: the counter row is read and bumped inside a single `BEGIN IMMEDIATE`
    transaction, so two processes can never both observe the same value. The
    `meta.key` PRIMARY KEY is the unique constraint that backs the sequence,
    and the retry loop re-attempts on the (theoretical) conflict instead of
    trusting a stale read. Existing `tasks.id` values for the day are also
    folded in, so out-of-band inserts can never be handed out twice.
    """
    prefix = f"t-{prefix_date}-"
    key = f"task_seq:{prefix_date}"
    while True:
        try:
            conn.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError:
            # Locked; busy_timeout usually hides this, but retry if it slips.
            time.sleep(0.01)
            continue
        try:
            seq = 0
            row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
            if row is not None and row[0] is not None:
                try:
                    seq = int(row[0])
                except (TypeError, ValueError):
                    seq = 0
            for existing in conn.execute(
                "SELECT id FROM tasks WHERE id LIKE ?", (prefix + "%",)
            ):
                tail = existing[0][len(prefix):]
                if tail.isdigit():
                    seq = max(seq, int(tail))
            seq += 1
            conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, str(seq)),
            )
            conn.execute("COMMIT")
            return f"{prefix}{seq:03d}"
        except sqlite3.IntegrityError:
            # Lost the race for the meta row — roll back and re-read.
            conn.execute("ROLLBACK")
            time.sleep(0.01)
            continue
        except BaseException:
            conn.execute("ROLLBACK")
            raise


def _audit_dir(conn: sqlite3.Connection) -> str:
    """The workspace directory that holds both the db file and the audit stream.

    `connect()` puts the database at `<workspace>/taskproof.db`, and ledger.py
    writes `<workspace>/events-<month>.jsonl`, so the audit dir is simply the
    directory containing the database file.
    """
    try:
        rows = conn.execute("PRAGMA database_list").fetchall()
    except sqlite3.Error:
        return ""
    for row in rows:
        # columns: seq, name, file
        if row[1] == "main":
            return os.path.dirname(os.path.abspath(row[2])) if row[2] else ""
    return ""


def append_event(conn: sqlite3.Connection, task_id: Optional[str], event: str, payload=None) -> None:
    """Append to BOTH the `events` table and the JSONL audit stream (see ledger.py).

    One timestamp and one record dict are built and used for both sinks, so the
    two entries are byte-for-byte the same content. The database insert runs in
    an explicit transaction that is committed only after the JSONL line is on
    disk: if the audit write fails, the row is rolled back, so the query surface
    never disagrees with the audit trail (the JSONL stream is append-only and is
    never read for logic, so a stray line is harmless whereas a missing one is
    not).
    """
    from . import ledger  # local import: ledger imports now_iso from this module

    ts = now_iso()
    payload_text = json.dumps(payload, ensure_ascii=False) if payload is not None else None
    record = {"ts": ts, "task_id": task_id, "event": event, "payload": payload}
    audit_dir = _audit_dir(conn)

    already_in_txn = conn.in_transaction
    if not already_in_txn:
        conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "INSERT INTO events (task_id, ts, event, payload) VALUES (?, ?, ?, ?)",
            (task_id, ts, event, payload_text),
        )
        ledger.append(audit_dir, record)
    except BaseException:
        if not already_in_txn:
            conn.execute("ROLLBACK")
        raise
    if not already_in_txn:
        conn.execute("COMMIT")


def list_events(conn: sqlite3.Connection, task_id: str):
    return conn.execute(
        "SELECT * FROM events WHERE task_id = ? ORDER BY id ASC", (task_id,)
    ).fetchall()
