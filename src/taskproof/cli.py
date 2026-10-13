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
from datetime import datetime

from . import (
    __version__,
    concurrency,
    dispatch,
    errors,
    ledger,
    registry,
    storage,
)
from .errors import RegistryError, UsageError
from .models import STATUS_DONE, TERMINAL_STATUSES

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
    # Imported inside the function (not at module scope) so cli does not depend
    # on api.server at import time; api.server pulls in package modules that cli
    # also imports, and a module-level import risks a cycle. 8787 lives in one
    # place: api/server.py:DEFAULT_PORT.
    from .api.server import DEFAULT_PORT

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
    p.add_argument("--project", help="attach this lane to an existing project id")
    # Deprecated and ignored: a new taskgroup's lock defaults to its own id,
    # but the flag stays so older scripts keep running.
    p.add_argument("--group", help=argparse.SUPPRESS)

    sub.add_parser("projects", help="list registered projects (with their lanes)")

    sub.add_parser("taskgroups", help="list registered taskgroups (lanes)")

    sub.add_parser(
        "workspaces", help="list lanes that declare a long-lived workspace"
    )

    p = sub.add_parser(
        "workspace-rm",
        help="delete a lane's long-lived workspace (prints evidence first)",
    )
    p.add_argument("lane", help="taskgroup id, alias, or path")
    p.add_argument(
        "--force",
        action="store_true",
        help="delete even with uncommitted changes or unmerged commits",
    )

    p = sub.add_parser("run", help="dispatch one task (primary command)")
    p.add_argument("project", help="project id, alias, or path")
    p.add_argument("brief", help="what the agent should do")
    p.add_argument("--adapter", default="codex", help="codex | claude | gemini | opencode | custom:<cmd>")
    p.add_argument("--model")
    p.add_argument("--reasoning", choices=["none", "high"])
    p.add_argument("--read-only", action="store_true", help="read-only sandbox; acceptance is skipped")
    p.add_argument(
        "--worktree",
        action="store_true",
        help=(
            "run in a fresh git worktree beside the repo; removed after the "
            "run unless it has changes, in which case it is kept at "
            "<repo>-wt-<task-id>, printed and recorded (rm <id> deletes it)"
        ),
    )
    p.add_argument("--no-verify", action="store_true", help="skip acceptance (recorded as SKIPPED, not passed)")
    p.add_argument("--timeout", type=int, help="override the registry timeout (seconds)")
    p.add_argument(
        "--cap",
        type=int,
        metavar="N",
        help=(
            "one-off global concurrency cap for THIS dispatch only (not written "
            "to the registry)"
        ),
    )
    p = sub.add_parser("tasks", help="list tasks")
    p.add_argument("--status")
    p.add_argument("--project", help="project id, alias, or path (overrides cwd)")
    p.add_argument("--all", dest="all_projects", action="store_true",
                   help="every project, ignoring the cwd scope (overrides cwd)")
    p.add_argument("--id", dest="ids", metavar="ID[,ID...]",
                   help="only these task ids (comma-separated)")
    p.add_argument("--lane", metavar="TASKGROUP_ID",
                   help="only tasks dispatched onto this lane (group_name)")
    p.add_argument("--limit", type=int, default=20)

    p = sub.add_parser("show", help="show one task")
    p.add_argument("task_id")

    p = sub.add_parser("wait", help="block until a task reaches a terminal state")
    p.add_argument("task_id")
    p.add_argument("--timeout", type=float, default=600.0,
                   help="give up after this many seconds (default: %(default)s)")
    p.add_argument("--poll", type=float, default=2.0,
                   help="seconds between status reads (default: %(default)s)")

    p = sub.add_parser("log", help="print a task's event stream")
    p.add_argument("task_id")
    p.add_argument("--follow", "-f", action="store_true")

    p = sub.add_parser("verify", help="re-run acceptance for a task")
    p.add_argument("task_id")

    p = sub.add_parser(
        "accept",
        help=(
            "clear a blocked or failed task: done if acceptance passed (a failed "
            "card needs --note), else failed"
        ),
    )
    p.add_argument("task_id")
    p.add_argument(
        "--note",
        help=(
            "why a failed card is being cleared; required for failed "
            "(人工收尾必须留说明)"
        ),
    )

    p = sub.add_parser(
        "rerun",
        help="start a fresh copy of a terminal task (same brief and run flags)",
    )
    p.add_argument("task_id")

    p = sub.add_parser(
        "cancel", help="stop a task (kill its process tree)"
    )
    p.add_argument("task_id")

    p = sub.add_parser("rm", help="delete a terminal task's record and events")
    p.add_argument("task_id")

    p = sub.add_parser(
        "board",
        help="dashboard: serve the desktop web build over the local REST API",
    )
    p.add_argument("--open", action="store_true",
                   help="serve the board and open it in a browser (the default)")
    p.add_argument("--serve", type=int, nargs="?", const=DEFAULT_PORT, metavar="PORT",
                   help="serve the board without opening a browser (blocks)")

    p = sub.add_parser("api", help="serve the local read-only REST API (consumed by the desktop frontend)")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)

    p = sub.add_parser(
        "config",
        help="show or set [defaults] (concurrency / timeout) without losing comments",
    )
    p.add_argument("--show", action="store_true", help="print the effective cap/timeout and where each came from")
    p.add_argument("--concurrency", metavar="N", help="pin the global concurrency cap in [defaults] concurrency")
    p.add_argument("--timeout", metavar="N", help="set [defaults] timeout (seconds)")

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
        "projects": 0,
        "next": [
            "taskproof register <path>",
            'taskproof run <project> "<task>"',
            "taskproof board --open",
        ],
    }
    human = (
        f"initialised workspace: {args.workspace}\n"
        f"  registry: {registry_path}  (no projects yet)\n"
        "next:\n"
        "  taskproof register <path>         # probe and register a repository\n"
        '  taskproof run <project> "<task>"  # dispatch, verify, record\n'
        "  taskproof board --open            # live dashboard (serves + opens a browser)\n"
        "  taskproof board --serve          # serve the board without a browser\n"
        "  registry format                   # examples/projects.example.toml"
    )
    emit(args, payload, human)
    return 0


def _toml_string(value) -> str:
    """A minimal TOML basic string (paths/ids are simple, but escape anyway)."""
    text = str(value)
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _append_taskgroup_block(reg_path, *, taskgroup_id, path, project,
                            command, kind, probe, probe_exit):
    """Append one `[[taskgroup]]` block through the surgical writer.

    Every existing byte is preserved and the candidate is validated by `load`
    before it replaces the file. A missing `project` means the lane stands up a
    same-named project (the zero-migration compat rule).
    """
    entry = {
        "id": taskgroup_id,
        "project": project,
        "path": path,
        "verify": command,
        "verify_kind": kind,
        "probe": probe,
        "probe_exit": probe_exit,
    }
    registry.append_taskgroup(reg_path, registry.registry_hash(reg_path), entry)


def _register_human(payload) -> str:
    lines = [
        f"project:   {payload['project']}  ({payload['path']})",
        f"taskgroup: {payload['id']}  (lock: {payload['group']})",
    ]
    if payload["verify"]:
        lines.append(f"verify:    {payload['verify']}")
        lines.append(f"probe:     {payload['probe']}")
    else:
        lines.append("verify:    (none inferred — set one by hand)")
    lines.append("hint:      you may add an AGENTS.md to describe the repo to agents")
    if payload["dry_run"]:
        lines.append("(dry run: nothing written)")
    return "\n".join(lines)


def cmd_register(args):
    path = os.path.abspath(os.path.expanduser(args.path))
    if not os.path.exists(path):
        raise UsageError(f"path does not exist: {args.path}")
    if not os.path.isdir(path):
        raise UsageError(f"not a directory: {args.path}")

    draft = registry.probe_repository(path)
    taskgroup_id = args.id or draft["id"]
    project = args.project or None
    command = draft["verify"]
    kind = draft["verify_kind"]
    probe = draft["probe"]
    probe_exit = draft["probe_exit"]

    payload = {
        "id": taskgroup_id,
        "project": project or taskgroup_id,
        "path": path,
        # The lock defaults to the taskgroup id. `group` is kept in the payload
        # so older callers that read it keep working.
        "group": taskgroup_id,
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
        if any(tg.id == taskgroup_id for tg in reg.taskgroups):
            raise RegistryError(
                f"taskgroup id already registered: {taskgroup_id}",
                hint=f"edit {reg_path}, or choose a different --id",
            )
        _append_taskgroup_block(
            reg_path,
            taskgroup_id=taskgroup_id,
            path=path,
            project=project,
            command=command,
            kind=kind,
            probe=probe,
            probe_exit=probe_exit,
        )
        payload["registered"] = True
        payload["registry"] = reg_path

    emit(args, payload, _register_human(payload))
    return 0


def _read_probe_flags(reg_path) -> dict:
    """{id: {probe, probe_exit}} for entries that carry probe metadata.

    Delegates to `registry.read_probe_flags`, which reads both `[[project]]`
    (legacy) and `[[taskgroup]]` blocks from the raw TOML (`registry.load` drops
    these human/API-only keys). Read-only.
    """
    return registry.read_probe_flags(reg_path)


def _lane_overview(reg, stats, probes):
    """Project rows: one per project, each carrying its lanes and totals."""
    projects = []
    known_lane_ids = set()
    for project in reg.projects:
        lanes = reg.lanes_for(project.id)
        lane_records = []
        totals = {"tasks": 0, "in_progress": 0, "failed": 0}
        last_activity = None
        for lane in lanes:
            known_lane_ids.add(lane.id)
            stat = stats.get(lane.id) or {}
            flags = probes.get(lane.id) or {}
            probe = flags.get("probe")
            if probe is None and lane.verify_kind == "none":
                probe = "none"  # no acceptance command -> the task is SKIPPED
            lane_records.append(
                {
                    "id": lane.id,
                    "path": lane.path,
                    "group": lane.group,
                    "aliases": list(lane.aliases),
                    "verify": lane.verify,
                    "verify_kind": lane.verify_kind,
                    "probe": probe,
                    "tasks": int(stat.get("total", 0)),
                    "in_progress": int(stat.get("in_progress", 0)),
                    "failed": int(stat.get("failed", 0)),
                    "last_activity": stat.get("last_activity"),
                }
            )
            totals["tasks"] += int(stat.get("total", 0))
            totals["in_progress"] += int(stat.get("in_progress", 0))
            totals["failed"] += int(stat.get("failed", 0))
            activity = stat.get("last_activity")
            if activity and (last_activity is None or activity > last_activity):
                last_activity = activity
        single = lane_records[0] if len(lane_records) == 1 else None
        projects.append(
            {
                "id": project.id,
                "path": project.path,
                "aliases": list(project.aliases),
                "taskgroups": lane_records,
                "tasks": totals["tasks"],
                "in_progress": totals["in_progress"],
                "failed": totals["failed"],
                "last_activity": last_activity,
                # Convenience mirror of the single lane's lane-level fields, so
                # callers written against the old one-block-per-entry view keep
                # reading `verify`/`group`/`probe` for single-lane projects.
                "group": single["group"] if single else None,
                "verify": single["verify"] if single else None,
                "verify_kind": single["verify_kind"] if single else None,
                "probe": single["probe"] if single else None,
            }
        )
    # Tasks may name a lane that is no longer in the registry (hand-edited
    # config or database). Keep it so the totals still match `tasks` exactly.
    for row in stats.values():
        if row["project"] in known_lane_ids:
            continue
        projects.append(
            {
                "id": row["project"],
                "path": None,
                "aliases": [],
                "taskgroups": [],
                "group": None,
                "verify": None,
                "verify_kind": None,
                "probe": None,
                "tasks": int(row["total"]),
                "in_progress": int(row["in_progress"]),
                "failed": int(row["failed"]),
                "last_activity": row["last_activity"],
            }
        )
    return projects


def cmd_projects(args):
    """Project overview: registry configuration joined with task aggregates.

    One row per project, carrying its taskgroups (lanes). The numbers come from
    a single aggregate query (`storage.project_overview`) so they can never
    disagree with `tasks`.
    """
    reg_path = registry.workspace_registry_path(args.workspace)
    reg = registry.load(reg_path)
    probes = _read_probe_flags(reg_path)

    overview = []
    db = storage.db_path(args.workspace)
    if os.path.exists(db):  # never create a database just to list projects
        conn = storage.connect(db)
        try:
            storage.migrate(conn)
            overview = storage.project_overview(conn)
        finally:
            conn.close()
    stats = {row["project"]: row for row in overview}

    projects = _lane_overview(reg, stats, probes)
    payload = {"projects": projects, "registry": reg_path}

    if not projects:
        human = f"no projects registered in {reg_path}"
    else:
        lines = [
            f"{'ID':<20} {'TASKGROUPS':<22} {'PROBE':<7} {'TASKS':>5} "
            f"{'ACTV':>4} {'FAIL':>4} {'LAST ACTIVITY':<25} VERIFY"
        ]
        for project in projects:
            lanes = ",".join(tg["id"] for tg in project["taskgroups"]) or "-"
            lines.append(
                f"{project['id']:<20} {lanes:<22} "
                f"{str(project['probe'] or '-'):<7} {project['tasks']:>5} "
                f"{project['in_progress']:>4} {project['failed']:>4} "
                f"{str(project['last_activity'] or '—'):<25} {project['verify'] or '-'}"
            )
            lines.append(f"  path: {project['path'] or '-'}")
            for lane in project["taskgroups"]:
                lines.append(
                    f"  taskgroup: {lane['id']} -> {lane['path']} "
                    f"({lane['verify'] or 'no verify command'})"
                )
        human = "\n".join(lines)
    emit(args, payload, human)
    return 0


def cmd_taskgroups(args):
    """List every taskgroup (lane): id, owning project, path and verify command."""
    reg_path = registry.workspace_registry_path(args.workspace)
    reg = registry.load(reg_path)
    probes = _read_probe_flags(reg_path)

    taskgroups = [registry.taskgroup_record(tg, probes) for tg in reg.taskgroups]
    payload = {"taskgroups": taskgroups, "registry": reg_path}

    if not taskgroups:
        human = f"no taskgroups registered in {reg_path}"
    else:
        lines = [
            f"{'ID':<20} {'PROJECT':<16} {'PATH':<40} VERIFY"
        ]
        for tg in taskgroups:
            lines.append(
                f"{tg['id']:<20} {tg['project']:<16} "
                f"{tg['path']:<40} {tg['verify'] or '-'}"
            )
        human = "\n".join(lines)
    emit(args, payload, human)
    return 0


def cmd_workspaces(args):
    """List every lane that opts into a long-lived workspace, with live status.

    Read-only: it reports the workspace path, whether it has been built yet, how
    many uncommitted changes and unmerged commits it holds, and which dependency
    paths are symlinked from the main checkout.
    """
    rows = dispatch.list_workspaces(args.workspace)
    payload = {
        "workspaces": rows,
        "registry": registry.workspace_registry_path(args.workspace),
    }
    if not rows:
        human = "no lanes declare a workspace"
    else:
        lines = [
            f"{'ID':<20} {'PROJECT':<16} {'BUILT':<6} {'CHANGES':>7} "
            f"{'UNMERGED':>8} {'LINKS':<22} WORKSPACE"
        ]
        for row in rows:
            links = ",".join(row["links"]) or "-"
            lines.append(
                f"{row['id']:<20} {row['project']:<16} "
                f"{('yes' if row['exists'] else 'no'):<6} "
                f"{row['changed']:>7} {row['unmerged']:>8} "
                f"{links:<22} {row['workspace'] or '-'}"
            )
        human = "\n".join(lines)
    emit(args, payload, human)
    return 0


def _workspace_evidence(status: dict) -> str:
    """The before-deletion evidence `workspace-rm` must always print."""
    lines = [
        f"workspace: {status['workspace'] or '-'}",
        f"repository: {status['repo'] or '-'}",
        f"uncommitted changes ({status['changed']}):",
    ]
    lines += [f"  {line}" for line in status["changed_files"]] or ["  (none)"]
    lines.append(f"unmerged commits ({status['unmerged']}):")
    lines += [f"  {line}" for line in status["unmerged_commits"]] or ["  (none)"]
    lines.append("this unregisters the git worktree (git worktree remove --force)")
    return "\n".join(lines)


def cmd_workspace_rm(args):
    status = dispatch.lane_workspace_status(args.workspace, args.lane)
    evidence = _workspace_evidence(status)

    if not status["exists"]:
        emit(
            args,
            {"workspace": status, "removed": False},
            evidence + "\nno workspace directory; nothing to remove",
        )
        return 0

    # The evidence goes out BEFORE anything is deleted, so an operator always
    # sees what is at stake -- including on a refusal (the error below follows).
    if not args.json:
        print(evidence, flush=True)

    result = dispatch.remove_workspace(args.workspace, args.lane, force=args.force)

    if args.json:
        emit(args, {"workspace": status, "result": result}, "")
        return 0
    note = ""
    if result.get("forced"):
        note = "  (forced: uncommitted changes / unmerged commits present)"
    print(f"removed workspace: {result['path']}{note}", flush=True)
    return 0


def cmd_run(args):
    cap = None
    if args.cap is not None:
        if args.cap < 1:
            raise UsageError(
                f"--cap must be >= 1 (got {args.cap})",
                hint="可用范围：整数且 >= 1（例如 --cap 5）",
            )
        cap = args.cap
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
        cap=cap,
    )
    task = dispatch.task_detail(args.workspace, task_id).get("task") or {}
    status = task.get("status")
    payload = {"task_id": task_id, "status": status, "task": task}
    emit(args, payload, f"{task_id}  {status or ''}  {args.project}")
    return 0


def _load_registry_best_effort(workspace):
    """Load the workspace registry, or ``None`` when it is missing/broken.

    `tasks` must still work against the database alone; a bad registry only
    drops the cwd inference back to "no registered projects".
    """
    try:
        return registry.load(registry.workspace_registry_path(workspace))
    except errors.TaskproofError:
        return None


def _scope_banner(project_id, source, n_projects) -> str:
    """The mandatory scope label: ``--project`` > ``--all`` > cwd > all."""
    if project_id is None:
        return f"作用域: 全部 {n_projects} 个项目（{source}）"
    return f"当前项目: {project_id}（{source}）"


def _row_brief(task) -> str:
    brief = (task.get("brief") or "").replace("\n", " ")
    return brief[:45] + "..." if len(brief) > 48 else brief


def _row_verify(task) -> str:
    """One cell for the VERIFY column.

    `SKIPPED` is deliberately rendered as an en dash, not a pass: a card whose
    acceptance never ran must not look like one that did. Without a recorded
    exit there is nothing to claim, so that is a `?`; otherwise `exit=N`.
    """
    if task.get("verify_cmd") == dispatch.VERIFY_SKIPPED:
        return "–"
    exit_code = task.get("verify_exit")
    if exit_code is None:
        return "?"
    return f"exit={exit_code}"


def _row_files(task) -> str:
    files_changed = task.get("files_changed")
    return "-" if files_changed is None else str(files_changed)


def _tasks_header(*, with_project: bool) -> str:
    # Column order is contractual: ID STATUS [PROJECT] VERIFY FILES BRIEF. The
    # single-project view drops PROJECT (it is constant there) and keeps its
    # compact shape; either way BRIEF stays last and keeps its 45-char cap
    # (`_row_brief`), so the new columns never squeeze it out.
    cells = [f"{'ID':<18}", f"{'STATUS':<10}"]
    if with_project:
        cells.append(f"{'PROJECT':<16}")
    cells += [f"{'VERIFY':<8}", f"{'FILES':<6}", "BRIEF"]
    return "    " + " ".join(cells)


def _tasks_row(task, *, with_project: bool) -> str:
    cells = [f"{str(task.get('id') or ''):<18}", f"{str(task.get('status') or ''):<10}"]
    if with_project:
        cells.append(f"{str(task.get('project') or ''):<16}")
    cells += [f"{_row_verify(task):<8}", f"{_row_files(task):<6}", _row_brief(task)]
    return "    " + " ".join(cells)


def _tasks_human(tasks, *, project_id, source, n_projects) -> str:
    """Human rendering of `tasks`, grouped by project for the "全部" scope."""
    lines = [_scope_banner(project_id, source, n_projects)]
    if project_id is None:
        groups = storage.group_tasks_by_project(tasks)
        if not groups:
            lines.append("no tasks")
            return "\n".join(lines)
        for pid, items in groups:
            lines.append("")
            lines.append(f"# {pid} ({len(items)} 个任务)")
            lines.append(_tasks_header(with_project=True))
            for task in items:
                lines.append(_tasks_row(task, with_project=True))
        return "\n".join(lines)

    if not tasks:
        lines.append("no tasks")
        return "\n".join(lines)
    lines.append(_tasks_header(with_project=False))
    for task in tasks:
        lines.append(_tasks_row(task, with_project=False))
    return "\n".join(lines)


def cmd_tasks(args):
    reg = _load_registry_best_effort(args.workspace)
    project_id, source = registry.resolve_scope(
        reg, explicit_project=args.project, force_all=args.all_projects
    )

    # `--id` / `--lane` have no SQL seam (`list_tasks` only knows status /
    # project), so they are applied here -- but AFTER the status/project
    # filter and BEFORE `--limit`, so every filter composes. `limit=-1` asks
    # SQLite for every row (its "no limit"), and the cap is applied below.
    id_filter = {
        tid.strip() for tid in (getattr(args, "ids", None) or "").split(",") if tid.strip()
    }
    lane = getattr(args, "lane", None)

    conn = storage.connect(storage.db_path(args.workspace))
    try:
        storage.migrate(conn)
        rows = storage.list_tasks(
            conn, status=args.status, project=project_id, limit=-1
        )
        tasks = [dict(row) for row in rows]
    finally:
        conn.close()

    if id_filter:
        tasks = [task for task in tasks if task.get("id") in id_filter]
    if lane:
        tasks = [task for task in tasks if task.get("group_name") == lane]
    tasks = tasks[: args.limit]

    if project_id is None:
        groups = storage.group_tasks_by_project(tasks)
        tasks = [task for _pid, items in groups for task in items]
    else:
        tasks = sorted(tasks, key=lambda t: t.get("created_at") or "", reverse=True)

    if reg is not None:
        n_projects = len(reg.projects)
    else:
        n_projects = len({t.get("project") for t in tasks if t.get("project")})

    payload = {
        "tasks": tasks,
        "count": len(tasks),
        "project": project_id,
        "scope": source,
    }
    emit(
        args,
        payload,
        _tasks_human(
            tasks, project_id=project_id, source=source, n_projects=n_projects
        ),
    )
    return 0


def cmd_show(args):
    detail = dispatch.task_detail(args.workspace, args.task_id)
    if detail.get("task") is None:
        raise UsageError(f"no such task: {args.task_id}")
    task = detail["task"]
    lines = [
        f"id:       {task.get('id')}",
        f"project:  {task.get('project')}",
        f"status:   {task.get('status')}",
        f"adapter:  {task.get('adapter')}",
        f"brief:    {task.get('brief')}",
        f"verify:   {task.get('verify_cmd')} (exit {task.get('verify_exit')})",
        f"created:  {task.get('created_at')}",
        f"finished: {task.get('finished_at')}",
        f"workdir:  {task.get('workdir')}",
        f"files:    {task.get('files_changed')} (changed)",
    ]
    lines.extend(_change_lines(detail.get("events") or []))
    emit(args, detail, "\n".join(lines))
    return 0


def _change_lines(events) -> list:
    """The `changes:` block of `show`, read from the `changes` event.

    One indented line per recorded path; a path that was already dirty before
    the run (the part of ``files_changed`` that is NOT this card's doing) gets a
    trailing marker so the reader can tell the two apart at a glance.
    """
    payload = next(
        (e.get("payload") for e in events if e.get("event") == "changes"),
        None,
    )
    if not isinstance(payload, dict):
        return []
    preexisting = set(payload.get("preexisting") or [])
    lines = ["changes:"]
    for path in payload.get("paths") or []:
        suffix = "  [跑前已脏]" if path in preexisting else ""
        lines.append(f"  {path}{suffix}")
    if payload.get("truncated"):
        lines.append("  … (截断)")
    return lines


def _wait_human(task) -> str:
    """`wait`'s text form: the run-ending line, then the verdict fields."""
    return "\n".join(
        [
            f"{task.get('id')}  {task.get('status') or ''}  {task.get('project') or ''}",
            f"status:   {task.get('status')}",
            f"exit:     {task.get('exit_code')}",
            f"verify:   {task.get('verify_cmd')} (exit {task.get('verify_exit')})",
            f"files:    {task.get('files_changed')}",
            f"started:  {task.get('started_at')}",
            f"finished: {task.get('finished_at')}",
        ]
    )


def cmd_wait(args):
    """Poll the ledger until a task is terminal, then report it.

    Read-only by construction: it never forks, daemonises or spawns a thread,
    it just re-reads the task row on `--poll` seconds like `log --follow`. A
    wait that runs out returns 124 and leaves the task exactly where it was.
    """
    deadline = time.monotonic() + args.timeout
    while True:
        status = _task_status(args.workspace, args.task_id)
        if status is None:
            raise UsageError(f"no such task: {args.task_id}")
        if status in TERMINAL_STATUSES:
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(args.poll, remaining))

    detail = dispatch.task_detail(args.workspace, args.task_id)
    task = detail.get("task") or {}
    emit(args, detail, _wait_human(task))

    status = task.get("status")
    if status not in TERMINAL_STATUSES:
        return 124  # the wait gave up; the task state was never touched
    return 0 if status == STATUS_DONE else 1


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


def cmd_accept(args):
    task = dispatch.accept_task(
        args.workspace, args.task_id, note=getattr(args, "note", None)
    )
    payload = {"task_id": args.task_id, "status": task.get("status"), "task": task}
    emit(args, payload, f"{args.task_id}  {task.get('status', '')}  accepted")
    return 0


def cmd_rerun(args):
    new_id = dispatch.rerun_task(args.workspace, args.task_id)
    task = dispatch.task_detail(args.workspace, new_id).get("task") or {}
    payload = {
        "task_id": new_id,
        "rerun_of": args.task_id,
        "status": task.get("status"),
        "task": task,
    }
    emit(args, payload, f"{new_id}  {task.get('status', '')}  rerun of {args.task_id}")
    return 0


def cmd_cancel(args):
    task = dispatch.cancel_task(args.workspace, args.task_id)
    payload = {"task_id": args.task_id, "status": task.get("status"), "task": task}
    emit(args, payload, f"{args.task_id}  {task.get('status', '')}  cancelled")
    return 0


def cmd_rm(args):
    removed = dispatch.remove_task(args.workspace, args.task_id)
    emit(args, {"removed": removed}, f"removed {removed}")
    return 0


def _board_static_root():
    """Where the desktop renderer's web build lives inside the package.

    A function, not a constant, so tests can point it at a temporary directory:
    the real ``src/taskproof/web/`` is produced by the desktop build and is
    absent from a source checkout until ``npm run build:web`` runs.
    """
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


def _board_serve(workspace, port, *, open_browser=False, httpd_factory=None):
    """Bind 127.0.0.1:port serving the real REST API + the desktop web build.

    Binding happens *before* the browser is opened, so a busy port surfaces as a
    UsageError instead of a tab that never loads. ``httpd_factory`` and
    ``open_browser`` are seams for the tests: they let a test observe the URL
    handed to ``webbrowser.open`` and stop the loop without a real socket or a
    permanent block. The opened URL uses the port the socket actually bound
    (so ``port=0`` still yields a reachable address).
    """
    import http.server

    from .api import server as api_server

    static_root = _board_static_root()
    if not os.path.isdir(static_root):
        raise UsageError(
            f"the board's web assets are missing: {static_root}",
            hint="run `npm run build:web` in desktop/",
        )

    factory = httpd_factory or http.server.ThreadingHTTPServer
    try:
        httpd = factory(("127.0.0.1", port), api_server.build_handler(workspace, static_root))
    except OSError as exc:
        raise UsageError(
            f"cannot serve the board on 127.0.0.1:{port}: {exc}",
            hint="the port is already in use; pass another --serve PORT",
        )
    bound_port = httpd.server_address[1]
    try:
        if open_browser:
            webbrowser.open(f"http://127.0.0.1:{bound_port}/")
        httpd.serve_forever()
    finally:
        httpd.server_close()
    return 0


def cmd_board(args):
    from .api.server import DEFAULT_PORT

    # One mode now: serve the same REST API the desktop app uses, plus the
    # desktop renderer's web build. A bare `board` (and the explicit `--open`
    # synonym) serves and opens a browser; `--serve [PORT]` serves only. The
    # server blocks either way. The old snapshot flags are gone.
    open_browser = args.open or args.serve is None
    port = args.serve if args.serve is not None else DEFAULT_PORT
    return _board_serve(args.workspace, port, open_browser=open_browser)


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


def _cap_source_text(cap) -> str:
    """Doctor's source gloss for a concurrency dict (``auto``/``toml``/``cli``)."""
    source = cap.get("source")
    detail = cap.get("detail", "")
    if source == concurrency.SOURCE_AUTO:
        return f"自动探测 {detail}"
    if source == concurrency.SOURCE_CLI:
        return f"本次 {detail}"
    return detail or str(source)


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
    cap = report.get("concurrency")
    if cap is not None:
        lines.append(
            f"  [ok] concurrency: {cap['value']} "
            f"（来源：{_cap_source_text(cap)}）"
        )
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


_DEFAULT_TIMEOUT = 1800


def _load_defaults(workspace):
    """The `[defaults]` table of the workspace registry, or ``{}``.

    Read-only and best-effort: a missing or broken registry simply means "no
    configured defaults", which is exactly the auto-detect case (card 42)."""
    try:
        reg = registry.load(registry.workspace_registry_path(workspace))
    except errors.TaskproofError:
        return {}
    return reg.defaults


def _timeout_setting(defaults):
    """The effective timeout plus its source, mirroring :func:`concurrency.resolve`."""
    if "timeout" in (defaults or {}):
        return {"value": int(defaults["timeout"]), "source": "toml", "detail": "projects.toml"}
    return {"value": _DEFAULT_TIMEOUT, "source": "default", "detail": "内置默认"}


def _positive_int(name, raw):
    """Parse ``raw`` as an integer >= 1, or raise a UsageError naming the range.

    Deliberately not delegated to argparse's ``type=int``: a rejected value must
    produce a message that states the usable range (card 42) and, crucially, the
    caller must be able to validate *every* flag before any write happens."""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise UsageError(
            f"{name} must be an integer >= 1 (got {raw!r})",
            hint="可用范围：整数且 >= 1（例如 --concurrency 4）",
        )
    if value < 1:
        raise UsageError(
            f"{name} must be >= 1 (got {value})",
            hint="可用范围：整数且 >= 1（例如 --concurrency 4）",
        )
    return value


def _elapsed_seconds(iso_str):
    if not iso_str:
        return None
    try:
        then = datetime.fromisoformat(iso_str)
    except (TypeError, ValueError):
        return None
    now = datetime.now(then.tzinfo) if then.tzinfo else datetime.now()
    return max(0, int((now - then).total_seconds()))


def _format_duration(seconds):
    if seconds is None:
        return "?"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m{sec}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes}m"


def _active_running_tasks(workspace):
    """Tasks currently holding a global slot: id / project / how long.

    Reads the *claims* table, so it names exactly the cards the concurrency gate
    is counting — never a card that merely looks busy. Strictly read-only: it
    never creates the database, and opening an existing one touches only SQLite's
    own sidecars."""
    path = storage.db_path(workspace)
    if not os.path.exists(path):
        return []
    conn = storage.connect(path)
    try:
        rows = conn.execute(
            "SELECT t.id AS id, t.project AS project, "
            "       COALESCE(t.started_at, c.claimed_at) AS started_at "
            "FROM claims c JOIN tasks t ON t.id = c.task_id "
            "WHERE c.scope != ? AND julianday(c.expires_at) > julianday('now') "
            "ORDER BY c.claimed_at",
            (concurrency.GLOBAL_SCOPE,),
        ).fetchall()
    finally:
        conn.close()
    running = []
    for row in rows:
        started_at = row["started_at"]
        running.append(
            {
                "id": row["id"],
                "project": row["project"],
                "started_at": started_at,
                "elapsed_seconds": _elapsed_seconds(started_at),
            }
        )
    return running


def cmd_config(args):
    """Show the effective `[defaults]`, or set `concurrency` / `timeout` in place.

    Setting a value edits only the one line (comment-preserving) — see
    `registry.set_default`. Every flag is validated before the first write, so a
    bad value leaves the registry byte-identical. `--show` (and any rejected
    input) is pure read."""
    # Validate every write target *before* touching disk.
    new_concurrency = None
    new_timeout = None
    if args.concurrency is not None:
        new_concurrency = _positive_int("--concurrency", args.concurrency)
    if args.timeout is not None:
        new_timeout = _positive_int("--timeout", args.timeout)

    reg_path = registry.workspace_registry_path(args.workspace)
    if new_concurrency is not None:
        registry.set_default(reg_path, "concurrency", new_concurrency)
    if new_timeout is not None:
        registry.set_default(reg_path, "timeout", new_timeout)

    defaults = _load_defaults(args.workspace)
    cap = concurrency.resolve(defaults)
    timeout = _timeout_setting(defaults)
    payload = {"concurrency": cap.as_dict(), "timeout": timeout}
    human_lines = [
        f"concurrency = {cap.value}（{concurrency.source_gloss(cap)}）",
        f"timeout = {timeout['value']}（{timeout['detail']}）",
    ]

    # Non-retroactive (Q4): a *smaller* cap never touches a running card.
    if new_concurrency is not None:
        running = _active_running_tasks(args.workspace)
        if len(running) > new_concurrency:
            payload["running_over_cap"] = running
            human_lines.append("")
            human_lines.append(
                f"注意：生效上限已降到 {new_concurrency}，但当前有 "
                f"{len(running)} 张卡在跑（超过新上限）。"
            )
            human_lines.append("不追溯：这些卡照常跑完，状态不改、进程不杀。")
            human_lines.append("在跑的卡：")
            for row in running:
                human_lines.append(
                    f"  {row['id']}  {row['project']}  "
                    f"{_format_duration(row['elapsed_seconds'])}"
                )

    emit(args, payload, "\n".join(human_lines))
    return 0


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
    report["concurrency"] = concurrency.resolve(_load_defaults(args.workspace)).as_dict()
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
    "taskgroups": cmd_taskgroups,
    "workspaces": cmd_workspaces,
    "workspace-rm": cmd_workspace_rm,
    "run": cmd_run,
    "tasks": cmd_tasks,
    "show": cmd_show,
    "wait": cmd_wait,
    "log": cmd_log,
    "verify": cmd_verify,
    "accept": cmd_accept,
    "rerun": cmd_rerun,
    "cancel": cmd_cancel,
    "rm": cmd_rm,
    "board": cmd_board,
    "api": cmd_api,
    "doctor": cmd_doctor,
    "gc": cmd_gc,
    "config": cmd_config,
}


def emit(args, payload, human: str) -> None:
    """One place where `--json` vs human output is decided."""
    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    elif not getattr(args, "quiet", False):
        print(human)


if __name__ == "__main__":
    sys.exit(main())
