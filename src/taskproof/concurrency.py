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

Design note
-----------
One `acquire()` writes exactly one row, scoped `group:<name>`. That single row
is *both* the group mutex and the global slot: the same-group check reads it as
`group:<name>`, while the global cap counts every live non-`global` row. The
`global` scope is reserved as a sentinel (never counted, never inserted by
`acquire`) so an operator can pin the global dimension without perturbing the
per-group accounting.
"""

import os
import socket
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import NamedTuple, Optional

from .errors import ConcurrencyError
from .storage import now_iso

GLOBAL_SCOPE = "global"

# A claim is live while `expires_at` is strictly in the future. `julianday()`
# parses the ISO-8601 +offset strings produced by `now_iso`/`_iso_after` and
# normalises them to UTC, so comparison never depends on the string offset.
_ACTIVE = "julianday(expires_at) > julianday('now')"
_EXPIRED = "julianday(expires_at) <= julianday('now')"


# ---------------------------------------------------------------------------
# The effective global cap: a value *and* where it came from (card 42).
# ---------------------------------------------------------------------------
#
# The cap has three possible sources, in precedence order:
#
#   1. ``cli``   — a one-off ``run --cap N`` for this dispatch only, never
#                  persisted;
#   2. ``toml``  — ``[defaults] concurrency`` in the workspace registry;
#   3. ``auto``  — the machine fallback below, used when the registry sets
#                  nothing. It is NEVER written back (Q3): a fresh workspace
#                  carries no ``concurrency`` key and the number an operator
#                  sees comes from the hardware that actually runs the tasks.
#
# Whatever the source, every surface (doctor, ``config --show``, a refusal, the
# read-only API) shows the *value plus source*, never a bare number.

SOURCE_AUTO = "auto"
SOURCE_TOML = "toml"
SOURCE_CLI = "cli"

# The fallback is deliberately conservative. A slot is a whole extra coding
# agent, so on a box a human is also using we want a handful of lanes, not one
# per core:
#
#     cap = clamp(2, cores // 4, 6)     # at most one slot per four cores
#     if RAM < 8 GiB: cap = 2           # a small box cannot afford cores / 4
#     if the core count is unknown: cap = 3   # the historic default, not a guess
#
# The floor keeps at least two lanes; the ceiling keeps a many-core box from
# melting under a full house of agents.
_AUTO_FLOOR = 2
_AUTO_CEIL = 6
_CORES_PER_SLOT = 4
_AUTO_UNKNOWN_CORES = 3
_MIN_MEMORY_BYTES = 8 * 1024 ** 3


class CapSetting(NamedTuple):
    """An effective global cap together with its provenance.

    ``source`` is one of :data:`SOURCE_CLI` / :data:`SOURCE_TOML` /
    :data:`SOURCE_AUTO`. ``detail`` is the short human gloss behind the source —
    ``"14 核 ÷ 4"`` for auto, ``"projects.toml"`` for toml, ``"--cap 5"`` for
    cli. ``as_dict`` is the wire shape the read-only API exposes (card 39
    consumes it verbatim).
    """

    value: int
    source: str
    detail: str

    def as_dict(self) -> dict:
        return {"value": self.value, "source": self.source, "detail": self.detail}


def _physical_memory_bytes() -> Optional[int]:
    """Physical RAM in bytes, or ``None`` when the platform will not say."""
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        pages = os.sysconf("SC_PHYS_PAGES")
    except (ValueError, OSError, AttributeError):
        return None
    if not isinstance(page_size, int) or not isinstance(pages, int):
        return None
    if page_size <= 0 or pages <= 0:
        return None
    return page_size * pages


def _auto_cap(cores, memory_bytes):
    """Pure: ``(logical cores, RAM bytes)`` -> ``(cap, detail)``.

    Split out of :func:`detect` so the arithmetic — and the "small memory -> 2"
    / "cores unknown -> 3" edges — can be exercised without reading the host.
    """
    if cores is None or cores < 1:
        return _AUTO_UNKNOWN_CORES, "核数不可用"
    if memory_bytes is not None and memory_bytes < _MIN_MEMORY_BYTES:
        return _AUTO_FLOOR, f"内存 {memory_bytes / 1024 ** 3:.0f} GB < 8 GB"
    value = min(max(cores // _CORES_PER_SLOT, _AUTO_FLOOR), _AUTO_CEIL)
    return value, f"{cores} 核 ÷ {_CORES_PER_SLOT}"


def detect() -> int:
    """The machine-derived fallback global cap for **this** box.

    Touches the hardware and nothing else — no file, no database, no write — so
    it is safe on a read-only path (``config --show``, ``doctor``, an API GET)
    and deterministic for a given machine.
    """
    return _auto_cap(os.cpu_count(), _physical_memory_bytes())[0]


def detect_detail() -> str:
    """The human gloss paired with :func:`detect` (e.g. ``"14 核 ÷ 4"``)."""
    return _auto_cap(os.cpu_count(), _physical_memory_bytes())[1]


def resolve(defaults, cap=None) -> CapSetting:
    """The effective global cap for one dispatch, with its source.

    ``cap`` (the CLI's ``--cap``) wins over ``[defaults] concurrency`` in
    ``defaults``, which wins over the machine fallback. ``defaults`` is the
    parsed registry ``[defaults]`` table, or ``None``.
    """
    if cap is not None:
        number = int(cap)
        return CapSetting(number, SOURCE_CLI, f"--cap {number}")
    configured = (defaults or {}).get("concurrency")
    if configured is not None:
        return CapSetting(int(configured), SOURCE_TOML, "projects.toml")
    return CapSetting(detect(), SOURCE_AUTO, detect_detail())


def source_label(setting: "CapSetting") -> str:
    """The phrase that follows ``来源：`` in a refusal (``自动探测 14 核 ÷ 4``)."""
    if setting.source == SOURCE_AUTO:
        return f"自动探测 {setting.detail}"
    if setting.source == SOURCE_CLI:
        return f"本次 {setting.detail}"
    return setting.detail


def source_gloss(setting: "CapSetting") -> str:
    """The phrase inside ``config --show``'s parentheses."""
    if setting.source == SOURCE_AUTO:
        return f"自动探测：{setting.detail}"
    return setting.detail


def group_scope(group: str) -> str:
    return f"group:{group}"


def _iso_after(seconds: int) -> str:
    return (datetime.now(timezone.utc).astimezone() + timedelta(seconds=seconds)).isoformat(
        timespec="seconds"
    )


def owner_token() -> str:
    """Identifies this process: `<host>:<pid>`."""
    return f"{socket.gethostname()}:{os.getpid()}"


class Lease(str):
    """A claimed scope, returned by :func:`acquire`.

    It *is* a ``str`` (so callers may keep treating the result as a list of
    scope names — ``group_scope(g) in scopes``), and it also carries the owner
    ``token``. That token is the proof of ownership :func:`release` checks: a
    bare ``str`` (e.g. ``group_scope("g1")`` built by hand) carries no token and
    is therefore never mistaken for a claim we hold.
    """

    def __new__(cls, scope: str, token: str) -> "Lease":
        obj = super().__new__(cls, scope)
        obj.token = token
        return obj


def reap_expired(conn: sqlite3.Connection) -> int:
    """Delete claims past `expires_at`. Returns how many were reclaimed.

    Runs before every acquire so a crashed run never blocks a group.
    """
    cur = conn.execute(f"DELETE FROM claims WHERE {_EXPIRED}")
    return max(0, cur.rowcount)


def count_active(conn: sqlite3.Connection) -> int:
    """Number of live (non-expired) claims, excluding the global sentinel."""
    row = conn.execute(
        f"SELECT COUNT(*) FROM claims WHERE scope != ? AND {_ACTIVE}",
        (GLOBAL_SCOPE,),
    ).fetchone()
    return int(row[0]) if row is not None else 0


def acquire(conn: sqlite3.Connection, task_id: str, group: str, *, cap: int, ttl: int):
    """Claim the group slot and a slot under the global cap.

    Must be atomic: two processes racing for the last global slot — exactly one
    wins. Use a single transaction (`BEGIN IMMEDIATE`) and re-check the count
    inside it.

    Raises ConcurrencyError (exit 75) when the group is busy or the cap is full.
    Returns the list of scopes claimed, so the caller can release exactly those.
    """
    scope = group_scope(group)
    token = owner_token()

    # `BEGIN IMMEDIATE` takes the write lock up front. Two racers cannot both
    # hold it: the second blocks (busy_timeout) until the first commits, then
    # re-reads the *committed* count below — so exactly one of them can pass the
    # cap check for the last slot. Nothing is ever queued; a loser raises.
    started = not conn.in_transaction
    if started:
        conn.execute("BEGIN IMMEDIATE")
    try:
        reap_expired(conn)  # a crashed run must not block the group
        held = conn.execute(
            "SELECT task_id FROM claims WHERE scope = ?", (scope,)
        ).fetchone()
        if held is not None:
            raise ConcurrencyError(
                describe_blocker(conn, group),
                hint="another task holds this group; retry once it finishes",
            )
        if count_active(conn) >= cap:
            raise ConcurrencyError(
                describe_blocker(conn, group),
                hint=f"global cap of {cap} reached; retry once a slot frees",
            )
        conn.execute(
            "INSERT INTO claims (scope, task_id, pid, claimed_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (scope, task_id, os.getpid(), now_iso(), _iso_after(ttl)),
        )
    except BaseException:
        if started:
            conn.execute("ROLLBACK")
        raise
    if started:
        conn.execute("COMMIT")
    return [Lease(scope, token)]


def _iter_leases(scopes):
    """Yield ``(scope, token)`` pairs from whatever the caller handed us.

    Accepts a single item or an iterable; each item may be a :class:`Lease`
    (carries a token), a bare ``str`` (token is ``None`` — unverifiable, so it
    will never release anything), a ``(scope, token)`` pair, or a mapping.
    """
    if scopes is None:
        return
    if isinstance(scopes, (Lease, str, dict)):
        items = [scopes]
    else:
        try:
            items = list(scopes)
        except TypeError:
            return
    for item in items:
        if isinstance(item, Lease):
            yield str(item), item.token
        elif isinstance(item, str):
            yield item, None
        elif isinstance(item, dict):
            yield item.get("scope"), item.get("token")
        elif isinstance(item, (tuple, list)) and len(item) == 2:
            yield item[0], item[1]


def release(conn: sqlite3.Connection, scopes) -> None:
    """Release the given scopes. Safe to call twice; never releases another
    process's claim (compare `pid`/token before deleting)."""
    mine = owner_token()
    pid = os.getpid()
    for scope, token in _iter_leases(scopes):
        if not scope or token != mine:
            # No proof of ownership (or a token minted by another process):
            # leave the claim alone. A hand-built bare scope never gets here.
            continue
        row = conn.execute("SELECT pid FROM claims WHERE scope = ?", (scope,)).fetchone()
        if row is None or row[0] != pid:
            continue
        conn.execute("DELETE FROM claims WHERE scope = ?", (scope,))


def describe_blocker(conn: sqlite3.Connection, group: str) -> str:
    """Human-readable reason a dispatch would be refused (for the error hint)."""
    row = conn.execute(
        "SELECT task_id, pid, claimed_at FROM claims "
        f"WHERE scope = ? AND {_ACTIVE}",
        (group_scope(group),),
    ).fetchone()
    if row is not None:
        # index-based: works whether or not the connection has a Row factory.
        return (
            f"group '{group}' is busy: task {row[0]} "
            f"(pid {row[1]}) has held it since {row[2]}"
        )
    return f"global cap reached: {count_active(conn)} task(s) already running"
