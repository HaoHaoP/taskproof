"""Local REST API.

Security choices (deliberate, and the whole reason this module exists):

* It binds to **127.0.0.1 only** — never ``0.0.0.0``. The API exposes task
  briefs, project paths and the audit trail; nothing here should ever be
  reachable from another machine. Loopback is the boundary.
* It is read-only by default. Writes exist only after the caller explicitly
  passes ``--allow-write``; without it every write verb (registry CRUD *and*
  the task-control endpoints) is 405. The read endpoints never change.
* Writes open only behind a session token. The token is generated for the
  lifetime of this process, kept in memory, and written only to the stdout pipe
  consumed by the parent process. It is never stored, logged, or returned in an
  HTTP response. Command-line arguments and environment variables are visible
  to other processes under the same macOS account via ``ps``; a stdout pipe has
  only the parent as reader.
* The write surface has two families sharing one gate: registry create / edit /
  delete, and task control. Task control is five action semantics —
  ``POST /api/tasks`` (dispatch, or ``start=false`` to park a queued row),
  ``POST /api/tasks/<id>/advance`` (fire ONE queued card now, out of its wave,
  via ``dispatch.run_queued``), ``POST /api/tasks/<id>/accept`` (clear a
  ``blocked`` card: ``done`` when its acceptance passed, else ``failed``,
  recorded as an ``accepted`` event), ``POST /api/tasks/<id>/cancel`` (SIGTERM
  -> SIGKILL the task's own process group, or drop a queued card), and
  ``DELETE /api/tasks/<id>`` (terminal only). Reordering a queued card is field
  maintenance, not a sixth action: ``PATCH /api/tasks/<id>`` accepts only
  ``queue_seq``.
* CORS is narrow on purpose. The browser renderer is never same-origin with
  this API: the dev renderer is a Vite dev server, and a packaged renderer is a
  ``file://`` page whose Origin is the literal string ``null``. Responses echo
  ``Access-Control-Allow-Origin`` back to *allowed* callers only — that literal
  ``null`` and loopback ``http`` origins (``http://localhost[:port]`` /
  ``http://127.0.0.1[:port]``). Every other http(s) origin
  (``https://evil.example`` …) gets no CORS header, and never ``*``. This opens
  cross-origin *reads* to the renderer, but the write surface is unchanged:
  ``OPTIONS`` answers the preflight without a token, yet every real write verb
  still passes the token gate below.

Standard library only (``http.server``). The frontend consumes these endpoints.
"""

import json
import os
import re
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

from .. import __version__, concurrency, dispatch, registry, storage
from ..errors import ConcurrencyError, RegistryError, UsageError

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
#: Body of `POST /api/tasks`. `start` names the two exits of the dispatch form
#: (fire now vs park queued); everything else mirrors `dispatch()`.
_TASK_CREATE_FIELDS = {
    "project",
    "brief",
    "adapter",
    "model",
    "reasoning",
    "read_only",
    "worktree",
    "skip_verify",
    "timeout",
    "start",
    "queue_seq",
}

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
#: have open. The write gate (``--allow-write`` + token) is unchanged by this.
_LOOPBACK_ORIGIN = re.compile(
    r"^http://(?:localhost|127\.0\.0\.1)(?::\d+)?$", re.IGNORECASE
)

#: Verbs a browser may use across origins. GET is the simple read; POST/PATCH/
#: DELETE are the write surface. PUT and HEAD are not advertised (they are
#: rejected shapes, not usable endpoints).
_CORS_METHODS = "GET, POST, PATCH, DELETE"

#: Request headers a cross-origin write may carry: the JSON content type (which
#: is what makes the request non-simple and triggers a preflight) and the
#: write-gate token. The browser matches these case-insensitively.
_CORS_HEADERS = "Content-Type, X-Taskproof-Token"

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


def _concurrency_payload(exc):
    """429 body for a refused spawn.

    The two refusals mean different things to a caller — "this project's group
    is busy, wait for it" vs "the global cap is full, wait for any slot" — so the
    body names the reason. ``concurrency.describe_blocker`` already phrases the
    distinct cases ("group '<g>' is busy" vs "global cap reached"); we surface
    that phrasing as a machine-readable ``reason`` rather than re-deriving the
    claim state here.
    """
    detail = str(exc)
    payload = {
        "error": "concurrency refused",
        "reason": "cap" if detail.startswith("global cap") else "group",
        "detail": detail,
    }
    if getattr(exc, "hint", None):
        payload["hint"] = exc.hint
    return payload


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

    def do_OPTIONS(self):  # noqa: N802
        # CORS preflight. A browser sends it *before* any non-simple write
        # (``content-type: application/json`` POST/PATCH/DELETE) and it never
        # carries credentials, so it must not demand the token -- the real
        # write verbs still go through the gate in ``_write_request``.
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
        except dispatch.TaskNotFoundError as exc:
            status, payload = 404, {"error": str(exc)}
        except dispatch.TaskStateError as exc:
            # Illegal state for the action (e.g. cancel a terminal task, or rm a
            # live one) is a conflict, not a malformed request: 409.
            status, payload = 409, {"error": str(exc)}
        except ConcurrencyError as exc:
            # Same-group serialisation or the global cap refused the spawn: the
            # caller should retry, not fix its request. 429, and the body says
            # which limit bit (see _concurrency_payload). An `advance` leaves the
            # queued row untouched, so retrying it later is safe.
            status, payload = 429, _concurrency_payload(exc)
        except RegistryError as exc:
            status, payload = 400, {"error": str(exc)}
        except UsageError as exc:
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
            if path == "/api/tasks":
                return self._create_task(self._body())
            if path.startswith("/api/tasks/") and path.endswith("/cancel"):
                task_id = unquote(
                    path[len("/api/tasks/"):-len("/cancel")]
                )
                if not task_id or "/" in task_id:
                    return 404, {"error": "not found", "path": parsed.path}
                return self._cancel_task(task_id)
            if path.startswith("/api/tasks/") and path.endswith("/advance"):
                task_id = unquote(
                    path[len("/api/tasks/"):-len("/advance")]
                )
                if not task_id or "/" in task_id:
                    return 404, {"error": "not found", "path": parsed.path}
                return self._advance_task(task_id)
            if path.startswith("/api/tasks/") and path.endswith("/accept"):
                task_id = unquote(
                    path[len("/api/tasks/"):-len("/accept")]
                )
                if not task_id or "/" in task_id:
                    return 404, {"error": "not found", "path": parsed.path}
                return self._accept_task(task_id)
            return 404, {"error": "not found", "path": parsed.path}

        if path.startswith("/api/projects/"):
            project_id = unquote(path[len("/api/projects/"):])
            if not project_id or "/" in project_id:
                return 404, {"error": "not found", "path": parsed.path}
            if method == "PATCH":
                return self._update_project(project_id, self._body())
            if method == "DELETE":
                return self._delete_project(project_id, self._body())

        if path.startswith("/api/tasks/"):
            task_id = unquote(path[len("/api/tasks/"):])
            if not task_id or "/" in task_id:
                return 404, {"error": "not found", "path": parsed.path}
            if method == "PATCH":
                return self._patch_task(task_id, self._body())
            if method == "DELETE":
                return self._delete_task(task_id)

        if method == "PUT":
            return 405, {"error": "method not allowed"}
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

    # -- task control -----------------------------------------------------

    def _create_task(self, body):
        unknown = set(body) - _TASK_CREATE_FIELDS
        if unknown:
            raise RegistryError(
                f"unsupported field(s): {', '.join(sorted(unknown))}"
            )
        project = body.get("project")
        brief = body.get("brief")
        if not isinstance(project, str) or not project.strip():
            raise RegistryError("project is required")
        if not isinstance(brief, str) or not brief.strip():
            raise RegistryError("brief is required")

        start = body.get("start", True)
        if not isinstance(start, bool):
            raise RegistryError("start must be a boolean")
        queue_seq = body.get("queue_seq")
        if queue_seq is not None and (
            isinstance(queue_seq, bool) or not isinstance(queue_seq, int)
        ):
            raise RegistryError("queue_seq must be an integer")
        timeout = body.get("timeout")
        if timeout is not None and (
            isinstance(timeout, bool) or not isinstance(timeout, int)
        ):
            raise RegistryError("timeout must be an integer")

        task_id = dispatch.dispatch(
            self.workspace,
            project,
            brief,
            adapter=body.get("adapter") or "codex",
            model=body.get("model"),
            reasoning=body.get("reasoning"),
            read_only=bool(body.get("read_only", False)),
            worktree=bool(body.get("worktree", False)),
            skip_verify=bool(body.get("skip_verify", False)),
            timeout=timeout,
            start=start,
            queue_seq=queue_seq,
        )
        return 201, {"task": self._task_record(task_id)}

    def _advance_task(self, task_id):
        # Fire ONE queued row now, out of its wave. ``run_queued`` keeps the id
        # and queue_seq; a concurrency refusal (exit 75) surfaces as 429 in
        # ``_write_request`` and leaves the row queued.
        dispatch.run_queued(self.workspace, task_id)
        return 200, {"task": self._task_record(task_id)}

    def _accept_task(self, task_id):
        # The same human disposition as `taskproof accept <id>`; the audit event
        # records that it came from the API surface (`by="api"`), not the CLI.
        return 200, {"task": dispatch.accept_task(self.workspace, task_id, by="api")}

    def _cancel_task(self, task_id):
        return 200, {"task": dispatch.cancel_task(self.workspace, task_id)}

    def _delete_task(self, task_id):
        return 200, {"removed": dispatch.remove_task(self.workspace, task_id)}

    def _patch_task(self, task_id, body):
        # Field maintenance, not an action: queue_seq is the only editable field.
        unknown = set(body) - {"queue_seq"}
        if unknown:
            raise RegistryError(
                f"unsupported field(s): {', '.join(sorted(unknown))}"
            )
        if "queue_seq" not in body:
            raise RegistryError("queue_seq is required")
        queue_seq = body["queue_seq"]
        if queue_seq is not None and (
            isinstance(queue_seq, bool) or not isinstance(queue_seq, int)
        ):
            raise RegistryError("queue_seq must be an integer")
        task = dispatch.set_queue_seq(self.workspace, task_id, queue_seq)
        return 200, {"task": task}

    def _task_record(self, task_id):
        detail = dispatch.task_detail(self.workspace, task_id)
        task = detail.get("task")
        if task is None:
            raise dispatch.TaskNotFoundError(f"no such task: {task_id}")
        return task

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
