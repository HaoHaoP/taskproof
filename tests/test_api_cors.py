"""Cross-origin read from the desktop renderer: CORS + preflight contract.

The desktop renderer is never same-origin with this API:

* dev builds fetch from the Vite dev server (``http://localhost:5173``);
* packaged builds fetch from a ``file://`` page, whose Origin is the literal
  string ``null``.

So the browser refuses to hand the renderer ``/api/health`` unless the response
carries ``Access-Control-Allow-Origin`` *for the caller's own origin*, and the
only routed verb is a simple ``GET``. There is no write surface and no session
token: ``OPTIONS`` still answers the preflight, but it advertises ``GET`` only.
``urllib`` never enforced the same-origin policy, so the old suite stayed green
while the app could read nothing; these assertions talk HTTP directly and pin
down the headers the browser actually checks.

A real server is bound to an ephemeral loopback port; nothing reaches the
network.
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


def _make(ws):
    from taskproof.api import server

    return server.make_server(ws, port=0)


class _ServerCase(unittest.TestCase):
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
        cls.httpd = _make(cls.ws)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=5)
        cls._tmp.cleanup()


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
    """d, e — OPTIONS advertises GET only, echoing the origin only."""

    _PREFLIGHT = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "content-type",
    }

    def test_d_allowed_origin_gets_a_get_only_preflight(self):
        status, headers, _ = _request(
            self.port, "OPTIONS", "/api/projects", dict(self._PREFLIGHT)
        )
        self.assertIn(status, (200, 201, 202, 203, 204, 205, 206))
        self.assertEqual(
            headers.get("access-control-allow-origin"), "http://localhost:5173"
        )
        self.assertEqual(headers.get("vary"), "Origin")
        raw_methods = headers.get("access-control-allow-methods", "")
        methods = {
            token.strip().upper() for token in raw_methods.split(",")
        }
        self.assertEqual(methods, {"GET"})
        # The write verbs must be gone from the advertised capability list.
        for verb in ("POST", "PATCH", "DELETE"):
            self.assertNotIn(verb, methods)
        allowed = headers.get("access-control-allow-headers", "").lower()
        self.assertIn("content-type", allowed)
        self.assertTrue(headers.get("access-control-max-age"))

    def test_e_foreign_origin_preflight_has_no_acao(self):
        headers_in = dict(self._PREFLIGHT)
        headers_in["Origin"] = "https://evil.example"
        status, headers, _ = _request(
            self.port, "OPTIONS", "/api/projects", headers_in
        )
        self.assertIn(status, (200, 201, 202, 203, 204, 205, 206))
        self.assertNotIn("access-control-allow-origin", headers)


class CorsReadOnlyRegressionTest(_ServerCase):
    """f — CORS does not resurrect a write path: there is simply no route.

    With the write surface gone the old endpoints are unrouted, so a write verb
    from an allowed origin is a plain 404 -- never a 403 (no gate) or 405.
    """

    def test_f_write_verb_is_404_even_with_cors_origin(self):
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
        self.assertEqual(status, 404, body)
        self.assertEqual(
            headers.get("access-control-allow-origin"), "http://localhost:5173"
        )


if __name__ == "__main__":
    unittest.main()
