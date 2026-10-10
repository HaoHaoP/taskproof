"""Card 36 layer 3: `accept <id>` (clearing a blocked card) and `rerun <id>`
(ledger-linked re-dispatch).

Everything here runs a harmless ``custom:`` adapter in a throwaway workspace —
no real agent is invoked and nothing reaches the network. The ``RealProcess``
classes drive the installed CLI as a subprocess so the seven delivery checks
run through the actual documented door, not just the in-process handler.
"""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

from taskproof import cli, dispatch, ledger, storage
from taskproof.errors import VerifyError
from taskproof.models import (
    STATUS_BLOCKED,
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_RUNNING,
    STATUS_TIMEOUT,
)

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: A run that touches the protected ``protected/`` tree, harmless elsewhere.
_BREACH = (
    "custom:sh -c 'mkdir -p protected && echo x > protected/out.txt && echo ok'"
)
_CLEAN = "custom:echo hi"


def _env():
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(_REPO, "src")
    return env


def _q(value) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def registry_toml(path, *, verify="exit 0", forbidden=("protected/",)) -> str:
    lines = [
        "[defaults]",
        "concurrency = 3",
        "timeout = 60",
        "",
        "[[project]]",
        'id = "proj"',
        f"path = {_q(path)}",
        'group = "proj"',
    ]
    if verify is not None:
        lines.append(f"verify = {_q(verify)}")
        lines.append('verify_kind = "check"')
    if forbidden:
        joined = ", ".join(_q(f) for f in forbidden)
        lines.append(f"forbidden_paths = [{joined}]")
    return "\n".join(lines) + "\n"


class _Base(unittest.TestCase):
    verify = "exit 0"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.ws = os.path.join(self.tmp, "workspace")
        self.proj = os.path.join(self.tmp, "project")
        os.makedirs(self.proj)
        dispatch.prepare_workspace(self.ws)
        self.write_registry()

    def tearDown(self):
        self._tmp.cleanup()

    # -- helpers -----------------------------------------------------------

    def write_registry(self, *, verify=None, forbidden=("protected/",)):
        if verify is None:
            verify = self.verify
        with open(os.path.join(self.ws, "projects.toml"), "w", encoding="utf-8") as fh:
            fh.write(registry_toml(self.proj, verify=verify, forbidden=forbidden))

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["--workspace", self.ws, "--json", *argv])
        return code, out.getvalue(), err.getvalue()

    def open_conn(self):
        conn = storage.connect(storage.db_path(self.ws))
        storage.migrate(conn)
        return conn

    def row(self, task_id):
        conn = self.open_conn()
        try:
            got = storage.get_task(conn, task_id)
            return dict(got) if got is not None else None
        finally:
            conn.close()

    def latest_id(self):
        # `list_tasks` orders by `created_at`, which is second-resolution: two
        # dispatches in the same second tie. Tests need the most recently
        # *inserted* row, so order by the implicit rowid instead.
        conn = self.open_conn()
        try:
            got = conn.execute(
                "SELECT id FROM tasks ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            return got[0] if got else None
        finally:
            conn.close()

    def events(self, task_id):
        return dispatch.task_detail(self.ws, task_id)["events"]

    def latest_event(self, task_id, name):
        found = [e for e in self.events(task_id) if e["event"] == name]
        return found[-1] if found else None

    def breach(self, *, verify="exit 0"):
        """Dispatch a run that touches ``protected/``; return the blocked id."""
        self.write_registry(verify=verify)
        with self.assertRaises(VerifyError):
            dispatch.dispatch(self.ws, "proj", "breach", adapter=_BREACH)
        return self.latest_id()

    def non_terminal(self, brief="pending", status=STATUS_RUNNING):
        """Insert a non-terminal row directly and return its id.

        The queue is gone, so there is no ``--park`` to mint a non-terminal
        card. The lifecycle guards under test only read the row's status, so a
        row written straight into the store is the honest fixture.
        """
        self._row_seq = getattr(self, "_row_seq", 0) + 1
        task_id = f"t-20261010-9{self._row_seq:02d}"
        conn = self.open_conn()
        try:
            storage.insert_task(conn, {
                "id": task_id,
                "project": "proj",
                "group": "proj",
                "brief": brief,
                "status": status,
                "adapter": _CLEAN,
            })
        finally:
            conn.close()
        return task_id

    def red(self, *, verify="exit 1"):
        """Dispatch a clean run whose acceptance goes red; return the failed id."""
        self.write_registry(verify=verify)
        with self.assertRaises(VerifyError):
            dispatch.dispatch(self.ws, "proj", "red", adapter=_CLEAN)
        return self.latest_id()

    def timed_out(self):
        """Dispatch an adapter that outlives its own timeout; return a timeout id."""
        with self.assertRaises(VerifyError):
            dispatch.dispatch(
                self.ws, "proj", "slow", adapter="custom:sleep 5", timeout=1
            )
        return self.latest_id()

    def cancelled(self):
        """Insert a running card and cancel it; return the cancelled id."""
        running = self.non_terminal("drop me")
        dispatch.cancel_task(self.ws, running)
        return running


# ---------------------------------------------------------------------------
# ①②③ accept
# ---------------------------------------------------------------------------


class AcceptTest(_Base):
    # ① breach + green acceptance -> accept flips blocked to done
    def test_accept_green_goes_done_and_records_the_breach(self):
        task_id = self.breach(verify="exit 0")
        self.assertEqual(self.row(task_id)["status"], STATUS_BLOCKED)

        code, out, err = self.run_cli("accept", task_id)
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["task_id"], task_id)
        self.assertEqual(payload["status"], STATUS_DONE)
        self.assertEqual(self.row(task_id)["status"], STATUS_DONE)

        event = self.latest_event(task_id, "accepted")
        self.assertIsNotNone(event)
        p = event["payload"]
        self.assertEqual(p["by"], "cli")
        self.assertEqual(p["verify"], "passed")
        self.assertEqual(p["verify_exit"], 0)
        self.assertEqual(p["from"], "blocked")
        self.assertEqual(p["to"], "done")
        # The breach this acceptance confirms rides along verbatim.
        self.assertIn("protected/", p["rules"])
        self.assertIn("protected/out.txt", p["paths"])
        self.assertTrue(p["violations"])
        # Acceptance is not a re-run: the verify columns are untouched.
        self.assertEqual(self.row(task_id)["verify_exit"], 0)

    # ② breach + red acceptance -> accept flips blocked to failed, still accepted
    def test_accept_red_goes_failed_but_still_records_accepted(self):
        task_id = self.breach(verify="exit 1")
        self.assertEqual(self.row(task_id)["status"], STATUS_BLOCKED)
        self.assertEqual(self.row(task_id)["verify_exit"], 1)

        code, out, err = self.run_cli("accept", task_id)
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["status"], STATUS_FAILED)
        self.assertEqual(self.row(task_id)["status"], STATUS_FAILED)

        event = self.latest_event(task_id, "accepted")
        self.assertIsNotNone(event)
        self.assertEqual(event["payload"]["verify"], "failed")
        self.assertEqual(event["payload"]["verify_exit"], 1)
        self.assertEqual(event["payload"]["to"], "failed")

    # A skip (no acceptance ran) is treated like a red: the work is not proven.
    def test_accept_skipped_goes_failed(self):
        self.write_registry(verify="exit 0")
        with self.assertRaises(VerifyError):
            dispatch.dispatch(
                self.ws, "proj", "breach", adapter=_BREACH, skip_verify=True
            )
        task_id = self.latest_id()
        self.assertIsNone(self.row(task_id)["verify_exit"])

        code, _out, err = self.run_cli("accept", task_id)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.row(task_id)["status"], STATUS_FAILED)
        self.assertEqual(self.latest_event(task_id, "accepted")["payload"]["verify"], "skipped")

    # ③ accept works on blocked (note optional) and failed (note required);
    # every other state is refused, unchanged.
    def test_accept_refuses_done_timeout_cancelled_and_running(self):
        done = dispatch.dispatch(self.ws, "proj", "clean", adapter=_CLEAN)
        timeout = self.timed_out()
        cancelled = self.cancelled()
        running = self.non_terminal("pending")

        for task_id, before in (
            (done, STATUS_DONE),
            (timeout, STATUS_TIMEOUT),
            (cancelled, STATUS_CANCELLED),
            (running, STATUS_RUNNING),
        ):
            self.assertEqual(self.row(task_id)["status"], before)
            code, _out, err = self.run_cli("accept", task_id)
            self.assertNotEqual(code, 0, task_id)
            self.assertIn("only a blocked or failed task", err)
            # The terminal state was not silently rewritten.
            self.assertEqual(self.row(task_id)["status"], before)
            self.assertIsNone(self.latest_event(task_id, "accepted"))


# ---------------------------------------------------------------------------
# failed -> done: a human sign-off that must leave a note
# ---------------------------------------------------------------------------


class AcceptFailedTest(_Base):
    NOTE = "假红：机器繁忙导致 8s 等待超时；成果已复核并合并"

    # A failed card is refused without a note; the row and ledger are untouched.
    def test_failed_without_note_is_refused_before_anything_changes(self):
        task_id = self.red(verify="exit 1")
        before = self.row(task_id)
        events_before = self.events(task_id)
        self.assertEqual(before["status"], STATUS_FAILED)

        for argv in (
            ("accept", task_id),
            ("accept", task_id, "--note", ""),
            ("accept", task_id, "--note", "   "),
        ):
            code, _out, err = self.run_cli(*argv)
            self.assertNotEqual(code, 0, argv)
            self.assertIn("人工收尾必须留说明", err)

        self.assertEqual(self.row(task_id)["status"], STATUS_FAILED)
        # One event, one status: nothing changed at all.
        self.assertEqual(len(self.events(task_id)), len(events_before))
        self.assertIsNone(self.latest_event(task_id, "accepted"))

    # A failed card with a note is closed as done, keeping the run's own facts.
    def test_failed_with_note_goes_done_and_preserves_verify_facts(self):
        task_id = self.red(verify="exit 1")
        before = self.row(task_id)
        self.assertEqual(before["status"], STATUS_FAILED)
        self.assertEqual(before["verify_exit"], 1)
        accepted_before = len(
            [e for e in self.events(task_id) if e["event"] == "accepted"]
        )

        code, out, err = self.run_cli("accept", task_id, "--note", self.NOTE)
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["status"], STATUS_DONE)

        after = self.row(task_id)
        self.assertEqual(after["status"], STATUS_DONE)
        # `accept` only moves `status`; the run's own facts are frozen.
        for column in (
            "verify_exit",
            "verify_cmd",
            "files_changed",
            "finished_at",
            "exit_code",
        ):
            self.assertEqual(after[column], before[column], column)

        events = self.events(task_id)
        accepted = [e for e in events if e["event"] == "accepted"]
        # Exactly one new `accepted` event; nothing else was appended.
        self.assertEqual(len(accepted), accepted_before + 1)
        p = accepted[-1]["payload"]
        self.assertEqual(p["by"], "cli")
        self.assertEqual(p["from"], "failed")
        self.assertEqual(p["to"], "done")
        self.assertEqual(p["note"], self.NOTE)  # verbatim, not trimmed
        self.assertEqual(p["verify_exit"], before["verify_exit"])
        self.assertEqual(p["files_changed"], before["files_changed"])

    # The note is preserved exactly even when surrounded by whitespace.
    def test_note_is_recorded_verbatim(self):
        task_id = self.red(verify="exit 1")
        code, _out, err = self.run_cli("accept", task_id, "--note", " keep me ")
        self.assertEqual(code, 0, err)
        self.assertEqual(
            self.latest_event(task_id, "accepted")["payload"]["note"], " keep me "
        )


# ---------------------------------------------------------------------------
# ⑤⑥ rerun
# ---------------------------------------------------------------------------


class RerunTest(_Base):
    # ⑤ rerun a terminal card: new id, same brief + flags, really runs, linked
    def test_rerun_terminal_card_reuses_brief_and_flags(self):
        old = dispatch.dispatch(
            self.ws, "proj", "hello world", adapter="custom:echo hi",
            model="gpt-x", reasoning="high", timeout=42,
        )
        self.assertEqual(self.row(old)["status"], STATUS_DONE)

        code, out, err = self.run_cli("rerun", old)
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        new = payload["task_id"]
        self.assertNotEqual(new, old)
        self.assertEqual(payload["rerun_of"], old)

        old_row, new_row = self.row(old), self.row(new)
        self.assertEqual(new_row["brief"], old_row["brief"])
        self.assertEqual(new_row["adapter"], old_row["adapter"])
        self.assertEqual(new_row["model"], "gpt-x")
        self.assertEqual(new_row["reasoning"], "high")
        self.assertEqual(new_row["status"], STATUS_DONE)  # it really ran

        # The recovered timeout rides on the new card's `started` event.
        started = self.latest_event(new, "started")
        self.assertEqual(started["payload"]["timeout"], 42)
        self.assertFalse(started["payload"]["read_only"])
        self.assertFalse(started["payload"]["worktree"])

        # Both cards can find each other through `log --json`.
        code, out, _ = self.run_cli("log", old)
        old_rerun = [
            e["payload"] for e in json.loads(out)["events"] if e["event"] == "rerun"
        ]
        self.assertIn({"rerun_as": new}, old_rerun)

        code, out, _ = self.run_cli("log", new)
        new_rerun = [
            e["payload"] for e in json.loads(out)["events"] if e["event"] == "rerun"
        ]
        self.assertIn({"rerun_of": old}, new_rerun)

    def test_rerun_is_allowed_on_a_blocked_card(self):
        old = self.breach(verify="exit 0")
        self.assertEqual(self.row(old)["status"], STATUS_BLOCKED)

        # A blocked card is terminal, so rerun is allowed. Its adapter is reused
        # verbatim, so drop the boundary here and the fresh copy runs clean
        # rather than re-breaching; the point under test is that rerun is *not*
        # refused on a blocked card.
        self.write_registry(verify="exit 0", forbidden=())
        code, out, err = self.run_cli("rerun", old)
        self.assertEqual(code, 0, err)
        new = json.loads(out)["task_id"]
        self.assertNotEqual(new, old)
        self.assertEqual(self.row(new)["status"], STATUS_DONE)
        # Both directions of the ledger link are present.
        self.assertIn({"rerun_of": old}, [
            e["payload"] for e in self.events(new) if e["event"] == "rerun"
        ])
        self.assertIn({"rerun_as": new}, [
            e["payload"] for e in self.events(old) if e["event"] == "rerun"
        ])

    # ⑥ rerun refuses a non-terminal card
    def test_rerun_non_terminal_is_refused(self):
        running = self.non_terminal("pending")
        code, _out, err = self.run_cli("rerun", running)
        self.assertNotEqual(code, 0)
        self.assertIn("only a terminal task can be rerun", err)
        # No new card was minted.
        conn = self.open_conn()
        try:
            self.assertEqual(len(storage.list_tasks(conn, limit=50)), 1)
        finally:
            conn.close()

    def test_rerun_unknown_id_is_usage_error(self):
        code, _out, err = self.run_cli("rerun", "t-nope")
        self.assertNotEqual(code, 0)
        self.assertIn("no such task", err)


# ---------------------------------------------------------------------------
# ⑦ verify stays a read-only-of-status operation
# ---------------------------------------------------------------------------


class VerifyRegressionTest(_Base):
    def test_verify_reruns_acceptance_without_touching_the_status(self):
        self.write_registry(verify="exit 1")
        with self.assertRaises(VerifyError):
            dispatch.dispatch(self.ws, "proj", "red", adapter=_CLEAN)
        task_id = self.latest_id()
        self.assertEqual(self.row(task_id)["status"], STATUS_FAILED)
        self.assertEqual(self.row(task_id)["verify_exit"], 1)

        # Acceptance is now green, but the terminal state must NOT follow it.
        self.write_registry(verify="exit 0")
        code, out, err = self.run_cli("verify", task_id)
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertTrue(payload["ran"])
        self.assertTrue(payload["passed"])

        row = self.row(task_id)
        self.assertEqual(row["status"], STATUS_FAILED)  # untouched
        self.assertEqual(row["verify_exit"], 0)         # verify_* updated
        self.assertEqual(row["verify_cmd"], "exit 0")


# ---------------------------------------------------------------------------
# The documented CLI door, as a real subprocess
# ---------------------------------------------------------------------------


class RealProcessTest(_Base):
    def _run_cli(self, *argv, timeout=60):
        return subprocess.run(
            [sys.executable, "-m", "taskproof", "--workspace", self.ws, *argv],
            env=_env(), capture_output=True, text=True, timeout=timeout,
        )

    def test_accept_and_rerun_through_the_real_binary(self):
        # ① accept a green blocked card through the real CLI
        blocked = self.breach(verify="exit 0")
        proc = self._run_cli("--json", "accept", blocked)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["status"], STATUS_DONE)

        # ⑤ rerun it; the real subprocess mints a linked new card that runs.
        # Rerun reuses the source adapter, so drop the boundary first: the fresh
        # card then runs clean instead of re-breaching (which would still be a
        # legal rerun, just with run's own 71 exit).
        self.write_registry(verify="exit 0", forbidden=())
        proc = self._run_cli("--json", "rerun", blocked)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        new = payload["task_id"]
        self.assertNotEqual(new, blocked)
        self.assertEqual(payload["rerun_of"], blocked)
        self.assertEqual(self.row(new)["status"], STATUS_DONE)
        # Same brief carried over, and both ledger links are visible.
        self.assertEqual(self.row(new)["brief"], self.row(blocked)["brief"])
        self.assertIn({"rerun_as": new}, [
            e["payload"] for e in self.events(blocked) if e["event"] == "rerun"
        ])
        self.assertIn({"rerun_of": blocked}, [
            e["payload"] for e in self.events(new) if e["event"] == "rerun"
        ])

        # ⑥ a non-terminal card is refused by the real CLI
        running = self.non_terminal("pending")
        proc = self._run_cli("rerun", running)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("only a terminal task can be rerun", proc.stderr)

        # ⑦ verify does not move the terminal state of a failed card
        self.write_registry(verify="exit 1")
        with self.assertRaises(VerifyError):
            dispatch.dispatch(self.ws, "proj", "red", adapter=_CLEAN)
        failed = self.latest_id()
        self.write_registry(verify="exit 0")
        proc = self._run_cli("verify", failed)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.row(failed)["status"], STATUS_FAILED)

    def test_accept_non_blocked_through_the_real_binary(self):
        done = dispatch.dispatch(self.ws, "proj", "clean", adapter=_CLEAN)
        proc = self._run_cli("accept", done)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("only a blocked or failed task", proc.stderr)


if __name__ == "__main__":
    unittest.main()
