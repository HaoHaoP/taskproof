-- taskproof schema, v1.
--
-- Configuration lives in a YAML registry (human editable).
-- Only RUNTIME STATE lives here.
--
-- The audit stream (events.jsonl) is written alongside these tables but is
-- never read for logic — queries go to this database.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id            TEXT PRIMARY KEY,
    project       TEXT NOT NULL,
    group_name    TEXT NOT NULL DEFAULT 'default',
    brief         TEXT NOT NULL,
    status        TEXT NOT NULL,
    adapter       TEXT NOT NULL DEFAULT 'codex',
    model         TEXT,
    reasoning     TEXT,
    attempt       INTEGER NOT NULL DEFAULT 1,
    exit_code     INTEGER,
    pid           INTEGER,
    workdir       TEXT,
    result_path   TEXT,
    verify_cmd    TEXT,
    verify_exit   INTEGER,
    files_changed INTEGER,
    created_at    TEXT NOT NULL,
    started_at    TEXT,
    finished_at   TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_status  ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at DESC);

-- Audit mirror of events.jsonl. Append-only.
CREATE TABLE IF NOT EXISTS events (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id  TEXT,
    ts       TEXT NOT NULL,
    event    TEXT NOT NULL,
    payload  TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id, id);
CREATE INDEX IF NOT EXISTS idx_events_ts   ON events(ts DESC);

-- Concurrency guard. Replaces lock files: a crashed process is reclaimed by
-- expiry rather than leaving a stale lock behind.
CREATE TABLE IF NOT EXISTS claims (
    scope      TEXT PRIMARY KEY,
    task_id    TEXT NOT NULL,
    pid        INTEGER,
    claimed_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
