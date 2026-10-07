"""Concurrency guard backed by the SQLite `claims` table.

Why not lock files
------------------
The predecessor used `<tmp>/<group>.lock`. When a process died mid-run the lock
survived and the group stalled until someone deleted it by hand. Here a claim
carries `expires_at`; an expired claim is reclaimed automatically.

Two dimensions, both enforced:
  * same-group serialisation  — scope `group:<name>`
  * global cap                — scope `global`, plus a live-claim count

A claim is only ever held by the process that created it, and only that process
may release it.
"""

import os
import socket
import sqlite3
from datetime import datetime, timedelta, timezone

from .errors import ConcurrencyError
from .storage import now_iso

GLOBAL_SCOPE = "global"


def group_scope(group: str) -> str:
    return f"group:{group}"


def _iso_after(seconds: int) -> str:
    return (datetime.now(timezone.utc).astimezone() + timedelta(seconds=seconds)).isoformat(
        timespec="seconds"
    )


def owner_token() -> str:
    """Identifies this process: `<host>:<pid>`."""
    return f"{socket.gethostname()}:{os.getpid()}"


def reap_expired(conn: sqlite3.Connection) -> int:
    """Delete claims past `expires_at`. Returns how many were reclaimed.

    Runs before every acquire so a crashed run never blocks a group.
    """
    raise NotImplementedError("card: concurrency")


def count_active(conn: sqlite3.Connection) -> int:
    """Number of live (non-expired) claims, excluding the global sentinel."""
    raise NotImplementedError("card: concurrency")


def acquire(conn: sqlite3.Connection, task_id: str, group: str, *, cap: int, ttl: int):
    """Claim the group slot and a slot under the global cap.

    Must be atomic: two processes racing for the last global slot — exactly one
    wins. Use a single transaction (`BEGIN IMMEDIATE`) and re-check the count
    inside it.

    Raises ConcurrencyError (exit 75) when the group is busy or the cap is full.
    Returns the list of scopes claimed, so the caller can release exactly those.
    """
    raise NotImplementedError("card: concurrency")


def release(conn: sqlite3.Connection, scopes) -> None:
    """Release the given scopes. Safe to call twice; never releases another
    process's claim (compare `pid`/token before deleting)."""
    raise NotImplementedError("card: concurrency")


def describe_blocker(conn: sqlite3.Connection, group: str) -> str:
    """Human-readable reason a dispatch would be refused (for the error hint)."""
    raise NotImplementedError("card: concurrency")
