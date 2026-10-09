"""Task control surface: pid/pgid identity, cancel/rm, queued + queue_seq,
schema migration, and the three write endpoints.

Everything here runs harmless ``custom:`` adapters in a throwaway workspace
under a TemporaryDirectory: no real agent is invoked and nothing reaches the
network. The one real-process test drives the installed CLI as a subprocess so
the recorded ``pid``/``pgid`` describe a genuinely separate process tree.
"""

import contextlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

from taskproof import cli, concurrency, dispatch, ledger, storage
from taskproof.api import server
from taskproof.models import (
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_QUEUED,
    STATUS_RUNNING,
    Task,
)

_SENTINEL = object()
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _env():
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(_REPO, "src")
    return env


def _q(value) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def registry_toml(path, *, pid="proj", group="proj", verify="exit 0",
                  verify_kind="check", cap=3, timeout=120) -> str:
    lines = [
        "[defaults]",
        f"concurrency = {cap}",
        f"timeout = {timeout}",
        "",
        "[[project]]",
        f"id = {_q(pid)}",
        f"path = {_q(path)}",
        f"group = {_q(group)}",
    ]
    if verify is not None:
        lines.append(f"verify = {_q(verify)}")
        lines.append(f"verify_kind = {_q(verify_kind)}")
    return "\n".join(lines) + "\n"


def _task_columns(conn):
    return {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}


def _group_alive(pgid) -> bool:
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False


class _WorkspaceCase(unittest.TestCase):
    """A fresh workspace with one registered project."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.ws = os.path.join(self.tmp, "workspace")
        self.proj = os.path.join(self.tmp, "project")
        os.makedirs(self.proj)
        dispatch.prepare_workspace(self.ws)
        with open(os.path.join(self.ws, "projects.toml"), "w", encoding="utf-8") as fh:
            fh.write(registry_toml(self.proj))

    def tearDown(self):
        self._tmp.cleanup()

    def open_conn(self):
        conn = storage.connect(storage.db_path(self.ws))
        storage.migrate(conn)
        return conn

    def park(self, brief="later", *, queue_seq=None, adapter="custom:echo hi"):
        return dispatch.dispatch(
            self.ws, "proj", brief, adapter=adapter, start=False, queue_seq=queue_seq
        )


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

#: The pre-pgid/queue_seq schema: current tasks table minus the two new columns.
_OLD_SCHEMA = """
CREATE TABLE schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    project TEXT NOT NULL,
    group_name TEXT NOT NULL DEFAULT 'default',
    brief TEXT NOT NULL,
    status TEXT NOT NULL,
    adapter TEXT NOT NULL DEFAULT 'codex',
    model TEXT,
    reasoning TEXT,
    attempt INTEGER NOT NULL DEFAULT 1,
    exit_code INTEGER,
    pid INTEGER,
    workdir TEXT,
    result_path TEXT,
    verify_cmd TEXT,
    verify_exit INTEGER,
    files_changed INTEGER,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT,
    ts TEXT NOT NULL,
    event TEXT NOT NULL,
    payload TEXT
);
CREATE TABLE claims (
    scope TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    pid INTEGER,
    claimed_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
INSERT INTO schema_version (version, applied_at) VALUES (1, '2020-01-01T00:00:00+00:00');
INSERT INTO tasks (id, project, group_name, brief, status, pid, created_at)
    VALUES ('t-old-001', 'proj', 'proj', 'legacy row', 'done', 4242,
            '2020-01-01T00:00:00+00:00');
"""


class MigrationTest(unittest.TestCase):
    def test_migrate_adds_columns_records_version_and_preserves_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "taskproof.db")
            conn = storage.connect(db)
            conn.executescript(_OLD_SCHEMA)
            cols_before = _task_columns(conn)
            self.assertNotIn("pgid", cols_before)
            self.assertNotIn("queue_seq", cols_before)
            conn.close()

            conn = storage.connect(db)
            try:
                storage.migrate(conn)
                cols = _task_columns(conn)
                self.assertIn("pgid", cols)
                self.assertIn("queue_seq", cols)

                # Old data survives, and the new columns are NULL on old rows.
                row = storage.get_task(conn, "t-old-001")
                self.assertIsNotNone(row)
                self.assertEqual(row["brief"], "legacy row")
                self.assertEqual(row["status"], "done")
                self.assertEqual(row["pid"], 4242)
                self.assertIsNone(row["pgid"])
                self.assertIsNone(row["queue_seq"])

                versions = [
                    r[0]
                    for r in conn.execute(
                        "SELECT version FROM schema_version ORDER BY version"
                    )
                ]
                self.assertIn(2, versions)
                self.assertEqual(max(versions), storage.SCHEMA_VERSION)

                # Idempotent: a second migrate adds no columns and no version row.
                snapshot = list(conn.execute("PRAGMA table_info(tasks)"))
                storage.migrate(conn)
                self.assertEqual(list(conn.execute("PRAGMA table_info(tasks)")), snapshot)
                self.assertEqual(
                    versions,
                    [
                        r[0]
                        for r in conn.execute(
                            "SELECT version FROM schema_version ORDER BY version"
                        )
                    ],
                )
                self.assertIsNotNone(storage.get_task(conn, "t-old-001"))
            finally:
                conn.close()

    def test_fresh_schema_has_the_new_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = storage.connect(os.path.join(tmp, "taskproof.db"))
            try:
                storage.migrate(conn)
                cols = _task_columns(conn)
                self.assertIn("pgid", cols)
                self.assertIn("queue_seq", cols)
            finally:
                conn.close()


class ColumnRegistrationTest(unittest.TestCase):
    def test_columns_are_registered_for_crud(self):
        for name in ("pgid", "queue_seq"):
            self.assertIn(name, storage.TASK_COLUMNS)

    def test_model_carries_the_new_fields(self):
        task = Task(id="t", project="p", group="g", brief="b", pgid=7, queue_seq=3)
        self.assertEqual(task.pgid, 7)
        self.assertEqual(task.queue_seq, 3)


# ---------------------------------------------------------------------------
# queued rows + queue_seq
# ---------------------------------------------------------------------------


class QueuedDispatchTest(_WorkspaceCase):
    def test_start_false_parks_a_queued_row_with_seq_and_no_process(self):
        task_id = self.park(queue_seq=5)
        task = dispatch.task_detail(self.ws, task_id)["task"]
        self.assertEqual(task["status"], STATUS_QUEUED)
        self.assertEqual(task["queue_seq"], 5)
        self.assertIsNone(task["pid"])
        self.assertIsNone(task["pgid"])
        self.assertFalse(task["started_at"])

        events = [e["event"] for e in dispatch.task_detail(self.ws, task_id)["events"]]
        self.assertIn("queued", events)
        self.assertNotIn("started", events)

    def test_queued_row_is_visible_to_cli_tasks(self):
        task_id = self.park("parked by cli", queue_seq=2)
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["--workspace", self.ws, "--json", "tasks"])
        self.assertEqual(code, 0, err.getvalue())
        listed = json.loads(out.getvalue())["tasks"]
        entry = next(t for t in listed if t["id"] == task_id)
        self.assertEqual(entry["status"], STATUS_QUEUED)
        self.assertEqual(entry["queue_seq"], 2)

    def test_set_queue_seq_edits_a_queued_row(self):
        task_id = self.park(queue_seq=1)
        updated = dispatch.set_queue_seq(self.ws, task_id, 9)
        self.assertEqual(updated["queue_seq"], 9)
        events = [e["event"] for e in dispatch.task_detail(self.ws, task_id)["events"]]
        self.assertIn("queue_seq", events)

    def test_set_queue_seq_refuses_a_non_queued_row(self):
        task_id = self.park(queue_seq=1)
        dispatch.cancel_task(self.ws, task_id)
        with self.assertRaises(dispatch.TaskStateError):
            dispatch.set_queue_seq(self.ws, task_id, 4)

    def test_set_queue_seq_unknown_id(self):
        with self.assertRaises(dispatch.TaskNotFoundError):
            dispatch.set_queue_seq(self.ws, "t-nope", 1)


# ---------------------------------------------------------------------------
# cancel / rm (state machine, no live processes)
# ---------------------------------------------------------------------------


class CancelQueuedTest(_WorkspaceCase):
    def test_cancel_queued_records_terminal_state_and_event(self):
        task_id = self.park(queue_seq=1)
        out = dispatch.cancel_task(self.ws, task_id)
        self.assertEqual(out["status"], STATUS_CANCELLED)
        self.assertTrue(out["finished_at"])
        events = [e["event"] for e in dispatch.task_detail(self.ws, task_id)["events"]]
        self.assertIn("cancelled", events)

    def test_cancel_terminal_is_a_readable_error(self):
        task_id = self.park(queue_seq=1)
        dispatch.cancel_task(self.ws, task_id)
        with self.assertRaises(dispatch.TaskStateError) as ctx:
            dispatch.cancel_task(self.ws, task_id)
        self.assertIn("cancelled", str(ctx.exception))

    def test_cancel_unknown_is_not_found(self):
        with self.assertRaises(dispatch.TaskNotFoundError):
            dispatch.cancel_task(self.ws, "t-nope")

    def test_cancel_does_not_touch_the_workdir(self):
        marker = os.path.join(self.proj, "precious.txt")
        with open(marker, "w", encoding="utf-8") as fh:
            fh.write("keep me\n")
        task_id = self.park(queue_seq=1)
        dispatch.cancel_task(self.ws, task_id)
        with open(marker, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "keep me\n")


class RemoveTest(_WorkspaceCase):
    def test_remove_running_is_refused_with_a_cancel_hint(self):
        conn = self.open_conn()
        try:
            storage.insert_task(
                conn,
                Task(
                    id="t-live",
                    project="proj",
                    group="proj",
                    brief="in flight",
                    status=STATUS_RUNNING,
                    pid=os.getpid(),
                    created_at=storage.now_iso(),
                ),
            )
        finally:
            conn.close()
        with self.assertRaises(dispatch.TaskStateError) as ctx:
            dispatch.remove_task(self.ws, "t-live")
        self.assertEqual(ctx.exception.hint, "taskproof cancel t-live")

    def test_remove_unknown_is_not_found(self):
        with self.assertRaises(dispatch.TaskNotFoundError):
            dispatch.remove_task(self.ws, "t-nope")

    def test_remove_terminal_deletes_task_and_events_but_keeps_audit_jsonl(self):
        task_id = self.park("to be removed", queue_seq=1)
        dispatch.cancel_task(self.ws, task_id)

        conn = self.open_conn()
        try:
            before = conn.execute(
                "SELECT COUNT(*) FROM events WHERE task_id = ?", (task_id,)
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertGreater(before, 0)

        removed = dispatch.remove_task(self.ws, task_id)
        self.assertEqual(removed, task_id)

        conn = self.open_conn()
        try:
            self.assertIsNone(storage.get_task(conn, task_id))
            after = conn.execute(
                "SELECT COUNT(*) FROM events WHERE task_id = ?", (task_id,)
            ).fetchone()[0]
            self.assertEqual(after, 0)
        finally:
            conn.close()

        # The append-only JSONL audit stream is deliberately NOT deleted.
        stream = ledger.stream_path(self.ws, ledger.month_key())
        self.assertTrue(os.path.exists(stream))
        with open(stream, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn(task_id, text)

    def test_remove_allows_a_done_task(self):
        task_id = dispatch.dispatch(
            self.ws, "proj", "quick", adapter="custom:echo hi", skip_verify=True
        )
        self.assertEqual(dispatch.task_detail(self.ws, task_id)["task"]["status"], STATUS_DONE)
        self.assertEqual(dispatch.remove_task(self.ws, task_id), task_id)


class CliControlTest(_WorkspaceCase):
    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["--workspace", self.ws, "--json", *argv])
        return code, out.getvalue(), err.getvalue()

    def test_cancel_and_rm_round_trip(self):
        task_id = self.park(queue_seq=3)
        code, out, err = self.run_cli("cancel", task_id)
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["status"], STATUS_CANCELLED)

        code, out, err = self.run_cli("rm", task_id)
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["removed"], task_id)

        code, _out, _err = self.run_cli("show", task_id)
        self.assertEqual(code, 64)

    def test_cli_cancel_terminal_reports_usage_error(self):
        task_id = self.park(queue_seq=3)
        self.run_cli("cancel", task_id)
        code, _out, err = self.run_cli("cancel", task_id)
        self.assertEqual(code, 64)
        self.assertIn("already", err)

    def test_cli_rm_non_terminal_prints_cancel_hint(self):
        task_id = self.park(queue_seq=3)
        code, _out, err = self.run_cli("rm", task_id)
        self.assertEqual(code, 64)
        self.assertIn("cancel", err)
        self.assertIn(f"taskproof cancel {task_id}", err)

    def test_cli_advance_fires_a_queued_card(self):
        task_id = self.park(queue_seq=4)
        code, out, err = self.run_cli("advance", task_id)
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["task_id"], task_id)
        self.assertEqual(payload["status"], STATUS_DONE)
        self.assertEqual(payload["task"]["queue_seq"], 4)

    def test_cli_advance_non_queued_is_nonzero(self):
        task_id = self.park(queue_seq=1)
        self.assertEqual(self.run_cli("advance", task_id)[0], 0)
        code, _out, err = self.run_cli("advance", task_id)
        self.assertNotEqual(code, 0)
        self.assertIn("only a queued task", err)


# ---------------------------------------------------------------------------
# Real process: cancel reaches the whole adapter tree
# ---------------------------------------------------------------------------


class CancelRealProcessTest(_WorkspaceCase):
    def _wait_for_running_row(self, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            conn = self.open_conn()
            try:
                rows = [dict(r) for r in storage.list_tasks(conn, status=STATUS_RUNNING, limit=5)]
            finally:
                conn.close()
            if rows and rows[0].get("pgid"):
                return rows[0]
            time.sleep(0.05)
        self.fail("no running task with a recorded pgid appeared")

    def _run_cli(self, *argv, timeout=30):
        return subprocess.run(
            [sys.executable, "-m", "taskproof", "--workspace", self.ws, *argv],
            env=_env(),
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def test_cancel_kills_the_tree_and_spares_unrelated_processes(self):
        sibling = subprocess.Popen(["sleep", "120"])
        self.addCleanup(sibling.wait)
        self.addCleanup(sibling.terminate)

        runner = subprocess.Popen(
            [
                sys.executable, "-m", "taskproof", "--workspace", self.ws,
                "run", "proj", "sleepy task",
                "--adapter", "custom:sh -c 'sleep 120'",
            ],
            env=_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(runner.wait)
        for stream in (runner.stdout, runner.stderr):
            if stream is not None:
                self.addCleanup(stream.close)

        row = self._wait_for_running_row()
        task_id, pid, pgid = row["id"], row["pid"], row["pgid"]

        # pid is the run process; pgid is the adapter's own new session.
        self.assertEqual(pid, runner.pid)
        self.assertNotEqual(pgid, os.getpgid(0))
        self.assertTrue(_group_alive(pgid))

        proc = self._run_cli("cancel", task_id)
        self.assertEqual(proc.returncode, 0, proc.stderr)

        # The adapter's whole group is gone ...
        self.assertFalse(_group_alive(pgid))
        # ... and the run process itself has exited (pid reaped -> no process).
        runner.wait(timeout=20)
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)
        # Unrelated processes were never touched.
        os.kill(sibling.pid, 0)
        os.kill(os.getpid(), 0)

        detail = dispatch.task_detail(self.ws, task_id)
        self.assertEqual(detail["task"]["status"], STATUS_CANCELLED)
        self.assertTrue(detail["task"]["finished_at"])
        events = [e["event"] for e in detail["events"]]
        self.assertIn("cancelled", events)
        # A deliberate stop must not ALSO be recorded as a failure: the terminal
        # state is written before the signal so the dispatcher yields cleanly.
        self.assertNotIn("failed", events)
        self.assertNotIn("timeout", events)

    def test_cancel_after_process_started_already_gone_is_safe(self):
        # A queued cancel path with no process at all: must not raise on kill.
        task_id = self.park("no process", queue_seq=1)
        out = dispatch.cancel_task(self.ws, task_id)
        self.assertEqual(out["status"], STATUS_CANCELLED)


class AdvanceRealProcessTest(_WorkspaceCase):
    """`taskproof advance` as a real subprocess: the documented CLI door."""

    def _run_cli(self, *argv, timeout=30):
        return subprocess.run(
            [sys.executable, "-m", "taskproof", "--workspace", self.ws, *argv],
            env=_env(),
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def test_advance_runs_a_queued_card_to_done(self):
        task_id = self.park("advance me", queue_seq=9)
        proc = self._run_cli("advance", task_id)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        detail = dispatch.task_detail(self.ws, task_id)
        self.assertEqual(detail["task"]["status"], STATUS_DONE)
        self.assertEqual(detail["task"]["queue_seq"], 9)

    def test_advance_non_queued_exits_nonzero(self):
        task_id = self.park("advance me", queue_seq=1)
        self.assertEqual(self._run_cli("advance", task_id).returncode, 0)
        proc = self._run_cli("advance", task_id)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("only a queued task", proc.stderr)


# ---------------------------------------------------------------------------
# Write API: four action endpoints + PATCH, behind --allow-write + token
# ---------------------------------------------------------------------------

_API_REGISTRY = (
    "[defaults]\nconcurrency = 3\ntimeout = 60\n\n"
    "[[project]]\n"
    'id = "alpha"\n'
    "{path}\n"
    'group = "alpha"\n'
    'verify = "exit 0"\n'
    'verify_kind = "check"\n'
)


class _TaskApiCase(unittest.TestCase):
    allow_write = True
    token = "fixed-session-token-0123456789"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.ws = os.path.join(self.tmp, "workspace")
        os.makedirs(self.ws)
        self.proj = os.path.join(self.tmp, "alpha-repo")
        os.makedirs(self.proj)
        with open(os.path.join(self.ws, "projects.toml"), "w", encoding="utf-8") as fh:
            fh.write(_API_REGISTRY.format(path=f'path = {_q(self.proj)}'))

        self.httpd = server.make_server(
            self.ws, port=0, allow_write=self.allow_write, token=self.token
        )
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        self._tmp.cleanup()

    def _request(self, path, *, method="GET", body=None, token=_SENTINEL):
        data = None
        headers = {}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if token is _SENTINEL:
            token = self.token
        if token is not None:
            headers["X-Taskproof-Token"] = token
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read().decode("utf-8"))
            finally:
                exc.close()

    def _mk_queued(self, queue_seq=None):
        body = {"project": "alpha", "brief": "park me", "start": False}
        if queue_seq is not None:
            body["queue_seq"] = queue_seq
        status, payload = self._request("/api/tasks", method="POST", body=body)
        self.assertEqual(status, 201, payload)
        return payload["task"]["id"]

    def _park(self, project="alpha", *, brief="park me", queue_seq=None):
        # A harmless custom: adapter, so ADVANCING it can never reach a real
        # agent even though it runs the task end to end.
        body = {
            "project": project,
            "brief": brief,
            "adapter": "custom:echo hi",
            "start": False,
        }
        if queue_seq is not None:
            body["queue_seq"] = queue_seq
        status, payload = self._request("/api/tasks", method="POST", body=body)
        self.assertEqual(status, 201, payload)
        return payload["task"]["id"]

    def open_conn(self):
        conn = storage.connect(storage.db_path(self.ws))
        storage.migrate(conn)
        return conn

    def _hold(self, group, *, cap):
        """Pin one live claim so the next spawn of `group` is refused.

        A committed claim is visible to the server thread's own connection, so
        the refusal is the real gate, not a mock.
        """
        conn = self.open_conn()
        lease = concurrency.acquire(conn, "holder", group, cap=cap, ttl=120)

        def _release():
            concurrency.release(conn, lease)
            conn.close()

        self.addCleanup(_release)
        return conn

    def _row(self, task_id):
        conn = self.open_conn()
        try:
            return dict(storage.get_task(conn, task_id))
        finally:
            conn.close()


class TaskWriteDisabledTest(_TaskApiCase):
    allow_write = False

    def test_all_task_writes_are_405(self):
        cases = [
            ("/api/tasks", "POST", {"project": "alpha", "brief": "x"}),
            ("/api/tasks/t-1/advance", "POST", None),
            ("/api/tasks/t-1/cancel", "POST", None),
            ("/api/tasks/t-1", "PATCH", {"queue_seq": 1}),
            ("/api/tasks/t-1", "DELETE", None),
        ]
        for path, method, body in cases:
            status, payload = self._request(path, method=method, body=body)
            self.assertEqual(status, 405, (path, method, payload))
            self.assertIn("error", payload)


class TaskWriteApiTest(_TaskApiCase):
    # -- advance: fire ONE queued card now, out of its wave ---------------

    def test_advance_fires_a_queued_card_keeping_id_and_queue_seq(self):
        task_id = self._park("alpha", brief="fire me", queue_seq=6)
        status, payload = self._request(f"/api/tasks/{task_id}/advance", method="POST")
        self.assertEqual(status, 200, payload)
        task = payload["task"]
        self.assertEqual(task["id"], task_id)          # id unchanged
        self.assertEqual(task["queue_seq"], 6)         # queue_seq unchanged
        self.assertEqual(task["status"], STATUS_DONE)  # actually ran

        # the same id / queue_seq are what the persisted row holds
        row = self._row(task_id)
        self.assertEqual(row["id"], task_id)
        self.assertEqual(row["queue_seq"], 6)
        self.assertEqual(row["status"], STATUS_DONE)

    def test_advance_non_queued_is_409(self):
        task_id = self._park("alpha")
        self.assertEqual(
            self._request(f"/api/tasks/{task_id}/advance", method="POST")[0], 200
        )
        status, payload = self._request(f"/api/tasks/{task_id}/advance", method="POST")
        self.assertEqual(status, 409, payload)
        self.assertIn("only a queued task", payload["error"])

    def test_advance_unknown_id_is_404(self):
        status, payload = self._request("/api/tasks/t-nope/advance", method="POST")
        self.assertEqual(status, 404, payload)
        self.assertIn("error", payload)

    def test_advance_without_token_is_403(self):
        task_id = self._park("alpha")
        status, _payload = self._request(
            f"/api/tasks/{task_id}/advance", method="POST", token=None
        )
        self.assertEqual(status, 403)

    def test_advance_group_busy_is_429_and_leaves_row_queued(self):
        task_id = self._park("alpha", queue_seq=3)
        # Pin the group: the card's own group is busy, so the spawn is refused.
        self._hold("alpha", cap=3)
        status, payload = self._request(f"/api/tasks/{task_id}/advance", method="POST")
        self.assertEqual(status, 429, payload)
        self.assertEqual(payload["reason"], "group")
        self.assertIn("busy", payload["detail"])

        # The refusal left the row exactly as it was: still queued, same seq.
        row = self._row(task_id)
        self.assertEqual(row["status"], STATUS_QUEUED)
        self.assertEqual(row["queue_seq"], 3)


    def test_create_queued_returns_201_visible_via_api(self):
        status, payload = self._request(
            "/api/tasks",
            method="POST",
            body={"project": "alpha", "brief": "park me", "start": False, "queue_seq": 4},
        )
        self.assertEqual(status, 201)
        task = payload["task"]
        self.assertEqual(task["status"], STATUS_QUEUED)
        self.assertEqual(task["queue_seq"], 4)
        self.assertIsNone(task["pid"])

        status, listed = self._request("/api/tasks")
        self.assertEqual(status, 200)
        self.assertIn(task["id"], [t["id"] for t in listed["tasks"]])

    def test_create_start_true_runs_to_done(self):
        status, payload = self._request(
            "/api/tasks",
            method="POST",
            body={
                "project": "alpha",
                "brief": "run now",
                "adapter": "custom:echo hi",
                "skip_verify": True,
            },
        )
        self.assertEqual(status, 201)
        task_id = payload["task"]["id"]
        status, detail = self._request(f"/api/tasks/{task_id}")
        self.assertEqual(status, 200)
        self.assertEqual(detail["task"]["status"], STATUS_DONE)

    def test_cancel_endpoint_marks_queued_cancelled(self):
        task_id = self._mk_queued()
        status, payload = self._request(f"/api/tasks/{task_id}/cancel", method="POST")
        self.assertEqual(status, 200)
        self.assertEqual(payload["task"]["status"], STATUS_CANCELLED)
        self.assertTrue(payload["task"]["finished_at"])

    def test_cancel_terminal_is_409(self):
        task_id = self._mk_queued()
        self._request(f"/api/tasks/{task_id}/cancel", method="POST")
        status, payload = self._request(f"/api/tasks/{task_id}/cancel", method="POST")
        self.assertEqual(status, 409, payload)

    def test_cancel_unknown_id_is_404(self):
        status, payload = self._request("/api/tasks/t-nope/cancel", method="POST")
        self.assertEqual(status, 404)
        self.assertIn("error", payload)

    def test_delete_non_terminal_is_409(self):
        task_id = self._mk_queued()
        status, payload = self._request(f"/api/tasks/{task_id}", method="DELETE")
        self.assertEqual(status, 409, payload)

    def test_delete_terminal_removes_task_and_its_events(self):
        task_id = self._mk_queued()
        self._request(f"/api/tasks/{task_id}/cancel", method="POST")
        self.assertEqual(self._request(f"/api/tasks/{task_id}")[0], 200)

        status, payload = self._request(f"/api/tasks/{task_id}", method="DELETE")
        self.assertEqual(status, 200)
        self.assertEqual(payload["removed"], task_id)

        self.assertEqual(self._request(f"/api/tasks/{task_id}")[0], 404)
        conn = storage.connect(storage.db_path(self.ws))
        try:
            events = conn.execute(
                "SELECT COUNT(*) FROM events WHERE task_id = ?", (task_id,)
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(events, 0)

    def test_delete_unknown_id_is_404(self):
        status, payload = self._request("/api/tasks/t-nope", method="DELETE")
        self.assertEqual(status, 404)

    def test_patch_edits_only_queue_seq(self):
        task_id = self._mk_queued(queue_seq=1)
        status, payload = self._request(
            f"/api/tasks/{task_id}", method="PATCH", body={"queue_seq": 9}
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["task"]["queue_seq"], 9)

    def test_patch_rejects_any_other_field(self):
        task_id = self._mk_queued(queue_seq=1)
        status, payload = self._request(
            f"/api/tasks/{task_id}", method="PATCH", body={"brief": "hijack"}
        )
        self.assertEqual(status, 400)
        self.assertIn("error", payload)

    def test_patch_non_queued_is_409(self):
        task_id = self._mk_queued()
        self._request(f"/api/tasks/{task_id}/cancel", method="POST")
        status, payload = self._request(
            f"/api/tasks/{task_id}", method="PATCH", body={"queue_seq": 2}
        )
        self.assertEqual(status, 409)

    def test_patch_unknown_id_is_404(self):
        status, payload = self._request(
            "/api/tasks/t-nope", method="PATCH", body={"queue_seq": 1}
        )
        self.assertEqual(status, 404)

    def test_create_unknown_field_is_400(self):
        status, payload = self._request(
            "/api/tasks",
            method="POST",
            body={"project": "alpha", "brief": "x", "start": False, "bogus": 1},
        )
        self.assertEqual(status, 400)
        self.assertIn("error", payload)

    def test_missing_token_is_403(self):
        status, payload = self._request(
            "/api/tasks",
            method="POST",
            body={"project": "alpha", "brief": "x", "start": False},
            token=None,
        )
        self.assertEqual(status, 403)

    def test_wrong_token_is_403(self):
        status, payload = self._request(
            "/api/tasks",
            method="POST",
            body={"project": "alpha", "brief": "x", "start": False},
            token="not-the-token",
        )
        self.assertEqual(status, 403)

    def test_token_is_never_echoed_or_written_to_disk(self):
        status, payload = self._request(
            "/api/tasks",
            method="POST",
            body={"project": "alpha", "brief": "x", "start": False},
        )
        self.assertEqual(status, 201)
        self.assertNotIn(self.token, json.dumps(payload))

        for root, _dirs, files in os.walk(self.ws):
            for name in files:
                with open(os.path.join(root, name), "rb") as fh:
                    self.assertNotIn(self.token.encode("utf-8"), fh.read(), name)


# ---------------------------------------------------------------------------
# advance: the 429 body must name WHICH limit bit (group vs global cap)
# ---------------------------------------------------------------------------


class _CapOneApiCase(_TaskApiCase):
    """cap = 1 with two projects in different groups.

    Pinning one group's claim then fills the single global slot *without*
    touching the other group -- the exact shape that tells the two refusals
    apart.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.ws = os.path.join(self.tmp, "workspace")
        os.makedirs(self.ws)
        self.proj = os.path.join(self.tmp, "alpha-repo")
        os.makedirs(self.proj)
        self.beta_proj = os.path.join(self.tmp, "beta-repo")
        os.makedirs(self.beta_proj)
        with open(os.path.join(self.ws, "projects.toml"), "w", encoding="utf-8") as fh:
            fh.write(
                "[defaults]\nconcurrency = 1\ntimeout = 60\n\n"
                '[[project]]\nid = "alpha"\n'
                f"path = {_q(self.proj)}\ngroup = \"alpha\"\n"
                'verify = "exit 0"\nverify_kind = "check"\n\n'
                '[[project]]\nid = "beta"\n'
                f"path = {_q(self.beta_proj)}\ngroup = \"beta\"\n"
                'verify = "exit 0"\nverify_kind = "check"\n'
            )
        self.httpd = server.make_server(
            self.ws, port=0, allow_write=True, token=self.token
        )
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()


class AdvanceCapApiTest(_CapOneApiCase):
    def test_advance_cap_full_is_429_naming_the_cap(self):
        beta_id = self._park("beta", queue_seq=2)
        # alpha holds the only global slot; beta's own group is still free.
        self._hold("alpha", cap=1)
        status, payload = self._request(f"/api/tasks/{beta_id}/advance", method="POST")
        self.assertEqual(status, 429, payload)
        self.assertEqual(payload["reason"], "cap")
        self.assertIn("global cap", payload["detail"])

        row = self._row(beta_id)
        self.assertEqual(row["status"], STATUS_QUEUED)
        self.assertEqual(row["queue_seq"], 2)


# ---------------------------------------------------------------------------
# Card 41: a global-cap refusal points at --park; a group refusal does not
# ---------------------------------------------------------------------------


class CapRefusalHintCliTest(unittest.TestCase):
    """The CLI `run` refusal hint must name the way out, per refusal kind."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.ws = os.path.join(self.tmp, "workspace")
        os.makedirs(self.ws)
        self.alpha = os.path.join(self.tmp, "alpha-repo")
        os.makedirs(self.alpha)
        self.beta = os.path.join(self.tmp, "beta-repo")
        os.makedirs(self.beta)
        with open(os.path.join(self.ws, "projects.toml"), "w", encoding="utf-8") as fh:
            fh.write(
                "[defaults]\nconcurrency = 1\ntimeout = 60\n\n"
                '[[project]]\nid = "alpha"\n'
                f"path = {_q(self.alpha)}\ngroup = \"alpha\"\n"
                'verify = "exit 0"\nverify_kind = "check"\n\n'
                '[[project]]\nid = "beta"\n'
                f"path = {_q(self.beta)}\ngroup = \"beta\"\n"
                'verify = "exit 0"\nverify_kind = "check"\n'
            )

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, *argv):
        return subprocess.run(
            [sys.executable, "-m", "taskproof", "--workspace", self.ws, *argv],
            env=_env(),
            capture_output=True,
            text=True,
            timeout=30,
        )

    def _acquire(self, group, cap=1):
        conn = storage.connect(storage.db_path(self.ws))
        storage.migrate(conn)
        lease = concurrency.acquire(conn, "holder-" + group, group, cap=cap, ttl=120)

        def _release():
            concurrency.release(conn, lease)
            conn.close()

        return _release

    def _hold(self, group):
        return self._acquire(group, cap=1)

    def test_global_cap_refusal_hint_names_park(self):
        release = self._hold("alpha")  # fills the only global slot
        try:
            proc = self._run("run", "beta", "brief", "--adapter", "custom:echo hi")
        finally:
            release()
        self.assertEqual(proc.returncode, 75, proc.stderr)
        self.assertIn("global cap", proc.stderr)
        self.assertIn("--park", proc.stderr)

    def test_same_group_refusal_hint_does_not_name_park(self):
        release = self._hold("beta")  # beta's own group is busy
        try:
            proc = self._run("run", "beta", "brief", "--adapter", "custom:echo hi")
        finally:
            release()
        self.assertEqual(proc.returncode, 75, proc.stderr)
        self.assertIn("group", proc.stderr)
        self.assertNotIn("--park", proc.stderr)

    def test_global_cap_refusal_names_value_source_and_three_exits(self):
        release = self._hold("alpha")  # fills the only global slot
        try:
            proc = self._run("run", "beta", "brief", "--adapter", "custom:echo hi")
        finally:
            release()
        self.assertEqual(proc.returncode, 75, proc.stderr)
        self.assertIn("上限 1", proc.stderr)
        self.assertIn("来源：projects.toml", proc.stderr)
        self.assertIn("--park", proc.stderr)
        self.assertIn("run --cap", proc.stderr)
        self.assertIn("taskproof config --concurrency", proc.stderr)

    def test_global_cap_refusal_reports_the_auto_source(self):
        # A registry with no `concurrency` key -> the effective cap (and the
        # refusal that names it) come from the hardware probe.
        with open(os.path.join(self.ws, "projects.toml"), "w", encoding="utf-8") as fh:
            fh.write(
                "[defaults]\ntimeout = 60\n\n"
                '[[project]]\nid = "alpha"\n'
                f"path = {_q(self.alpha)}\ngroup = \"alpha\"\n"
                'verify = "exit 0"\nverify_kind = "check"\n\n'
                '[[project]]\nid = "beta"\n'
                f"path = {_q(self.beta)}\ngroup = \"beta\"\n"
                'verify = "exit 0"\nverify_kind = "check"\n'
            )
        n = concurrency.detect()
        releases = [self._acquire(f"hold{i}", cap=n) for i in range(n)]
        try:
            proc = self._run("run", "beta", "brief", "--adapter", "custom:echo hi")
        finally:
            for release in releases:
                release()
        self.assertEqual(proc.returncode, 75, proc.stderr)
        self.assertIn(f"上限 {n}", proc.stderr)
        self.assertIn("来源：自动探测", proc.stderr)
        self.assertIn("run --cap", proc.stderr)


# ---------------------------------------------------------------------------
# --version
# ---------------------------------------------------------------------------


class VersionTest(unittest.TestCase):
    def test_module_version_flag(self):
        from taskproof import __version__

        proc = subprocess.run(
            [sys.executable, "-m", "taskproof", "--version"],
            env=_env(),
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), f"taskproof {__version__}")
        self.assertNotIn("\n", proc.stdout.strip())


if __name__ == "__main__":
    unittest.main()
