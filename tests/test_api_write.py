"""Write surface: token gating, project CRUD, conflict detection, surgical edits.

A real server is bound to an ephemeral loopback port and exercised with
`urllib`. The registry is a hand-edited TOML file carrying comments and an
unknown key, so the tests double as a proof that writes never re-serialise.
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

from taskproof.api import server

_SENTINEL = object()


def _fixture(alpha_path, beta_path):
    return (
        "# taskproof registry - handwritten header, must survive writes\n"
        "\n"
        "[defaults]\n"
        "concurrency = 2   # inline human comment\n"
        "\n"
        "# alpha: note directly above the block (owned by alpha)\n"
        "[[project]]\n"
        'id = "alpha"\n'
        f'path = "{alpha_path}"\n'
        'group = "alpha"\n'
        'aliases = ["a", "aa"]\n'
        'verify = "exit 0"\n'
        'verify_kind = "check"\n'
        'forbidden_paths = ["dist/"]\n'
        'note = "keep me"   # unknown key that registry.load() drops\n'
        "\n"
        "# beta upstream note separated by a blank line (NOT owned by beta)\n"
        "\n"
        "# beta: note directly above the block (owned by beta)\n"
        "[[project]]\n"
        'id = "beta"\n'
        f'path = "{beta_path}"\n'
        'group = "beta"\n'
        'aliases = ["b"]\n'
        'verify = "exit 0"\n'
        'verify_kind = "check"\n'
    )


class _WriteServerCase(unittest.TestCase):
    """Shared harness. Subclasses pick whether writes are enabled."""

    allow_write = True
    token = "fixed-session-token-0123456789"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = os.path.join(self._tmp.name, "workspace")
        os.makedirs(self.ws)
        self.reg_path = os.path.join(self.ws, "projects.toml")
        alpha = os.path.join(self._tmp.name, "alpha-repo")
        beta = os.path.join(self._tmp.name, "beta-repo")
        os.makedirs(alpha)
        os.makedirs(beta)
        with open(self.reg_path, "w", encoding="utf-8") as fh:
            fh.write(_fixture(alpha, beta))

        self.httpd = server.make_server(
            self.ws, port=0, allow_write=self.allow_write, token=self.token
        )
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        self._tmp.cleanup()

    # -- helpers ----------------------------------------------------------

    def _request(self, path, *, method="GET", body=None, token=_SENTINEL):
        data = None
        headers = {}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if token is _SENTINEL:
            token = self.token
        if token is not None:
            headers["X-Taskproof-Token"] = token
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read().decode("utf-8"))
            finally:
                exc.close()

    def _read_registry(self):
        with open(self.reg_path, "rb") as fh:
            return fh.read()

    def _hash(self):
        return hashlib.sha256(self._read_registry()).hexdigest()

    def _current_hash(self):
        status, body = self._request("/api/registry")
        self.assertEqual(status, 200)
        return body["hash"]

    def _beta_bytes(self):
        text = self._read_registry().decode("utf-8")
        start = text.index("# beta upstream")
        return text[start:].encode("utf-8")


class DefaultReadOnlyTest(_WriteServerCase):
    """Without --allow-write the surface is exactly the old read-only one."""

    allow_write = False

    def test_every_write_verb_is_405(self):
        for method in ("POST", "PATCH", "DELETE", "PUT"):
            status, body = self._request(
                "/api/projects", method=method, body={"path": "/tmp"}
            )
            self.assertEqual(status, 405, method)
            self.assertIn("error", body)

    def test_405_even_with_a_token_header(self):
        status, _ = self._request(
            "/api/projects", method="POST", body={}, token="anything"
        )
        self.assertEqual(status, 405)

    def test_get_still_works(self):
        status, body = self._request("/api/projects")
        self.assertEqual(status, 200)
        self.assertEqual([p["id"] for p in body["projects"]], ["alpha", "beta"])


class TokenGateTest(_WriteServerCase):
    def test_missing_header_is_403(self):
        status, body = self._request(
            "/api/projects", method="POST", body={"path": "/tmp"}, token=None
        )
        self.assertEqual(status, 403)
        self.assertIn("error", body)

    def test_wrong_token_is_403(self):
        status, _ = self._request(
            "/api/projects",
            method="POST",
            body={"path": "/tmp"},
            token="not-the-token",
        )
        self.assertEqual(status, 403)

    def test_token_never_echoed_in_responses(self):
        status, body = self._request(
            "/api/projects",
            method="POST",
            body={"path": "/tmp"},
            token="not-the-token",
        )
        self.assertEqual(status, 403)
        self.assertNotIn(self.token, json.dumps(body))


class RegistryMetadataTest(_WriteServerCase):
    def test_registry_endpoint_reports_hash_and_path(self):
        status, body = self._request("/api/registry")
        self.assertEqual(status, 200)
        self.assertEqual(os.path.abspath(body["path"]), os.path.abspath(self.reg_path))
        self.assertEqual(body["hash"], self._hash())
        self.assertIsInstance(body["mtime"], float)


class ProbeTest(_WriteServerCase):
    def test_probe_returns_draft_without_writing(self):
        target = os.path.join(self._tmp.name, "probe-target")
        os.makedirs(target)
        with open(os.path.join(target, "pyproject.toml"), "w", encoding="utf-8") as fh:
            fh.write("[project]\nname = 'probe-target'\n")
        with open(os.path.join(target, "mod.py"), "w", encoding="utf-8") as fh:
            fh.write("x = 1\n")

        before = self._read_registry()
        status, body = self._request(
            "/api/projects/probe", method="POST", body={"path": target}
        )
        self.assertEqual(status, 200)
        for key in (
            "id",
            "path",
            "group",
            "verify",
            "verify_kind",
            "probe",
            "probe_exit",
            "aliases",
            "forbidden_paths",
        ):
            self.assertIn(key, body, key)
        self.assertEqual(body["id"], "probe-target")
        self.assertEqual(os.path.abspath(body["path"]), os.path.abspath(target))
        self.assertIn(body["probe"], ("passed", "failed", None))
        # The whole point: a probe must not touch the registry.
        self.assertEqual(self._read_registry(), before)

    def test_probe_rejects_missing_path(self):
        status, body = self._request(
            "/api/projects/probe",
            method="POST",
            body={"path": os.path.join(self._tmp.name, "nope")},
        )
        self.assertEqual(status, 400)
        self.assertIn("error", body)


class CreateTest(_WriteServerCase):
    def test_create_appends_and_is_visible(self):
        new_path = os.path.join(self._tmp.name, "gamma-repo")
        os.makedirs(new_path)
        expected = self._current_hash()
        status, body = self._request(
            "/api/projects",
            method="POST",
            body={
                "path": new_path,
                "expected_hash": expected,
                "id": "gamma",
                "group": "gamma",
                "verify": "exit 0",
                "verify_kind": "check",
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(body["project"]["id"], "gamma")

        status, body = self._request("/api/projects")
        self.assertEqual(status, 200)
        self.assertEqual([p["id"] for p in body["projects"]], ["alpha", "beta", "gamma"])

    def test_create_preserves_handwritten_comments(self):
        new_path = os.path.join(self._tmp.name, "gamma-repo")
        os.makedirs(new_path)
        status, _ = self._request(
            "/api/projects",
            method="POST",
            body={"path": new_path, "expected_hash": self._hash(), "id": "gamma"},
        )
        self.assertEqual(status, 201)
        text = self._read_registry().decode("utf-8")
        self.assertIn("# taskproof registry - handwritten header", text)
        self.assertIn("# alpha: note directly above the block", text)
        self.assertIn("# beta upstream note", text)
        self.assertIn("# inline human comment", text)

    def test_create_requires_absolute_existing_path(self):
        status, body = self._request(
            "/api/projects",
            method="POST",
            body={
                "path": os.path.join(self._tmp.name, "ghost"),
                "expected_hash": self._hash(),
            },
        )
        self.assertEqual(status, 400)
        self.assertIn("error", body)


class UpdateTest(_WriteServerCase):
    def test_update_changes_fields_on_disk(self):
        status, body = self._request(
            "/api/projects/alpha",
            method="PATCH",
            body={
                "expected_hash": self._hash(),
                "aliases": ["a", "aa", "alpha"],
                "group": "renamed-group",
                "verify": "exit 1",
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["project"]["group"], "renamed-group")
        self.assertEqual(body["project"]["aliases"], ["a", "aa", "alpha"])
        self.assertEqual(body["project"]["verify"], "exit 1")

        text = self._read_registry().decode("utf-8")
        self.assertIn('group = "renamed-group"', text)
        self.assertIn('aliases = ["a", "aa", "alpha"]', text)
        self.assertIn('verify = "exit 1"', text)

    def test_update_leaves_other_project_bytes_untouched(self):
        before = self._beta_bytes()
        status, _ = self._request(
            "/api/projects/alpha",
            method="PATCH",
            body={"expected_hash": self._hash(), "group": "moved"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(self._beta_bytes(), before)

    def test_update_preserves_unknown_keys(self):
        status, _ = self._request(
            "/api/projects/alpha",
            method="PATCH",
            body={"expected_hash": self._hash(), "group": "moved"},
        )
        self.assertEqual(status, 200)
        self.assertIn('note = "keep me"', self._read_registry().decode("utf-8"))

    def test_update_id_is_400(self):
        before = self._read_registry()
        status, body = self._request(
            "/api/projects/alpha",
            method="PATCH",
            body={"expected_hash": self._hash(), "id": "omega"},
        )
        self.assertEqual(status, 400)
        self.assertIn("error", body)
        self.assertEqual(self._read_registry(), before)

    def test_update_path_is_400(self):
        before = self._read_registry()
        status, body = self._request(
            "/api/projects/alpha",
            method="PATCH",
            body={"expected_hash": self._hash(), "path": "/somewhere/else"},
        )
        self.assertEqual(status, 400)
        self.assertIn("error", body)
        self.assertEqual(self._read_registry(), before)

    def test_update_unknown_id_is_404(self):
        status, body = self._request(
            "/api/projects/nope",
            method="PATCH",
            body={"expected_hash": self._hash(), "group": "x"},
        )
        self.assertEqual(status, 404)
        self.assertIn("error", body)

    def test_update_clearing_verify_sets_kind_none(self):
        status, body = self._request(
            "/api/projects/alpha",
            method="PATCH",
            body={"expected_hash": self._hash(), "verify": None},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["project"]["verify"], None)
        self.assertEqual(body["project"]["verify_kind"], "none")
        text = self._read_registry().decode("utf-8")
        # alpha's line is gone; beta (same command) still carries one.
        self.assertEqual(text.count('verify = "exit 0"'), 1)
        self.assertIn('verify_kind = "none"', text)


class DeleteTest(_WriteServerCase):
    def test_delete_removes_block_and_owned_comment_keeps_upstream(self):
        status, body = self._request(
            "/api/projects/beta",
            method="DELETE",
            body={"expected_hash": self._hash()},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["removed"], "beta")

        text = self._read_registry().decode("utf-8")
        self.assertNotIn('id = "beta"', text)
        self.assertNotIn("# beta: note directly above the block", text)
        # Separated by a blank line -> it belongs to nobody in particular.
        self.assertIn("# beta upstream note", text)
        # The other project is intact.
        self.assertIn('id = "alpha"', text)
        self.assertIn('note = "keep me"', text)

    def test_delete_unknown_id_is_404(self):
        status, body = self._request(
            "/api/projects/nope",
            method="DELETE",
            body={"expected_hash": self._hash()},
        )
        self.assertEqual(status, 404)
        self.assertIn("error", body)

    def test_delete_leaves_other_project_untouched(self):
        before = self._beta_bytes()
        status, _ = self._request(
            "/api/projects/alpha",
            method="DELETE",
            body={"expected_hash": self._hash()},
        )
        self.assertEqual(status, 200)
        self.assertEqual(self._beta_bytes(), before)


class ConflictTest(_WriteServerCase):
    def test_stale_hash_conflicts_and_does_not_write(self):
        stale = self._hash()
        # Someone edited the file by hand after we read the hash.
        with open(self.reg_path, "a", encoding="utf-8") as fh:
            fh.write("\n# hand edit after the read\n")
        current = self._read_registry()

        status, body = self._request(
            "/api/projects",
            method="POST",
            body={
                "path": os.path.join(self._tmp.name, "alpha-repo"),
                "expected_hash": stale,
                "id": "gamma",
            },
        )
        self.assertEqual(status, 409)
        self.assertEqual(body["error"], "conflict")
        self.assertEqual(body["hash"], hashlib.sha256(current).hexdigest())
        self.assertIn("content", body)
        self.assertIn("# hand edit after the read", body["content"])
        self.assertIsInstance(body["projects"], list)
        # A conflict must never write.
        self.assertEqual(self._read_registry(), current)

    def test_conflict_on_patch(self):
        stale = self._hash()
        with open(self.reg_path, "a", encoding="utf-8") as fh:
            fh.write("\n# another hand edit\n")
        current = self._read_registry()
        status, body = self._request(
            "/api/projects/alpha",
            method="PATCH",
            body={"expected_hash": stale, "group": "x"},
        )
        self.assertEqual(status, 409)
        self.assertEqual(body["error"], "conflict")
        self.assertEqual(self._read_registry(), current)


class ProjectFieldsTest(_WriteServerCase):
    def test_projects_list_includes_probe_fields(self):
        # Give alpha a probe verdict the way the CLI writes it.
        text = self._read_registry().decode("utf-8")
        text = text.replace(
            'note = "keep me"   # unknown key that registry.load() drops\n',
            'note = "keep me"\n' 'probe = "passed"\n' "probe_exit = 0\n",
        )
        with open(self.reg_path, "w", encoding="utf-8") as fh:
            fh.write(text)

        status, body = self._request("/api/projects")
        self.assertEqual(status, 200)
        alpha = next(p for p in body["projects"] if p["id"] == "alpha")
        self.assertEqual(alpha["probe"], "passed")
        self.assertEqual(alpha["probe_exit"], 0)

    def test_projects_without_verify_report_probe_none(self):
        status, body = self._request("/api/projects")
        self.assertEqual(status, 200)
        beta = next(p for p in body["projects"] if p["id"] == "beta")
        self.assertEqual(beta["verify_kind"], "check")
        self.assertIn("probe", beta)
        self.assertIn("probe_exit", beta)


class TokenStdoutTest(unittest.TestCase):
    """`api --allow-write` prints exactly two lines; the token leaks nowhere."""

    def test_stdout_has_two_lines_and_token_is_not_on_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = os.path.join(tmp, "workspace")
            os.makedirs(ws)
            with open(os.path.join(ws, "projects.toml"), "w", encoding="utf-8") as fh:
                fh.write("[defaults]\nconcurrency = 1\n")

            env = dict(os.environ)
            env["PYTHONPATH"] = os.path.join(os.getcwd(), "src")
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "taskproof",
                    "--workspace",
                    ws,
                    "api",
                    "--allow-write",
                    "--port",
                    "0",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            lines = []

            def _reader():
                for _ in range(2):
                    line = proc.stdout.readline()
                    if not line:
                        break
                    lines.append(line)

            reader = threading.Thread(target=_reader, daemon=True)
            reader.start()
            reader.join(timeout=20)
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

            if proc.stdout is not None:
                proc.stdout.close()
            if proc.stderr is not None:
                proc.stderr.close()
            self.assertEqual(len(lines), 2, f"expected 2 lines, got {lines!r}")
            self.assertRegex(lines[0], r"^taskproof api listening on http://127\.0\.0\.1:\d+\n$")
            self.assertRegex(lines[1], r"^taskproof api token \S+\n$")

            token = lines[1].split()[-1]
            self.assertGreaterEqual(len(token), 32)

            # The token must not be readable from anything inside the workspace.
            for root, _dirs, files in os.walk(ws):
                for name in files:
                    with open(os.path.join(root, name), "rb") as fh:
                        self.assertNotIn(token.encode("utf-8"), fh.read(), name)

    def test_read_only_start_prints_only_one_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = os.path.join(tmp, "workspace")
            os.makedirs(ws)
            with open(os.path.join(ws, "projects.toml"), "w", encoding="utf-8") as fh:
                fh.write("[defaults]\nconcurrency = 1\n")
            env = dict(os.environ)
            env["PYTHONPATH"] = os.path.join(os.getcwd(), "src")
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "taskproof",
                    "--workspace",
                    ws,
                    "api",
                    "--port",
                    "0",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            lines = []

            def _reader():
                for line in proc.stdout:
                    lines.append(line)

            reader = threading.Thread(target=_reader, daemon=True)
            reader.start()
            # Give the (slow) second line a chance to appear before asserting.
            time.sleep(1.5)
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
            reader.join(timeout=5)

            if proc.stdout is not None:
                proc.stdout.close()
            if proc.stderr is not None:
                proc.stderr.close()
            self.assertEqual(len(lines), 1, f"read-only start printed: {lines!r}")
            self.assertRegex(
                lines[0], r"^taskproof api listening on http://127\.0\.0\.1:\d+\n$"
            )
            self.assertNotIn("taskproof api token", "".join(lines))


if __name__ == "__main__":
    unittest.main()
