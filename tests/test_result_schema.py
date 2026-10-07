"""Structured-result contract wiring.

Pinned here:
  * an omitted (or explicit ``"default"``) ``result_schema`` resolves to the
    package-shipped schema, which exists and is valid JSON
  * ``"none"`` disables structured output (no ``--output-schema``) and records
    an explicit task event — a free-text result is never silent
  * a missing custom path, a relative path, and a non-string value are refused
    with ``RegistryError`` (never a silent fall back to the default)
  * the built-in schema satisfies DeepSeek strict mode: every object level
    lists ALL of its ``properties`` keys as ``required`` (recursively)
  * a proxy in the parent env cannot hijack a loopback service: ``no_proxy`` /
    ``NO_PROXY`` are extended with 127.0.0.1 / localhost / ::1, merged — never
    overwritten
"""

import io
import json
import os
import tempfile
import textwrap
import unittest
from unittest import mock

from taskproof import registry
from taskproof.adapters import get
from taskproof.dispatch import (
    _ensure_localhost_no_proxy,
    _run_adapter,
    dispatch,
    prepare_workspace,
    task_detail,
)
from taskproof.errors import RegistryError


def _q(value) -> str:
    """A minimal TOML basic string."""
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


class SchemaResolutionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, body):
        path = os.path.join(self.tmp.name, "projects.toml")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(textwrap.dedent(body))
        return path

    def test_omitted_defaults_to_packaged_schema(self):
        path = self.write(
            f"""
            [[project]]
            id = "p"
            path = {_q(self.tmp.name)}
            """
        )
        project = registry.load(path).by_id("p")
        self.assertEqual(project.result_schema, "default")

        resolved = registry.result_schema_path(project)
        self.assertEqual(resolved, registry.builtin_result_schema_path())
        self.assertTrue(os.path.isfile(resolved))
        with open(resolved, encoding="utf-8") as fh:
            json.load(fh)  # must be valid JSON

    def test_explicit_default_equals_omitted(self):
        path = self.write(
            f"""
            [[project]]
            id = "p"
            path = {_q(self.tmp.name)}
            result_schema = "default"
            """
        )
        project = registry.load(path).by_id("p")
        self.assertEqual(
            registry.result_schema_path(project), registry.builtin_result_schema_path()
        )

    def test_none_disables_structured_result(self):
        path = self.write(
            f"""
            [[project]]
            id = "p"
            path = {_q(self.tmp.name)}
            result_schema = "none"
            """
        )
        project = registry.load(path).by_id("p")
        self.assertIsNone(registry.result_schema_path(project))

    def test_custom_path_is_used(self):
        schema = os.path.join(self.tmp.name, "custom.json")
        with open(schema, "w", encoding="utf-8") as fh:
            fh.write("{}")
        path = self.write(
            f"""
            [[project]]
            id = "p"
            path = {_q(self.tmp.name)}
            result_schema = {_q(schema)}
            """
        )
        project = registry.load(path).by_id("p")
        self.assertEqual(registry.result_schema_path(project), schema)

    def test_missing_custom_path_is_rejected(self):
        missing = os.path.join(self.tmp.name, "nope.json")
        path = self.write(
            f"""
            [[project]]
            id = "p"
            path = {_q(self.tmp.name)}
            result_schema = {_q(missing)}
            """
        )
        with self.assertRaises(RegistryError) as ctx:
            registry.load(path)
        # The message must name the offending path — no silent fall back.
        self.assertIn(missing, str(ctx.exception))

    def test_relative_custom_path_is_rejected(self):
        path = self.write(
            f"""
            [[project]]
            id = "p"
            path = {_q(self.tmp.name)}
            result_schema = "schemas/result.json"
            """
        )
        with self.assertRaises(RegistryError):
            registry.load(path)

    def test_non_string_result_schema_is_rejected(self):
        for raw in ("true", "1"):
            with self.subTest(raw=raw):
                path = self.write(
                    f"""
                    [[project]]
                    id = "p"
                    path = {_q(self.tmp.name)}
                    result_schema = {raw}
                    """
                )
                with self.assertRaises(RegistryError):
                    registry.load(path)


class BuiltinSchemaStrictModeTest(unittest.TestCase):
    """DeepSeek strict mode: required must list every property key, recursively."""

    def test_all_object_levels_list_every_property_as_required(self):
        with open(registry.builtin_result_schema_path(), encoding="utf-8") as fh:
            schema = json.load(fh)

        visited = []

        def check(node, where):
            if isinstance(node, dict):
                if "properties" in node:
                    props = node["properties"]
                    self.assertIsInstance(props, dict, f"{where}: properties")
                    required = node.get("required")
                    self.assertIsInstance(required, list, f"{where}: required")
                    self.assertEqual(
                        set(props),
                        set(required),
                        f"{where}: required must list every property key",
                    )
                    self.assertIs(
                        node.get("additionalProperties"),
                        False,
                        f"{where}: additionalProperties must be false",
                    )
                    for name, subschema in props.items():
                        check(subschema, f"{where}.{name}")
                if "items" in node:
                    check(node["items"], f"{where}[]")
                visited.append(where)
            elif isinstance(node, list):
                for index, item in enumerate(node):
                    check(item, f"{where}[{index}]")

        check(schema, "$")
        # Sanity: the top level was actually inspected.
        self.assertIn("$", visited)

    def test_top_level_fields_are_the_contract(self):
        with open(registry.builtin_result_schema_path(), encoding="utf-8") as fh:
            schema = json.load(fh)
        self.assertEqual(
            list(schema["properties"]),
            [
                "status",
                "summary",
                "files_changed",
                "verify",
                "blockers",
                "needs_approval",
                "contract_dispute",
            ],
        )


class PipelineSchemaWiringTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = os.path.join(self.tmp.name, "ws")
        self.proj = os.path.join(self.tmp.name, "proj")
        os.makedirs(self.proj)
        prepare_workspace(self.ws)

    def tearDown(self):
        self.tmp.cleanup()

    def write_registry(self, extra=""):
        body = (
            "[defaults]\n"
            "concurrency = 3\n"
            "timeout = 60\n\n"
            "[[project]]\n"
            'id = "proj"\n'
            f"path = {_q(self.proj)}\n"
            'group = "g"\n'
            'verify = "exit 0"\n'
            'verify_kind = "check"\n'
            + extra
        )
        with open(os.path.join(self.ws, "projects.toml"), "w", encoding="utf-8") as fh:
            fh.write(body)

    def _run_capturing_schema(self):
        captured = {}

        def fake_run_adapter(adapter_obj, *, brief, workdir, log_path,
                             schema_path=None, read_only=False):
            captured["schema_path"] = schema_path
            return 0, '{"status": "done", "summary": "ok"}', ""

        with mock.patch("taskproof.dispatch._run_adapter", side_effect=fake_run_adapter):
            task_id = dispatch(self.ws, "proj", "x", adapter="custom:echo hi")
        return task_id, captured

    def _result_schema_events(self, task_id):
        events = task_detail(self.ws, task_id)["events"]
        return [e for e in events if e["event"] == "result_schema"]

    def test_default_schema_is_passed_to_adapter(self):
        self.write_registry()
        task_id, captured = self._run_capturing_schema()

        self.assertEqual(captured["schema_path"], registry.builtin_result_schema_path())
        events = self._result_schema_events(task_id)
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0]["payload"]["enabled"])
        self.assertEqual(
            events[0]["payload"]["path"], registry.builtin_result_schema_path()
        )

    def test_none_passes_no_schema_and_records_event(self):
        self.write_registry('result_schema = "none"\n')
        task_id, captured = self._run_capturing_schema()

        self.assertIsNone(captured["schema_path"])
        events = self._result_schema_events(task_id)
        self.assertEqual(len(events), 1)
        payload = events[0]["payload"]
        self.assertFalse(payload["enabled"])
        self.assertIn("disabled", payload["note"])

    def test_custom_schema_path_is_passed(self):
        schema = os.path.join(self.tmp.name, "custom.json")
        with open(schema, "w", encoding="utf-8") as fh:
            fh.write("{}")
        self.write_registry(f"result_schema = {_q(schema)}\n")
        _, captured = self._run_capturing_schema()
        self.assertEqual(captured["schema_path"], schema)


class _FakeProc:
    """Minimal stand-in for subprocess.Popen, used to capture the child env."""

    def __init__(self, argv, env, stdout_text="ok\n", stderr_text=""):
        self.argv = argv
        self.env = env
        self.stdout = io.StringIO(stdout_text)
        self.stderr = io.StringIO(stderr_text)

    def wait(self, timeout=None):
        return 0


class NoProxyDefenceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_helper_merges_existing_no_proxy(self):
        env = {"https_proxy": "http://proxy:8080", "no_proxy": "example.com"}
        _ensure_localhost_no_proxy(env)
        entries = [e.strip() for e in env["no_proxy"].split(",")]
        self.assertIn("example.com", entries)  # user value preserved
        self.assertIn("127.0.0.1", entries)
        self.assertIn("localhost", entries)
        self.assertIn("::1", entries)
        # NO_PROXY is filled in too.
        self.assertIn("127.0.0.1", env["NO_PROXY"])

    def test_helper_leaves_env_alone_without_proxy(self):
        env = {"no_proxy": "example.com"}
        _ensure_localhost_no_proxy(env)
        self.assertEqual(env["no_proxy"], "example.com")
        self.assertNotIn("NO_PROXY", env)

    def test_child_env_has_loopback_no_proxy(self):
        captured = {}

        def fake_popen(argv, **kwargs):
            captured["argv"] = argv
            captured["env"] = kwargs["env"]
            return _FakeProc(argv, kwargs.get("env"))

        adapter = get("codex")
        log_path = os.path.join(self.tmp.name, "run.log")
        with mock.patch("taskproof.dispatch.subprocess.Popen", side_effect=fake_popen):
            with mock.patch.dict(
                os.environ,
                {"https_proxy": "http://proxy:8080", "no_proxy": "example.com"},
                clear=False,
            ):
                os.environ.pop("NO_PROXY", None)
                exit_code, _, _ = _run_adapter(
                    adapter, brief="x", workdir=self.tmp.name, log_path=log_path
                )

        self.assertEqual(exit_code, 0)
        env = captured["env"]
        for name in ("no_proxy", "NO_PROXY"):
            entries = [e.strip() for e in env[name].split(",")]
            self.assertIn("127.0.0.1", entries, name)
            self.assertIn("localhost", entries, name)
            self.assertIn("::1", entries, name)
        # The user's existing entry survived the merge.
        self.assertIn("example.com", [e.strip() for e in env["no_proxy"].split(",")])


if __name__ == "__main__":
    unittest.main()
