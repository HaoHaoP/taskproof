"""The resident queue daemon behind ``taskproof queue``.

Design (control-plane.md, section 3)
------------------------------------
A parked (``queued``) task is only a row: parking takes no slot and spawns no
process. This module is the *推进者* (the pusher): it watches the ``tasks`` table
and, on every tick, advances the current wave.

*Wave = queue_seq.* Tasks that share a ``queue_seq`` are one wave and are
launched together; a wave only advances once every lower-numbered wave has fully
drained (no member is still queued / running / verifying). Within a wave, cards
are tried oldest first (``created_at`` ASC).

"Together" is not "simultaneously". The physical layer is still
``concurrency.acquire`` (per-group mutex + global cap): two same-group cards in
one wave do not both run — one takes the group, the other is refused (exit 75)
and *stays queued* for a later tick, while two different groups really do run in
parallel. The daemon retries the refused card on the next tick; it never
sleep-holds a slot.

Single process, interruptible: each launch runs in a worker thread (so a wave's
different-group members overlap), the main thread only schedules. SIGINT/SIGTERM
stop the loop, terminate the in-flight adapter groups, join the workers (whose
``finally`` releases their claims) and finally drop any claim still stamped with
this pid — so a stopped queue never leaves a claim behind.

Standard library only.
"""

import os
import signal
import threading
import time

from . import concurrency, dispatch, storage
from .errors import ConcurrencyError, TaskproofError
from .models import STATUS_QUEUED, STATUS_RUNNING, STATUS_VERIFYING

#: Seconds between ticks. v1 keeps this a plain constant on purpose — the tick
#: interval is deliberately NOT a registry or CLI setting.
TICK_SECONDS = 1.0

#: Statuses that still hold the queue cursor on their wave. A wave is "drained"
#: only once none of its members is in one of these.
_LIVE_STATUSES = (STATUS_QUEUED, STATUS_RUNNING, STATUS_VERIFYING)

#: How long `_shutdown` waits for an in-flight attempt to unwind after its
#: adapter group has been signalled.
_SHUTDOWN_GRACE_SECONDS = 10.0


def _wave_key(seq):
    """Order key for a ``queue_seq``: numbered waves first, the NULL wave last.

    A card parked without a seq (the API permits it) is its own wave, sorted
    after every explicitly numbered one so ``seq=1,2,3`` keep their order.
    """
    return (seq is None, seq if seq is not None else 0)


def select_wave(conn):
    """The current wave's still-queued task ids, oldest first.

    "Current" is the smallest ``queue_seq`` among *every* non-terminal task
    (queued, running or verifying). Because running/verifying members keep the
    cursor on their wave, a higher-numbered wave is never touched until every
    lower one has fully drained. Returns ``[]`` when nothing is queued.
    """
    placeholders = ", ".join("?" for _ in _LIVE_STATUSES)
    rows = conn.execute(
        f"SELECT id, status, queue_seq, created_at FROM tasks "
        f"WHERE status IN ({placeholders})",
        _LIVE_STATUSES,
    ).fetchall()
    if not rows:
        return []
    active = min(_wave_key(row["queue_seq"]) for row in rows)
    queued = [
        row
        for row in rows
        if row["status"] == STATUS_QUEUED and _wave_key(row["queue_seq"]) == active
    ]
    queued.sort(key=lambda row: (row["created_at"] or "", row["id"]))
    return [row["id"] for row in queued]


class QueueDaemon:
    """One resident process that advances the queue until stopped."""

    def __init__(self, workspace: str, *, tick_seconds: float = TICK_SECONDS):
        self.workspace = workspace
        self.tick_seconds = tick_seconds
        self._stop = threading.Event()
        self._lock = threading.Lock()
        #: task_id -> live worker Thread for attempts this daemon has launched.
        self._inflight: dict = {}
        self._handlers_installed = False

    # -- scheduling --------------------------------------------------------

    def tick(self) -> int:
        """One pass: launch the current wave's not-yet-running members.

        Returns how many attempts were started. A member already in flight is
        skipped so it is never double-launched; a refusal (exit 75) is
        discovered inside its own worker and does not block the rest of the wave.
        """
        dispatch.prepare_workspace(self.workspace)
        conn = storage.connect(storage.db_path(self.workspace))
        try:
            storage.migrate(conn)
            ids = select_wave(conn)
        finally:
            conn.close()

        started = 0
        for task_id in ids:
            if self._launch(task_id):
                started += 1
        return started

    def _launch(self, task_id: str) -> bool:
        with self._lock:
            live = self._inflight.get(task_id)
            if live is not None and live.is_alive():
                return False
            worker = threading.Thread(
                target=self._attempt,
                args=(task_id,),
                name=f"taskproof-queue-{task_id}",
                daemon=True,
            )
            self._inflight[task_id] = worker
        worker.start()
        return True

    def _attempt(self, task_id: str) -> None:
        try:
            dispatch.run_queued(self.workspace, task_id)
        except ConcurrencyError:
            # The group or the global cap refused us. The row is untouched — it
            # is still queued and the next tick retries it. This IS the rule
            # "the queue retries; the run never waits".
            pass
        except TaskproofError:
            # Already recorded terminal by `run_queued` (adapter / verify
            # failure), or the row changed state under us. Nothing left to do.
            pass
        finally:
            with self._lock:
                self._inflight.pop(task_id, None)

    # -- lifecycle ---------------------------------------------------------

    def install_signal_handlers(self) -> None:
        """Route SIGINT/SIGTERM to a clean stop (called from the main thread)."""
        signal.signal(signal.SIGTERM, self._on_signal)
        signal.signal(signal.SIGINT, self._on_signal)
        self._handlers_installed = True

    def _on_signal(self, _signum, _frame) -> None:
        self._stop.set()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> int:
        """Block, ticking until stopped, then shut down cleanly. Returns 0."""
        if not self._handlers_installed:
            try:
                self.install_signal_handlers()
            except ValueError:
                # Not on the main thread (e.g. an embedding process): keep the
                # stop() seam and let the caller drive us.
                self._handlers_installed = True
        try:
            while not self._stop.is_set():
                self.tick()
                self._stop.wait(self.tick_seconds)
        except KeyboardInterrupt:
            self._stop.set()
        finally:
            self._shutdown()
        return 0

    def _shutdown(self) -> None:
        """Stop every in-flight attempt and make sure no claim survives us.

        However the stop arrived, the queue must leave the workspace
        consistent: signal the adapter groups it can see, wait for the workers to
        unwind (their ``finally`` releases the slot), then as a last resort
        delete any claim still stamped with this pid.
        """
        deadline = time.monotonic() + _SHUTDOWN_GRACE_SECONDS
        while True:
            with self._lock:
                workers = [w for w in self._inflight.values() if w.is_alive()]
            if not workers:
                break
            for pgid in self._running_pgids():
                dispatch._terminate_recorded_group(pgid)
            if time.monotonic() >= deadline:
                break
            time.sleep(0.1)
        with self._lock:
            workers = list(self._inflight.values())
        for worker in workers:
            worker.join(timeout=1.0)
        self._release_own_claims()

    def _running_pgids(self):
        """pgids of the running rows this process is responsible for."""
        conn = storage.connect(storage.db_path(self.workspace))
        try:
            storage.migrate(conn)
            rows = conn.execute(
                "SELECT pgid FROM tasks WHERE status = ? AND pid = ?",
                (STATUS_RUNNING, os.getpid()),
            ).fetchall()
            return [row[0] for row in rows if row[0] is not None]
        finally:
            conn.close()

    def _release_own_claims(self) -> None:
        """Delete every claim this pid still owns (never another process's).

        ``acquire`` stamps ``pid = os.getpid()``, so this only ever removes the
        queue's own rows — a sibling `taskproof run` keeps its slot.
        """
        conn = storage.connect(storage.db_path(self.workspace))
        try:
            storage.migrate(conn)
            conn.execute("DELETE FROM claims WHERE pid = ?", (os.getpid(),))
        finally:
            conn.close()


def run_forever(workspace: str, *, tick_seconds: float = TICK_SECONDS) -> int:
    """Run the resident queue daemon for ``workspace`` (blocks)."""
    return QueueDaemon(workspace, tick_seconds=tick_seconds).run()
