"""CLI contract, driven through `cli.main([...])` (no subprocess, no network).

The handlers are thin, so these tests pin the observable surface: return codes
(0 / 2 / 64 / 70 / 71), `--json` parseability, and the init -> projects -> run
-> tasks -> show -> log chain with a harmless `custom:` adapter.
"""

import contextlib
import io
import json
import os
import tempfile
import unittest

from taskproof import cli, registry


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


if __name__ == "__main__":
    unittest.main()
