"""The resident queue (`taskproof queue`): wave selection + advance semantics.

Everything here runs the real pipeline in a throwaway workspace with harmless
``custom:`` adapters. No real agent is invoked and nothing reaches the network.

Covered:
  * wave = queue_seq; only the lowest wave is selected, oldest card first
  * a running/verifying member keeps the cursor on its wave
  * same wave + different group -> both run (parallel)
  * same wave + same group  -> one runs, the other stays queued and is retried
  * global cap full         -> refused card stays queued (role still there)
  * a parked row is advanced by id: the SAME row runs, no new id
  * a `blocked` (boundary breach) card is terminal: the queue never advances it
  * the queue daemon stops cleanly on SIGTERM and leaves no concurrency claim
  * a stopped queue's leftover queued rows are resumed by a restart
"""

import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from taskproof import concurrency, dispatch, queue, storage
from taskproof.errors import ConcurrencyError, VerifyError
from taskproof.models import (
    STATUS_BLOCKED,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    TERMINAL_STATUSES,
)

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _env():
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(_REPO, "src")
    return env


def _q(value) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def registry_toml(path, projects, *, cap=3, timeout=120) -> str:
    """A registry with one [[project]] per ``(id, group)`` in ``projects``."""
    lines = ["[defaults]", f"concurrency = {cap}", f"timeout = {timeout}", ""]
    for pid, group in projects:
        lines += [
            "[[project]]",
            f"id = {_q(pid)}",
            f"path = {_q(path)}",
            f"group = {_q(group)}",
            'verify = "exit 0"',
            'verify_kind = "check"',
            "",
        ]
    return "\n".join(lines) + "\n"


class _WorkspaceCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.ws = os.path.join(self.tmp, "workspace")
        self.proj = os.path.join(self.tmp, "project")
        os.makedirs(self.proj)
        dispatch.prepare_workspace(self.ws)

    def tearDown(self):
        self._tmp.cleanup()

    def write_registry(self, projects, **kwargs):
        with open(
            os.path.join(self.ws, "projects.toml"), "w", encoding="utf-8"
        ) as fh:
            fh.write(registry_toml(self.proj, projects, **kwargs))

    def open_conn(self):
        conn = storage.connect(storage.db_path(self.ws))
        storage.migrate(conn)
        return conn

    def park(self, project, brief, *, queue_seq=None, adapter="custom:echo hi", **kw):
        return dispatch.dispatch(
            self.ws, project, brief, adapter=adapter, start=False,
            queue_seq=queue_seq, **kw,
        )

    def status(self, task_id):
        conn = self.open_conn()
        try:
            return storage.get_task(conn, task_id)["status"]
        finally:
            conn.close()

    def row(self, task_id):
        conn = self.open_conn()
        try:
            return dict(storage.get_task(conn, task_id))
        finally:
            conn.close()

    def count_tasks(self):
        conn = self.open_conn()
        try:
            return conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        finally:
            conn.close()

    def active_claims(self):
        conn = self.open_conn()
        try:
            return concurrency.count_active(conn)
        finally:
            conn.close()

    def wait_for(self, predicate, *, timeout=20.0, step=0.05, message="condition"):
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            last = predicate()
            if last:
                return last
            time.sleep(step)
        self.fail(f"timed out waiting for {message}; last={last!r}")


# ---------------------------------------------------------------------------
# Wave selection
# ---------------------------------------------------------------------------


class WaveSelectionTest(_WorkspaceCase):
    def setUp(self):
        super().setUp()
        self.write_registry([("p", "g")])

    def test_only_the_lowest_wave_is_selected(self):
        first = self.park("p", "one", queue_seq=1)
        second = self.park("p", "two", queue_seq=2)
        third = self.park("p", "three", queue_seq=9)

        conn = self.open_conn()
        try:
            self.assertEqual(queue.select_wave(conn), [first])
        finally:
            conn.close()
        # The higher waves are untouched (still queued) while wave 1 exists.
        self.assertEqual(self.status(second), STATUS_QUEUED)
        self.assertEqual(self.status(third), STATUS_QUEUED)

    def test_same_wave_is_oldest_first(self):
        a = self.park("p", "a", queue_seq=7)
        b = self.park("p", "b", queue_seq=7)
        c = self.park("p", "c", queue_seq=7)
        conn = self.open_conn()
        try:
            self.assertEqual(queue.select_wave(conn), [a, b, c])
        finally:
            conn.close()

    def test_next_wave_selected_after_lower_drains(self):
        first = self.park("p", "one", queue_seq=1, adapter="custom:echo hi")
        second = self.park("p", "two", queue_seq=2)
        dispatch.run_queued(self.ws, first)
        self.assertEqual(self.status(first), STATUS_DONE)

        conn = self.open_conn()
        try:
            self.assertEqual(queue.select_wave(conn), [second])
        finally:
            conn.close()

    def test_running_member_holds_the_cursor(self):
        slow = self.park("p", "slow", queue_seq=1,
                         adapter="custom:sh -c 'sleep 1.5; echo done'")
        later = self.park("p", "later", queue_seq=2)

        worker = threading.Thread(target=dispatch.run_queued, args=(self.ws, slow))
        worker.start()
        try:
            self.wait_for(lambda: self.status(slow) == STATUS_RUNNING,
                          message="wave-1 card running")
            conn = self.open_conn()
            try:
                # Wave 1 is in flight, wave 2 is queued: nothing to launch.
                self.assertEqual(queue.select_wave(conn), [])
            finally:
                conn.close()
        finally:
            worker.join(timeout=30)
        self.assertEqual(self.status(slow), STATUS_DONE)

        conn = self.open_conn()
        try:
            self.assertEqual(queue.select_wave(conn), [later])
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# run_queued: the "advance an existing row" entry
# ---------------------------------------------------------------------------


class RunQueuedTest(_WorkspaceCase):
    def test_advances_the_same_id(self):
        self.write_registry([("p", "g")])
        task_id = self.park("p", "advance me", queue_seq=3,
                            adapter="custom:echo hi")
        before = self.count_tasks()

        returned = dispatch.run_queued(self.ws, task_id)

        self.assertEqual(returned, task_id)
        self.assertEqual(self.count_tasks(), before)  # no new row was minted
        row = self.row(task_id)
        self.assertEqual(row["status"], STATUS_DONE)
        self.assertEqual(row["queue_seq"], 3)  # the seq is preserved
        events = [
            e["event"]
            for e in dispatch.task_detail(self.ws, task_id)["events"]
        ]
        self.assertIn("queued", events)
        self.assertIn("started", events)

    def test_unknown_id_is_not_found(self):
        self.write_registry([("p", "g")])
        with self.assertRaises(dispatch.TaskNotFoundError):
            dispatch.run_queued(self.ws, "t-nope")

    def test_non_queued_row_is_a_state_error(self):
        self.write_registry([("p", "g")])
        task_id = self.park("p", "x", queue_seq=1)
        dispatch.run_queued(self.ws, task_id)
        with self.assertRaises(dispatch.TaskStateError):
            dispatch.run_queued(self.ws, task_id)

    def test_parked_run_flags_survive_to_the_advance(self):
        self.write_registry([("p", "g")])
        task_id = self.park("p", "x", queue_seq=1, adapter="custom:echo hi",
                            skip_verify=True)
        dispatch.run_queued(self.ws, task_id)
        row = self.row(task_id)
        self.assertEqual(row["status"], STATUS_DONE)
        self.assertEqual(row["verify_cmd"], "SKIPPED")  # not "passed"

    def test_workdir_is_recorded_while_running(self):
        """A real advance lands workdir on the row before the adapter spawns.

        Card 55: the live `files_changed_live` probe needs the run's directory
        on the row *while* it runs, not only at `_finish_task` time. This drives
        a genuine queued -> running advance with a slow adapter and reads the
        row back from the database during the running window -- no hand-built
        ``Task(status="running", workdir=...)`` fixture (that shape never occurs
        in production).
        """
        self.write_registry([("p", "g")])
        task_id = self.park(
            "p", "slow", queue_seq=1,
            adapter="custom:sh -c 'sleep 1.5; echo done'",
        )
        worker = threading.Thread(
            target=dispatch.run_queued, args=(self.ws, task_id)
        )
        worker.start()
        try:
            # Wait for the running flip AND the workdir write: they are two
            # statements, so `running` alone can be seen a beat before the path.
            self.wait_for(
                lambda: self.status(task_id) == STATUS_RUNNING
                and self.row(task_id)["workdir"] == self.proj,
                message="slow card running with its workdir recorded",
            )
            row = self.row(task_id)
            self.assertEqual(row["status"], STATUS_RUNNING)
            # The project path, not NULL and not a leftover from a worktree run.
            self.assertEqual(row["workdir"], self.proj)
        finally:
            worker.join(timeout=30)
        self.assertFalse(worker.is_alive())
        self.assertEqual(self.status(task_id), STATUS_DONE)
        # The finish write is the same value, so it stays put.
        self.assertEqual(self.row(task_id)["workdir"], self.proj)


class BlockedNotAdvancedTest(_WorkspaceCase):
    """⑥ Card 34: `blocked` is a true terminal, so the queue skips it."""

    def _make_blocked(self):
        # A project that protects `protected/`, run by an adapter that writes to
        # it: the breach is recorded `blocked` (green acceptance still runs).
        with open(os.path.join(self.ws, "projects.toml"), "w", encoding="utf-8") as fh:
            fh.write(
                "[defaults]\nconcurrency = 3\ntimeout = 120\n\n"
                "[[project]]\n"
                'id = "p"\n'
                f"path = {_q(self.proj)}\n"
                'group = "g"\n'
                'verify = "exit 0"\n'
                'verify_kind = "check"\n'
                'forbidden_paths = ["protected/"]\n'
            )
        with self.assertRaises(VerifyError):
            dispatch.dispatch(
                self.ws, "p", "breach",
                adapter=("custom:sh -c 'mkdir -p protected && "
                         "echo x > protected/out.txt && echo ok'"),
            )
        conn = self.open_conn()
        try:
            return storage.list_tasks(conn, limit=1)[0]["id"]
        finally:
            conn.close()

    def test_blocked_card_is_not_advanced(self):
        task_id = self._make_blocked()
        self.assertEqual(self.status(task_id), STATUS_BLOCKED)

        # The wave selector only sees live rows, so a terminal card is invisible.
        conn = self.open_conn()
        try:
            self.assertEqual(queue.select_wave(conn), [])
        finally:
            conn.close()

        # A real daemon tick launches nothing and leaves the terminal row alone.
        daemon = queue.QueueDaemon(self.ws, tick_seconds=0.01)
        self.assertEqual(daemon.tick(), 0)
        row = self.row(task_id)
        self.assertEqual(row["status"], STATUS_BLOCKED)
        self.assertEqual(self.count_tasks(), 1)


class SameWaveSameGroupTest(_WorkspaceCase):
    def setUp(self):
        super().setUp()
        # Two projects that share one group -> same-wave same-group contention.
        self.write_registry([("one", "shared"), ("two", "shared")])

    def test_second_card_stays_queued_then_advances(self):
        first = self.park("one", "first", queue_seq=8,
                          adapter="custom:sh -c 'sleep 1.5; echo done'")
        second = self.park("two", "second", queue_seq=8,
                           adapter="custom:echo hi")

        worker = threading.Thread(target=dispatch.run_queued, args=(self.ws, first))
        worker.start()
        try:
            self.wait_for(lambda: self.status(first) == STATUS_RUNNING,
                          message="first same-group card running")
            # The group is held: the second card is refused (exit 75) ...
            with self.assertRaises(ConcurrencyError):
                dispatch.run_queued(self.ws, second)
        finally:
            worker.join(timeout=30)

        # ... and it is safely back to queued (not dropped, seq unchanged).
        row = self.row(second)
        self.assertEqual(row["status"], STATUS_QUEUED)
        self.assertEqual(row["queue_seq"], 8)
        self.assertEqual(self.status(first), STATUS_DONE)

        # The next tick can now advance it.
        dispatch.run_queued(self.ws, second)
        self.assertEqual(self.status(second), STATUS_DONE)


class CapFullTest(_WorkspaceCase):
    def test_refused_by_cap_stays_queued(self):
        self.write_registry([("other", "g1"), ("mine", "g2")], cap=1)
        parked = self.park("mine", "wait", queue_seq=1)

        conn = self.open_conn()
        try:
            # Fill the single global slot with an unrelated group so only the
            # cap (not the group mutex) can refuse the parked card.
            concurrency.acquire(conn, "holder", "g1", cap=1, ttl=120)
        finally:
            conn.close()

        with self.assertRaises(ConcurrencyError):
            dispatch.run_queued(self.ws, parked)

        row = self.row(parked)
        self.assertEqual(row["status"], STATUS_QUEUED)  # not running, not gone
        self.assertIsNone(row["pid"])
        self.assertEqual(self.count_tasks(), 1)


# ---------------------------------------------------------------------------
# The daemon proper: parallelism, clean SIGTERM, restart
# ---------------------------------------------------------------------------


class DaemonParallelTest(_WorkspaceCase):
    def test_same_wave_different_groups_run_together(self):
        self.write_registry([("one", "g1"), ("two", "g2")], cap=3)
        a = self.park("one", "a", queue_seq=7,
                      adapter="custom:sh -c 'sleep 1.5; echo done'")
        b = self.park("two", "b", queue_seq=7,
                      adapter="custom:sh -c 'sleep 1.5; echo done'")

        daemon = queue.QueueDaemon(self.ws, tick_seconds=0.1)
        runner = threading.Thread(target=daemon.run)
        runner.start()
        try:
            # Both must leave `queued` while both are still sleeping: real
            # parallelism, not a sequential drain.
            self.wait_for(
                lambda: self.status(a) == STATUS_RUNNING
                and self.status(b) == STATUS_RUNNING,
                message="both same-wave cards running together",
            )
        finally:
            daemon.stop()
            runner.join(timeout=30)
        self.assertFalse(runner.is_alive())


class DaemonShutdownTest(_WorkspaceCase):
    def setUp(self):
        super().setUp()
        self.write_registry([("p", "g")], cap=3)

    def _start_queue(self):
        proc = subprocess.Popen(
            [sys.executable, "-m", "taskproof", "--workspace", self.ws, "queue"],
            env=_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(proc.wait)
        for stream in (proc.stdout, proc.stderr):
            if stream is not None:
                self.addCleanup(stream.close)
        return proc

    def _term(self, proc):
        proc.terminate()
        proc.wait(timeout=30)

    def test_sigterm_mid_run_leaves_no_claim(self):
        task_id = self.park("p", "long", queue_seq=1,
                            adapter="custom:sh -c 'sleep 30'")
        proc = self._start_queue()
        self.wait_for(lambda: self.status(task_id) == STATUS_RUNNING,
                      message="queue launched the card")

        self._term(proc)

        self.assertEqual(proc.returncode, 0, proc.stderr.read())
        self.assertEqual(self.active_claims(), 0)
        # The interrupted attempt is recorded terminal, never left running.
        self.assertIn(self.status(task_id), TERMINAL_STATUSES)

    def test_leftover_queued_rows_resume_after_restart(self):
        first = self.park("p", "first", queue_seq=1,
                          adapter="custom:sh -c 'sleep 30'")
        second = self.park("p", "second", queue_seq=2,
                           adapter="custom:echo hi")

        proc = self._start_queue()
        self.wait_for(lambda: self.status(first) == STATUS_RUNNING,
                      message="wave-1 card running")
        self.assertEqual(self.status(second), STATUS_QUEUED)

        self._term(proc)
        # Wave 1 was interrupted, so it is terminal; wave 2 is still parked.
        self.assertIn(self.status(first), TERMINAL_STATUSES)
        self.assertEqual(self.status(second), STATUS_QUEUED)
        self.assertEqual(self.active_claims(), 0)

        # A fresh daemon picks the queued row up and drives it to completion.
        proc2 = self._start_queue()
        try:
            self.wait_for(lambda: self.status(second) == STATUS_DONE,
                          message="wave-2 card advanced by the restarted queue")
        finally:
            self._term(proc2)
        self.assertEqual(self.active_claims(), 0)


if __name__ == "__main__":
    unittest.main()
