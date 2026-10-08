"""Local REST API.

Security choices (deliberate, and the whole reason this module exists):

* It binds to **127.0.0.1 only** — never ``0.0.0.0``. The API exposes task
  briefs, project paths and the audit trail; nothing here should ever be
  reachable from another machine. Loopback is the boundary.
* It is read-only by default. Registry writes exist only after the caller
  explicitly passes ``--allow-write``; without it every write verb is 405.
* The write token is generated for the lifetime of this process, kept in
  memory, and written only to the stdout pipe consumed by the parent process.
  It is never stored, logged, or returned in an HTTP response. Command-line
  arguments and environment variables are visible to other processes under the
  same macOS account via ``ps``; a stdout pipe has only the parent as reader.

Standard library only (``http.server``). The frontend consumes these endpoints;
the default read-only boundary is frozen here.
"""

import json
import os
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

from .. import __version__, dispatch, registry, storage
from ..errors import RegistryError, UsageError

#: Loopback only. Do not make this configurable to a routable address.
HOST = "127.0.0.1"
DEFAULT_PORT = 8787
_DEFAULT_LIMIT = 20

_CREATE_FIELDS = {
    "path",
    "expected_hash",
    "id",
    "group",
    "aliases",
    "verify",
    "verify_kind",
    "forbidden_paths",
    "probe",
    "probe_exit",
}
_PATCH_FIELDS = {
    "expected_hash",
    "aliases",
    "group",
    "verify",
    "verify_kind",
    "forbidden_paths",
    "result_schema",
}


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
    allow_write = False
    token = None

    # -- verbs ------------------------------------------------------------

    def do_GET(self):  # noqa: N802 (stdlib naming)
        try:
            status, payload = self._route()
        except Exception:
            # Never leak a traceback (or internals) to the client.
            status, payload = 500, {"error": "internal server error"}
        self._send(status, payload)

    def do_POST(self):  # noqa: N802
        self._write_request("POST")

    def do_PATCH(self):  # noqa: N802
        self._write_request("PATCH")

    def do_DELETE(self):  # noqa: N802
        self._write_request("DELETE")

    def do_PUT(self):  # noqa: N802
        self._write_request("PUT")

    def do_HEAD(self):  # noqa: N802
        # HEAD was already a write-shaped rejection in the read-only API. Keep
        # that behaviour: it is not a registry mutation request.
        self._send(405, {"error": "method not allowed"})

    # -- routing ----------------------------------------------------------

    def _route(self):
        parsed = urlsplit(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/api/health":
            return 200, {"ok": True, "version": __version__}
        if path == "/api/summary":
            return 200, {"summary": self._summary()}
        if path == "/api/registry":
            return self._registry()
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

    def _write_request(self, method):
        if not self.allow_write:
            self._send(405, {"error": "method not allowed"})
            return
        if not self._authorised():
            self._send(403, {"error": "forbidden"})
            return
        try:
            status, payload = self._route_write(method)
        except registry.RegistryConflictError as exc:
            status, payload = 409, {
                "error": "conflict",
                "hash": exc.current_hash,
                "content": exc.content,
                "projects": exc.projects,
            }
        except registry.RegistryNotFoundError as exc:
            status, payload = 404, {"error": str(exc)}
        except RegistryError as exc:
            status, payload = 400, {"error": str(exc)}
        except Exception:
            status, payload = 500, {"error": "internal server error"}
        self._send(status, payload)

    def _route_write(self, method):
        parsed = urlsplit(self.path)
        path = parsed.path.rstrip("/") or "/"

        if method == "POST":
            if path == "/api/projects/probe":
                body = self._body()
                return 200, registry.probe_repository(self._path(body))
            if path == "/api/projects":
                return self._create_project(self._body())
            return 404, {"error": "not found", "path": parsed.path}

        if path.startswith("/api/projects/"):
            project_id = unquote(path[len("/api/projects/"):])
            if not project_id or "/" in project_id:
                return 404, {"error": "not found", "path": parsed.path}
            if method == "PATCH":
                return self._update_project(project_id, self._body())
            if method == "DELETE":
                return self._delete_project(project_id, self._body())

        if method == "PUT":
            return 405, {"error": "method not allowed"}
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
        for project in reg.projects:
            record = registry.project_record(project, probes)
            stat = overview.get(project.id) or {}
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

    def _registry(self):
        reg_path = registry.workspace_registry_path(self.workspace)
        try:
            return 200, registry.registry_metadata(reg_path)
        except RegistryError as exc:
            return 404, {"error": str(exc), "path": reg_path}

    def _create_project(self, body):
        unknown = set(body) - _CREATE_FIELDS
        if unknown:
            raise RegistryError(
                f"unsupported field(s): {', '.join(sorted(unknown))}"
            )
        expected_hash = self._expected_hash(body)
        path = self._path(body)
        project = {"path": path}
        if "id" in body:
            project["id"] = body["id"]
        else:
            project["id"] = os.path.basename(os.path.normpath(path)) or path
        project["group"] = body.get("group") or project["id"]
        for key in (
            "aliases",
            "verify",
            "verify_kind",
            "forbidden_paths",
            "probe",
            "probe_exit",
        ):
            if key in body:
                project[key] = body[key]

        reg_path = registry.workspace_registry_path(self.workspace)
        registry.append_project(reg_path, expected_hash, project)
        return 201, {"project": self._project_record(project["id"])}

    def _update_project(self, project_id, body):
        unknown = set(body) - _PATCH_FIELDS
        if unknown:
            raise RegistryError(
                f"unsupported field(s): {', '.join(sorted(unknown))}"
            )
        if "id" in body or "path" in body:
            raise RegistryError("project id and path are immutable")
        expected_hash = self._expected_hash(body)
        changes = {key: value for key, value in body.items() if key != "expected_hash"}
        if not changes:
            raise RegistryError("no project fields were provided")
        reg_path = registry.workspace_registry_path(self.workspace)
        registry.update_project(reg_path, project_id, expected_hash, changes)
        return 200, {"project": self._project_record(project_id)}

    def _delete_project(self, project_id, body):
        unknown = set(body) - {"expected_hash"}
        if unknown:
            raise RegistryError(
                f"unsupported field(s): {', '.join(sorted(unknown))}"
            )
        expected_hash = self._expected_hash(body)
        reg_path = registry.workspace_registry_path(self.workspace)
        registry.delete_project(reg_path, project_id, expected_hash)
        return 200, {"removed": project_id}

    def _project_record(self, project_id):
        reg_path = registry.workspace_registry_path(self.workspace)
        reg = registry.load(reg_path)
        project = reg.by_id(project_id)
        if project is None or project.id != project_id:
            raise registry.RegistryNotFoundError(f"project not found: {project_id}")
        return registry.project_record(project, registry.read_probe_flags(reg_path))

    def _path(self, body):
        value = body.get("path")
        if not isinstance(value, str) or not value.strip():
            raise RegistryError("path is required")
        path = os.path.abspath(os.path.expanduser(value))
        if not os.path.exists(path):
            raise RegistryError(f"path does not exist: {value}")
        if not os.path.isdir(path):
            raise RegistryError(f"not a directory: {value}")
        return path

    def _expected_hash(self, body):
        value = body.get("expected_hash")
        if not isinstance(value, str) or not value:
            raise RegistryError("expected_hash is required")
        return value

    def _body(self):
        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length or "0")
        except (TypeError, ValueError):
            raise RegistryError("invalid Content-Length")
        if length < 0:
            raise RegistryError("invalid Content-Length")
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise RegistryError("request body must be valid JSON")
        if not isinstance(body, dict):
            raise RegistryError("request body must be a JSON object")
        return body

    def _authorised(self):
        supplied = self.headers.get("X-Taskproof-Token")
        if not supplied or not self.token:
            return False
        return secrets.compare_digest(str(supplied), str(self.token))

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


def make_server(
    workspace: str,
    port: int = DEFAULT_PORT,
    host: str = HOST,
    allow_write: bool = False,
    token: str = None,
):
    """Build (but do not start) the API server. ``port=0`` picks a free port."""
    write_token = None
    if allow_write:
        # Session-only: this value is never placed in argv, the environment, a
        # file, a log line, or an HTTP response.
        write_token = token or secrets.token_urlsafe(32)
    handler = type(
        "TaskproofAPIHandler",
        (_Handler,),
        {
            "workspace": workspace,
            "allow_write": bool(allow_write),
            "token": write_token,
        },
    )
    try:
        httpd = ThreadingHTTPServer((host, port), handler)
    except OSError as exc:
        raise UsageError(
            f"cannot bind the API to {host}:{port}: {exc}",
            hint="the port is already in use; choose another with --port",
        )
    httpd.allow_write = bool(allow_write)
    httpd.write_token = write_token
    return httpd


def listening_line(httpd) -> str:
    """The line ``serve`` prints so a parent process can learn the port.

    A caller that passes ``port=0`` cannot know the port in advance; the desktop
    app spawns the API that way and reads the bound port back from this line.
    """
    host, port = httpd.server_address[0], httpd.server_address[1]
    return f"taskproof api listening on http://{host}:{port}"


def token_line(token: str) -> str:
    return f"taskproof api token {token}"


def serve(workspace: str, port: int = DEFAULT_PORT, allow_write: bool = False):
    """Serve until interrupted. Blocks; returns 0 on a clean shutdown."""
    httpd = make_server(workspace, port, allow_write=allow_write)
    # Flush before serve_forever blocks, or the parent never sees these lines.
    print(listening_line(httpd), flush=True)
    if allow_write:
        print(token_line(httpd.write_token), flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0
