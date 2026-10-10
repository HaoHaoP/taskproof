"""Dispatch pipeline contract.

The pipeline is the thing this project exists to provide, so it is pinned end
to end here — with a `custom:` adapter running harmless shell commands. No real
agent is ever invoked and nothing reaches the network:

  * happy path -> done, verify_cmd/verify_exit written, started + done events
  * acceptance failure -> failed, and the slot is released
  * --no-verify / read-only -> SKIPPED, never "passed"
  * a forbidden-path change -> blocked (human review), acceptance still runs
  * an adapter failure raises AdapterError and still releases the slot
  * the concurrency gate refuses a second task in the same group
  * `_run_adapter` enforces its timeout and kills the process it started
  * `task_detail` / `summary_counts` shapes
"""

import contextlib
import io
import os
import subprocess
import tempfile
import threading
import time
import unittest

from taskproof import concurrency, storage
from taskproof.adapters import get
from taskproof.dispatch import (
    TaskStateError,
    _run_adapter,
    _worktree_target_path,
    cancel_task,
    dispatch,
    prepare_workspace,
    remove_task,
    summary_counts,
    task_detail,
)
from taskproof.errors import AdapterError, ConcurrencyError, UsageError, VerifyError
from taskproof.models import (
    STATUS_BLOCKED,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_RUNNING,
    STATUS_TIMEOUT,
    STATUS_VERIFYING,
    TERMINAL_STATUSES,
)


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
    else:
        # Even without an acceptance command this is a lane: any lane field on a
        # `[[project]]` block makes it a same-named taskgroup (zero migration).
        lines.append('verify_kind = "none"')
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
    def test_forbidden_change_blocks_even_on_reported_success(self):
        subprocess.run(["git", "init", "-q"], cwd=self.proj, check=True)
        self.write_registry(verify="exit 0", forbidden=["dist/"])
        command = "custom:sh -c 'mkdir -p dist && echo x > dist/out.txt && echo done'"
        with self.assertRaises(VerifyError):
            dispatch(self.ws, "proj", "x", adapter=command)

        task_id = self.latest_task_id()
        detail = task_detail(self.ws, task_id)
        self.assertEqual(detail["task"]["status"], STATUS_BLOCKED)

        blob = " ".join(json_event_text(e) for e in detail["events"])
        self.assertIn("dist", blob)
        self.assertEqual(self.active_claims(), 0)


class ForbiddenTerminalSemanticsTest(DispatchBase):
    """Card 34 layer 2 — a boundary breach is `blocked`, and acceptance runs.

    The six true-process checks (real ``python -m taskproof`` invocations) are
    reproduced in the delivery notes; here we pin the same facts end to end
    through the pipeline the CLI drives, with a harmless ``custom:`` adapter.
    """

    def _violate(self, *, verify):
        """Dispatch a run that touches ``protected/``; return the task id."""
        self.write_registry(verify=verify, forbidden=["protected/"])
        command = (
            "custom:sh -c 'mkdir -p protected && echo x > protected/out.txt "
            "&& echo ok'"
        )
        with self.assertRaises(VerifyError) as ctx:
            dispatch(self.ws, "proj", "x", adapter=command)
        # CLI exit code stays 71: the command's outcome is a verify error even
        # though the task is recorded as `blocked`.
        self.assertEqual(ctx.exception.exit_code, 71)
        return self.latest_task_id()

    def _event(self, task_id, name):
        return next(
            e for e in task_detail(self.ws, task_id)["events"] if e["event"] == name
        )

    # ① real breach + green acceptance -> blocked, acceptance actually ran
    def test_violation_with_green_acceptance_is_blocked(self):
        task_id = self._violate(verify="exit 0")
        detail = task_detail(self.ws, task_id)
        self.assertEqual(detail["task"]["status"], STATUS_BLOCKED)
        self.assertEqual(detail["task"]["verify_cmd"], "exit 0")
        self.assertEqual(detail["task"]["verify_exit"], 0)

        names = [e["event"] for e in detail["events"]]
        self.assertIn("forbidden", names)
        self.assertIn("verify", names)
        self.assertIn("blocked", names)
        self.assertNotIn("failed", names)

        verify = self._event(task_id, "verify")["payload"]
        self.assertTrue(verify["ran"])
        self.assertEqual(verify["status"], "PASSED")
        self.assertEqual(verify["exit_code"], 0)
        self.assertEqual(self.active_claims(), 0)

    # ② real breach + red acceptance -> still blocked; both facts in the ledger
    def test_violation_with_red_acceptance_is_still_blocked(self):
        task_id = self._violate(verify="exit 1")
        detail = task_detail(self.ws, task_id)
        self.assertEqual(detail["task"]["status"], STATUS_BLOCKED)
        self.assertEqual(detail["task"]["verify_exit"], 1)

        names = [e["event"] for e in detail["events"]]
        self.assertIn("forbidden", names)
        self.assertIn("verify", names)
        self.assertNotIn("failed", names)

        verify = self._event(task_id, "verify")["payload"]
        self.assertEqual(verify["status"], "FAILED")
        self.assertEqual(verify["exit_code"], 1)
        # The `blocked` event carries both the breach and the verify verdict.
        blocked = self._event(task_id, "blocked")["payload"]
        self.assertEqual(blocked["stage"], "forbidden")
        self.assertEqual(blocked["verify"], "FAILED")
        self.assertEqual(blocked["verify_exit"], 1)

    # ③ regression: a clean run is still done
    def test_clean_run_is_done(self):
        self.write_registry(verify="exit 0", forbidden=["protected/"])
        task_id = dispatch(self.ws, "proj", "x", adapter="custom:sh -c 'echo ok'")
        detail = task_detail(self.ws, task_id)
        self.assertEqual(detail["task"]["status"], STATUS_DONE)
        self.assertNotIn("forbidden", [e["event"] for e in detail["events"]])

    # ④ regression: a red acceptance with NO breach is still `failed`
    def test_red_acceptance_without_violation_is_failed(self):
        self.write_registry(verify="exit 1", forbidden=["protected/"])
        with self.assertRaises(VerifyError):
            dispatch(self.ws, "proj", "x", adapter="custom:sh -c 'echo ok'")
        detail = task_detail(self.ws, self.latest_task_id())
        self.assertEqual(detail["task"]["status"], STATUS_FAILED)
        names = [e["event"] for e in detail["events"]]
        self.assertIn("verify", names)
        self.assertNotIn("forbidden", names)

    # ⑤ summary counts the blocked card (and nothing as failed)
    def test_summary_counts_blocked(self):
        self._violate(verify="exit 0")
        conn = self.open_conn()
        try:
            counts = summary_counts(self.ws, conn)
        finally:
            conn.close()
        self.assertEqual(counts["blocked"], 1)
        self.assertEqual(counts["failed"], 0)

    # blocked is a true terminal: no process, cancel refuses, rm allows
    def test_blocked_is_terminal_cancel_refuses_rm_allows(self):
        task_id = self._violate(verify="exit 0")
        self.assertIn(STATUS_BLOCKED, TERMINAL_STATUSES)
        with self.assertRaises(TaskStateError):
            cancel_task(self.ws, task_id)
        # The refused cancel left the terminal state untouched.
        self.assertEqual(
            task_detail(self.ws, task_id)["task"]["status"], STATUS_BLOCKED
        )
        self.assertEqual(remove_task(self.ws, task_id), task_id)


class ForbiddenSignalDiffTest(DispatchBase):
    """End-to-end coverage for the card-31 signals."""

    def _init_repo(self):
        subprocess.run(["git", "init", "-q"], cwd=self.proj, check=True)
        subprocess.run(
            ["git", "config", "user.email", "probe@example.invalid"],
            cwd=self.proj,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "probe"],
            cwd=self.proj,
            check=True,
        )

    def _commit_file(self, relative, content):
        path = os.path.join(self.proj, relative)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
        subprocess.run(["git", "add", relative], cwd=self.proj, check=True)
        subprocess.run(["git", "commit", "-qm", "seed"], cwd=self.proj, check=True)

    def _forbidden_payload(self, task_id):
        detail = task_detail(self.ws, task_id)
        event = next(e for e in detail["events"] if e["event"] == "forbidden")
        return event["payload"]

    def test_pre_existing_noise_with_noop_adapter_passes(self):
        self._init_repo()
        os.makedirs(os.path.join(self.proj, "noise"))
        with open(os.path.join(self.proj, "noise", ".DS_Store"), "w") as handle:
            handle.write("finder")
        self.write_registry(verify="exit 0", forbidden=["noise/"])

        task_id = dispatch(
            self.ws, "proj", "x", adapter="custom:sh -c 'echo ok'"
        )

        detail = task_detail(self.ws, task_id)
        self.assertEqual(detail["task"]["status"], STATUS_DONE)
        self.assertFalse(any(e["event"] == "forbidden" for e in detail["events"]))

    def test_pre_existing_noise_does_not_mask_outside_change(self):
        self._init_repo()
        self._commit_file("src/main.txt", "seed")
        os.makedirs(os.path.join(self.proj, "noise"))
        with open(os.path.join(self.proj, "noise", ".DS_Store"), "w") as handle:
            handle.write("finder")
        self.write_registry(verify="exit 0", forbidden=["noise/"])

        task_id = dispatch(
            self.ws,
            "proj",
            "x",
            adapter=(
                "custom:sh -c 'printf changed > src/main.txt && echo ok'"
            ),
        )

        self.assertEqual(
            task_detail(self.ws, task_id)["task"]["status"], STATUS_DONE
        )

    def test_presence_reports_a_new_file(self):
        self._init_repo()
        os.makedirs(os.path.join(self.proj, "dist"))
        with open(os.path.join(self.proj, "dist", "keep.txt"), "w") as handle:
            handle.write("keep")
        self.write_registry(verify="exit 0", forbidden=["presence:dist/"])

        with self.assertRaises(VerifyError) as ctx:
            dispatch(
                self.ws,
                "proj",
                "x",
                adapter=(
                    "custom:sh -c 'printf new > dist/new.js && echo ok'"
                ),
            )

        self.assertEqual(ctx.exception.exit_code, 71)
        payload = self._forbidden_payload(self.latest_task_id())
        self.assertEqual(payload["violations"][0]["kind"], "presence")
        self.assertEqual(payload["violations"][0]["rule"], "presence:dist/")
        self.assertIn("dist/new.js", payload["violations"][0]["paths"])

    def test_presence_ignores_other_process_rewriting_existing_file(self):
        self._init_repo()
        self._commit_file("dist/app.js", "seed")
        self.write_registry(verify="exit 0", forbidden=["presence:dist/"])

        task_id = dispatch(
            self.ws,
            "proj",
            "x",
            adapter=(
                "custom:sh -c '(sleep 0.2; "
                "printf devserver-rewrite > dist/app.js) & sleep 0.6; echo ok'"
            ),
        )

        self.assertEqual(
            task_detail(self.ws, task_id)["task"]["status"], STATUS_DONE
        )

    def test_presence_ignores_adapter_rewriting_existing_file(self):
        self._init_repo()
        self._commit_file("dist/app.js", "seed")
        self.write_registry(verify="exit 0", forbidden=["presence:dist/"])

        task_id = dispatch(
            self.ws,
            "proj",
            "x",
            adapter=(
                "custom:sh -c 'printf adapter-rewrite > dist/app.js && echo ok'"
            ),
        )

        self.assertEqual(
            task_detail(self.ws, task_id)["task"]["status"], STATUS_DONE
        )

    def test_explicit_git_rule_reports_a_commit_as_git_state(self):
        self._init_repo()
        self.write_registry(verify="exit 0", forbidden=["git:.git/"])
        with self.assertRaises(VerifyError) as ctx:
            dispatch(
                self.ws,
                "proj",
                "x",
                adapter=(
                    "custom:sh -c 'git -C {workdir} commit --allow-empty "
                    "-qm probe && echo ok'"
                ),
            )
        self.assertEqual(ctx.exception.exit_code, 71)
        payload = self._forbidden_payload(self.latest_task_id())
        violation = payload["violations"][0]
        self.assertEqual(violation["kind"], "git-state")
        self.assertEqual(violation["rule"], "git:.git/")
        self.assertIn("HEAD", violation["changed"])

    def test_explicit_file_dot_git_rule_matches_legacy_untargeted_behavior(self):
        # `file:.git/` deliberately opts back into the file-fingerprint signal
        # for the `.git/` tree, the same tree legacy untyped non-`.git` rules
        # fingerprint. A commit mutates that tree, so it is a violation.
        self._init_repo()
        self.write_registry(verify="exit 0", forbidden=["file:.git/"])
        with self.assertRaises(VerifyError) as ctx:
            dispatch(
                self.ws,
                "proj",
                "x",
                adapter=(
                    "custom:sh -c 'git -C {workdir} commit --allow-empty "
                    "-qm probe && echo ok'"
                ),
            )
        self.assertEqual(ctx.exception.exit_code, 71)

    def test_file_rule_still_reports_content_rewrite(self):
        self._init_repo()
        self._commit_file("protected/keep.txt", "seed")
        self.write_registry(verify="exit 0", forbidden=["protected/"])

        with self.assertRaises(VerifyError) as ctx:
            dispatch(
                self.ws,
                "proj",
                "x",
                adapter=(
                    "custom:sh -c 'printf adapter-rewrite > protected/keep.txt "
                    "&& echo ok'"
                ),
            )

        self.assertEqual(ctx.exception.exit_code, 71)
        payload = self._forbidden_payload(self.latest_task_id())
        self.assertEqual(payload["violations"][0]["kind"], "file")
        self.assertIn("protected/keep.txt", payload["violations"][0]["paths"])


class PythonBytecodeGateTest(DispatchBase):
    """Card 46: running Python must not trip a forbidden source-directory rule.

    Reproduces card 45: a desktop card (forbidden ``t/`` == "do not touch the
    Python source") ran Python inside its worktree, which dropped a ``.pyc``
    under ``t/__pycache__/``; the real gate then reported ``blocked``. The
    byte-code exemption makes that a ``done`` run while a genuine edit under the
    same rule is still caught.
    """

    def _init_repo(self):
        subprocess.run(["git", "init", "-q"], cwd=self.proj, check=True)
        subprocess.run(
            ["git", "config", "user.email", "probe@example.invalid"],
            cwd=self.proj,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "probe"],
            cwd=self.proj,
            check=True,
        )

    def _commit_file(self, relative, content):
        path = os.path.join(self.proj, relative)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
        subprocess.run(["git", "add", relative], cwd=self.proj, check=True)
        subprocess.run(["git", "commit", "-qm", "seed"], cwd=self.proj, check=True)

    def _forbidden_payload(self, task_id):
        detail = task_detail(self.ws, task_id)
        event = next(e for e in detail["events"] if e["event"] == "forbidden")
        return event["payload"]

    def test_bytecode_under_a_forbidden_dir_is_not_a_breach(self):
        # `t/` is in .gitignore so only the fingerprint backstop can see it.
        self._init_repo()
        self._commit_file("t/keep.py", "keep")
        self.write_registry(verify="exit 0", forbidden=["t/"])
        with open(os.path.join(self.proj, ".gitignore"), "w") as handle:
            handle.write("__pycache__/\n")
        subprocess.run(["git", "add", ".gitignore"], cwd=self.proj, check=True)
        subprocess.run(["git", "commit", "-qm", "ignore"], cwd=self.proj, check=True)

        task_id = dispatch(
            self.ws,
            "proj",
            "x",
            adapter=(
                "custom:sh -c 'mkdir -p t/__pycache__ && "
                "echo x > t/__pycache__/mod.cpython-314.pyc && echo ok'"
            ),
        )

        detail = task_detail(self.ws, task_id)
        self.assertEqual(detail["task"]["status"], STATUS_DONE)
        self.assertFalse(any(e["event"] == "forbidden" for e in detail["events"]))

    def test_new_python_source_under_a_forbidden_dir_is_still_blocked(self):
        self._init_repo()
        self._commit_file("t/keep.py", "keep")
        self.write_registry(verify="exit 0", forbidden=["t/"])

        with self.assertRaises(VerifyError) as ctx:
            dispatch(
                self.ws,
                "proj",
                "x",
                adapter=(
                    "custom:sh -c 'printf evil > t/evil.py && echo ok'"
                ),
            )

        self.assertEqual(ctx.exception.exit_code, 71)
        self.assertEqual(
            task_detail(self.ws, self.latest_task_id())["task"]["status"],
            STATUS_BLOCKED,
        )
        self.assertIn(
            "t/evil.py", self._forbidden_payload(self.latest_task_id())["violations"][0]["paths"]
        )

    def test_existing_tracked_file_under_a_forbidden_dir_is_still_blocked(self):
        self._init_repo()
        self._commit_file("t/keep.py", "keep")
        self.write_registry(verify="exit 0", forbidden=["t/"])

        with self.assertRaises(VerifyError) as ctx:
            dispatch(
                self.ws,
                "proj",
                "x",
                adapter=(
                    "custom:sh -c 'printf changed > t/keep.py && echo ok'"
                ),
            )

        self.assertEqual(ctx.exception.exit_code, 71)
        self.assertEqual(
            task_detail(self.ws, self.latest_task_id())["task"]["status"],
            STATUS_BLOCKED,
        )


class GitStateForbiddenTest(DispatchBase):
    def _init_repo(self):
        subprocess.run(["git", "init", "-q"], cwd=self.proj, check=True)
        subprocess.run(
            ["git", "config", "user.email", "probe@example.invalid"],
            cwd=self.proj,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "probe"],
            cwd=self.proj,
            check=True,
        )

    def _forbidden_payload(self, task_id):
        detail = task_detail(self.ws, task_id)
        event = next(e for e in detail["events"] if e["event"] == "forbidden")
        return event["payload"]

    def test_read_only_status_is_not_a_forbidden_change(self):
        self._init_repo()
        tracked = os.path.join(self.proj, "tracked.txt")
        with open(tracked, "w") as handle:
            handle.write("seed\n")
        subprocess.run(["git", "add", "tracked.txt"], cwd=self.proj, check=True)
        subprocess.run(
            ["git", "commit", "-qm", "seed"], cwd=self.proj, check=True
        )
        # Force `git status` to refresh the index during the adapter run.
        os.utime(tracked, None)
        self.write_registry(verify="exit 0", forbidden=[".git/"])

        task_id = dispatch(
            self.ws,
            "proj",
            "x",
            adapter=(
                "custom:sh -c 'git status --porcelain && "
                "git diff --quiet || true; echo ok'"
            ),
        )

        detail = task_detail(self.ws, task_id)
        self.assertEqual(detail["task"]["status"], STATUS_DONE)
        self.assertIn("verify", [e["event"] for e in detail["events"]])

    def test_no_op_in_repo_is_not_a_forbidden_change(self):
        self._init_repo()
        subprocess.run(
            ["git", "commit", "--allow-empty", "-qm", "seed"],
            cwd=self.proj,
            check=True,
        )
        self.write_registry(verify="exit 0", forbidden=[".git/"])
        task_id = dispatch(
            self.ws, "proj", "x", adapter="custom:sh -c 'echo ok'"
        )
        detail = task_detail(self.ws, task_id)
        self.assertEqual(detail["task"]["status"], STATUS_DONE)
        self.assertIn("verify", [e["event"] for e in detail["events"]])

    def test_commit_is_a_git_state_violation(self):
        self._init_repo()
        self.write_registry(verify="exit 0", forbidden=[".git/"])
        with self.assertRaises(VerifyError) as ctx:
            dispatch(
                self.ws,
                "proj",
                "x",
                adapter=(
                    "custom:sh -c 'git -C {workdir} commit --allow-empty "
                    "-qm probe && echo ok'"
                ),
            )
        self.assertEqual(ctx.exception.exit_code, 71)

        payload = self._forbidden_payload(self.latest_task_id())
        git_violation = next(v for v in payload["violations"] if v["kind"] == "git-state")
        self.assertIn("HEAD", git_violation["changed"])

    def test_branch_change_is_a_git_state_violation(self):
        self._init_repo()
        subprocess.run(
            ["git", "commit", "--allow-empty", "-qm", "seed"],
            cwd=self.proj,
            check=True,
        )
        self.write_registry(verify="exit 0", forbidden=[".git/"])
        with self.assertRaises(VerifyError) as ctx:
            dispatch(
                self.ws,
                "proj",
                "x",
                adapter=(
                    "custom:sh -c 'git -C {workdir} checkout -q -b probe-branch "
                    "&& echo ok'"
                ),
            )
        self.assertEqual(ctx.exception.exit_code, 71)
        payload = self._forbidden_payload(self.latest_task_id())
        self.assertEqual(payload["violations"][0]["kind"], "git-state")

    def test_non_git_rule_stays_a_file_violation(self):
        self._init_repo()
        self.write_registry(verify="exit 0", forbidden=["protected/"])
        with self.assertRaises(VerifyError) as ctx:
            dispatch(
                self.ws,
                "proj",
                "x",
                adapter=(
                    "custom:sh -c 'mkdir -p protected && echo x > protected/x "
                    "&& echo ok'"
                ),
            )
        self.assertEqual(ctx.exception.exit_code, 71)

        payload = self._forbidden_payload(self.latest_task_id())
        file_violation = next(v for v in payload["violations"] if v["kind"] == "file")
        self.assertEqual(file_violation["rule"], "protected/")
        self.assertIn("protected/x", file_violation["paths"])

    def test_git_rule_with_no_repo_is_not_a_violation(self):
        self.write_registry(verify="exit 0", forbidden=[".git/"])
        task_id = dispatch(
            self.ws, "proj", "x", adapter="custom:sh -c 'echo ok'"
        )
        self.assertEqual(
            task_detail(self.ws, task_id)["task"]["status"], STATUS_DONE
        )


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
            # The lock is the taskgroup id ("proj"); the legacy `group` key is
            # not a lane knob any more.
            scopes = concurrency.acquire(conn, "t-other", "proj", cap=3, ttl=60)
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
    """`--worktree` keeps a run's uncommitted work, and only that.

    The card this pins: a worktree run with changes must NOT be discarded, so
    the checkout is kept beside the repo and announced. A clean run still
    removes it, exactly as before, and a plain run is untouched by any of it.
    """

    def _git_repo(self):
        subprocess.run(["git", "init", "-q"], cwd=self.proj, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=self.proj, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=self.proj, check=True)
        with open(os.path.join(self.proj, "seed.txt"), "w", encoding="utf-8") as fh:
            fh.write("seed\n")
        subprocess.run(["git", "add", "seed.txt"], cwd=self.proj, check=True)
        subprocess.run(["git", "commit", "-qm", "seed"], cwd=self.proj, check=True)

    def _run(self, command, **kwargs):
        """Dispatch a worktree run with stdout captured -> (task_id, stdout)."""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            task_id = dispatch(
                self.ws, "proj", "x", worktree=True, adapter=command, **kwargs
            )
        return task_id, buf.getvalue()

    def _events(self, task_id):
        return task_detail(self.ws, task_id)["events"]

    def _worktree_listing(self):
        return subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=self.proj,
            stdout=subprocess.PIPE,
            text=True,
            check=True,
        ).stdout

    def test_worktree_with_changes_is_kept_and_printed(self):
        self._git_repo()
        self.write_registry(verify="exit 0")
        task_id, out = self._run("custom:sh -c 'echo made > made.txt && echo ok'")

        self.assertEqual(task_detail(self.ws, task_id)["task"]["status"], STATUS_DONE)
        expected = os.path.join(self.tmp, f"project-wt-{task_id}")
        # Kept, beside the repo, carrying the uncommitted change...
        self.assertTrue(os.path.isdir(expected))
        self.assertNotEqual(
            subprocess.run(
                ["git", "-C", expected, "status", "--porcelain"],
                stdout=subprocess.PIPE,
                text=True,
                check=True,
            ).stdout.strip(),
            "",
        )
        # ...while the main checkout was never touched.
        self.assertFalse(os.path.exists(os.path.join(self.proj, "made.txt")))
        # stdout names the path and the change count.
        self.assertIn(f"worktree kept: {expected}", out)
        self.assertIn("1 files changed", out)
        # The `worktree` event records path + changed.
        kept = [e for e in self._events(task_id) if e["event"] == "worktree"]
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["payload"]["path"], expected)
        self.assertEqual(kept[0]["payload"]["changed"], 1)
        self.assertEqual(self.active_claims(), 0)

    def test_worktree_without_changes_is_removed(self):
        self._git_repo()
        self.write_registry(verify="exit 0")
        task_id, out = self._run("custom:sh -c 'echo ok'")

        self.assertEqual(task_detail(self.ws, task_id)["task"]["status"], STATUS_DONE)
        expected = os.path.join(self.tmp, f"project-wt-{task_id}")
        self.assertFalse(os.path.exists(expected))
        self.assertNotIn("worktree kept", out)
        # Only the main checkout remains; nothing kept, nothing left behind.
        self.assertEqual(self._worktree_listing().count("worktree "), 1)
        names = [e["event"] for e in self._events(task_id)]
        self.assertIn("worktree_removed", names)
        self.assertNotIn("worktree", names)

    def test_worktree_path_is_fresh_each_run(self):
        self._git_repo()
        self.write_registry(verify="exit 0")
        first, _ = self._run("custom:sh -c 'echo a > a.txt && echo ok'")
        second, _ = self._run("custom:sh -c 'echo b > b.txt && echo ok'")

        self.assertNotEqual(first, second)
        p1 = os.path.join(self.tmp, f"project-wt-{first}")
        p2 = os.path.join(self.tmp, f"project-wt-{second}")
        self.assertTrue(os.path.isdir(p1))
        self.assertTrue(os.path.isdir(p2))
        self.assertNotEqual(p1, p2)
        # Two kept checkouts plus the main one.
        self.assertEqual(self._worktree_listing().count("worktree "), 3)

    def test_worktree_target_path_avoids_a_taken_name(self):
        # Re-running into an already-taken name must not collide: the helper
        # yields a fresh sibling rather than reusing the existing directory.
        self._git_repo()
        taken = os.path.join(self.tmp, "project-wt-20000101-001")
        os.makedirs(taken)
        fresh = _worktree_target_path(self.proj, "20000101-001")
        self.assertNotEqual(fresh, taken)
        self.assertTrue(fresh.startswith(taken + "-"))
        self.assertFalse(os.path.exists(fresh))

    def test_rm_deletes_a_kept_worktree(self):
        self._git_repo()
        self.write_registry(verify="exit 0")
        task_id, _ = self._run("custom:sh -c 'echo made > made.txt && echo ok'")
        kept = os.path.join(self.tmp, f"project-wt-{task_id}")
        self.assertTrue(os.path.isdir(kept))

        remove_task(self.ws, task_id)

        self.assertFalse(os.path.exists(kept))
        self.assertIsNone(task_detail(self.ws, task_id)["task"])
        # Only the main checkout survives in git's registry too.
        self.assertEqual(self._worktree_listing().count("worktree "), 1)

    def test_without_worktree_keeps_todays_behaviour(self):
        self._git_repo()
        self.write_registry(verify="exit 0")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            task_id = dispatch(
                self.ws, "proj", "x",
                adapter="custom:sh -c 'echo made > made.txt && echo ok'",
            )
        # No worktree anywhere: no event, no stdout line, change in the repo.
        names = [e["event"] for e in self._events(task_id)]
        self.assertFalse(any(n.startswith("worktree") for n in names))
        self.assertNotIn("worktree kept", buf.getvalue())
        self.assertTrue(os.path.exists(os.path.join(self.proj, "made.txt")))
        self.assertEqual(self._worktree_listing().count("worktree "), 1)

    def test_workdir_is_the_worktree_while_running(self):
        """Card 55: a --worktree run records the *worktree* path as its workdir.

        A real run (not a hand-built row) is driven on a worker thread so we can
        read the row back during the running window. The workdir must be the
        fresh checkout, never the main project path -- the live
        `files_changed_live` probe would otherwise count the wrong tree.
        """
        self._git_repo()
        self.write_registry(verify="exit 0")

        result = {}

        def _run():
            result["task_id"] = dispatch(
                self.ws, "proj", "x", worktree=True,
                adapter="custom:sh -c 'sleep 1.5; echo done'",
            )

        worker = threading.Thread(target=_run)
        worker.start()
        try:
            # The id is minted inside dispatch, so discover it from the row the
            # run is writing: wait for a running row that already carries its
            # workdir (the status insert and the workdir update are not atomic,
            # so `running` alone can be observed a beat before the path).
            deadline = time.monotonic() + 20.0
            row = None
            while time.monotonic() < deadline:
                conn = self.open_conn()
                try:
                    candidates = storage.list_tasks(
                        conn, status=STATUS_RUNNING, limit=5
                    )
                finally:
                    conn.close()
                for candidate in candidates:
                    if candidate["workdir"]:
                        row = dict(candidate)
                        break
                if row is not None:
                    break
                time.sleep(0.05)
            self.assertIsNotNone(row, "no running row observed for the worktree run")

            task_id = row["id"]
            expected = os.path.join(self.tmp, f"project-wt-{task_id}")
            # The recorded workdir is the checkout, provably not the main tree.
            self.assertEqual(row["workdir"], expected)
            self.assertNotEqual(row["workdir"], self.proj)
            self.assertTrue(os.path.isdir(expected))
        finally:
            worker.join(timeout=30)
        self.assertFalse(worker.is_alive())
        self.assertEqual(result.get("task_id"), task_id)
        self.assertEqual(
            task_detail(self.ws, task_id)["task"]["status"], STATUS_DONE
        )
        # The finish write keeps the same worktree path.
        conn = self.open_conn()
        try:
            self.assertEqual(
                storage.get_task(conn, task_id)["workdir"],
                os.path.join(self.tmp, f"project-wt-{task_id}"),
            )
        finally:
            conn.close()

    def test_worktree_requires_git_repo(self):
        self.write_registry(verify="exit 0")  # self.proj is a plain directory
        with self.assertRaises(UsageError):
            dispatch(self.ws, "proj", "x", worktree=True,
                     adapter="custom:sh -c 'echo hello'")
        self.assertEqual(self.active_claims(), 0)


class VerifyingLifecycleTest(DispatchBase):
    """The acceptance window is a real, observable ``verifying`` state.

    The evidence is a *real* run: a ``custom:`` adapter finishes quickly, then a
    slow acceptance command holds the card in ``verifying`` long enough to catch
    it in the database. No hand-built ``Task(status="verifying")`` is involved --
    the point is that ``dispatch`` itself persists the state.
    """

    def test_acceptance_window_persists_verifying_then_done(self):
        self.write_registry(verify="sh -c 'sleep 1.5; echo ok'")

        result = {}

        def _run():
            result["task_id"] = dispatch(
                self.ws,
                "proj",
                "x",
                adapter="custom:sh -c 'sleep 0.2; echo done'",
            )

        worker = threading.Thread(target=_run)
        worker.start()
        task_id = None
        seen_verifying = False
        deadline = time.monotonic() + 30.0
        try:
            while time.monotonic() < deadline:
                conn = self.open_conn()
                try:
                    rows = {
                        r["id"]: r["status"]
                        for r in storage.list_tasks(conn, limit=10)
                    }
                finally:
                    conn.close()
                if task_id is None:
                    for candidate_id in rows:
                        task_id = candidate_id
                        break
                if task_id is not None and rows.get(task_id) == STATUS_VERIFYING:
                    seen_verifying = True
                    break
                if task_id is not None and rows.get(task_id) in TERMINAL_STATUSES:
                    break
                time.sleep(0.02)
        finally:
            worker.join(timeout=30)

        self.assertFalse(worker.is_alive())
        self.assertIsNotNone(task_id, "no task row observed for the run")
        self.assertTrue(seen_verifying, "never observed the card in `verifying`")
        detail = task_detail(self.ws, task_id)
        self.assertEqual(detail["task"]["status"], STATUS_DONE)
        events = [e["event"] for e in detail["events"]]
        self.assertIn("verifying", events)


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
        self.assertIn("running", counts)
        self.assertIn("timeout", counts)
        for value in counts.values():
            self.assertIsInstance(value, int)


if __name__ == "__main__":
    unittest.main()
