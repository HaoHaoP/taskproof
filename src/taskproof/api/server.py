"""Local read-only REST API.

Security choices (deliberate, and the whole reason this module exists):

* It binds to **127.0.0.1 only** — never ``0.0.0.0``. The API exposes task
  briefs, project paths and the audit trail; nothing here should ever be
  reachable from another machine. Loopback is the boundary.
* It is **read-only**: there is no endpoint that mutates state. Every route is
  a GET.

Standard library only (``http.server``). The stage 2 frontend consumes these
endpoints; the boundary is frozen here so only the rendering layer changes
later.
"""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from .. import __version__, dispatch, registry, storage
from ..errors import UsageError

#: Loopback only. Do not make this configurable to a routable address.
HOST = "127.0.0.1"
DEFAULT_PORT = 8787
_DEFAULT_LIMIT = 20


def _json_default(value):
    # sqlite3.Row / datetime / etc. — keep the response always serialisable.
    return str(value)


def _first(query, key):
    values = query.get(key)
    if not values:
        return None
    value = values[0]
    return value if value != "" else None


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
        self._send(405, {"error": "method not allowed"})

    do_PUT = do_DELETE = do_PATCH = do_HEAD = do_POST

    # -- routing ----------------------------------------------------------

    def _route(self):
        parsed = urlsplit(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/api/health":
            return 200, {"ok": True, "version": __version__}
        if path == "/api/summary":
            return 200, {"summary": self._summary()}
        if path == "/api/projects":
            return 200, {"projects": self._projects()}
        if path == "/api/tasks":
            return self._tasks(parse_qs(parsed.query))

        prefix = "/api/tasks/"
        if path.startswith(prefix):
            rest = path[len(prefix):]
            if rest.endswith("/events"):
                return self._events(rest[: -len("/events")])
            if "/" in rest:
                return 404, {"error": "not found", "path": parsed.path}
            return self._detail(rest)

        return 404, {"error": "not found", "path": parsed.path}

    # -- endpoints --------------------------------------------------------

    def _summary(self):
        conn = storage.connect(storage.db_path(self.workspace))
        try:
            storage.migrate(conn)
            return dispatch.summary_counts(self.workspace, conn)
        finally:
            conn.close()

    def _projects(self):
        reg = registry.load(registry.workspace_registry_path(self.workspace))
        conn = storage.connect(storage.db_path(self.workspace))
        try:
            storage.migrate(conn)
            overview = {row["project"]: row for row in storage.project_overview(conn)}
        finally:
            conn.close()
        projects = []
        for project in reg.projects:
            stat = overview.get(project.id) or {}
            projects.append(
                {
                    "id": project.id,
                    "path": project.path,
                    "group": project.group,
                    "aliases": list(project.aliases),
                    "verify": project.verify,
                    "verify_kind": project.verify_kind,
                    "forbidden_paths": list(project.forbidden_paths),
                    "auto_registered": bool(project.auto_registered),
                    # Overview numbers, derived from the same aggregate SQL the
                    # `projects` command uses.
                    "tasks": int(stat.get("total", 0)),
                    "in_progress": int(stat.get("in_progress", 0)),
                    "failed": int(stat.get("failed", 0)),
                    "last_activity": stat.get("last_activity"),
                }
            )
        return projects

    def _tasks(self, query):
        limit = _DEFAULT_LIMIT
        raw_limit = _first(query, "limit")
        if raw_limit is not None:
            try:
                limit = max(1, int(raw_limit))
            except (TypeError, ValueError):
                limit = _DEFAULT_LIMIT

        conn = storage.connect(storage.db_path(self.workspace))
        try:
            storage.migrate(conn)
            rows = storage.list_tasks(
                conn,
                status=_first(query, "status"),
                project=_first(query, "project"),
                limit=limit,
            )
            tasks = [dict(row) for row in rows]
        finally:
            conn.close()
        return 200, {"tasks": tasks, "count": len(tasks)}

    def _detail(self, task_id):
        detail = dispatch.task_detail(self.workspace, task_id)
        if detail.get("task") is None:
            return 404, {"error": "no such task", "task_id": task_id}
        return 200, detail

    def _events(self, task_id):
        detail = dispatch.task_detail(self.workspace, task_id)
        if detail.get("task") is None:
            return 404, {"error": "no such task", "task_id": task_id}
        return 200, {"task_id": task_id, "events": detail["events"]}

    # -- plumbing ---------------------------------------------------------

    def _send(self, status, payload):
        body = json.dumps(
            payload, ensure_ascii=False, default=_json_default, indent=2
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def log_message(self, *args):  # keep the test/CI output clean
        pass


def make_server(workspace: str, port: int = DEFAULT_PORT, host: str = HOST):
    """Build (but do not start) the API server. ``port=0`` picks a free port."""
    handler = type("TaskproofAPIHandler", (_Handler,), {"workspace": workspace})
    try:
        return ThreadingHTTPServer((host, port), handler)
    except OSError as exc:
        raise UsageError(
            f"cannot bind the API to {host}:{port}: {exc}",
            hint="the port is already in use; choose another with --port",
        )


def serve(workspace: str, port: int = DEFAULT_PORT):
    """Serve until interrupted. Blocks; returns 0 on a clean shutdown."""
    httpd = make_server(workspace, port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0
