"""Local REST API.

Security choices (deliberate, and the whole reason this module exists):

* It binds to **127.0.0.1 only** — never ``0.0.0.0``. The API exposes task
  briefs, project paths and the audit trail; nothing here should ever be
  reachable from another machine. Loopback is the boundary.
* It is **read-only**. There is no write surface and no session token: every
  mutation lives behind the CLI, and the only routed verbs are ``GET`` (reads)
  and ``OPTIONS`` (the CORS preflight). A write-shaped request to a path that
  used to be a write endpoint is an unrouted method/path pair, so it is a plain
  404 — never a 403. There is no gate left to forbid anything.
* CORS is narrow on purpose. The browser renderer is never same-origin with
  this API: the dev renderer is a Vite dev server, and a packaged renderer is a
  ``file://`` page whose Origin is the literal string ``null``. Responses echo
  ``Access-Control-Allow-Origin`` back to *allowed* callers only — that literal
  ``null`` and loopback ``http`` origins (``http://localhost[:port]`` /
  ``http://127.0.0.1[:port]``). Every other http(s) origin
  (``https://evil.example`` …) gets no CORS header, and never ``*``. This opens
  cross-origin *reads* to the renderer, and that read access is the whole
  surface.

Standard library only (``http.server``). The frontend consumes these endpoints.
"""

import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

from .. import __version__, concurrency, dispatch, registry, storage, verify
from ..errors import RegistryError, UsageError

#: Loopback only. Do not make this configurable to a routable address.
HOST = "127.0.0.1"
DEFAULT_PORT = 8787
_DEFAULT_LIMIT = 20

#: Stable buckets in the grouped `/api/projects?by=project` summary. Every key is
#: always present so a client can draw the same set of columns without guessing.
_PROJECT_SUMMARY_STATUSES = (
    "running",
    "verifying",
    "done",
    "failed",
    "blocked",
    "timeout",
    "cancelled",
)

#: `GET /api/tasks/<id>/log` — with no `offset`, return the file's last
#: LOG_TAIL_BYTES. There is deliberately no "page backwards" affordance: the
#: window is the tail, and later requests resume forward from `next`.
LOG_TAIL_BYTES = 65536
#: Hard cap on the bytes any single log response may carry, tail or incremental.
LOG_CHUNK_BYTES = 262144
#: Floor between live `git status` probes for one task, in seconds.
LIVE_FILES_MIN_INTERVAL = 3.0
#: Short bound (seconds) on each live probe; a slow repo yields ``null``.
LIVE_PROBE_TIMEOUT = 5

#: The origins the desktop renderer may legitimately present, and nothing else.
#:
#: * ``null`` — a packaged renderer fetched from a ``file://`` page: the browser
#:   sends the literal string ``null`` as ``Origin``.
#: * ``http://localhost[:port]`` and ``http://127.0.0.1[:port]`` — the Vite dev
#:   server during development, which serves the renderer over loopback http.
#:
#: Everything else (``https://evil.example`` and any other routable http(s)
#: origin) is refused a CORS header. We echo the caller's origin instead of
#: sending ``*``: ``*`` would hand the API to any web page the user happens to
#: have open.
_LOOPBACK_ORIGIN = re.compile(
    r"^http://(?:localhost|127\.0\.0\.1)(?::\d+)?$", re.IGNORECASE
)

#: Verbs a browser may use across origins. GET is the only routed verb; HEAD
#: and the write verbs are not advertised (they are rejected shapes, not usable
#: endpoints).
_CORS_METHODS = "GET"

#: Request header a cross-origin read may carry. The write-gate token is gone,
#: so nothing secret is advertised here; the browser matches case-insensitively.
_CORS_HEADERS = "Content-Type"

#: How long a browser may cache a successful preflight, in seconds.
_CORS_MAX_AGE = "600"


def _allowed_origin(origin):
    """True when ``origin`` may receive an ``Access-Control-Allow-Origin`` echo.

    Only the packaged ``file://`` renderer (origin ``null``) and loopback http
    dev origins qualify; any other value is refused.
    """
    if not origin:
        return False
    if origin == "null":
        return True
    return bool(_LOOPBACK_ORIGIN.match(origin))


def _json_default(value):
    # sqlite3.Row / datetime / etc. — keep the response always serialisable.
    return str(value)


def _first(query, key):
    values = query.get(key)
    if not values:
        return None
    value = values[0]
    return value if value != "" else None


#: Statuses whose worktree we probe for `files_changed_live`. Every other row
#: reports ``None`` -- the final `files_changed` is written once at step ⑥.
_LIVE_STATUSES = ("running", "verifying")

#: Process-wide `{task_id: (monotonic, value)}` cache for the live probe.
#:
#: It must live at module scope, not on the handler: ``ThreadingHTTPServer``
#: builds a fresh handler instance per request, so an instance attribute would
#: never be hit and every poll would re-shell out to `git`.
_LIVE_FILES_CACHE = {}


def _utf8_lead_length(byte):
    """Expected total length of the UTF-8 character starting at ``byte``."""
    if byte < 0x80:
        return 1
    if byte >= 0xF0:
        return 4
    if byte >= 0xE0:
        return 3
    if byte >= 0xC0:
        return 2
    return 1


def _utf8_prefix_length(raw):
    """Largest prefix length of ``raw`` that ends on a UTF-8 character boundary.

    The caller picked the slice; if its final bytes open a multi-byte character
    that the slice cuts in half, drop them and let the caller resume at that
    character's first byte. Decoding only a boundary-aligned prefix keeps the
    resume point loss-free: the next read starts exactly where the dropped bytes
    began.
    """
    back = 1
    while back <= 3 and back <= len(raw):
        byte = raw[-back]
        if byte & 0xC0 != 0x80:
            # ``byte`` is a lead (or ASCII) byte at distance ``back`` from the end.
            needed = _utf8_lead_length(byte)
            if needed <= back:
                return len(raw)  # its character completes inside the slice
            return len(raw) - back  # cut: drop from this character's first byte
        back += 1
    return len(raw)


def _log_leading_partial(raw):
    """Count leading continuation bytes: a character whose start lies before ``raw``.

    Only used for a tail slice, whose window start we chose. Skipping them lets
    the response begin on a character boundary instead of a replacement glyph.
    """
    skipped = 0
    while skipped < 3 and skipped < len(raw) and raw[skipped] & 0xC0 == 0x80:
        skipped += 1
    return skipped


def _empty_log(task_id, size=0, offset=0):
    return {
        "task_id": task_id,
        "offset": offset,
        "next": offset,
        "text": "",
        "eof": True,
        "size": size,
        "omitted": 0,
    }


def _read_log(log_path, task_id, offset):
    """Read one log window. ``offset is None`` requests the tail.

    Contract (Card B depends on these exact names): a 200 body is
    ``{task_id, offset, next, text, eof, size, omitted}`` -- ``offset`` is where
    the returned bytes start, ``next`` where the client resumes, and ``omitted``
    the bytes before the window the client does not have (0 for an incremental
    request). A missing log file is a normal empty tail, never an error.
    """
    try:
        size = os.stat(log_path).st_size
    except OSError:
        return _empty_log(task_id)

    if offset is None:
        start = max(0, size - LOG_TAIL_BYTES)
        omitted = start
        tail = True
    else:
        if offset > size:
            # File was truncated/rotated under us: nothing to show, resume at EOF.
            return _empty_log(task_id, size=size, offset=size)
        start = offset
        omitted = 0
        tail = False

    end = min(size, start + LOG_CHUNK_BYTES)
    try:
        with open(log_path, "rb") as handle:
            handle.seek(start)
            raw = handle.read(end - start)
    except OSError:
        return _empty_log(task_id)

    if tail:
        skipped = _log_leading_partial(raw)
        if skipped:
            start += skipped
            omitted += skipped
            raw = raw[skipped:]

    kept = _utf8_prefix_length(raw)
    raw = raw[:kept]
    next_offset = start + len(raw)
    return {
        "task_id": task_id,
        "offset": start,
        "next": next_offset,
        "text": raw.decode("utf-8", errors="replace"),
        "eof": next_offset >= size,
        "size": size,
        "omitted": omitted,
    }


def _live_files_changed(row):
    """`files_changed_live` for one row: an int while running/verifying, else None.

    Same yardstick as the final `files_changed` (`git status --porcelain` line
    count), probed through `verify.detect_changes` with a short timeout. The
    result is cached per task for `LIVE_FILES_MIN_INTERVAL` seconds -- a cache
    hit returns the previous value without shelling out again. Any probe failure
    (not a repo, no git, timeout) is `None`, never an exception: this must never
    500 or stall a list request.
    """
    if row.get("status") not in _LIVE_STATUSES:
        return None
    workdir = row.get("workdir")
    if not workdir:
        return None
    task_id = row.get("id")
    now = time.monotonic()
    cached = _LIVE_FILES_CACHE.get(task_id)
    if cached is not None and now - cached[0] < LIVE_FILES_MIN_INTERVAL:
        return cached[1]
    try:
        value = verify.detect_changes(workdir, timeout=LIVE_PROBE_TIMEOUT)
    except Exception:
        value = None
    _LIVE_FILES_CACHE[task_id] = (now, value)
    return value


def _with_live_files(row):
    """Copy ``row`` and add the derived ``files_changed_live`` field."""
    row = dict(row)
    row["files_changed_live"] = _live_files_changed(row)
    return row


def _with_live_files_many(rows):
    """One shared helper for both the list and the detail endpoint."""
    return [_with_live_files(row) for row in rows]


class _Handler(BaseHTTPRequestHandler):
    """One request handler per server; ``workspace`` is set per instance class."""

    server_version = "taskproof/" + __version__
    workspace = None

    # -- verbs ------------------------------------------------------------

    def do_GET(self):  # noqa: N802 (stdlib naming)
        try:
            status, payload = self._route()
        except Exception:
            # Never leak a traceback (or internals) to the client.
            status, payload = 500, {"error": "internal server error"}
        self._send(status, payload)

    def do_POST(self):  # noqa: N802
        # The write surface is gone, so these requests no longer correspond to
        # any route: that is a plain 404 (an unrouted method/path pair), never a
        # permission problem -- there is no gate left to forbid anything.
        self._reject_write()

    def do_PATCH(self):  # noqa: N802
        self._reject_write()

    def do_DELETE(self):  # noqa: N802
        self._reject_write()

    def do_PUT(self):  # noqa: N802
        self._reject_write()

    def do_HEAD(self):  # noqa: N802
        # HEAD is not a routed read; keep the long-standing "method not allowed"
        # rejection for it.
        self._send(405, {"error": "method not allowed"})

    def _reject_write(self):
        # Every old write verb lands here: the method/path pair is simply not
        # routed any more.
        parsed = urlsplit(self.path)
        self._send(404, {"error": "not found", "path": parsed.path})

    def do_OPTIONS(self):  # noqa: N802
        # CORS preflight. A browser sends it before a cross-origin request that
        # is not "simple"; the reads this API routes are simple GETs, so this
        # exists for completeness and echoes the GET-only capability list.
        #
        # An allowed origin gets the capability list; anyone else gets a bare
        # 2xx with no ``Access-Control-Allow-Origin`` and the browser blocks the
        # actual request. We do not 4xx a foreign origin: the browser owns that
        # decision, and a different status would leak nothing useful anyway.
        self.send_response(204)
        self._send_cors_headers()
        if _allowed_origin(self.headers.get("Origin")):
            self.send_header("Access-Control-Allow-Methods", _CORS_METHODS)
            self.send_header("Access-Control-Allow-Headers", _CORS_HEADERS)
            self.send_header("Access-Control-Max-Age", _CORS_MAX_AGE)
        self.send_header("Content-Length", "0")
        self.end_headers()

    # -- routing ----------------------------------------------------------

    def _route(self):
        parsed = urlsplit(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/api/health":
            return 200, {
                "ok": True,
                "version": __version__,
                # Read-only effective cap + source (card 42). Card 39's desktop
                # picks this up; the shape is `concurrency.CapSetting.as_dict()`.
                "concurrency": self._concurrency(),
            }
        if path == "/api/summary":
            return 200, {
                "summary": self._summary(),
                "concurrency": self._concurrency(),
            }
        if path == "/api/registry":
            return self._registry()
        if path == "/api/projects":
            if _first(parse_qs(parsed.query), "by") == "project":
                return 200, {"projects": self._projects_by_project()}
            return 200, {"projects": self._projects()}
        if path == "/api/tasks":
            return self._tasks(parse_qs(parsed.query))

        prefix = "/api/tasks/"
        if path.startswith(prefix):
            rest = path[len(prefix):]
            if rest.endswith("/events"):
                return self._events(rest[: -len("/events")])
            # `GET /api/tasks/<id>/log` is a read-only log window: no offset ->
            # the tail (last LOG_TAIL_BYTES); with an offset -> forward from it,
            # capped at LOG_CHUNK_BYTES per response. There is intentionally NO
            # "page backwards" affordance -- the client owns what it has read and
            # resumes from the `next` byte offset.
            if rest.endswith("/log"):
                return self._log(rest[: -len("/log")], parse_qs(parsed.query))
            if "/" in rest:
                return 404, {"error": "not found", "path": parsed.path}
            return self._detail(rest)

        return 404, {"error": "not found", "path": parsed.path}

    # -- endpoints --------------------------------------------------------

    def _concurrency(self):
        """The effective global cap + its source, from the registry (never writes).

        This is the one new *field* on an existing read-only endpoint — no new
        write surface. Shape: ``{value: int, source: "auto"|"toml"|"cli",
        detail: str}`` (see ``concurrency.CapSetting``).
        """
        try:
            reg = registry.load(registry.workspace_registry_path(self.workspace))
            defaults = reg.defaults
        except RegistryError:
            defaults = {}
        return concurrency.resolve(defaults).as_dict()

    def _summary(self):
        conn = storage.connect(storage.db_path(self.workspace))
        try:
            storage.migrate(conn)
            return dispatch.summary_counts(self.workspace, conn)
        finally:
            conn.close()

    def _projects(self):
        reg_path = registry.workspace_registry_path(self.workspace)
        reg = registry.load(reg_path)
        probes = registry.read_probe_flags(reg_path)
        conn = storage.connect(storage.db_path(self.workspace))
        try:
            storage.migrate(conn)
            overview = {row["project"]: row for row in storage.project_overview(conn)}
        finally:
            conn.close()
        projects = []
        # One row per lane (taskgroup), unchanged shape: the dashboard keys its
        # `?project=` filter off the row id. The only addition is the owning
        # `project` field inside `taskgroup_record`.
        for taskgroup in reg.taskgroups:
            record = registry.taskgroup_record(taskgroup, probes)
            stat = overview.get(taskgroup.id) or {}
            record.update(
                {
                    # Overview numbers, derived from the same aggregate SQL the
                    # `projects` command uses.
                    "tasks": int(stat.get("total", 0)),
                    "in_progress": int(stat.get("in_progress", 0)),
                    "failed": int(stat.get("failed", 0)),
                    "last_activity": stat.get("last_activity"),
                }
            )
            projects.append(record)
        return projects

    def _projects_by_project(self):
        """`GET /api/projects?by=project` -- one row per owning project.

        This is deliberately a separate view: the historical `/api/projects`
        payload stays one row per lane for the desktop client. The grouped view
        nests each project's lane records and sums their lifecycle statuses.
        """
        reg_path = registry.workspace_registry_path(self.workspace)
        reg = registry.load(reg_path)
        probes = registry.read_probe_flags(reg_path)
        conn = storage.connect(storage.db_path(self.workspace))
        try:
            storage.migrate(conn)
            lane_counts = {}
            for row in conn.execute(
                "SELECT project, status, COUNT(*) AS count "
                "FROM tasks GROUP BY project, status"
            ):
                lane_counts.setdefault(row["project"], {})[row["status"]] = int(
                    row["count"]
                )
        finally:
            conn.close()

        projects = []
        for project in reg.projects:
            lanes = reg.lanes_for(project.id)
            summary = {status: 0 for status in _PROJECT_SUMMARY_STATUSES}
            for lane in lanes:
                for status, count in lane_counts.get(lane.id, {}).items():
                    if status in summary:
                        summary[status] += count
            projects.append(
                {
                    "id": project.id,
                    "path": project.path,
                    "aliases": list(project.aliases),
                    "taskgroups": [
                        registry.taskgroup_record(lane, probes) for lane in lanes
                    ],
                    "summary": summary,
                }
            )
        return projects

    def _registry(self):
        reg_path = registry.workspace_registry_path(self.workspace)
        try:
            return 200, registry.registry_metadata(reg_path)
        except RegistryError as exc:
            return 404, {"error": str(exc), "path": reg_path}

    def _tasks(self, query):
        limit = _DEFAULT_LIMIT
        raw_limit = _first(query, "limit")
        if raw_limit is not None:
            try:
                limit = max(1, int(raw_limit))
            except (TypeError, ValueError):
                limit = _DEFAULT_LIMIT

        project_key = _first(query, "project")
        project_ids = None
        if project_key is not None:
            project_ids = self._project_filter_ids(project_key)

        conn = storage.connect(storage.db_path(self.workspace))
        try:
            storage.migrate(conn)
            status = _first(query, "status")
            if project_ids is None:
                rows = storage.list_tasks(conn, status=status, limit=limit)
            else:
                rows = []
                for lane_id in project_ids:
                    rows.extend(
                        storage.list_tasks(
                            conn, status=status, project=lane_id, limit=limit
                        )
                    )
                rows.sort(
                    key=lambda row: row["created_at"] or "",
                    reverse=True,
                )
                rows = rows[:limit]
            tasks = _with_live_files_many(rows)
        finally:
            conn.close()
        return 200, {"tasks": tasks, "count": len(tasks)}

    def _project_filter_ids(self, key):
        """Resolve `?project=` to lane ids while preserving lane-only fallback.

        A taskgroup id wins over a project id (the old filter contract). A
        project id expands to every lane it owns. If the registry is missing or
        malformed, the key is treated as a lane id exactly as it was before this
        endpoint learned about projects. Unknown keys return no rows, not 500.
        """
        if not key:
            return []
        try:
            reg = registry.load(registry.workspace_registry_path(self.workspace))
        except RegistryError:
            return [key]
        if any(lane.id == key for lane in reg.taskgroups):
            return [key]
        if any(project.id == key for project in reg.projects):
            return [lane.id for lane in reg.lanes_for(key)]
        return []

    def _detail(self, task_id):
        detail = dispatch.task_detail(self.workspace, task_id)
        if detail.get("task") is None:
            return 404, {"error": "no such task", "task_id": task_id}
        # Same helper as `_tasks`, so the card and the drawer cannot disagree.
        detail["task"] = _with_live_files(detail["task"])
        return 200, detail

    def _log(self, task_id, query):
        """`GET /api/tasks/<id>/log` -- tail by default, forward with `offset`."""
        task_id = unquote(task_id)
        # Log paths are only ever `workspace/logs/<id>.log`; reject any id that
        # could steer that join (path separators or ``..``) before touching disk.
        if not task_id or "/" in task_id or "\\" in task_id or ".." in task_id:
            return 404, {"error": "not found", "path": self.path}

        # A missing task is a 404; a missing *log file* on a real task is a
        # normal empty tail (a task that never produced output).
        detail = dispatch.task_detail(self.workspace, task_id)
        if detail.get("task") is None:
            return 404, {"error": "no such task", "task_id": task_id}

        raw_offset = _first(query, "offset")
        offset = None
        if raw_offset is not None:
            try:
                offset = int(raw_offset)
            except (TypeError, ValueError):
                return 400, {"error": "offset must be an integer", "offset": raw_offset}
            if offset < 0:
                return 400, {"error": "offset must be >= 0", "offset": raw_offset}

        log_path = os.path.join(self.workspace, "logs", task_id + ".log")
        return 200, _read_log(log_path, task_id, offset)

    def _events(self, task_id):
        detail = dispatch.task_detail(self.workspace, task_id)
        if detail.get("task") is None:
            return 404, {"error": "no such task", "task_id": task_id}
        return 200, {"task_id": task_id, "events": detail["events"]}

    # -- plumbing ---------------------------------------------------------

    def _send_cors_headers(self):
        """Emit the CORS headers, echoing the caller's origin only if allowed.

        ``Vary: Origin`` is always sent: the response depends on the request's
        ``Origin``, so a shared cache must not serve one origin's answer (with
        its ``Access-Control-Allow-Origin``) to a caller with a different one.
        ``Access-Control-Allow-Origin`` carries the request's own origin, never
        ``*`` -- see ``_allowed_origin``.
        """
        self.send_header("Vary", "Origin")
        origin = self.headers.get("Origin")
        if _allowed_origin(origin):
            self.send_header("Access-Control-Allow-Origin", origin)

    def _send(self, status, payload):
        body = json.dumps(
            payload, ensure_ascii=False, default=_json_default, indent=2
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors_headers()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def log_message(self, *args):  # keep the test/CI output clean
        pass


def make_server(workspace: str, port: int = DEFAULT_PORT, host: str = HOST):
    """Build (but do not start) the API server. ``port=0`` picks a free port."""
    handler = type(
        "TaskproofAPIHandler",
        (_Handler,),
        {"workspace": workspace},
    )
    try:
        httpd = ThreadingHTTPServer((host, port), handler)
    except OSError as exc:
        raise UsageError(
            f"cannot bind the API to {host}:{port}: {exc}",
            hint="the port is already in use; choose another with --port",
        )
    return httpd


def listening_line(httpd) -> str:
    """The line ``serve`` prints so a parent process can learn the port.

    A caller that passes ``port=0`` cannot know the port in advance; the desktop
    app spawns the API that way and reads the bound port back from this line.
    """
    host, port = httpd.server_address[0], httpd.server_address[1]
    return f"taskproof api listening on http://{host}:{port}"


def serve(workspace: str, port: int = DEFAULT_PORT):
    """Serve until interrupted. Blocks; returns 0 on a clean shutdown."""
    httpd = make_server(workspace, port)
    # Flush before serve_forever blocks, or the parent never sees the line.
    print(listening_line(httpd), flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0
