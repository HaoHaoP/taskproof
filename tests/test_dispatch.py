"""Dispatch pipeline contract.

The pipeline is the thing this project exists to provide, so it is pinned end
to end here — with a `custom:` adapter running harmless shell commands. No real
agent is ever invoked and nothing reaches the network:

  * happy path -> done, verify_cmd/verify_exit written, started + done events
  * acceptance failure -> failed, and the slot is released
  * --no-verify / read-only -> SKIPPED, never "passed"
  * a forbidden-path change fails the task even when the agent "succeeds"
  * an adapter failure raises AdapterError and still releases the slot
  * the concurrency gate refuses a second task in the same group
  * `_run_adapter` enforces its timeout and kills the process it started
  * `task_detail` / `summary_counts` shapes
"""

import os
import subprocess
import tempfile
import time
import unittest

from taskproof import concurrency, storage
from taskproof.adapters import get
from taskproof.dispatch import (
    _run_adapter,
    dispatch,
    prepare_workspace,
    summary_counts,
    task_detail,
)
from taskproof.errors import AdapterError, ConcurrencyError, UsageError, VerifyError
from taskproof.models import STATUS_DONE, STATUS_FAILED, STATUS_TIMEOUT


def _q(value) -> str:
    """A minimal TOML basic string (paths here are simple, but escape anyway)."""
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def registry_toml(
    path,
    *,
    pid="proj",
    group="g",
    verify="exit 0",
    verify_kind="check",
    forbidden=(),
    cap=3,
    timeout=60,
) -> str:
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
    if forbidden:
        joined = ", ".join(_q(f) for f in forbidden)
        lines.append(f"forbidden_paths = [{joined}]")
    return "\n".join(lines) + "\n"


def json_event_text(event) -> str:
    return f"{event.get('event', '')} {event.get('payload', '')}"


class DispatchBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.ws = os.path.join(self.tmp, "workspace")
        self.proj = os.path.join(self.tmp, "project")
        os.makedirs(self.proj)
        prepare_workspace(self.ws)

    def tearDown(self):
        self._tmp.cleanup()

    # -- helpers -----------------------------------------------------------

    def write_registry(self, **kwargs):
        body = registry_toml(self.proj, **kwargs)
        with open(os.path.join(self.ws, "projects.toml"), "w", encoding="utf-8") as fh:
            fh.write(body)

    def open_conn(self):
        conn = storage.connect(storage.db_path(self.ws))
        storage.migrate(conn)
        return conn

    def active_claims(self):
        conn = self.open_conn()
        try:
            return concurrency.count_active(conn)
        finally:
            conn.close()

    def latest_task_id(self):
        conn = self.open_conn()
        try:
            rows = storage.list_tasks(conn, limit=1)
            return rows[0]["id"] if rows else None
        finally:
            conn.close()


class PrepareWorkspaceTest(unittest.TestCase):
    def test_writes_sample_registry_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = os.path.join(tmp, "fresh")
            prepare_workspace(ws)
            reg_path = os.path.join(ws, "projects.toml")
            self.assertTrue(os.path.exists(reg_path))
            self.assertTrue(os.path.exists(os.path.join(ws, "taskproof.db")))
            with open(reg_path, encoding="utf-8") as fh:
                self.assertIn("[[project]]", fh.read())

            # A user edit must not be clobbered by a second prepare.
            with open(reg_path, "w", encoding="utf-8") as fh:
                fh.write('[[project]]\nid = "mine"\npath = "/tmp/mine"\n')
            prepare_workspace(ws)
            with open(reg_path, encoding="utf-8") as fh:
                self.assertIn('id = "mine"', fh.read())


class HappyPathTest(DispatchBase):
    def test_full_pipeline_marks_done_and_records(self):
        self.write_registry(verify="exit 0", forbidden=[".git/"])
        task_id = dispatch(
            self.ws, "proj", "say hello", adapter="custom:sh -c 'echo hello'"
        )

        self.assertRegex(task_id, r"^t-\d{8}-\d{3}$")
        detail = task_detail(self.ws, task_id)
        self.assertEqual(detail["task"]["status"], STATUS_DONE)
        self.assertEqual(detail["task"]["verify_cmd"], "exit 0")
        self.assertEqual(detail["task"]["verify_exit"], 0)
        self.assertEqual(detail["task"]["project"], "proj")

        names = [e["event"] for e in detail["events"]]
        self.assertIn("started", names)
        self.assertIn("done", names)

        # The log streamed into the workspace.
        log_path = os.path.join(self.ws, "logs", f"{task_id}.log")
        self.assertTrue(os.path.exists(log_path))
        with open(log_path, encoding="utf-8") as fh:
            self.assertIn("hello", fh.read())

        # Slot released on the success path.
        self.assertEqual(self.active_claims(), 0)


class AcceptanceFailureTest(DispatchBase):
    def test_failed_acceptance_marks_failed_and_releases(self):
        self.write_registry(verify="exit 1")
        with self.assertRaises(VerifyError):
            dispatch(self.ws, "proj", "x", adapter="custom:sh -c 'echo hello'")

        task_id = self.latest_task_id()
        detail = task_detail(self.ws, task_id)
        self.assertEqual(detail["task"]["status"], STATUS_FAILED)
        self.assertEqual(detail["task"]["verify_exit"], 1)
        self.assertEqual(self.active_claims(), 0)


class SkipVerifyTest(DispatchBase):
    def test_skip_verify_is_skipped_not_passed(self):
        self.write_registry(verify="exit 0")
        task_id = dispatch(
            self.ws, "proj", "x", adapter="custom:sh -c 'echo hello'", skip_verify=True
        )

        detail = task_detail(self.ws, task_id)
        self.assertEqual(detail["task"]["status"], STATUS_DONE)
        self.assertEqual(detail["task"]["verify_cmd"], "SKIPPED")
        self.assertIsNone(detail["task"]["verify_exit"])

        statuses = [
            e["payload"].get("status")
            for e in detail["events"]
            if isinstance(e.get("payload"), dict)
        ]
        self.assertIn("SKIPPED", statuses)
        self.assertNotIn("PASSED", statuses)
        for event in detail["events"]:
            self.assertNotIn("PASSED", json_event_text(event))

    def test_read_only_is_skipped_not_passed(self):
        self.write_registry(verify="exit 0")
        task_id = dispatch(
            self.ws, "proj", "x", adapter="custom:sh -c 'echo hello'", read_only=True
        )
        detail = task_detail(self.ws, task_id)
        self.assertEqual(detail["task"]["verify_cmd"], "SKIPPED")
        self.assertIsNone(detail["task"]["verify_exit"])

    def test_no_acceptance_command_is_skipped(self):
        self.write_registry(verify=None)
        task_id = dispatch(self.ws, "proj", "x", adapter="custom:sh -c 'echo hello'")
        detail = task_detail(self.ws, task_id)
        self.assertEqual(detail["task"]["status"], STATUS_DONE)
        self.assertEqual(detail["task"]["verify_cmd"], "SKIPPED")


class ForbiddenPathTest(DispatchBase):
    def test_forbidden_change_fails_even_on_reported_success(self):
        subprocess.run(["git", "init", "-q"], cwd=self.proj, check=True)
        self.write_registry(verify="exit 0", forbidden=["dist/"])
        command = "custom:sh -c 'mkdir -p dist && echo x > dist/out.txt && echo done'"
        with self.assertRaises(VerifyError):
            dispatch(self.ws, "proj", "x", adapter=command)

        task_id = self.latest_task_id()
        detail = task_detail(self.ws, task_id)
        self.assertEqual(detail["task"]["status"], STATUS_FAILED)

        blob = " ".join(json_event_text(e) for e in detail["events"])
        self.assertIn("dist", blob)
        self.assertEqual(self.active_claims(), 0)


class AdapterFailureTest(DispatchBase):
    def test_nonzero_exit_raises_and_releases(self):
        self.write_registry(verify="exit 0")
        with self.assertRaises(AdapterError):
            dispatch(self.ws, "proj", "x", adapter="custom:sh -c 'exit 3'")

        task_id = self.latest_task_id()
        self.assertEqual(task_detail(self.ws, task_id)["task"]["status"], STATUS_FAILED)
        self.assertEqual(self.active_claims(), 0)

    def test_unparseable_output_raises_adapter_error(self):
        self.write_registry(verify="exit 0")
        # Exit 0 but print nothing: the custom adapter cannot salvage a result.
        with self.assertRaises(AdapterError):
            dispatch(self.ws, "proj", "x", adapter="custom:sh -c 'true'")
        self.assertEqual(self.active_claims(), 0)


class BadAdapterTest(DispatchBase):
    def test_unknown_adapter_raises_before_any_task_row(self):
        self.write_registry(verify="exit 0")
        with self.assertRaises(UsageError):
            dispatch(self.ws, "proj", "x", adapter="definitely-not-an-agent")
        # No task row and no leaked slot: the failure happened before ④.
        self.assertIsNone(self.latest_task_id())
        self.assertEqual(self.active_claims(), 0)


class ConcurrencyGateTest(DispatchBase):
    def test_same_group_claim_blocks_dispatch(self):
        self.write_registry(verify="exit 0", group="g")
        conn = self.open_conn()
        try:
            scopes = concurrency.acquire(conn, "t-other", "g", cap=3, ttl=60)
            with self.assertRaises(ConcurrencyError):
                dispatch(self.ws, "proj", "x", adapter="custom:sh -c 'echo hello'")
        finally:
            concurrency.release(conn, scopes)
            conn.close()

        # The refused dispatch never even wrote a task row.
        self.assertIsNone(self.latest_task_id())


class RunAdapterTimeoutTest(unittest.TestCase):
    def test_timeout_kills_process_and_raises(self):
        adapter = get("custom:sh -c 'sleep 30'", timeout=1)
        with tempfile.TemporaryDirectory() as tmp:
            log_path = os.path.join(tmp, "run.log")
            started = time.monotonic()
            with self.assertRaises(VerifyError) as ctx:
                _run_adapter(adapter, brief="x", workdir=tmp, log_path=log_path)
            elapsed = time.monotonic() - started

            self.assertIn("timeout", str(ctx.exception).lower())
            # The sleep(30) must have been killed; otherwise this would take ~30s.
            self.assertLess(elapsed, 10)
            self.assertTrue(os.path.exists(log_path))

    def test_dispatch_timeout_sets_timeout_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = os.path.join(tmp, "ws")
            proj = os.path.join(tmp, "proj")
            os.makedirs(proj)
            prepare_workspace(ws)
            with open(os.path.join(ws, "projects.toml"), "w", encoding="utf-8") as fh:
                fh.write(registry_toml(proj, verify="exit 0"))
            with self.assertRaises(VerifyError):
                dispatch(
                    ws,
                    "proj",
                    "x",
                    adapter="custom:sh -c 'sleep 30'",
                    timeout=1,
                )
            conn = storage.connect(storage.db_path(ws))
            try:
                storage.migrate(conn)
                row = storage.list_tasks(conn, limit=1)[0]
                self.assertEqual(row["status"], STATUS_TIMEOUT)
                self.assertEqual(row["exit_code"], 71)
                self.assertEqual(concurrency.count_active(conn), 0)
            finally:
                conn.close()


class WorktreeTest(DispatchBase):
    def _git_repo(self):
        subprocess.run(["git", "init", "-q"], cwd=self.proj, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=self.proj, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=self.proj, check=True)
        with open(os.path.join(self.proj, "seed.txt"), "w", encoding="utf-8") as fh:
            fh.write("seed\n")
        subprocess.run(["git", "add", "seed.txt"], cwd=self.proj, check=True)
        subprocess.run(["git", "commit", "-qm", "seed"], cwd=self.proj, check=True)

    def test_worktree_runs_then_is_cleaned_up(self):
        self._git_repo()
        self.write_registry(verify="exit 0")
        command = "custom:sh -c 'echo made > made.txt && echo ok'"
        task_id = dispatch(self.ws, "proj", "x", worktree=True, adapter=command)

        self.assertEqual(task_detail(self.ws, task_id)["task"]["status"], STATUS_DONE)
        # The scratch worktree is gone; only the main checkout remains.
        listing = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=self.proj,
            stdout=subprocess.PIPE,
            text=True,
            check=True,
        ).stdout
        self.assertEqual(listing.count("worktree "), 1)
        self.assertFalse(os.path.exists(os.path.join(self.proj, "made.txt")))
        self.assertEqual(self.active_claims(), 0)

    def test_worktree_requires_git_repo(self):
        self.write_registry(verify="exit 0")  # self.proj is a plain directory
        with self.assertRaises(UsageError):
            dispatch(self.ws, "proj", "x", worktree=True,
                     adapter="custom:sh -c 'echo hello'")
        self.assertEqual(self.active_claims(), 0)


class ShapesTest(DispatchBase):
    def test_task_detail_shape(self):
        self.write_registry(verify="exit 0")
        task_id = dispatch(self.ws, "proj", "x", adapter="custom:sh -c 'echo hello'")
        detail = task_detail(self.ws, task_id)

        self.assertEqual(set(detail.keys()), {"task", "events"})
        self.assertIsInstance(detail["task"], dict)
        self.assertIn("status", detail["task"])
        self.assertIn("id", detail["task"])
        self.assertIsInstance(detail["events"], list)
        self.assertTrue(detail["events"])
        self.assertIn("event", detail["events"][0])

        missing = task_detail(self.ws, "t-does-not-exist")
        self.assertEqual(set(missing.keys()), {"task", "events"})
        self.assertIsNone(missing["task"])
        self.assertEqual(missing["events"], [])

    def test_summary_counts_shape(self):
        self.write_registry(verify="exit 0")
        dispatch(self.ws, "proj", "x", adapter="custom:sh -c 'echo hello'")

        conn = self.open_conn()
        try:
            counts = summary_counts(self.ws, conn)
        finally:
            conn.close()

        self.assertEqual(counts["done"], 1)
        self.assertEqual(counts["failed"], 0)
        self.assertIn("queued", counts)
        self.assertIn("running", counts)
        self.assertIn("timeout", counts)
        for value in counts.values():
            self.assertIsInstance(value, int)


if __name__ == "__main__":
    unittest.main()
