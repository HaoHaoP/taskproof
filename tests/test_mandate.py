"""Dispatch mandates pin acceptance to the contract in force at launch."""

import contextlib
import hashlib
import io
import json
import os
import tempfile
import unittest

from taskproof import cli, dispatch, storage
from taskproof.errors import VerifyError


def _q(value) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def registry_toml(
    path, *, verify="exit 0", forbidden=("protected/",), timeout=60
) -> str:
    lines = [
        "[defaults]",
        "concurrency = 3",
        f"timeout = {timeout}",
        "",
        "[[project]]",
        'id = "proj"',
        f"path = {_q(path)}",
        'group = "proj"',
        f"verify = {_q(verify)}",
        'verify_kind = "check"',
    ]
    if forbidden:
        joined = ", ".join(_q(item) for item in forbidden)
        lines.append(f"forbidden_paths = [{joined}]")
    return "\n".join(lines) + "\n"


class MandateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.ws = os.path.join(self.root, "workspace")
        self.proj = os.path.join(self.root, "project")
        os.makedirs(self.proj)
        dispatch.prepare_workspace(self.ws)
        self.write_registry()

    def tearDown(self):
        self._tmp.cleanup()

    def write_registry(self, *, verify="exit 0", forbidden=("protected/",)):
        path = os.path.join(self.ws, "projects.toml")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(
                registry_toml(
                    self.proj, verify=verify, forbidden=forbidden
                )
            )

    def row(self, task_id):
        conn = storage.connect(storage.db_path(self.ws))
        try:
            storage.migrate(conn)
            found = storage.get_task(conn, task_id)
            return dict(found) if found is not None else None
        finally:
            conn.close()

    def latest_id(self):
        conn = storage.connect(storage.db_path(self.ws))
        try:
            storage.migrate(conn)
            found = conn.execute(
                "SELECT id FROM tasks ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            return found[0] if found is not None else None
        finally:
            conn.close()

    def events(self, task_id, name):
        return [
            event
            for event in dispatch.task_detail(self.ws, task_id)["events"]
            if event["event"] == name
        ]

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["--workspace", self.ws, "--json", *argv])
        return code, out.getvalue(), err.getvalue()

    def test_mandate_written_with_all_keys(self):
        task_id = dispatch.dispatch(
            self.ws,
            "proj",
            "card body",
            adapter="custom:echo hi",
            timeout=42,
            idle_timeout=7,
        )

        row = self.row(task_id)
        mandate = json.loads(row["mandate"])
        self.assertEqual(
            set(mandate),
            {
                "card_sha256",
                "lane",
                "branch",
                "verify",
                "verify_kind",
                "forbidden_paths",
                "adapter",
                "model",
                "reasoning",
                "timeout",
                "idle_timeout",
                "issued_at",
            },
        )
        self.assertEqual(
            mandate["card_sha256"],
            hashlib.sha256(b"card body").hexdigest(),
        )
        self.assertEqual(mandate["lane"], "proj")
        self.assertEqual(mandate["verify"], "exit 0")
        self.assertEqual(mandate["verify_kind"], "check")
        self.assertEqual(mandate["forbidden_paths"], ["protected/"])
        self.assertEqual(mandate["adapter"], "custom:echo hi")
        self.assertIsNone(mandate["model"])
        self.assertIsNone(mandate["reasoning"])
        self.assertEqual(mandate["timeout"], 42)
        self.assertEqual(mandate["idle_timeout"], 7)
        self.assertTrue(mandate["issued_at"])

        events = self.events(task_id, "mandate")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["payload"], mandate)

    def test_verify_uses_mandated_command_after_registry_change(self):
        self.write_registry(verify="exit 1")
        with self.assertRaises(VerifyError):
            dispatch.dispatch(
                self.ws, "proj", "red", adapter="custom:echo hi"
            )
        task_id = self.latest_id()

        self.write_registry(verify="exit 0")
        code, out, err = self.run_cli("verify", task_id)
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertFalse(payload["passed"])
        self.assertEqual(payload["command"], "exit 1")
        self.assertEqual(self.row(task_id)["verify_exit"], 1)

    def test_mandate_drift_event_recorded(self):
        self.write_registry(verify="exit 1")
        with self.assertRaises(VerifyError):
            dispatch.dispatch(
                self.ws, "proj", "red", adapter="custom:echo hi"
            )
        task_id = self.latest_id()

        self.write_registry(verify="exit 0")
        dispatch.verify_task(self.ws, task_id)
        drift = self.events(task_id, "mandate_drift")
        self.assertEqual(len(drift), 1)
        self.assertEqual(
            drift[0]["payload"],
            {
                "field": "verify",
                "mandated": "exit 1",
                "current": "exit 0",
            },
        )

    def test_verify_current_uses_live_value(self):
        self.write_registry(verify="exit 1")
        with self.assertRaises(VerifyError):
            dispatch.dispatch(
                self.ws, "proj", "red", adapter="custom:echo hi"
            )
        task_id = self.latest_id()

        self.write_registry(verify="exit 0")
        code, out, err = self.run_cli("verify", "--current", task_id)
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertTrue(payload["passed"])
        self.assertEqual(payload["command"], "exit 0")
        self.assertEqual(self.row(task_id)["verify_cmd"], "exit 0")

        drift = self.events(task_id, "mandate_drift")
        self.assertEqual(len(drift), 1)
        self.assertEqual(
            drift[0]["payload"],
            {
                "field": "verify",
                "mandated": "exit 1",
                "current": "exit 0",
                "forced": True,
            },
        )

    def test_rerun_gets_its_own_mandate(self):
        first = dispatch.dispatch(
            self.ws, "proj", "same card", adapter="custom:echo hi"
        )
        self.write_registry(verify="exit 1")
        with self.assertRaises(VerifyError):
            dispatch.rerun_task(self.ws, first)
        second = self.latest_id()

        self.assertNotEqual(first, second)
        first_mandate = json.loads(self.row(first)["mandate"])
        second_mandate = json.loads(self.row(second)["mandate"])
        self.assertEqual(first_mandate["verify"], "exit 0")
        self.assertEqual(second_mandate["verify"], "exit 1")
        self.assertEqual(
            self.events(first, "mandate")[0]["payload"], first_mandate
        )
        self.assertEqual(
            self.events(second, "mandate")[0]["payload"], second_mandate
        )


if __name__ == "__main__":
    unittest.main()
