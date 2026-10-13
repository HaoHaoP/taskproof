"""The live board server: real REST API handler + static web build.

`taskproof board` now serves the desktop renderer's built web assets and the
full REST API from one loopback origin. These tests bind a *real*
``ThreadingHTTPServer`` (via ``make_server(..., static_root=...)``) against a
throwaway web directory and speak HTTP to it directly, so the exact status
codes, content types, caching headers and the path-traversal boundary are
pinned.

Covered:
  * static hits resolve with the right ``Content-Type`` and ``Cache-Control``;
  * a missing *extension-shaped* path is a 404 and never the SPA fallback;
  * ``/`` / extension-less / directory paths fall back to ``index.html``;
  * ``..`` and ``%2e%2e%2f`` escapes (and an out-of-tree symlink) are refused;
  * a sibling ``<file>.gz`` is preferred when the client accepts gzip;
  * the retired ``?project=``/``?task=`` query 302s onto the hash router;
  * a missing web directory makes ``cmd_board`` a ``UsageError``;
  * ``--out`` / ``--snapshot`` / ``--project`` are gone from the CLI.
"""

import contextlib
import gzip
import http.client
import io
import os
import tempfile
import threading
import unittest
from unittest import mock

from taskproof import cli, errors
from taskproof.api import server


def _request(port, path, headers=None):
    """Return ``(status, headers_dict, body_bytes)`` with lower-cased keys."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("GET", path, headers=headers or {})
        response = conn.getresponse()
        body = response.read()
        lowered = {key.lower(): value for key, value in response.getheaders()}
        return response.status, lowered, body
    finally:
        conn.close()


class _WebCase(unittest.TestCase):
    """A real server in front of a temp web build."""

    #: ``<file> -> (extension, expected Content-Type)`` for the required set.
    _TYPED = {
        "index.html": "text/html; charset=utf-8",
        "app.js": "text/javascript; charset=utf-8",
        "style.css": "text/css; charset=utf-8",
        "icon.svg": "image/svg+xml",
        "logo.png": "image/png",
        "favicon.ico": "image/x-icon",
        "data.json": "application/json; charset=utf-8",
        "app.js.map": "application/json; charset=utf-8",
        "font.woff2": "font/woff2",
        "blob.bin": "application/octet-stream",
    }

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = os.path.realpath(cls._tmp.name)
        cls.web = os.path.join(cls.root, "web")
        os.makedirs(cls.web)
        for name in cls._TYPED:
            with open(os.path.join(cls.web, name), "wb") as fh:
                fh.write(b"payload:" + name.encode())
        # A nested asset plus a pre-compressed sibling.
        os.makedirs(os.path.join(cls.web, "assets"))
        with open(os.path.join(cls.web, "assets", "chunk.js"), "wb") as fh:
            fh.write(b"console.log('chunk')")
        with gzip.open(os.path.join(cls.web, "assets", "chunk.js.gz"), "wb") as fh:
            fh.write(b"console.log('chunk')")
        # An out-of-tree secret reachable only by a symlink inside the root.
        with open(os.path.join(cls.root, "secret.txt"), "w", encoding="utf-8") as fh:
            fh.write("top secret")
        os.symlink(
            os.path.join(cls.root, "secret.txt"),
            os.path.join(cls.web, "leak.txt"),
        )

        cls.ws = os.path.join(cls.root, "workspace")
        os.makedirs(cls.ws, exist_ok=True)
        cls.httpd = server.make_server(cls.ws, port=0, static_root=cls.web)
        cls.port = cls.httpd.server_address[1]
        cls._thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls._thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls._thread.join(timeout=5)
        cls._tmp.cleanup()

    def get(self, path, headers=None):
        return _request(self.port, path, headers)


class StaticHitTest(_WebCase):
    def test_required_extensions_get_their_content_type(self):
        for name, expected in self._TYPED.items():
            with self.subTest(name=name):
                status, headers, body = self.get("/" + name)
                self.assertEqual(status, 200, name)
                self.assertEqual(headers["content-type"], expected, name)
                self.assertEqual(headers["cache-control"], "no-cache", name)
                self.assertEqual(body, b"payload:" + name.encode(), name)

    def test_nested_asset_is_served(self):
        status, headers, body = self.get("/assets/chunk.js")
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "text/javascript; charset=utf-8")
        self.assertEqual(body, b"console.log('chunk')")

    def test_gzip_sibling_is_preferred_with_vary(self):
        status, headers, body = self.get(
            "/assets/chunk.js", {"Accept-Encoding": "gzip"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-encoding"], "gzip")
        self.assertEqual(headers["vary"], "Accept-Encoding")
        self.assertEqual(gzip.decompress(body), b"console.log('chunk')")

    def test_gzip_is_ignored_without_the_request_header(self):
        status, headers, body = self.get("/assets/chunk.js")
        self.assertEqual(status, 200)
        self.assertNotIn("content-encoding", headers)
        self.assertEqual(body, b"console.log('chunk')")


class SPAFallbackTest(_WebCase):
    def test_root_serves_index(self):
        status, headers, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "text/html; charset=utf-8")
        self.assertEqual(body, b"payload:index.html")

    def test_extensionless_path_falls_back_to_index(self):
        status, headers, body = self.get("/matrix")
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "text/html; charset=utf-8")
        self.assertEqual(body, b"payload:index.html")

    def test_directory_falls_back_to_index(self):
        status, headers, body = self.get("/assets/")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"payload:index.html")

    def test_missing_asset_is_404_never_html(self):
        status, headers, body = self.get("/assets/missing.js")
        self.assertEqual(status, 404)
        self.assertEqual(headers["content-type"], "application/json; charset=utf-8")
        self.assertNotIn(b"<html", body.lower())

    def test_api_paths_still_route_to_the_api(self):
        status, headers, _ = self.get("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "application/json; charset=utf-8")


class TraversalTest(_WebCase):
    def test_plain_dotdot_is_refused(self):
        status, _, _ = self.get("/../secret.txt")
        self.assertEqual(status, 403)

    def test_encoded_dotdot_is_refused(self):
        status, _, _ = self.get("/%2e%2e%2fsecret.txt")
        self.assertEqual(status, 403)

    def test_out_of_tree_symlink_is_refused(self):
        status, _, _ = self.get("/leak.txt")
        self.assertEqual(status, 403)


class LegacyQueryRedirectTest(_WebCase):
    def _location(self, path):
        status, headers, _ = self.get(path)
        self.assertEqual(status, 302, path)
        return headers["location"]

    def test_projects_redirect_to_hash_route(self):
        self.assertEqual(
            self._location("/?project=a&project=b"),
            "/#/matrix?projects=a,b",
        )

    def test_task_redirects_to_matrix_route(self):
        self.assertEqual(self._location("/?task=x"), "/#/matrix/x")

    def test_task_and_projects_combine(self):
        self.assertEqual(
            self._location("/?task=x&project=a&project=b"),
            "/#/matrix/x?projects=a,b",
        )

    def test_blank_filters_serve_index_instead(self):
        status, _, body = self.get("/?project=")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"payload:index.html")


class MissingWebRootTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = os.path.join(self._tmp.name, "workspace")
        self.missing = os.path.join(self._tmp.name, "no-such-web")

    def tearDown(self):
        self._tmp.cleanup()

    def test_cmd_board_without_web_build_is_a_usage_error(self):
        args = cli.build_parser().parse_args(
            ["--workspace", self.ws, "board", "--serve"]
        )
        with mock.patch.object(cli, "_board_static_root", return_value=self.missing):
            with self.assertRaises(errors.UsageError) as ctx:
                cli.cmd_board(args)
        message = str(ctx.exception)
        self.assertIn("missing", message)
        self.assertIn("npm run build:web", ctx.exception.hint)
        self.assertIn("desktop/", ctx.exception.hint)


class MissingIndexTest(unittest.TestCase):
    """A root without ``index.html`` is a clean 500, never a bare traceback."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.web = os.path.join(self._tmp.name, "web")
        os.makedirs(self.web)
        self.ws = os.path.join(self._tmp.name, "workspace")
        self.httpd = server.make_server(self.ws, port=0, static_root=self.web)
        self.port = self.httpd.server_address[1]
        self._thread = threading.Thread(
            target=self.httpd.serve_forever, daemon=True
        )
        self._thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self._thread.join(timeout=5)
        self._tmp.cleanup()

    def test_missing_index_is_500_json(self):
        status, headers, body = _request(self.port, "/")
        self.assertEqual(status, 500)
        self.assertEqual(headers["content-type"], "application/json; charset=utf-8")
        self.assertIn(b"index.html", body)


class RemovedFlagsTest(unittest.TestCase):
    """The snapshot parameter surface is gone, not silently ignored."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = os.path.join(self._tmp.name, "workspace")

    def tearDown(self):
        self._tmp.cleanup()

    def _parse(self, *argv):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as ctx:
                cli.build_parser().parse_args(
                    ["--workspace", self.ws, "board", *argv]
                )
        # The CLI's `_UsageErrorParser` maps bad invocations to its documented
        # usage exit code (64), not argparse's bare default of 2.
        self.assertEqual(ctx.exception.code, errors.EXIT_USAGE)
        return err.getvalue()

    def test_out_flag_is_gone(self):
        self.assertIn("--out", self._parse("--out", "x.html"))

    def test_snapshot_flag_is_gone(self):
        self.assertIn("--snapshot", self._parse("--snapshot"))

    def test_project_flag_is_gone(self):
        self.assertIn("--project", self._parse("--project", "alpha"))


if __name__ == "__main__":
    unittest.main()
