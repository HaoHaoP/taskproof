"""Adapter resolution + command-construction contract.

Pins the two accident classes from the design notes:

  * an unknown bare adapter name must NEVER silently fall back to another
    agent — it raises UsageError (exit 64)
  * the Codex command is an argv list (no shell metacharacter concatenation),
    and read-only vs read-write genuinely differ
"""

import json
import os
import tempfile
import unittest

from taskproof.adapters import available, get, load_class
from taskproof.adapters.base import Adapter, ResultParseError
from taskproof.adapters.codex import CodexAdapter
from taskproof.adapters.custom import CustomAdapter
from taskproof.errors import EXIT_USAGE, UsageError


class ResolveTest(unittest.TestCase):
    def test_get_codex_returns_codex_adapter(self):
        self.assertIsInstance(get("codex"), CodexAdapter)

    def test_get_custom_prefix_returns_custom_adapter(self):
        adapter = get("custom:echo hi")
        self.assertIsInstance(adapter, CustomAdapter)
        self.assertEqual(adapter.command, "echo hi")

    def test_unknown_bare_name_raises_usage_error(self):
        with self.assertRaises(UsageError) as ctx:
            get("definitely-not-an-agent")
        self.assertEqual(ctx.exception.exit_code, EXIT_USAGE)

    def test_all_builtin_names_resolve(self):
        for name in ("codex", "claude", "gemini", "opencode"):
            self.assertIsInstance(get(name), Adapter, name)

    def test_available_is_a_list_of_known_names(self):
        names = available()
        self.assertIsInstance(names, list)
        for name in names:
            self.assertIn(name, ("codex", "claude", "gemini", "opencode"))

    def test_load_class(self):
        self.assertIs(load_class("codex"), CodexAdapter)


class CodexCommandTest(unittest.TestCase):
    def test_argv_shape(self):
        adapter = get("codex", model="o3")
        argv = adapter.build_command(
            brief="do the thing",
            workdir="/tmp/repo",
            schema_path="/tmp/schema.json",
            read_only=False,
        )
        # argv list, not a shell string
        self.assertIsInstance(argv, list)
        self.assertTrue(all(isinstance(token, str) for token in argv))
        self.assertEqual(argv[0], "codex")
        self.assertIn("exec", argv)
        self.assertIn("--output-schema", argv)
        self.assertEqual(argv[argv.index("--output-schema") + 1], "/tmp/schema.json")
        # the prompt is ONE element, never split or shell-joined
        self.assertEqual(argv[-1], "do the thing")
        self.assertEqual(argv.count("do the thing"), 1)
        # no shell metacharacter concatenation anywhere
        for token in argv:
            self.assertNotIn("&&", token)
            self.assertNotIn("||", token)
            self.assertNotIn(";", token)

    def test_read_only_changes_argv(self):
        adapter = get("codex")
        read_only = adapter.build_command(
            brief="x", workdir="/tmp/repo",
            schema_path="/tmp/schema.json", read_only=True,
        )
        read_write = adapter.build_command(
            brief="x", workdir="/tmp/repo",
            schema_path="/tmp/schema.json", read_only=False,
        )
        self.assertNotEqual(read_only, read_write)
        self.assertIn("read-only", read_only)
        self.assertIn("workspace-write", read_write)
        # everything else stays identical
        self.assertEqual(len(read_only), len(read_write))

    def test_supports_schema(self):
        self.assertTrue(CodexAdapter().supports_schema)


class CodexParseTest(unittest.TestCase):
    def test_clean_result_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "result.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"status": "ok", "summary": "did the thing", "files": 2}, handle)
            result = get("codex").parse_result(
                exit_code=0, stdout="", stderr="", result_path=path,
            )
            self.assertFalse(result.parse_degraded)
            self.assertEqual(result.payload["status"], "ok")
            self.assertEqual(result.summary, "did the thing")

    def test_fenced_result_file_is_structured(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "result.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write('```json\n{"status": "ok", "summary": "fenced"}\n```\n')
            result = get("codex").parse_result(
                exit_code=0, stdout="", stderr="", result_path=path,
            )
            # The fence lives in the `-o` file, so this is still the structured
            # result (extract_json unwraps it) -> not degraded.
            self.assertFalse(result.parse_degraded)
            self.assertEqual(result.payload["status"], "ok")

    def test_missing_file_degrades_to_stdout(self):
        result = get("codex").parse_result(
            exit_code=0,
            stdout='{"status": "ok", "summary": "from stdout"}',
            stderr="",
            result_path="/nonexistent/taskproof/result.json",
        )
        self.assertTrue(result.parse_degraded)
        self.assertEqual(result.payload["status"], "ok")
        self.assertEqual(result.summary, "from stdout")

    def test_missing_file_plain_stdout_degrades_to_summary(self):
        result = get("codex").parse_result(
            exit_code=0,
            stdout="just some prose\nsecond line",
            stderr="",
            result_path="/nonexistent/taskproof/result.json",
        )
        self.assertTrue(result.parse_degraded)
        self.assertIsNone(result.payload)
        self.assertIn("second line", result.summary)

    def test_nothing_anywhere_raises(self):
        with self.assertRaises(ResultParseError):
            get("codex").parse_result(
                exit_code=0, stdout="", stderr="",
                result_path="/nonexistent/taskproof/result.json",
            )


class CustomCommandTest(unittest.TestCase):
    def test_placeholder_substitution(self):
        adapter = get("custom:my-agent --cwd {workdir} --task {prompt}")
        argv = adapter.build_command(
            brief="fix the bug", workdir="/tmp/repo",
            schema_path=None, read_only=False,
        )
        self.assertEqual(argv, ["my-agent", "--cwd", "/tmp/repo", "--task", "fix the bug"])

    def test_prompt_with_spaces_is_one_argv_element(self):
        adapter = get("custom:agent {prompt}")
        argv = adapter.build_command(
            brief="a b c", workdir="/tmp/repo", read_only=True,
        )
        self.assertEqual(argv, ["agent", "a b c"])

    def test_supports_schema_false(self):
        self.assertFalse(CustomAdapter(command="echo hi").supports_schema)

    def test_parse_result_degrades(self):
        result = CustomAdapter(command="agent").parse_result(
            exit_code=0, stdout='{"summary": "done"}', stderr="", result_path=None,
        )
        self.assertTrue(result.parse_degraded)
        self.assertEqual(result.summary, "done")

    def test_parse_result_empty_raises(self):
        with self.assertRaises(ResultParseError):
            CustomAdapter(command="agent").parse_result(
                exit_code=0, stdout="", stderr="", result_path=None,
            )


class PreflightTest(unittest.TestCase):
    def test_preflight_does_not_execute_agent(self):
        # On this machine codex exists, so preflight returns None; whatever the
        # machine, preflight must never raise and never run the agent.
        for name in ("codex", "claude", "gemini", "opencode"):
            problem = get(name).preflight()
            self.assertTrue(problem is None or isinstance(problem, str))


if __name__ == "__main__":
    unittest.main()
