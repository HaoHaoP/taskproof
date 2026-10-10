"""CLI contract, driven through `cli.main([...])` (no subprocess, no network).

The handlers are thin, so these tests pin the observable surface: return codes
(0 / 2 / 64 / 70 / 71), `--json` parseability, and the init -> projects -> run
-> tasks -> show -> log chain with a harmless `custom:` adapter.
"""

import contextlib
import hashlib
import io
import json
import os
import subprocess
import tempfile
import unittest

from taskproof import cli, concurrency, dispatch, registry, storage
from taskproof.models import STATUS_DONE, STATUS_RUNNING, Task


def _q(value) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def registry_toml(path, *, pid="proj", group="proj", verify="exit 0",
                  verify_kind="check", forbidden=()) -> str:
    lines = [
        "[defaults]",
        "concurrency = 3",
        "timeout = 60",
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


class CliBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.ws = os.path.join(self.tmp, "workspace")
        self.proj = os.path.join(self.tmp, "project")
        os.makedirs(self.proj)

    def tearDown(self):
        self._tmp.cleanup()

    def run_cli(self, *argv):
        """Call main() directly, swallowing human output."""
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue()

    def write_registry(self, **kwargs):
        os.makedirs(self.ws, exist_ok=True)
        with open(os.path.join(self.ws, "projects.toml"), "w", encoding="utf-8") as fh:
            fh.write(registry_toml(self.proj, **kwargs))


class ChainTest(CliBase):
    def test_init_is_idempotent_and_reports_workspace(self):
        code, out = self.run_cli("--workspace", self.ws, "--json", "init")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["workspace"], self.ws)
        self.assertEqual(payload["projects"], 0)
        self.assertTrue(os.path.exists(os.path.join(self.ws, "projects.toml")))
        # The registry starts with no projects at all. An entry seeded here would
        # be a project whose path does not exist, and `projects` -- plus the live
        # dashboard -- would list it until someone deleted the block. Asserted on
        # the parsed registry, not the raw text: the header comment mentions
        # `[[project]]` on purpose, to show what an entry looks like.
        self.assertEqual(registry.load(os.path.join(self.ws, "projects.toml")).projects, [])
        # Idempotent: a second init must not fail.
        self.assertEqual(self.run_cli("--workspace", self.ws, "init")[0], 0)

    def test_full_chain_init_projects_run_tasks_show_log(self):
        self.run_cli("--workspace", self.ws, "init")
        self.write_registry()

        code, out = self.run_cli("--workspace", self.ws, "--json", "projects")
        self.assertEqual(code, 0)
        projects = json.loads(out)["projects"]
        self.assertEqual([p["id"] for p in projects], ["proj"])
        self.assertEqual(projects[0]["verify"], "exit 0")

        code, out = self.run_cli(
            "--workspace", self.ws, "--json", "run", "proj", "harmless task",
            "--adapter", "custom:echo hi",
        )
        self.assertEqual(code, 0)
        task_id = json.loads(out)["task_id"]
        self.assertTrue(task_id)

        code, out = self.run_cli("--workspace", self.ws, "--json", "tasks")
        self.assertEqual(code, 0)
        tasks = json.loads(out)["tasks"]
        self.assertEqual([t["id"] for t in tasks], [task_id])
        self.assertEqual(tasks[0]["status"], "done")

        code, out = self.run_cli("--workspace", self.ws, "--json", "show", task_id)
        self.assertEqual(code, 0)
        detail = json.loads(out)
        self.assertEqual(detail["task"]["id"], task_id)
        self.assertTrue(detail["events"])

        code, out = self.run_cli("--workspace", self.ws, "--json", "log", task_id)
        self.assertEqual(code, 0)
        events = json.loads(out)["events"]
        self.assertEqual(events[-1]["event"], "done")

    def test_tasks_default_limit_is_20(self):
        self.run_cli("--workspace", self.ws, "init")
        self.write_registry()
        # Insert 25 rows directly; only the newest 20 must be listed.
        from taskproof import storage
        from taskproof.models import Task

        conn = storage.connect(storage.db_path(self.ws))
        try:
            storage.migrate(conn)
            for i in range(25):
                storage.insert_task(conn, Task(
                    id=f"t-{i:03d}", project="proj", group="proj", brief="x",
                    status="done", created_at=storage.now_iso(),
                ))
        finally:
            conn.close()
        code, out = self.run_cli("--workspace", self.ws, "--json", "tasks")
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(out)["tasks"]), 20)


class RunCliTest(CliBase):
    """`taskproof run` fires immediately; there is no queue and no `--park`."""

    def setUp(self):
        super().setUp()
        self.run_cli("--workspace", self.ws, "init")
        self.write_registry()

    def test_run_immediately_runs_to_completion(self):
        code, out = self.run_cli(
            "--workspace", self.ws, "--json", "run", "proj", "now",
            "--adapter", "custom:echo hi",
        )
        self.assertEqual(code, 0, out)
        payload = json.loads(out)
        self.assertEqual(payload["status"], STATUS_DONE)
        task = dispatch.task_detail(self.ws, payload["task_id"])["task"]
        self.assertEqual(task["status"], STATUS_DONE)
        # The queue is gone: the payload advertises no seq, and the retired
        # physical column (kept for live DBs) is never populated.
        self.assertNotIn("queue_seq", payload)
        self.assertIsNone(task["queue_seq"])

    def test_run_rejects_park(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as ctx:
            cli.main([
                "--workspace", self.ws, "run", "proj", "parked",
                "--adapter", "custom:echo hi", "--park",
            ])
        self.assertEqual(ctx.exception.code, 64)
        self.assertIn("park", err.getvalue())


class ExitCodeTest(CliBase):
    def test_unknown_project_is_2(self):
        self.run_cli("--workspace", self.ws, "init")
        self.write_registry()
        code, _ = self.run_cli(
            "--workspace", self.ws, "run", "does-not-exist", "brief",
            "--adapter", "custom:echo hi",
        )
        self.assertEqual(code, 2)

    def test_unknown_task_show_is_64(self):
        self.run_cli("--workspace", self.ws, "init")
        code, _ = self.run_cli("--workspace", self.ws, "show", "t-00000000-999")
        self.assertEqual(code, 64)

    def test_unknown_adapter_is_64(self):
        self.run_cli("--workspace", self.ws, "init")
        self.write_registry()
        code, _ = self.run_cli(
            "--workspace", self.ws, "run", "proj", "brief", "--adapter", "no-such-agent"
        )
        self.assertEqual(code, 64)

    def test_adapter_failure_is_70(self):
        self.run_cli("--workspace", self.ws, "init")
        self.write_registry()
        code, _ = self.run_cli(
            "--workspace", self.ws, "run", "proj", "brief", "--adapter", "custom:false"
        )
        self.assertEqual(code, 70)

    def test_verify_failure_is_71(self):
        self.run_cli("--workspace", self.ws, "init")
        self.write_registry(verify="exit 3")
        code, _ = self.run_cli(
            "--workspace", self.ws, "run", "proj", "brief", "--adapter", "custom:echo hi"
        )
        self.assertEqual(code, 71)

    def test_register_missing_path_is_64(self):
        code, _ = self.run_cli(
            "--workspace", self.ws, "register", os.path.join(self.tmp, "missing")
        )
        self.assertEqual(code, 64)


class BlockedStatusTest(CliBase):
    """Card 34: a boundary breach is recorded as `blocked`, still exit 71, and
    shows up under `tasks --status blocked`."""

    def _breach(self):
        self.run_cli("--workspace", self.ws, "init")
        self.write_registry(forbidden=["protected/"])
        return self.run_cli(
            "--workspace", self.ws, "run", "proj", "breach",
            "--adapter",
            "custom:sh -c 'mkdir -p protected && echo x > protected/out.txt "
            "&& echo ok'",
        )

    def test_forbidden_run_exits_71_but_is_blocked(self):
        code, _ = self._breach()
        self.assertEqual(code, 71)  # the command's outcome, not the task state

        code, out = self.run_cli(
            "--workspace", self.ws, "--json", "tasks", "--status", "blocked"
        )
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["tasks"][0]["status"], "blocked")

        # A `failed` filter must NOT see it: the ledger did not mix the two.
        code, out = self.run_cli(
            "--workspace", self.ws, "--json", "tasks", "--status", "failed"
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["count"], 0)


class RegisterTest(CliBase):
    def test_dry_run_probes_without_writing(self):
        open(os.path.join(self.proj, "pyproject.toml"), "w").close()
        with open(os.path.join(self.proj, "m.py"), "w", encoding="utf-8") as fh:
            fh.write("x = 1\n")
        code, out = self.run_cli(
            "--workspace", self.ws, "--json", "register", self.proj, "--dry-run"
        )
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["verify"], "python -m compileall -q .")
        self.assertEqual(payload["verify_kind"], "build")
        self.assertEqual(payload["probe"], "passed")
        self.assertFalse(payload["registered"])
        # Dry run must not touch the workspace at all.
        self.assertFalse(os.path.exists(os.path.join(self.ws, "projects.toml")))

    def test_register_appends_and_keeps_existing_entries(self):
        open(os.path.join(self.proj, "pyproject.toml"), "w").close()
        with open(os.path.join(self.proj, "m.py"), "w", encoding="utf-8") as fh:
            fh.write("x = 1\n")
        code, out = self.run_cli(
            "--workspace", self.ws, "--json", "register", self.proj,
            "--id", "app", "--group", "app",
        )
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["id"], "app")
        self.assertTrue(payload["registered"])
        self.assertEqual(payload["verify"], "python -m compileall -q .")

        with open(os.path.join(self.ws, "projects.toml"), encoding="utf-8") as fh:
            text = fh.read()
        # A fresh workspace starts with no projects. The placeholder entry that
        # used to be seeded here showed up as a repository that did not exist.
        self.assertNotIn('id = "my-app"', text)
        self.assertIn('id = "app"', text)
        self.assertIn('probe = "passed"', text)

    def test_unrecognised_project_records_none(self):
        code, out = self.run_cli(
            "--workspace", self.ws, "--json", "register", self.proj,
            "--id", "plain", "--dry-run",
        )
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertIsNone(payload["verify"])
        self.assertEqual(payload["verify_kind"], "none")
        self.assertIsNone(payload["probe"])

    def test_duplicate_id_is_2(self):
        self.write_registry(pid="dup")
        code, _ = self.run_cli(
            "--workspace", self.ws, "register", self.proj, "--id", "dup"
        )
        self.assertEqual(code, 2)


HANDWRITTEN_REGISTRY = """\
# taskproof registry -- hand written, keep every comment

[defaults]
concurrency = 3   # global cap on simultaneous tasks
timeout = 60    # seconds

[[project]]
id = "proj"
path = "{path}"
group = "proj"
verify = "exit 0"
verify_kind = "check"
"""


class ConfigCliTest(CliBase):
    """Card 42: `taskproof config` shows source, writes in place, rejects bad input."""

    def setUp(self):
        super().setUp()
        self.run_cli("--workspace", self.ws, "init")
        self.reg_path = os.path.join(self.ws, "projects.toml")

    def _hash(self):
        with open(self.reg_path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()

    def _write_handwritten(self):
        os.makedirs(self.ws, exist_ok=True)
        with open(self.reg_path, "w", encoding="utf-8") as fh:
            fh.write(HANDWRITTEN_REGISTRY.format(path=self.proj))

    def test_show_reports_auto_when_key_is_absent(self):
        # `init` now ships the cap commented out, so a fresh workspace omits it.
        code, out = self.run_cli("--workspace", self.ws, "--json", "config", "--show")
        self.assertEqual(code, 0)
        cap = json.loads(out)["concurrency"]
        self.assertEqual(cap["source"], "auto")
        self.assertEqual(cap["value"], concurrency.detect())
        self.assertIn("核", cap["detail"])

    def test_show_is_read_only(self):
        self._write_handwritten()
        before = self._hash()
        code, out = self.run_cli("--workspace", self.ws, "config", "--show")
        self.assertEqual(code, 0)
        self.assertIn("concurrency = 3", out)
        self.assertIn("projects.toml", out)  # the source is shown
        self.assertEqual(self._hash(), before)

    def test_set_writes_value_and_keeps_the_comment(self):
        self._write_handwritten()
        code, out = self.run_cli("--workspace", self.ws, "--json", "config", "--concurrency", "5")
        self.assertEqual(code, 0, out)
        payload = json.loads(out)
        self.assertEqual(payload["concurrency"], {"value": 5, "source": "toml", "detail": "projects.toml"})
        with open(self.reg_path, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("concurrency = 5   # global cap on simultaneous tasks", text)
        self.assertIn("timeout = 60    # seconds", text)
        self.assertIn('id = "proj"', text)

    def test_set_timeout(self):
        code, out = self.run_cli("--workspace", self.ws, "config", "--timeout", "120")
        self.assertEqual(code, 0, out)
        reg = registry.load(self.reg_path)
        self.assertEqual(reg.timeout, 120)

    def test_non_integer_is_rejected_without_writing(self):
        self._write_handwritten()
        before = self._hash()
        code, _ = self.run_cli("--workspace", self.ws, "config", "--concurrency", "abc")
        self.assertNotEqual(code, 0)
        self.assertEqual(self._hash(), before)

    def test_below_one_is_rejected_without_writing(self):
        self._write_handwritten()
        before = self._hash()
        code, _ = self.run_cli("--workspace", self.ws, "config", "--concurrency", "0")
        self.assertNotEqual(code, 0)
        self.assertEqual(self._hash(), before)

    def test_lowering_prints_reminder_and_never_touches_running_cards(self):
        self._write_handwritten()
        conn = storage.connect(storage.db_path(self.ws))
        try:
            storage.migrate(conn)
            for i in range(3):
                tid = f"t-hold{i}"
                storage.insert_task(
                    conn,
                    Task(
                        id=tid, project="proj", group=f"g{i}", brief="x",
                        status=STATUS_RUNNING, adapter="codex",
                        created_at=storage.now_iso(), started_at=storage.now_iso(),
                    ),
                )
                concurrency.acquire(conn, tid, f"g{i}", cap=99, ttl=600)
            before = {
                row["id"]: row["status"]
                for row in conn.execute("SELECT id, status FROM tasks").fetchall()
            }
        finally:
            conn.close()

        code, out = self.run_cli("--workspace", self.ws, "--json", "config", "--concurrency", "2")
        self.assertEqual(code, 0, out)
        payload = json.loads(out)
        self.assertEqual(payload["concurrency"]["value"], 2)
        self.assertEqual(len(payload["running_over_cap"]), 3)
        self.assertEqual(
            {row["id"] for row in payload["running_over_cap"]}, {"t-hold0", "t-hold1", "t-hold2"}
        )

        # The reminder (human view) names every running card and promises no kill.
        code, human = self.run_cli("--workspace", self.ws, "config", "--concurrency", "2")
        self.assertIn("不追溯", human)
        self.assertIn("t-hold0", human)
        self.assertIn("proj", human)

        conn = storage.connect(storage.db_path(self.ws))
        try:
            after = {
                row["id"]: row["status"]
                for row in conn.execute("SELECT id, status FROM tasks").fetchall()
            }
        finally:
            conn.close()
        self.assertEqual(after, before)


class RunCapCliTest(CliBase):
    """Card 42: `run --cap N` is a one-off override, recorded in the event stream."""

    def setUp(self):
        super().setUp()
        self.run_cli("--workspace", self.ws, "init")
        self.write_registry()  # concurrency = 3
        self.reg_path = os.path.join(self.ws, "projects.toml")

    def _hash(self):
        with open(self.reg_path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()

    def _hold(self, n):
        conn = storage.connect(storage.db_path(self.ws))
        try:
            storage.migrate(conn)
            for i in range(n):
                tid = f"t-hold{i}"
                storage.insert_task(
                    conn,
                    Task(
                        id=tid, project="proj", group=f"g{i}", brief="x",
                        status=STATUS_RUNNING, adapter="codex",
                        created_at=storage.now_iso(), started_at=storage.now_iso(),
                    ),
                )
                concurrency.acquire(conn, tid, f"g{i}", cap=99, ttl=600)
        finally:
            conn.close()

    def test_default_cap_refuses_but_cap_override_admits(self):
        self._hold(3)  # fills the toml cap of 3
        code, _ = self.run_cli(
            "--workspace", self.ws, "run", "proj", "brief",
            "--adapter", "custom:echo hi",
        )
        self.assertEqual(code, 75)

        before = self._hash()
        code, out = self.run_cli(
            "--workspace", self.ws, "--json", "run", "proj", "brief",
            "--adapter", "custom:echo hi", "--cap", "5",
        )
        self.assertEqual(code, 0, out)
        task_id = json.loads(out)["task_id"]
        self.assertEqual(self._hash(), before, "run --cap must not rewrite the registry")

        detail = dispatch.task_detail(self.ws, task_id)
        started = next(e for e in detail["events"] if e["event"] == "started")
        self.assertEqual(started["payload"]["cap"], 5)
        self.assertEqual(started["payload"]["cap_source"], "cli")

    def test_cap_below_one_is_a_usage_error(self):
        code, _ = self.run_cli(
            "--workspace", self.ws, "run", "proj", "brief",
            "--adapter", "custom:echo hi", "--cap", "0",
        )
        self.assertEqual(code, 64)


class WorkspaceCliTest(CliBase):
    """Card 66: `workspaces` lists opt-in lanes; `workspace-rm` prints evidence,
    refuses a dirty workspace with a file-naming message, and `--force` overrides.

    Driven through `cli.main` against a real temporary git repo -- the same
    in-process seam as every other CLI test, never the operator's registry.
    """

    def setUp(self):
        super().setUp()
        for args in (
            ["init", "-q"],
            ["config", "user.email", "t@t"],
            ["config", "user.name", "t"],
        ):
            subprocess.run(["git", *args], cwd=self.proj, check=True)
        with open(os.path.join(self.proj, "seed.txt"), "w", encoding="utf-8") as fh:
            fh.write("seed\n")
        subprocess.run(["git", "add", "seed.txt"], cwd=self.proj, check=True)
        subprocess.run(["git", "commit", "-qm", "seed"], cwd=self.proj, check=True)
        self.run_cli("--workspace", self.ws, "init")
        self.write_registry(workspace="worktree")

    def write_registry(self, **kwargs):
        # Opt this lane into a long-lived workspace by appending the lane field
        # to the shared `[[project]]` block (which a lane field promotes).
        os.makedirs(self.ws, exist_ok=True)
        body = registry_toml(self.proj, **{k: v for k, v in kwargs.items()
                                           if k != "workspace"})
        body = body.rstrip("\n") + f'\nworkspace = "{kwargs.get("workspace", "none")}"\n'
        with open(os.path.join(self.ws, "projects.toml"), "w", encoding="utf-8") as fh:
            fh.write(body)

    def run_cli_both(self, *argv):
        """Like `run_cli`, but also returns stderr (for the refusal message)."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def _ws_path(self):
        return os.path.join(self.tmp, "project-ws-proj")

    def _build(self):
        code, out = self.run_cli(
            "--workspace", self.ws, "--json", "run", "proj", "make ws",
            "--adapter", "custom:echo hi",
        )
        self.assertEqual(code, 0, out)
        self.assertTrue(os.path.isdir(self._ws_path()))
        return json.loads(out)["task_id"]

    def test_workspaces_lists_opt_in_lane_before_it_is_built(self):
        code, out = self.run_cli("--workspace", self.ws, "workspaces")
        self.assertEqual(code, 0)
        self.assertIn("proj", out)

        code, out = self.run_cli("--workspace", self.ws, "--json", "workspaces")
        self.assertEqual(code, 0)
        rows = json.loads(out)["workspaces"]
        self.assertEqual([r["id"] for r in rows], ["proj"])
        self.assertFalse(rows[0]["exists"])

    def test_workspaces_reports_a_built_clean_workspace(self):
        self._build()
        code, out = self.run_cli("--workspace", self.ws, "--json", "workspaces")
        self.assertEqual(code, 0)
        row = json.loads(out)["workspaces"][0]
        self.assertTrue(row["exists"])
        self.assertEqual(row["changed"], 0)
        self.assertEqual(row["unmerged"], 0)

    def test_workspace_rm_clean_exits_zero(self):
        self._build()
        code, out = self.run_cli("--workspace", self.ws, "workspace-rm", "proj")
        self.assertEqual(code, 0)
        self.assertIn("removed workspace", out)
        self.assertFalse(os.path.exists(self._ws_path()))

    def test_workspace_rm_dirty_is_refused_with_the_file_name(self):
        self._build()
        with open(os.path.join(self._ws_path(), "dirty.txt"), "w", encoding="utf-8") as fh:
            fh.write("x\n")
        code, out, err = self.run_cli_both(
            "--workspace", self.ws, "workspace-rm", "proj"
        )
        self.assertEqual(code, 64)
        # Evidence precedes deletion (stdout), and the refusal names the file.
        self.assertIn("dirty.txt", out)
        self.assertIn("dirty.txt", err)
        self.assertIn("--force", err)
        self.assertTrue(os.path.isdir(self._ws_path()))

    def test_workspace_rm_force_deletes_a_dirty_workspace(self):
        self._build()
        with open(os.path.join(self._ws_path(), "dirty.txt"), "w", encoding="utf-8") as fh:
            fh.write("x\n")
        code, out, _ = self.run_cli_both(
            "--workspace", self.ws, "workspace-rm", "proj", "--force"
        )
        self.assertEqual(code, 0)
        self.assertIn("forced", out)
        self.assertFalse(os.path.exists(self._ws_path()))



if __name__ == "__main__":
    unittest.main()
