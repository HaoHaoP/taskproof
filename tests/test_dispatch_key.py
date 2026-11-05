"""One card may be dispatched only once unless force/rerun says otherwise."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from taskproof import concurrency, dispatch, registry, storage
from taskproof.errors import DuplicateError


ROOT = Path(__file__).resolve().parents[1]
CHECK_CARD = ROOT / "tools" / "check-card.py"


def _write_registry(workspace: str, project: str) -> None:
    os.makedirs(workspace, exist_ok=True)
    body = (
        "[defaults]\n"
        "concurrency = 3\n"
        "timeout = 60\n\n"
        "[[project]]\n"
        'id = "proj"\n'
        f'path = "{project}"\n'
        'group = "proj"\n'
        'verify = "exit 0"\n'
        'verify_kind = "check"\n'
    )
    with open(
        registry.workspace_registry_path(workspace), "w", encoding="utf-8"
    ) as handle:
        handle.write(body)


class DispatchKeyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = os.path.join(self.tmp.name, "workspace")
        self.project = os.path.join(self.tmp.name, "project")
        os.makedirs(self.project)
        dispatch.prepare_workspace(self.workspace)
        _write_registry(self.workspace, self.project)

    def tearDown(self):
        self.tmp.cleanup()

    def open_conn(self):
        conn = storage.connect(storage.db_path(self.workspace))
        storage.migrate(conn)
        return conn

    def row(self, task_id):
        conn = self.open_conn()
        try:
            return storage.get_task(conn, task_id)
        finally:
            conn.close()

    def events(self, task_id):
        return dispatch.task_detail(self.workspace, task_id)["events"]

    def first(self):
        return dispatch.dispatch(
            self.workspace,
            "proj",
            "same card",
            adapter="custom:echo hi",
            model="gpt-first",
        )

    def test_second_dispatch_same_brief_refused_76(self):
        first = self.first()

        with self.assertRaises(DuplicateError) as caught:
            dispatch.dispatch(
                self.workspace,
                "proj",
                "same card",
                adapter="custom:echo hi",
            )

        self.assertEqual(caught.exception.exit_code, 76)
        self.assertIn(first, str(caught.exception))
        self.assertIn("--force", str(caught.exception))
        self.assertIn("rerun", str(caught.exception))

    def test_refusal_leaves_no_row_and_no_claim(self):
        first = self.first()
        conn = self.open_conn()
        try:
            before = (
                conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],
                conn.execute("SELECT COUNT(*) FROM events").fetchone()[0],
                concurrency.count_active(conn),
            )
        finally:
            conn.close()

        with self.assertRaises(DuplicateError):
            self.first()

        conn = self.open_conn()
        try:
            after = (
                conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],
                conn.execute("SELECT COUNT(*) FROM events").fetchone()[0],
                concurrency.count_active(conn),
            )
        finally:
            conn.close()
        self.assertEqual(after, before)
        self.assertEqual(self.row(first)["status"], "done")

    def test_force_allows_second_row(self):
        first = self.first()

        second = dispatch.dispatch(
            self.workspace,
            "proj",
            "same card",
            adapter="custom:echo hi",
            model="gpt-first",
            force=True,
        )

        self.assertNotEqual(second, first)
        self.assertIsNone(self.row(second)["dispatch_key"])
        started = next(e for e in self.events(second) if e["event"] == "started")
        self.assertTrue(started["payload"]["forced"])
        self.assertEqual(started["payload"]["duplicate_of"], first)

    def test_rerun_records_duplicate_of(self):
        first = self.first()
        second = dispatch.rerun_task(self.workspace, first)

        self.assertIsNone(self.row(second)["dispatch_key"])
        rerun = next(e for e in self.events(second) if e["event"] == "rerun")
        self.assertEqual(rerun["payload"]["rerun_of"], first)
        self.assertEqual(rerun["payload"]["duplicate_of"], first)

    def test_key_ignores_adapter_and_model(self):
        first = self.first()

        with self.assertRaises(DuplicateError) as caught:
            dispatch.dispatch(
                self.workspace,
                "proj",
                "same card",
                adapter="custom:echo differently",
                model="another-model",
            )

        self.assertIn(first, str(caught.exception))

    def test_check_card_warns_on_date_in_body(self):
        card = Path(self.tmp.name) / "card.md"
        card.write_text(
            "# duplicate card\n\n"
            "## 要做的事\n\n"
            "在 2026-11-05 核对此行为。\n",
            encoding="utf-8",
        )
        proc = subprocess.run(
            [sys.executable, "-B", str(CHECK_CARD), str(card), "--json"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        warnings = [item for item in payload["checks"] if item["result"] == "warn"]
        self.assertTrue(
            any(
                "卡文带日期会让重复检查失效，日期挪到文件名" in item["detail"]
                for item in warnings
            )
        )


if __name__ == "__main__":
    unittest.main()
