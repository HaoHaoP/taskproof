"""Cross-origin read from the desktop renderer: CORS + preflight contract.

The desktop renderer is never same-origin with this API:

* dev builds fetch from the Vite dev server (``http://localhost:5173``);
* packaged builds fetch from a ``file://`` page, whose Origin is the literal
  string ``null``.

So the browser refuses to hand the renderer ``/api/health`` unless the response
carries ``Access-Control-Allow-Origin`` *for the caller's own origin*, and it
refuses every ``content-type: application/json`` write (POST/PATCH/DELETE)
unless ``OPTIONS`` answers the preflight with matching ``Allow-Methods`` /
``Allow-Headers``. ``urllib`` never enforced the same-origin policy, so the old
suite stayed green while the app could read nothing; these assertions talk HTTP
directly and pin down the headers the browser actually checks.

A real server is bound to an ephemeral loopback port; nothing reaches the
network. Writes (case f) run against a ``/tmp`` one-shot workspace only.
"""

import http.client
import os
import tempfile
import threading
import unittest

from taskproof import dispatch, registry


def _request(port, method, path, headers=None):
    """Return ``(status, headers_dict, body_bytes)`` with lower-cased keys."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request(method, path, headers=headers or {})
        response = conn.getresponse()
        body = response.read()
        lowered = {key.lower(): value for key, value in response.getheaders()}
        return response.status, lowered, body
    finally:
        conn.close()


class _ServerCase(unittest.TestCase):
    allow_write = False
    token = None

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.ws = os.path.join(cls._tmp.name, "workspace")
        dispatch.prepare_workspace(cls.ws)
        with open(
            registry.workspace_registry_path(cls.ws), "w", encoding="utf-8"
        ) as fh:
            fh.write(
                "[[project]]\n"
                'id = "proj"\n'
                f'path = "{cls._tmp.name}"\n'
                'group = "proj"\n'
                'verify = "exit 0"\n'
                'verify_kind = "check"\n'
            )
        cls.httpd = _make(cls.ws, cls.allow_write, cls.token)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=5)
        cls._tmp.cleanup()


def _make(ws, allow_write, token):
    from taskproof.api import server

    return server.make_server(ws, port=0, allow_write=allow_write, token=token)


class PreflightContractTest(_ServerCase):
    """a, b, c — a simple GET must carry the echoing ACAO for the caller only."""

    def test_a_dev_origin_gets_echoed_acao_and_vary(self):
        status, headers, _ = _request(
            self.port,
            "GET",
            "/api/health",
            {"Origin": "http://localhost:5173"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            headers.get("access-control-allow-origin"), "http://localhost:5173"
        )
        self.assertEqual(headers.get("vary"), "Origin")

    def test_b_file_origin_null_gets_null_acao(self):
        status, headers, _ = _request(
            self.port, "GET", "/api/health", {"Origin": "null"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("access-control-allow-origin"), "null")

    def test_c_foreign_origin_gets_no_acao(self):
        status, headers, _ = _request(
            self.port,
            "GET",
            "/api/health",
            {"Origin": "https://evil.example"},
        )
        self.assertEqual(status, 200)
        self.assertNotIn("access-control-allow-origin", headers)


class PreflightOptionTest(_ServerCase):
    """d, e — OPTIONS answers the write preflight, echoing the origin only."""

    _PREFLIGHT = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,x-taskproof-token",
    }

    def test_d_allowed_origin_gets_a_full_preflight(self):
        status, headers, _ = _request(
            self.port, "OPTIONS", "/api/projects", dict(self._PREFLIGHT)
        )
        self.assertIn(status, (200, 201, 202, 203, 204, 205, 206))
        self.assertEqual(
            headers.get("access-control-allow-origin"), "http://localhost:5173"
        )
        self.assertEqual(headers.get("vary"), "Origin")
        methods = {
            token.strip().upper()
            for token in headers.get("access-control-allow-methods", "").split(",")
        }
        for verb in ("POST", "PATCH", "DELETE"):
            self.assertIn(verb, methods)
        allowed = headers.get("access-control-allow-headers", "").lower()
        self.assertIn("content-type", allowed)
        self.assertIn("x-taskproof-token", allowed)
        self.assertTrue(headers.get("access-control-max-age"))

    def test_e_foreign_origin_preflight_has_no_acao(self):
        headers_in = dict(self._PREFLIGHT)
        headers_in["Origin"] = "https://evil.example"
        status, headers, _ = _request(
            self.port, "OPTIONS", "/api/projects", headers_in
        )
        self.assertIn(status, (200, 201, 202, 203, 204, 205, 206))
        self.assertNotIn("access-control-allow-origin", headers)


class CorsWriteGateRegressionTest(_ServerCase):
    """f — CORS must not loosen the write gate (no token, or no --allow-write)."""

    allow_write = True
    token = "fixed-session-token-0123456789"

    def test_f_missing_token_still_forbidden(self):
        status, headers, body = _request(
            self.port,
            "POST",
            "/api/projects",
            {
                "Origin": "http://localhost:5173",
                "Content-Type": "application/json",
                "Content-Length": "2",
            },
        )
        self.assertEqual(status, 403, body)
        self.assertEqual(
            headers.get("access-control-allow-origin"), "http://localhost:5173"
        )


class CorsReadOnlyGateRegressionTest(_ServerCase):
    """f — without --allow-write every write verb is still 405, CORS or not."""

    allow_write = False

    def test_f_write_verb_is_405_without_allow_write(self):
        status, _, body = _request(
            self.port,
            "POST",
            "/api/projects",
            {
                "Origin": "http://localhost:5173",
                "Content-Type": "application/json",
                "Content-Length": "2",
            },
        )
        self.assertEqual(status, 405, body)


if __name__ == "__main__":
    unittest.main()
