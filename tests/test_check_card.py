import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECK_CARD = ROOT / "tools" / "check-card.py"


class CheckCardTest(unittest.TestCase):
    def run_card(self, body, extra_args=(), path_env=None, json_output=True):
        with tempfile.TemporaryDirectory() as tmp:
            card = Path(tmp) / "card.md"
            card.write_text(body, encoding="utf-8")
            env = os.environ.copy()
            if path_env is not None:
                env["PATH"] = path_env
            command = [sys.executable, str(CHECK_CARD), str(card)]
            if json_output:
                command.append("--json")
            command.extend(extra_args)
            proc = subprocess.run(
                command,
                cwd=str(ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
        if not json_output:
            return proc, None
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            self.fail(
                "check-card did not emit JSON: "
                f"exit={proc.returncode} stdout={proc.stdout!r} stderr={proc.stderr!r}"
            )
        return proc, payload

    def make_fake_taskproof(self, directory, taskgroups, workspaces):
        executable = Path(directory) / "taskproof"
        executable.write_text(
            "#!/bin/sh\n"
            "case \"$*\" in\n"
            "  *taskgroups*) printf '%s\\n' '" + taskgroups + "' ;;\n"
            "  *workspaces*) printf '%s\\n' '" + workspaces + "' ;;\n"
            "  *) exit 2 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        executable.chmod(0o755)
        return str(Path(directory)) + os.pathsep + os.environ.get("PATH", "")

    def test_rejects_absolute_path_outside_write_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            path_env = self.make_fake_taskproof(
                tmp,
                '{"taskgroups":[{"id":"lane-a","path":"/tmp/repo"}]}',
                "no lanes declare a workspace",
            )
            proc, payload = self.run_card(
                "# 卡\n\n## 要做的事\n\n写 `/absolute/path/to/repo/file.py`。\n",
                ("--lane", "lane-a"),
                path_env,
            )
        self.assertEqual(proc.returncode, 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["checks"][4]["result"], "fail")

    def test_allows_absolute_path_under_tmp(self):
        with tempfile.TemporaryDirectory() as tmp:
            path_env = self.make_fake_taskproof(
                tmp,
                '{"taskgroups":[{"id":"lane-a","path":"/tmp/repo"}]}',
                "no lanes declare a workspace",
            )
            proc, payload = self.run_card(
                "# 卡\n\n## 要做的事\n\n写 `/tmp/cards/file.py`。\n",
                ("--lane", "lane-a"),
                path_env,
            )
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["checks"][4]["result"], "pass")

    def test_acceptance_commands_and_toolchain_paths_are_not_write_intent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path_env = self.make_fake_taskproof(
                tmp,
                '{"taskgroups":[{"id":"lane-a","path":"/tmp/repo"}]}',
                "no lanes declare a workspace",
            )
            proc, payload = self.run_card(
                "# 卡\n\n## 要做的事\n\n"
                "调用 `/usr/bin/python3` 执行相对路径脚本。\n\n"
                "## 验收\n\n"
                "cd /absolute/path/to/taskproof && "
                "/opt/homebrew/Caskroom/miniconda/base/bin/python3 -m unittest\n",
                ("--lane", "lane-a"),
                path_env,
            )
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["checks"][4]["result"], "pass")

    def test_no_lane_marks_write_scope_not_applicable(self):
        proc, payload = self.run_card(
            "# 卡\n\n## 要做的事\n\n修改相对路径 src/example.py。\n"
        )
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(payload["ok"])
        check5 = payload["checks"][4]
        self.assertEqual(check5["result"], "n/a")
        self.assertIn("不知道这道跑在哪，写域判不了", check5["detail"])

    def test_rejects_browser_acceptance_without_budget_or_stop_loss(self):
        proc, payload = self.run_card(
            "# 卡\n\n## 验收\n\n用 Chrome 截图核对。\n"
        )
        self.assertEqual(proc.returncode, 1)
        self.assertFalse(payload["ok"])

    def test_allows_browser_acceptance_with_stop_loss(self):
        proc, payload = self.run_card(
            "# 卡\n\n## 验收\n\n用 Chrome 截图核对。\n\n"
            "## 硬约束\n\n止损：一次失败即停。\n"
        )
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(payload["ok"])

    def test_warns_test_only_contract_with_test_command(self):
        body = (
            "# 卡\n\n## 硬约束\n\n只写测试。\n\n"
            "## 验收\n\npython -m unittest tests.test_example\n"
        )
        text_proc, _ = self.run_card(body, json_output=False)
        self.assertEqual(text_proc.returncode, 0)
        self.assertIn("[WARN] 查7 契约：", text_proc.stdout)

        proc, payload = self.run_card(body)
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["checks"][6]["result"], "warn")

    def test_allows_test_only_contract_without_test_command(self):
        proc, payload = self.run_card(
            "# 卡\n\n## 硬约束\n\n只写测试。\n\n## 验收\n\n人工核对输出。\n"
        )
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(payload["ok"])

    def test_plain_logic_card_runs_universal_checks(self):
        proc, payload = self.run_card(
            "# 卡\n\n## 要做的事\n\n修改相对路径 src/example.py。\n"
        )
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["skipped"])

    def test_lane_path_is_an_allowed_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            path_env = self.make_fake_taskproof(
                tmp,
                '{"taskgroups":[{"id":"lane-a","path":"/absolute/path/to/repo"}]}',
                "no lanes declare a workspace",
            )
            proc, payload = self.run_card(
                "# 卡\n\n## 要做的事\n\n写 `/absolute/path/to/repo/file.py`。\n",
                ("--lane", "lane-a"),
                path_env,
            )
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(payload["ok"])

    def test_lane_workspace_yes_path_is_an_allowed_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            path_env = self.make_fake_taskproof(
                tmp,
                '{"taskgroups":[{"id":"lane-a","path":"/tmp/repo"}]}',
                "ID PROJECT BUILT CHANGES UNMERGED LINKS WORKSPACE\n"
                "lane-a project yes 0 0 - /absolute/path/to/workspace",
            )
            proc, payload = self.run_card(
                "# 卡\n\n## 要做的事\n\n写 "
                "`/absolute/path/to/workspace/file.py`。\n",
                ("--lane", "lane-a"),
                path_env,
            )
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(payload["ok"])

    def test_unresolved_lane_marks_write_scope_not_applicable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path_env = self.make_fake_taskproof(
                tmp,
                '{"taskgroups":[{"id":"other-lane","path":"/tmp/other"}]}',
                "no lanes declare a workspace",
            )
            proc, payload = self.run_card(
                "# 卡\n\n## 要做的事\n\n写 `/absolute/path/to/repo/file.py`。\n",
                ("--lane", "missing-lane"),
                path_env,
            )
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["checks"][4]["result"], "n/a")

    def test_check_card_compiles_on_system_python_39(self):
        python39 = Path("/usr/bin/python3")
        if not python39.exists():
            self.skipTest("/usr/bin/python3 does not exist")
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["PYTHONPYCACHEPREFIX"] = tmp
            proc = subprocess.run(
                [str(python39), "-m", "py_compile", str(CHECK_CARD)],
                cwd=str(ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
