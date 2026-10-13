"""`taskproof board` parameter semantics: one mode, serve the desktop build.

`board` binds a loopback HTTP server that answers the real REST API *and* the
desktop renderer's web build; the browser sees the desktop UI. There is no
snapshot mode any more, so the only question these tests pin is *how* the live
server is wired:

  * a bare `board` and `--open` both serve and open a browser;
  * `--serve [PORT]` serves only (no browser), and blocks either way;
  * the browser is opened *after* a successful bind, pointing at
    ``http://127.0.0.1:<port>/`` with the port the socket actually bound.

``_board_static_root`` is patched to a temp directory so `_board_serve` reaches
the bind instead of failing on the (build-time) ``src/taskproof/web/`` directory.
"""

import contextlib
import io
import os
import socket
import tempfile
import unittest
from unittest import mock

from taskproof import cli, dispatch, errors
from taskproof.api.server import DEFAULT_PORT


class _FakeServer:
    """A stand-in for ``ThreadingHTTPServer`` that never loops forever.

    ``address`` is the requested bind address; a port of 0 is reported back as a
    concrete bound port (like a real socket would), so the URL assertion can
    check the code reads ``server_address`` instead of echoing the request.
    """

    def __init__(self, address, handler):
        self.address = address
        self.handler = handler
        requested = address[1]
        self.server_address = ("127.0.0.1", requested or 54321)
        self.served = False
        self.closed = False

    def serve_forever(self):
        self.served = True

    def server_close(self):
        self.closed = True


class BoardCliBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = os.path.join(self._tmp.name, "workspace")
        dispatch.prepare_workspace(self.ws)
        # `_board_serve` refuses to start without built web assets; give it a
        # throwaway one so these tests exercise the bind/open wiring instead.
        self.web = os.path.join(self._tmp.name, "web")
        os.makedirs(self.web, exist_ok=True)
        with open(os.path.join(self.web, "index.html"), "w", encoding="utf-8") as fh:
            fh.write("<!doctype html><title>board</title>")
        patcher = mock.patch.object(cli, "_board_static_root", return_value=self.web)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self._tmp.cleanup()

    def args(self, *argv):
        return cli.build_parser().parse_args(["--workspace", self.ws, *argv])

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["--workspace", self.ws, *argv])
        return code, out.getvalue(), err.getvalue()


class OpenWiringTest(BoardCliBase):
    """`cmd_board` must delegate the live flags to `_board_serve` correctly."""

    def test_bare_board_serves_default_port_and_opens_browser(self):
        with mock.patch.object(cli, "_board_serve", return_value=0) as serve:
            code, _, _ = self.run_cli("board")
        self.assertEqual(code, 0)
        self.assertEqual(serve.call_args.args[1], DEFAULT_PORT)
        self.assertTrue(serve.call_args.kwargs["open_browser"])

    def test_open_uses_default_port_and_opens_browser(self):
        with mock.patch.object(cli, "_board_serve", return_value=0) as serve:
            code, _, _ = self.run_cli("board", "--open")
        self.assertEqual(code, 0)
        self.assertEqual(serve.call_args.args[1], DEFAULT_PORT)
        self.assertTrue(serve.call_args.kwargs["open_browser"])

    def test_open_serve_forwards_the_explicit_port(self):
        with mock.patch.object(cli, "_board_serve", return_value=0) as serve:
            code, _, _ = self.run_cli("board", "--open", "--serve", "8899")
        self.assertEqual(code, 0)
        self.assertEqual(serve.call_args.args[1], 8899)
        self.assertTrue(serve.call_args.kwargs["open_browser"])

    def test_serve_only_does_not_open_a_browser(self):
        with mock.patch.object(cli, "_board_serve", return_value=0) as serve:
            code, _, _ = self.run_cli("board", "--serve")
        self.assertEqual(code, 0)
        self.assertEqual(serve.call_args.args[1], DEFAULT_PORT)
        self.assertFalse(serve.call_args.kwargs["open_browser"])

    def test_serve_explicit_port_does_not_open_a_browser(self):
        with mock.patch.object(cli, "_board_serve", return_value=0) as serve:
            code, _, _ = self.run_cli("board", "--serve", "8899")
        self.assertEqual(code, 0)
        self.assertEqual(serve.call_args.args[1], 8899)
        self.assertFalse(serve.call_args.kwargs["open_browser"])


class OpenUrlTest(BoardCliBase):
    """The URL passed to `webbrowser.open`, and the bind-before-open order."""

    def test_open_url_is_the_live_loopback_endpoint(self):
        def factory(address, handler):
            return _FakeServer((address[0], 8899), handler)

        with mock.patch.object(cli.webbrowser, "open") as opener:
            code = cli._board_serve(self.ws, 8899, open_browser=True,
                                    httpd_factory=factory)
        self.assertEqual(code, 0)
        opener.assert_called_once_with("http://127.0.0.1:8899/")

    def test_open_url_uses_the_bound_port_not_the_requested_zero(self):
        def factory(address, handler):
            return _FakeServer((address[0], 0), handler)

        with mock.patch.object(cli.webbrowser, "open") as opener:
            code = cli._board_serve(self.ws, 0, open_browser=True,
                                    httpd_factory=factory)
        self.assertEqual(code, 0)
        url = opener.call_args.args[0]
        self.assertRegex(url, r"^http://127\.0\.0\.1:\d+/$")
        self.assertNotIn(":0/", url)

    def test_browser_opens_only_after_a_successful_bind(self):
        events = []

        def factory(address, handler):
            events.append("bind")
            return _FakeServer((address[0], 8899), handler)

        def record(url):
            events.append(("open", url))

        with mock.patch.object(cli.webbrowser, "open", side_effect=record):
            cli._board_serve(self.ws, 8899, open_browser=True,
                             httpd_factory=factory)
        self.assertEqual(events[0], "bind")
        self.assertEqual(events[1], ("open", "http://127.0.0.1:8899/"))

    def test_serve_seam_closes_the_server_after_looping(self):
        created = {}

        def factory(address, handler):
            server = _FakeServer((address[0], 8899), handler)
            created["server"] = server
            return server

        with mock.patch.object(cli.webbrowser, "open") as opener:
            cli._board_serve(self.ws, 8899, httpd_factory=factory)
        opener.assert_not_called()  # open_browser defaults off
        self.assertTrue(created["server"].served)
        self.assertTrue(created["server"].closed)


class PortInUseTest(BoardCliBase):
    def test_occupied_port_is_a_usage_error_without_opening_a_browser(self):
        blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            blocker.bind(("127.0.0.1", 0))
            blocker.listen(1)
            port = blocker.getsockname()[1]
            with mock.patch.object(cli.webbrowser, "open") as opener:
                code, _, err = self.run_cli("board", "--open", "--serve", str(port))
            self.assertEqual(code, errors.EXIT_USAGE)
            opener.assert_not_called()
            self.assertIn("cannot serve the board", err)
            self.assertIn("already in use", err)
        finally:
            blocker.close()

    def test_bind_failure_raises_usageerror_before_any_open(self):
        def factory(address, handler):
            raise OSError("address already in use")

        with mock.patch.object(cli.webbrowser, "open") as opener:
            with self.assertRaises(errors.UsageError):
                cli._board_serve(self.ws, 8787, open_browser=True,
                                 httpd_factory=factory)
        opener.assert_not_called()


class HelpTextTest(BoardCliBase):
    def test_board_help_lists_live_flags_and_no_snapshot_flags(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            cli.build_parser().parse_args(["board", "--help"])
        text = out.getvalue()
        self.assertIn("--open", text)
        self.assertIn("--serve", text)
        self.assertNotIn("--snapshot", text)
        self.assertNotIn("--out", text)


if __name__ == "__main__":
    unittest.main()
