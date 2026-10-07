"""Command line interface.

Exit codes are contractual — see errors.py and docs/DESIGN.md.
Human-readable output follows the locale; `--json` is for machines.
"""

import argparse
import json
import os
import sys

from . import __version__, errors

DEFAULT_WORKSPACE = os.path.join(os.path.expanduser("~"), ".taskproof")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
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
    raise NotImplementedError("card: cli-commands")


def cmd_register(args):
    raise NotImplementedError("card: register")


def cmd_projects(args):
    raise NotImplementedError("card: cli-commands")


def cmd_run(args):
    raise NotImplementedError("card: dispatch")


def cmd_tasks(args):
    raise NotImplementedError("card: cli-commands")


def cmd_show(args):
    raise NotImplementedError("card: cli-commands")


def cmd_log(args):
    raise NotImplementedError("card: ledger")


def cmd_verify(args):
    raise NotImplementedError("card: verify")


def cmd_board(args):
    raise NotImplementedError("card: board")


def cmd_api(args):
    raise NotImplementedError("card: api")


def cmd_doctor(args):
    raise NotImplementedError("card: cli-commands")


def cmd_gc(args):
    raise NotImplementedError("card: ledger")


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
