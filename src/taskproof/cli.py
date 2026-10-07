"""Command line interface.

Exit codes are contractual — see errors.py and docs/DESIGN.md.
Human-readable output follows the locale; `--json` is for machines.
"""

import argparse
import json
import os
import sqlite3
import sys
import time
import webbrowser

from . import (
    __version__,
    concurrency,
    dispatch,
    errors,
    ledger,
    registry,
    storage,
    verify,
)
from .errors import RegistryError, UsageError
from .models import TERMINAL_STATUSES

DEFAULT_WORKSPACE = os.path.join(os.path.expanduser("~"), ".taskproof")


class _UsageErrorParser(argparse.ArgumentParser):
    """Route usage errors to EXIT_USAGE (64) instead of argparse's default 2.

    The exit-code table in errors.py is a contract for callers. argparse exits 2
    on a bad invocation, which collides with EXIT_REGISTRY (also 2) — leaving a
    caller unable to tell "you typed the command wrong" apart from "that project
    is not registered". Overriding here restores the documented distinction.
    """

    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"{self.prog}: {message}", file=sys.stderr)
        sys.exit(errors.EXIT_USAGE)


def build_parser() -> argparse.ArgumentParser:
    parser = _UsageErrorParser(
        prog="taskproof",
        description="A conveyor belt for AI coding agents: dispatch, independently verify, record.",
    )
    parser.add_argument("--version", action="version", version=f"taskproof {__version__}")
    parser.add_argument("--workspace", default=os.environ.get("TASKPROOF_HOME", DEFAULT_WORKSPACE),
                        help="state directory (default: %(default)s)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("-q", "--quiet", action="store_true")

    sub = parser.add_subparsers(dest="command", metavar="<command>")

    sub.add_parser("init", help="initialise a workspace (database + sample registry)")

    p = sub.add_parser("register", help="probe a repository and register it")
    p.add_argument("path")
    p.add_argument("--dry-run", action="store_true", help="probe only, write nothing")
    p.add_argument("--id")
    p.add_argument("--group")

    sub.add_parser("projects", help="list registered projects")

    p = sub.add_parser("run", help="dispatch one task (primary command)")
    p.add_argument("project", help="project id, alias, or path")
    p.add_argument("brief", help="what the agent should do")
    p.add_argument("--adapter", default="codex", help="codex | claude | gemini | opencode | custom:<cmd>")
    p.add_argument("--model")
    p.add_argument("--reasoning", choices=["none", "high"])
    p.add_argument("--read-only", action="store_true", help="read-only sandbox; acceptance is skipped")
    p.add_argument("--worktree", action="store_true", help="run in a fresh git worktree")
    p.add_argument("--no-verify", action="store_true", help="skip acceptance (recorded as SKIPPED, not passed)")
    p.add_argument("--timeout", type=int, help="override the registry timeout (seconds)")

    p = sub.add_parser("tasks", help="list tasks")
    p.add_argument("--status")
    p.add_argument("--project")
    p.add_argument("--limit", type=int, default=20)

    p = sub.add_parser("show", help="show one task")
    p.add_argument("task_id")

    p = sub.add_parser("log", help="print a task's event stream")
    p.add_argument("task_id")
    p.add_argument("--follow", "-f", action="store_true")

    p = sub.add_parser("verify", help="re-run acceptance for a task")
    p.add_argument("task_id")

    p = sub.add_parser("board", help="dashboard")
    p.add_argument("--open", action="store_true", help="write HTML and open it")
    p.add_argument("--serve", type=int, nargs="?", const=8787, metavar="PORT")
    p.add_argument("--out", help="write a standalone HTML snapshot to this path")

    p = sub.add_parser("api", help="serve the local REST API (consumed by the desktop frontend)")
    p.add_argument("--port", type=int, default=8787)

    sub.add_parser("doctor", help="environment self-check")
    sub.add_parser("gc", help="rotate the audit stream and prune old state")

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0

    try:
        handler = COMMANDS.get(args.command)
        if handler is None:
            parser.error(f"unknown command: {args.command}")
        return handler(args) or 0
    except errors.TaskproofError as exc:
        print(f"taskproof: {exc}", file=sys.stderr)
        if getattr(exc, "hint", None):
            print(f"  hint: {exc.hint}", file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        print("taskproof: interrupted", file=sys.stderr)
        return 130


# --------------------------------------------------------------------------
# Handlers are thin: argument parsing and output formatting only. All behaviour
# lives in the modules above, so it can be tested without the CLI.
# --------------------------------------------------------------------------


def cmd_init(args):
    dispatch.prepare_workspace(args.workspace)
    registry_path = registry.workspace_registry_path(args.workspace)
    payload = {
        "workspace": args.workspace,
        "registry": registry_path,
        "next": [
            "taskproof register <path>",
            'taskproof run <project> "<task>"',
            "taskproof board --open",
        ],
    }
    human = (
        f"initialised workspace: {args.workspace}\n"
        f"  registry: {registry_path}\n"
        "next:\n"
        "  taskproof register <path>         # probe and register a repository\n"
        '  taskproof run <project> "<task>"  # dispatch, verify, record\n'
        "  taskproof board --open            # static dashboard snapshot"
    )
    emit(args, payload, human)
    return 0


#: Build file -> (candidate acceptance command, verify_kind). Deliberately a
#: short, opinionated list, not a general-purpose project detector.
_BUILD_FILES = (
    ("package.json", "npm run build", "build"),
    ("pyproject.toml", "python -m compileall -q .", "build"),
    ("setup.py", "python -m compileall -q .", "build"),
    ("pom.xml", "mvn -q -DskipTests compile", "build"),
    ("Cargo.toml", "cargo check", "build"),
    ("go.mod", "go build ./...", "build"),
)

#: The probe runs the candidate command once on a clean tree. Long builds are
#: allowed but bounded so `register` cannot hang forever.
_PROBE_TIMEOUT = 600


def _infer_verify(path):
    """Return (command, verify_kind) for the first recognised build file."""
    for name, command, kind in _BUILD_FILES:
        if os.path.isfile(os.path.join(path, name)):
            return command, kind
    return None, "none"


def _toml_string(value) -> str:
    """A minimal TOML basic string (paths/ids are simple, but escape anyway)."""
    text = str(value)
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _append_project_block(reg_path, *, project_id, path, group, command, kind, probe):
    """Append one [[project]] table, leaving every existing byte untouched."""
    lines = [
        "",
        "[[project]]",
        f"id = {_toml_string(project_id)}",
        f"path = {_toml_string(path)}",
        f"group = {_toml_string(group)}",
    ]
    if command:
        lines.append(f"verify = {_toml_string(command)}")
        lines.append(f"verify_kind = {_toml_string(kind)}")
        if probe:
            lines.append(f"probe = {_toml_string(probe)}")
    else:
        lines.append('verify_kind = "none"')
    with open(reg_path, "a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def _register_human(payload) -> str:
    lines = [
        f"project: {payload['id']}  ({payload['path']})",
        f"group:   {payload['group']}",
    ]
    if payload["verify"]:
        lines.append(f"verify:  {payload['verify']}")
        lines.append(f"probe:   {payload['probe']}")
    else:
        lines.append("verify:  (none inferred — set one by hand)")
    lines.append("hint:    you may add an AGENTS.md to describe the repo to agents")
    if payload["dry_run"]:
        lines.append("(dry run: nothing written)")
    return "\n".join(lines)


def cmd_register(args):
    path = os.path.abspath(os.path.expanduser(args.path))
    if not os.path.exists(path):
        raise UsageError(f"path does not exist: {args.path}")
    if not os.path.isdir(path):
        raise UsageError(f"not a directory: {args.path}")

    project_id = args.id or os.path.basename(os.path.normpath(path)) or path
    group = args.group or project_id

    command, kind = _infer_verify(path)
    probe = None
    probe_exit = None
    if command is not None:
        # ④ probe once, on the clean tree, before writing anything.
        outcome = verify.run_acceptance(path, command, timeout=_PROBE_TIMEOUT)
        probe = "passed" if outcome.passed else "failed"
        probe_exit = outcome.exit_code

    payload = {
        "id": project_id,
        "path": path,
        "group": group,
        "verify": command,
        "verify_kind": kind,
        "probe": probe,
        "probe_exit": probe_exit,
        "dry_run": bool(args.dry_run),
        "registered": False,
    }

    if not args.dry_run:
        dispatch.prepare_workspace(args.workspace)
        reg_path = registry.workspace_registry_path(args.workspace)
        reg = registry.load(reg_path)
        if any(project.id == project_id for project in reg.projects):
            raise RegistryError(
                f"project id already registered: {project_id}",
                hint=f"edit {reg_path}, or choose a different --id",
            )
        _append_project_block(
            reg_path,
            project_id=project_id,
            path=path,
            group=group,
            command=command,
            kind=kind,
            probe=probe,
        )
        payload["registered"] = True
        payload["registry"] = reg_path

    emit(args, payload, _register_human(payload))
    return 0


def _read_probe_flags(reg_path) -> dict:
    """{id: probe} for the entries that carry a `probe` key.

    `registry.load` drops unknown keys, so the raw TOML is read here. Read-only.
    """
    import tomllib

    probes = {}
    try:
        with open(reg_path, "rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return probes
    for entry in data.get("project", []) or []:
        if isinstance(entry, dict) and isinstance(entry.get("id"), str):
            probe = entry.get("probe")
            if probe is not None:
                probes[entry["id"]] = probe
    return probes


def cmd_projects(args):
    reg_path = registry.workspace_registry_path(args.workspace)
    reg = registry.load(reg_path)
    probes = _read_probe_flags(reg_path)
    projects = [
        {
            "id": project.id,
            "group": project.group,
            "path": project.path,
            "verify": project.verify,
            "verify_kind": project.verify_kind,
            "probe": probes.get(project.id),
        }
        for project in reg.projects
    ]
    payload = {"projects": projects, "registry": reg_path}

    if not projects:
        human = f"no projects registered in {reg_path}"
    else:
        lines = [f"{'ID':<20} {'GROUP':<14} {'PROBE':<7} VERIFY"]
        for project in projects:
            lines.append(
                f"{project['id']:<20} {project['group']:<14} "
                f"{str(project['probe'] or '-'):<7} {project['verify'] or '-'}"
            )
            lines.append(f"  path: {project['path']}")
        human = "\n".join(lines)
    emit(args, payload, human)
    return 0


def cmd_run(args):
    task_id = dispatch.dispatch(
        args.workspace,
        args.project,
        args.brief,
        adapter=args.adapter,
        model=args.model,
        reasoning=args.reasoning,
        read_only=args.read_only,
        worktree=args.worktree,
        skip_verify=args.no_verify,
        timeout=args.timeout,
    )
    task = dispatch.task_detail(args.workspace, task_id).get("task") or {}
    payload = {"task_id": task_id, "status": task.get("status"), "task": task}
    emit(args, payload, f"{task_id}  {task.get('status', '')}  {args.project}")
    return 0


def _resolve_project_key(workspace, key):
    """Map an id/alias/path to the canonical project id, best effort."""
    if not key:
        return key
    try:
        reg = registry.load(registry.workspace_registry_path(workspace))
    except errors.TaskproofError:
        return key
    project = reg.by_id(key)
    return project.id if project is not None else key


def _tasks_human(tasks) -> str:
    if not tasks:
        return "no tasks"
    lines = [f"{'ID':<18} {'STATUS':<10} {'PROJECT':<16} BRIEF"]
    for task in tasks:
        brief = (task.get("brief") or "").replace("\n", " ")
        if len(brief) > 48:
            brief = brief[:45] + "..."
        lines.append(
            f"{str(task.get('id') or ''):<18} {str(task.get('status') or ''):<10} "
            f"{str(task.get('project') or ''):<16} {brief}"
        )
    return "\n".join(lines)


def cmd_tasks(args):
    project_key = _resolve_project_key(args.workspace, args.project)
    conn = storage.connect(storage.db_path(args.workspace))
    try:
        storage.migrate(conn)
        rows = storage.list_tasks(
            conn, status=args.status, project=project_key, limit=args.limit
        )
        tasks = [dict(row) for row in rows]
    finally:
        conn.close()
    payload = {"tasks": tasks, "count": len(tasks)}
    emit(args, payload, _tasks_human(tasks))
    return 0


def cmd_show(args):
    detail = dispatch.task_detail(args.workspace, args.task_id)
    if detail.get("task") is None:
        raise UsageError(f"no such task: {args.task_id}")
    task = detail["task"]
    human = "\n".join(
        [
            f"id:       {task.get('id')}",
            f"project:  {task.get('project')}",
            f"status:   {task.get('status')}",
            f"adapter:  {task.get('adapter')}",
            f"brief:    {task.get('brief')}",
            f"verify:   {task.get('verify_cmd')} (exit {task.get('verify_exit')})",
            f"created:  {task.get('created_at')}",
            f"finished: {task.get('finished_at')}",
            f"workdir:  {task.get('workdir')}",
        ]
    )
    emit(args, detail, human)
    return 0


#: `log --follow` polls the audit stream instead of blocking on a `tail -f`.
_LOG_POLL_SECONDS = 1.0


def _format_event(event) -> str:
    payload = event.get("payload")
    if payload is not None:
        try:
            payload = json.dumps(payload, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            payload = str(payload)
    return (
        f"{event.get('ts', '')}  {str(event.get('task_id') or '-'):<18} "
        f"{event.get('event', '')}  {payload or ''}"
    ).rstrip()


def _task_status(workspace, task_id):
    conn = storage.connect(storage.db_path(workspace))
    try:
        storage.migrate(conn)
        row = storage.get_task(conn, task_id)
        return row["status"] if row is not None else None
    finally:
        conn.close()


def cmd_log(args):
    if _task_status(args.workspace, args.task_id) is None:
        raise UsageError(f"no such task: {args.task_id}")

    if not args.follow:
        events = list(ledger.iter_events(args.workspace, task_id=args.task_id))
        payload = {"task_id": args.task_id, "events": events, "count": len(events)}
        human = "\n".join(_format_event(event) for event in events) or "(no events)"
        emit(args, payload, human)
        return 0

    seen = 0
    while True:
        events = list(ledger.iter_events(args.workspace, task_id=args.task_id))
        for event in events[seen:]:
            if args.json:
                print(json.dumps(event, ensure_ascii=False, default=str), flush=True)
            elif not args.quiet:
                print(_format_event(event), flush=True)
        seen = len(events)
        if _task_status(args.workspace, args.task_id) in TERMINAL_STATUSES:
            break
        time.sleep(_LOG_POLL_SECONDS)
    return 0


def cmd_verify(args):
    outcome = dispatch.verify_task(args.workspace, args.task_id)
    payload = {
        "task_id": args.task_id,
        "ran": outcome.ran,
        "passed": outcome.passed,
        "exit_code": outcome.exit_code,
        "command": outcome.command,
        "note": outcome.note,
        "violations": outcome.violations,
        "output_tail": outcome.output_tail,
    }
    status = "SKIPPED" if not outcome.ran else ("PASSED" if outcome.passed else "FAILED")
    emit(args, payload, f"{args.task_id}  verify: {status}  exit={outcome.exit_code}")
    return 0


def _board_serve(workspace, port):
    import http.server
    from urllib.parse import urlsplit

    from .board import render

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if urlsplit(self.path).path not in ("/", "/index.html"):
                self.send_error(404, "not found")
                return
            body = render.render_board(workspace).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    try:
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError as exc:
        raise UsageError(
            f"cannot serve the board on 127.0.0.1:{port}: {exc}",
            hint="the port is already in use; pass another --serve PORT",
        )
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
    return 0


def cmd_board(args):
    from .board import render

    if args.serve is not None:
        return _board_serve(args.workspace, args.serve)

    out = args.out or os.path.join(args.workspace, "board.html")
    document = render.render_board(args.workspace)
    directory = os.path.dirname(os.path.abspath(out))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(out, "w", encoding="utf-8") as handle:
        handle.write(document)

    opened = False
    if args.open:
        webbrowser.open("file://" + os.path.abspath(out))
        opened = True
    payload = {"path": os.path.abspath(out), "opened": opened, "bytes": len(document)}
    human = f"board written: {os.path.abspath(out)}" + (" (opened)" if opened else "")
    emit(args, payload, human)
    return 0


def cmd_api(args):
    from .api import server

    return server.serve(args.workspace, args.port)


def _check_workspace(workspace) -> dict:
    try:
        os.makedirs(workspace, exist_ok=True)
        probe = os.path.join(workspace, ".doctor-write-probe")
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write("ok")
        os.remove(probe)
    except OSError as exc:
        return {"ok": False, "path": workspace, "detail": f"workspace not writable: {exc}"}
    return {"ok": True, "path": workspace, "detail": ""}


def _check_registry(workspace) -> dict:
    reg_path = registry.workspace_registry_path(workspace)
    try:
        reg = registry.load(reg_path)
    except errors.TaskproofError as exc:
        return {"ok": False, "path": reg_path, "projects": 0, "detail": f"registry: {exc}"}
    return {"ok": True, "path": reg_path, "projects": len(reg.projects), "detail": ""}


def _adapter_status() -> list:
    from . import adapters

    results = []
    for name in adapters.KNOWN:
        if name.startswith("custom"):
            continue
        adapter_cls = None
        problem = None
        try:
            adapter_cls = adapters.load_class(name)
            problem = adapter_cls().preflight()
        except Exception as exc:  # doctor must never crash on a broken adapter
            problem = str(exc)
        binary = getattr(adapter_cls, "binary", "") if adapter_cls is not None else ""
        installed = problem is None
        results.append(
            {
                "name": name,
                "installed": installed,
                "binary": binary,
                "detail": "" if installed else problem,
            }
        )
    return results


def _doctor_human(report) -> str:
    lines = ["taskproof doctor", ""]
    python = report["python"]
    lines.append(
        f"  [{'ok' if python['ok'] else '!!'}] "
        f"python {python['version']} (needs {python['required']})"
    )
    sqlite = report["sqlite"]
    lines.append(
        f"  [{'ok' if sqlite['ok'] else '!!'}] sqlite "
        f"{sqlite.get('version') or sqlite.get('detail', '')}"
    )
    workspace = report["workspace"]
    lines.append(
        f"  [{'ok' if workspace['ok'] else '!!'}] workspace: {workspace['path']}"
    )
    reg = report["registry"]
    if reg["ok"]:
        lines.append(
            f"  [ok] registry: {reg['path']} ({reg['projects']} project(s))"
        )
    else:
        lines.append(f"  [!!] {reg['detail']}")
    lines.append("  adapters:")
    for item in report["adapters"]:
        mark = "ok" if item["installed"] else "!!"
        extra = "" if item["installed"] else f"  ({item['detail']})"
        lines.append(f"    [{mark}] {item['name']}{extra}")
    lines.append("")
    if report["problems"]:
        lines.append("problems:")
        lines.extend(f"  - {problem}" for problem in report["problems"])
    else:
        lines.append("all checks passed")
    return "\n".join(lines)


def cmd_doctor(args):
    report = {}

    version = sys.version.split()[0]
    python_ok = sys.version_info >= (3, 11)
    report["python"] = {"ok": python_ok, "version": version, "required": ">=3.11"}

    try:
        probe = sqlite3.connect(":memory:")
        sqlite_version = probe.execute("SELECT sqlite_version()").fetchone()[0]
        probe.close()
        report["sqlite"] = {"ok": True, "version": sqlite_version}
    except sqlite3.Error as exc:
        report["sqlite"] = {"ok": False, "version": None, "detail": str(exc)}

    report["workspace"] = _check_workspace(args.workspace)
    report["registry"] = _check_registry(args.workspace)
    report["adapters"] = _adapter_status()

    problems = []
    if not report["python"]["ok"]:
        problems.append(f"python {version} is older than 3.11")
    if not report["sqlite"]["ok"]:
        problems.append(f"sqlite unavailable: {report['sqlite'].get('detail', '')}")
    if not report["workspace"]["ok"]:
        problems.append(report["workspace"]["detail"])
    if not report["registry"]["ok"]:
        problems.append(report["registry"]["detail"])
    for item in report["adapters"]:
        if not item["installed"]:
            problems.append(f"adapter '{item['name']}' unavailable: {item['detail']}")
    report["problems"] = problems
    report["ok"] = not problems

    emit(args, report, _doctor_human(report))
    return 0


def cmd_gc(args):
    touched = ledger.rotate(args.workspace)
    conn = storage.connect(storage.db_path(args.workspace))
    try:
        storage.migrate(conn)
        reaped = concurrency.reap_expired(conn)
    finally:
        conn.close()

    payload = {
        "rotated": touched,
        "rotated_count": len(touched),
        "reaped_claims": reaped,
    }
    human = (
        f"rotated {len(touched)} audit file(s)\n"
        f"reaped {reaped} expired claim(s)"
    )
    emit(args, payload, human)
    return 0


COMMANDS = {
    "init": cmd_init,
    "register": cmd_register,
    "projects": cmd_projects,
    "run": cmd_run,
    "tasks": cmd_tasks,
    "show": cmd_show,
    "log": cmd_log,
    "verify": cmd_verify,
    "board": cmd_board,
    "api": cmd_api,
    "doctor": cmd_doctor,
    "gc": cmd_gc,
}


def emit(args, payload, human: str) -> None:
    """One place where `--json` vs human output is decided."""
    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    elif not getattr(args, "quiet", False):
        print(human)


if __name__ == "__main__":
    sys.exit(main())
