"""Human disposition: the second ledger axis beside lifecycle status."""

import contextlib
import io
import json
import os
import tempfile
import unittest

from taskproof import cli, dispatch, storage
from taskproof.api import server
from taskproof.models import (
    DISPO_AWAITING_REVIEW,
    DISPO_BLOCKED,
    DISPO_DISPUTED,
    DISPO_FAILED,
    DISPO_SETTLED,
    DISPO_UNKNOWN,
    STATUS_BLOCKED,
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_RUNNING,
    STATUS_TIMEOUT,
    AdapterResult,
    Task,
    derive_disposition,
)


class DispositionDerivationTest(unittest.TestCase):
    def test_blockers_is_never_settled(self):
        disposition, reason = derive_disposition(
            STATUS_DONE,
            0,
            {
                "status": "done",
                "blockers": ["missing gitignored config"],
                "needs_approval": [],
                "contract_dispute": "",
            },
        )
        self.assertEqual(disposition, DISPO_BLOCKED)
        self.assertIn("blockers: 1", reason)

    def test_needs_approval_on_done_is_awaiting_review(self):
        disposition, reason = derive_disposition(
            STATUS_DONE,
            0,
            {
                "status": "done",
                "blockers": [],
                "needs_approval": ["install a dependency", "change config"],
                "contract_dispute": "",
            },
        )
        self.assertEqual(disposition, DISPO_AWAITING_REVIEW)
        self.assertIn("needs_approval: 2", reason)

    def test_no_structured_result_is_unknown(self):
        disposition, reason = derive_disposition(STATUS_DONE, 0, None)
        self.assertEqual(disposition, DISPO_UNKNOWN)
        self.assertIn("structured result", reason)

    def test_contract_dispute_wins_over_review(self):
        disposition, reason = derive_disposition(
            STATUS_DONE,
            0,
            {
                "status": "done",
                "blockers": [],
                "needs_approval": ["approve this"],
                "contract_dispute": "the named file does not exist",
            },
        )
        self.assertEqual(disposition, DISPO_DISPUTED)
        self.assertIn("contract_dispute", reason)


class DispositionStorageTest(unittest.TestCase):
    def test_old_row_without_disposition_reads_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = storage.connect(storage.db_path(tmp))
            try:
                storage.migrate(conn)
                storage.insert_task(
                    conn,
                    Task(
                        id="t-old-001",
                        project="proj",
                        group="proj",
                        brief="old card",
                        status=STATUS_DONE,
                        created_at=storage.now_iso(),
                        finished_at=storage.now_iso(),
                    ),
                )
            finally:
                conn.close()

            task = dispatch.task_detail(tmp, "t-old-001")["task"]
            self.assertEqual(task["disposition"], DISPO_UNKNOWN)
            self.assertEqual(task["disposition_reason"], "")

    def test_finish_verify_accept_and_api_all_carry_disposition(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "project")
            os.makedirs(project)
            result_path = os.path.join(tmp, "result.json")
            with open(result_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "status": "done",
                        "blockers": [],
                        "needs_approval": ["approve config"],
                        "contract_dispute": "",
                    },
                    handle,
                )

            conn = storage.connect(storage.db_path(tmp))
            try:
                storage.migrate(conn)
                storage.insert_task(
                    conn,
                    Task(
                        id="t-finish-001",
                        project="proj",
                        group="proj",
                        brief="finish",
                        status=STATUS_RUNNING,
                        created_at=storage.now_iso(),
                    ),
                )
                dispatch._finish_task(
                    conn,
                    "t-finish-001",
                    status=STATUS_DONE,
                    verify_exit=0,
                    result_path=result_path,
                    result=AdapterResult(
                        exit_code=0,
                        payload={
                            "status": "done",
                            "blockers": [],
                            "needs_approval": ["approve config"],
                            "contract_dispute": "",
                        },
                    ),
                )
                row = storage.get_task(conn, "t-finish-001")
                self.assertEqual(row["disposition"], DISPO_AWAITING_REVIEW)
            finally:
                conn.close()

            projected = server._with_live_files(
                {"id": "t-old", "status": STATUS_DONE, "workdir": None}
            )
            self.assertEqual(projected["disposition"], DISPO_UNKNOWN)
            self.assertEqual(projected["disposition_reason"], "")

    def test_verify_and_accept_recompute_from_result_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "project")
            os.makedirs(project)
            result_path = os.path.join(tmp, "result.json")
            with open(result_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "status": "done",
                        "blockers": [],
                        "needs_approval": ["approve config"],
                        "contract_dispute": "",
                    },
                    handle,
                )
            with open(os.path.join(tmp, "projects.toml"), "w", encoding="utf-8") as fh:
                fh.write(
                    "[defaults]\n"
                    "concurrency = 1\n"
                    "timeout = 30\n\n"
                    "[[project]]\n"
                    'id = "proj"\n'
                    f'path = "{project}"\n'
                    'verify = "exit 0"\n'
                    'verify_kind = "check"\n'
                )

            conn = storage.connect(storage.db_path(tmp))
            try:
                storage.migrate(conn)
                storage.insert_task(
                    conn,
                    Task(
                        id="t-verify-001",
                        project="proj",
                        group="proj",
                        brief="verify",
                        status=STATUS_DONE,
                        workdir=project,
                        result_path=result_path,
                        verify_cmd="exit 1",
                        verify_exit=1,
                        created_at=storage.now_iso(),
                        finished_at=storage.now_iso(),
                    ),
                )
            finally:
                conn.close()

            dispatch.verify_task(tmp, "t-verify-001")
            row = dispatch.task_detail(tmp, "t-verify-001")["task"]
            self.assertEqual(row["status"], STATUS_DONE)
            self.assertEqual(row["disposition"], DISPO_AWAITING_REVIEW)

            conn = storage.connect(storage.db_path(tmp))
            try:
                storage.update_task(
                    conn,
                    "t-verify-001",
                    status=STATUS_BLOCKED,
                    verify_exit=0,
                )
            finally:
                conn.close()
            dispatch.accept_task(tmp, "t-verify-001")
            row = dispatch.task_detail(tmp, "t-verify-001")["task"]
            self.assertEqual(row["status"], STATUS_DONE)
            self.assertEqual(row["disposition"], DISPO_AWAITING_REVIEW)

    def test_tasks_table_and_filters_expose_disposition(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = storage.connect(storage.db_path(tmp))
            try:
                storage.migrate(conn)
                for task_id, status, disposition in (
                    ("t-review", STATUS_DONE, DISPO_AWAITING_REVIEW),
                    ("t-settled", STATUS_DONE, DISPO_SETTLED),
                    ("t-failed", STATUS_FAILED, DISPO_FAILED),
                    ("t-blocked", STATUS_BLOCKED, DISPO_BLOCKED),
                ):
                    storage.insert_task(
                        conn,
                        Task(
                            id=task_id,
                            project="proj",
                            group="proj",
                            brief=task_id,
                            status=status,
                            created_at=storage.now_iso(),
                        ),
                    )
                    storage.update_task(
                        conn,
                        task_id,
                        disposition=disposition,
                        disposition_reason="test",
                    )
            finally:
                conn.close()

            code, out = self._run_cli(tmp, "tasks")
            self.assertEqual(code, 0)
            header = next(line for line in out.splitlines() if "DISPO" in line)
            self.assertIn("DISPO", header)
            review_row = next(line for line in out.splitlines() if "t-review" in line)
            self.assertIn("待批", review_row)

            code, out = self._run_cli(tmp, "--json", "tasks", "--dispo", "待批")
            self.assertEqual(code, 0)
            self.assertEqual([task["id"] for task in json.loads(out)["tasks"]], ["t-review"])

            code, out = self._run_cli(
                tmp, "--json", "tasks", "--dispo", "awaiting_review"
            )
            self.assertEqual(code, 0)
            self.assertEqual([task["id"] for task in json.loads(out)["tasks"]], ["t-review"])

    def _run_cli(self, workspace, *argv):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli.main(["--workspace", workspace, *argv])
        self.assertEqual(stderr.getvalue(), "")
        return code, stdout.getvalue()


class WaitDispositionExitTest(unittest.TestCase):
    def test_wait_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = storage.connect(storage.db_path(tmp))
            try:
                storage.migrate(conn)
                cases = (
                    ("t-settled", STATUS_DONE, DISPO_SETTLED),
                    ("t-review", STATUS_DONE, DISPO_AWAITING_REVIEW),
                    ("t-disputed", STATUS_DONE, DISPO_DISPUTED),
                    ("t-blocked", STATUS_BLOCKED, DISPO_BLOCKED),
                    ("t-timeout", STATUS_TIMEOUT, DISPO_FAILED),
                    ("t-unknown", STATUS_DONE, DISPO_UNKNOWN),
                )
                for task_id, status, disposition in cases:
                    storage.insert_task(
                        conn,
                        Task(
                            id=task_id,
                            project="proj",
                            group="proj",
                            brief=task_id,
                            status=status,
                            created_at=storage.now_iso(),
                            finished_at=storage.now_iso(),
                        ),
                    )
                    storage.update_task(
                        conn,
                        task_id,
                        disposition=disposition,
                        disposition_reason="test",
                    )
                storage.insert_task(
                    conn,
                    Task(
                        id="t-running",
                        project="proj",
                        group="proj",
                        brief="running",
                        status=STATUS_RUNNING,
                        created_at=storage.now_iso(),
                    ),
                )
            finally:
                conn.close()

            expected = {
                "t-settled": 0,
                "t-review": 3,
                "t-disputed": 3,
                "t-blocked": 3,
                "t-timeout": 3,
                "t-unknown": 1,
            }
            for task_id, exit_code in expected.items():
                code, _out = self._wait(tmp, task_id)
                self.assertEqual(code, exit_code, task_id)

            code, _out = self._wait(tmp, "t-running", "--timeout", "0.05", "--poll", "0.01")
            self.assertEqual(code, 124)

    def _wait(self, workspace, task_id, *extra):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli.main(
                ["--workspace", workspace, "wait", task_id, *extra]
            )
        self.assertEqual(stderr.getvalue(), "")
        return code, stdout.getvalue()

