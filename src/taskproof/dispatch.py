"""The dispatch pipeline.

    resolve project -> take concurrency slots -> run adapter -> parse result
        -> check forbidden paths -> run acceptance -> record -> release slots

Every step appends to the audit stream, so a crashed run is reconstructable
from `events-*.jsonl` alone.

What this module deliberately does NOT do: decide whether the agent's claim is
true. The acceptance command in `verify.py` decides that.

Slot handling
-------------
`concurrency.acquire()` returns a list of :class:`concurrency.Lease` objects.
A ``Lease`` is a ``str`` (the scope name) that *also* carries the owner
``token``; `concurrency.release()` walks that list through ``_iter_leases`` and
only deletes a row whose token matches this process. The value returned by
``acquire`` is therefore kept verbatim and handed straight back to ``release``
inside a ``finally`` — passing it through anything lossy (e.g. a bare scope
string) would strip the proof of ownership and silently leak the slot.
"""

import json
import os
import shutil
import signal
import subprocess
import threading
import time
from datetime import datetime
from typing import Optional

from . import concurrency, registry, storage, verify
from .adapters import get as get_adapter
from .adapters.base import ResultParseError
from .errors import EXIT_VERIFY, AdapterError, UsageError, VerifyError
from .models import (
    STATUS_BLOCKED,
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    STATUS_TIMEOUT,
    STATUS_VERIFYING,
    TERMINAL_STATUSES,
    Task,
)

#: Seconds to wait after SIGTERM before escalating to SIGKILL for a task tree.
#: Mirrors the grace period `_terminate_tree` uses on the adapter-spawn path.
TERMINATE_GRACE_SECONDS = 5.0


class TaskNotFoundError(UsageError):
    """No task with that id. The API maps this to HTTP 404."""


class TaskStateError(UsageError):
    """The task is not in a state that allows the action. The API maps this
    to HTTP 409 (state conflict), the CLI to its usual usage exit code."""


#: Every status the dashboard reports on, so a status with no rows still shows
#: up as 0 instead of disappearing from the summary.
_ALL_STATUSES = (
    STATUS_QUEUED,
    STATUS_RUNNING,
    STATUS_VERIFYING,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_BLOCKED,
    STATUS_TIMEOUT,
    STATUS_CANCELLED,
)

#: Written to `tasks.verify_cmd` when acceptance did not run. Deliberately NOT a
#: command: a skipped check must never be readable as a pass.
VERIFY_SKIPPED = "SKIPPED"


def prepare_workspace(workspace: str) -> None:
    """Create the workspace, database and audit directory if missing.

    A brand-new workspace gets a registry holding the `[defaults]` table and no
    projects: `register` is how entries arrive. Seeding an example project here
    meant the dashboard listed a placeholder repository until someone deleted it.
    """
    os.makedirs(workspace, exist_ok=True)
    # The audit stream (`events-<month>.jsonl`) and per-task logs live beside the
    # database, i.e. in the workspace itself; `logs/` keeps the logs tidy.
    os.makedirs(os.path.join(workspace, "logs"), exist_ok=True)

    conn = storage.connect(storage.db_path(workspace))
    try:
        storage.migrate(conn)
    finally:
        conn.close()

    reg_path = registry.workspace_registry_path(workspace)
    if not os.path.exists(reg_path):
        with open(reg_path, "w", encoding="utf-8") as handle:
            handle.write(registry.SAMPLE_REGISTRY)


def dispatch(
    workspace: str,
    project_key: str,
    brief: str,
    *,
    adapter: str = "codex",
    model: Optional[str] = None,
    reasoning: Optional[str] = None,
    read_only: bool = False,
    worktree: bool = False,
    skip_verify: bool = False,
    timeout: Optional[int] = None,
    start: bool = True,
    queue_seq: Optional[int] = None,
) -> str:
    """Run one task end to end (``start=True``) or park it queued.

    With ``start=False`` this only builds the row: status ``queued``, the
    requested ``queue_seq``, no concurrency claim, no adapter. The queue daemon
    (card 24) is what later advances a queued row; a manual ``run`` still takes
    the ``start=True`` path. Returns the task id either way.

    Raises the typed errors in `errors.py` so the CLI can map them to exit codes:
      ConcurrencyError -> 75, AdapterError -> 70, VerifyError -> 71, RegistryError -> 2

    Rules that must survive any refactor:
      * the acceptance command runs in the PROJECT workdir, never the workspace
      * `skip_verify` records verify as SKIPPED, never as passed
      * slots are released on every exit path, including exceptions
      * only processes this function spawned are ever terminated
    """
    # ② prepare + connect (creates the db and, on a fresh workspace, the sample
    # registry we are about to read).
    prepare_workspace(workspace)

    # ① resolve the project. A missing/unknown key is a RegistryError (exit 2).
    reg = registry.load(registry.workspace_registry_path(workspace))
    project = reg.require(project_key)

    effective_timeout = timeout if timeout is not None else reg.timeout

    # Resolve the adapter object now (a bare constructor, no side effects): a bad
    # adapter name is a UsageError raised before any task row or slot exists, so
    # a typo can never leave a task stuck in `running`.
    adapter_obj = get_adapter(
        adapter, model=model, reasoning=reasoning, timeout=effective_timeout
    )

    conn = storage.connect(storage.db_path(workspace))
    try:
        storage.migrate(conn)

        # ② allocate the task id before claiming a slot, so the claim row can
        # name the task it is protecting.
        prefix_date = datetime.now().strftime("%Y%m%d")
        task_id = storage.next_task_id(conn, prefix_date=prefix_date)

        # ②b A parked task is only a row: no slot, no adapter, no process. Its
        # explicit `queue_seq` is the sole source of queue order (same number =
        # same wave). `start=True` keeps the historic synchronous behaviour.
        if not start:
            storage.insert_task(
                conn,
                Task(
                    id=task_id,
                    project=project.id,
                    group=project.group,
                    brief=brief,
                    status=STATUS_QUEUED,
                    adapter=adapter,
                    model=model,
                    reasoning=reasoning,
                    queue_seq=queue_seq,
                    created_at=storage.now_iso(),
                ),
            )
            storage.append_event(
                conn,
                task_id,
                "queued",
                {
                    "project": project.id,
                    "group": project.group,
                    "adapter": adapter,
                    "queue_seq": queue_seq,
                    # Card 22 parks a row with only its `tasks` columns; the
                    # run flags have no column, so they ride along in this
                    # event payload. `run_queued` reads them back when the
                    # queue advances the row.
                    "read_only": read_only,
                    "worktree": worktree,
                    "skip_verify": skip_verify,
                    "timeout": timeout,
                },
            )
            return task_id

        # ③ claim the group slot + a slot under the global cap. A refusal is a
        # ConcurrencyError (exit 75) and nothing is queued.
        ttl = max(1, int(effective_timeout)) + 60
        scopes = concurrency.acquire(
            conn, task_id, project.group, cap=reg.concurrency, ttl=ttl
        )

        # ⑨ Whatever happens below — success, a recorded failure, or a raised
        # error — the exact credential from ③ is released. `release` verifies the
        # ownership token, so this can only ever drop our own claim.
        try:
            # ④ the task row + the `started` event.
            task = Task(
                id=task_id,
                project=project.id,
                group=project.group,
                brief=brief,
                status=STATUS_RUNNING,
                adapter=adapter,
                model=model,
                reasoning=reasoning,
                pid=os.getpid(),
                queue_seq=queue_seq,
                created_at=storage.now_iso(),
                started_at=storage.now_iso(),
            )
            storage.insert_task(conn, task)
            storage.append_event(
                conn,
                task_id,
                "started",
                {
                    "project": project.id,
                    "group": project.group,
                    "adapter": adapter,
                    "read_only": read_only,
                    "worktree": worktree,
                    "skip_verify": skip_verify,
                    "queue_seq": queue_seq,
                },
            )

            _execute_claimed(
                conn,
                task_id=task_id,
                project=project,
                adapter_obj=adapter_obj,
                adapter_name=adapter,
                brief=brief,
                workspace=workspace,
                read_only=read_only,
                worktree=worktree,
                skip_verify=skip_verify,
                timeout=effective_timeout,
            )
            return task_id
        finally:
            concurrency.release(conn, scopes)
    finally:
        conn.close()


def _execute_claimed(
    conn,
    *,
    task_id: str,
    project,
    adapter_obj,
    adapter_name: str,
    brief: str,
    workspace: str,
    read_only: bool,
    worktree: bool,
    skip_verify: bool,
    timeout: int,
) -> None:
    """Steps 5-8 for a task that is already `running` and holds a slot.

    Shared by `dispatch(start=True)` (row inserted running) and `run_queued`
    (row flipped from queued to running). Owns the whole worktree lifecycle
    (create -> execute -> keep-if-changed / remove-if-clean) and raises whatever
    `_execute` raises; it never touches the concurrency claim, which stays the
    caller's.
    """
    worktree_path = None
    run_dir = project.path
    try:
        if worktree:
            if not _is_git_repo(project.path):
                raise UsageError(
                    f"--worktree needs a git repository, but {project.path} "
                    "is not one",
                    hint="run without --worktree, or point the registry at a git checkout",
                )
            worktree_path = _create_worktree(project.path, task_id)
            run_dir = worktree_path
            storage.append_event(conn, task_id, "worktree_created", {"path": run_dir})

        _execute(
            conn,
            task_id=task_id,
            project=project,
            adapter_obj=adapter_obj,
            adapter_name=adapter_name,
            brief=brief,
            run_dir=run_dir,
            workspace=workspace,
            read_only=read_only,
            skip_verify=skip_verify,
            timeout=timeout,
        )
    finally:
        # Decide the worktree's fate on every exit path. A run that left changes
        # behind KEEPS the checkout and announces it -- silently discarding
        # uncommitted work was the whole bug this replaced. A clean run removes
        # it as before; a cleanup failure is recorded rather than raised (it
        # would mask the real outcome).
        if worktree_path is not None:
            changed = _worktree_change_count(worktree_path)
            if changed:
                print(
                    f"worktree kept: {worktree_path} ({changed} files changed)",
                    flush=True,
                )
                storage.append_event(
                    conn,
                    task_id,
                    "worktree",
                    {
                        "path": worktree_path,
                        "changed": changed,
                        # The source repo, so `rm` can unregister the checkout
                        # without a registry lookup.
                        "repo": project.path,
                    },
                )
            else:
                error = _remove_worktree(project.path, worktree_path)
                if error:
                    storage.append_event(
                        conn,
                        task_id,
                        "worktree_cleanup_failed",
                        {"path": worktree_path, "error": error},
                    )
                else:
                    storage.append_event(
                        conn, task_id, "worktree_removed", {"path": worktree_path}
                    )


def _queued_options(conn, task_id: str) -> dict:
    """Recover the run flags a parked task carried in its `queued` event.

    Card 22 parked a row with only its `tasks` columns (project, brief, adapter,
    model, reasoning, queue_seq); read_only / worktree / skip_verify / timeout
    have no column, so they were recorded in the `queued` event payload. The
    latest such event wins. A row parked by an older build (no payload) yields
    `{}` and the queue advances it with the documented defaults.
    """
    row = conn.execute(
        "SELECT payload FROM events WHERE task_id = ? AND event = 'queued' "
        "ORDER BY id DESC LIMIT 1",
        (task_id,),
    ).fetchone()
    if row is None or row[0] is None:
        return {}
    try:
        payload = json.loads(row[0])
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def run_queued(workspace: str, task_id: str) -> str:
    """Advance ONE existing ``queued`` row: ``queued -> running -> ...``.

    THE population point `taskproof queue` is built on, and the same entry the
    manual "fire now" button (card 23) calls to jump a single card out of its
    wave. It mints NO new id: the row named by ``task_id`` is the very row that
    ends up running (and terminal), so a queued card keeps its id, its
    ``queue_seq`` and its place in history.

    Differences from ``dispatch(start=True)``:
      * the project / brief / adapter / model / reasoning come from the stored
        row, not from arguments (the `queued` event carries the run flags);
      * a refusal by the concurrency gate (``ConcurrencyError``, exit 75) leaves
        the row ``queued`` and unchanged — the queue retries it on a later tick
        instead of dropping or duplicating it.

    Raises ``TaskNotFoundError`` (no such row) or ``TaskStateError`` (the row is
    not ``queued``); an attempt that starts raises whatever ``_execute`` raises
    (the row is still recorded terminal in that case). Returns ``task_id``.
    """
    prepare_workspace(workspace)
    conn = storage.connect(storage.db_path(workspace))
    try:
        storage.migrate(conn)
        row = storage.get_task(conn, task_id)
        if row is None:
            raise TaskNotFoundError(f"no such task: {task_id}")
        if row["status"] != STATUS_QUEUED:
            raise TaskStateError(
                f"task {task_id} is {row['status']}; only a queued task can be advanced"
            )

        reg = registry.load(registry.workspace_registry_path(workspace))
        project = reg.require(row["project"])
        options = _queued_options(conn, task_id)
        effective_timeout = (
            options.get("timeout") if options.get("timeout") is not None else reg.timeout
        )
        # Resolve the adapter the row was parked with, before any claim exists.
        adapter_obj = get_adapter(
            row["adapter"],
            model=row["model"],
            reasoning=row["reasoning"],
            timeout=effective_timeout,
        )

        # 3. Claim the slot BEFORE flipping the row, so a refusal (exit 75)
        # leaves it exactly as the queue found it: `queued`, same seq, no pid.
        ttl = max(1, int(effective_timeout)) + 60
        scopes = concurrency.acquire(
            conn, task_id, project.group, cap=reg.concurrency, ttl=ttl
        )
        try:
            # 4. queued -> running, SAME id. Only status / pid / started_at are
            # rewritten; brief, queue_seq and created_at are left untouched.
            storage.update_task(
                conn,
                task_id,
                status=STATUS_RUNNING,
                pid=os.getpid(),
                started_at=storage.now_iso(),
            )
            storage.append_event(
                conn,
                task_id,
                "started",
                {
                    "project": project.id,
                    "group": project.group,
                    "adapter": row["adapter"],
                    "read_only": bool(options.get("read_only")),
                    "worktree": bool(options.get("worktree")),
                    "skip_verify": bool(options.get("skip_verify")),
                    "queue_seq": row["queue_seq"],
                    # Distinguishes "left the queue" from a task that was born
                    # running via `dispatch(start=True)`.
                    "advanced": True,
                },
            )
            _execute_claimed(
                conn,
                task_id=task_id,
                project=project,
                adapter_obj=adapter_obj,
                adapter_name=row["adapter"],
                brief=row["brief"],
                workspace=workspace,
                read_only=bool(options.get("read_only")),
                worktree=bool(options.get("worktree")),
                skip_verify=bool(options.get("skip_verify")),
                timeout=effective_timeout,
            )
            return task_id
        finally:
            concurrency.release(conn, scopes)
    finally:
        conn.close()


def _execute(
    conn,
    *,
    task_id: str,
    project,
    adapter_obj,
    adapter_name: str,
    brief: str,
    run_dir: str,
    workspace: str,
    read_only: bool,
    skip_verify: bool,
    timeout: int,
) -> None:
    """Steps ⑤-⑧: run the adapter, gate on forbidden paths, verify, then record.

    Raises AdapterError / VerifyError; always leaves the task row in a terminal
    state (or already recorded) before it does.
    """
    log_path = os.path.join(workspace, "logs", f"{task_id}.log")

    # Resolve the structured-result contract for THIS project: the project
    # setting wins, otherwise the package default. `None` means structured
    # output is disabled — that is recorded rather than done silently, so a
    # free-text result can always be explained after the fact.
    schema_path = registry.result_schema_path(project)
    if schema_path is None:
        storage.append_event(
            conn,
            task_id,
            "result_schema",
            {
                "enabled": False,
                "path": None,
                "note": "structured result disabled (result_schema = \"none\")",
            },
        )
    else:
        storage.append_event(
            conn, task_id, "result_schema", {"enabled": True, "path": schema_path}
        )

    # ⑤ run the agent CLI, teeing its output to `log_path` as it goes.
    #
    # Fingerprint the protected paths first. The git change list consulted below
    # cannot see inside `.git/` and omits ignored paths, so this snapshot is what
    # actually covers `forbidden_paths`.
    forbidden_before, forbidden_truncated = verify.snapshot_forbidden(
        run_dir, project.forbidden_paths
    )

    def _record_pgid(proc) -> None:
        """Persist the adapter's own group id the moment it exists.

        `_run_adapter` spawns with ``start_new_session=True``, so the child leads
        a brand-new session/process group and its pgid equals its pid. That is
        the only group that contains the adapter and its descendants without
        also containing this dispatcher or unrelated siblings — exactly what
        `cancel <id>` must signal after a restart. The row's `pid` stays this
        run process' ``os.getpid()`` (written before the adapter exists); the
        pgid cannot be known until ``Popen`` returns, so it is recorded here,
        immediately after the spawn and before we wait on the tree.
        """
        try:
            pgid = os.getpgid(proc.pid)
        except (ProcessLookupError, OSError):
            return
        storage.update_task(conn, task_id, pgid=pgid)

    try:
        exit_code, out, err = _run_adapter(
            adapter_obj,
            brief=brief,
            workdir=run_dir,
            log_path=log_path,
            schema_path=schema_path,
            read_only=read_only,
            on_spawn=_record_pgid,
        )
    except VerifyError as exc:
        if _task_cancelled(conn, task_id):
            # A concurrent `cancel` already recorded the terminal state; do not
            # overwrite it or append a contradictory event.
            return
        # timeout: `timeout` terminal state, exit code carries EXIT_VERIFY meaning.
        _finish_task(
            conn, task_id, status=STATUS_TIMEOUT, exit_code=EXIT_VERIFY, workdir=run_dir
        )
        storage.append_event(
            conn, task_id, "timeout", {"adapter": adapter_name, "detail": str(exc)}
        )
        raise
    except AdapterError as exc:
        if _task_cancelled(conn, task_id):
            return
        _finish_task(conn, task_id, status=STATUS_FAILED, workdir=run_dir)
        storage.append_event(
            conn, task_id, "failed", {"stage": "adapter", "reason": str(exc)}
        )
        raise

    # The adapter is gone. If a `cancel` landed while it was running (e.g. it
    # was signalled from another process), the row is already `cancelled`: stop
    # here so the pipeline cannot round a cancelled task up to done/failed.
    if _task_cancelled(conn, task_id):
        return

    # Snapshot the protected paths again here — immediately after the agent
    # exits, and BEFORE our own change detection runs. `git status` refreshes the
    # index and takes a lock file, so snapshotting after it would attribute our
    # own housekeeping to the agent: with a `.git/` rule that made every run fail.
    forbidden_after, _ = verify.snapshot_forbidden(run_dir, project.forbidden_paths)

    # ⑤ (cont.) parse the adapter's result. A parse failure is an adapter failure
    # (exit 70) — it must never be rounded up to success.
    result_path = getattr(adapter_obj, "result_path", None)
    result = None
    parse_error = None
    if exit_code == 0:
        try:
            result = adapter_obj.parse_result(
                exit_code=exit_code, stdout=out, stderr=err, result_path=result_path
            )
        except ResultParseError as exc:
            parse_error = exc

    if exit_code != 0 or result is None:
        reason = parse_error or f"agent CLI exited {exit_code}"
        _finish_task(
            conn,
            task_id,
            status=STATUS_FAILED,
            exit_code=exit_code,
            workdir=run_dir,
            result_path=result_path,
        )
        storage.append_event(
            conn,
            task_id,
            "failed",
            {"stage": "adapter", "exit_code": exit_code, "reason": str(reason)},
        )
        raise AdapterError(
            f"adapter '{adapter_name}' failed: {reason}",
            hint=f"see {log_path} for the full agent output",
        )

    storage.append_event(
        conn,
        task_id,
        "adapter",
        {
            "exit_code": exit_code,
            "degraded": bool(result.parse_degraded),
            "summary": result.summary,
        },
    )

    # ⑥ change + forbidden-path check, on the PROJECT workdir (or its worktree).
    changed = verify.changed_files(run_dir)
    files_changed = verify.detect_changes(run_dir)
    # Two signals, unioned: the git change list (cheap, good for tracked edits)
    # and the before/after snapshot of the protected paths themselves (the only
    # one that can see `.git/` and ignored paths).
    violations = sorted(
        set(verify.check_forbidden(run_dir, project.forbidden_paths, changed))
        | set(verify.diff_snapshots(forbidden_before, forbidden_after))
    )
    if violations:
        # A protected path was touched: fail outright, even though the adapter
        # reported success. The offending paths go into the audit stream.
        _finish_task(
            conn,
            task_id,
            status=STATUS_FAILED,
            exit_code=exit_code,
            files_changed=files_changed,
            workdir=run_dir,
            result_path=result_path,
        )
        storage.append_event(
            conn,
            task_id,
            "forbidden",
            {
                "paths": violations,
                "rules": list(project.forbidden_paths),
                # True when a protected tree was too large to walk fully, so the
                # guarantee for that rule was partial.
                "snapshot_truncated": forbidden_truncated,
            },
        )
        storage.append_event(
            conn, task_id, "failed", {"stage": "forbidden", "paths": violations}
        )
        raise VerifyError(
            f"forbidden path(s) changed: {', '.join(violations)}",
            hint="the task touched a path the registry protects",
        )

    # ⑦ acceptance, run in the PROJECT workdir — never the workspace. A run that
    # is skipped (read-only, --no-verify, or no configured command) is recorded
    # as SKIPPED, never as a pass.
    skip_reason = _skip_reason(read_only, skip_verify, project.verify)
    outcome = None
    if skip_reason is not None:
        verify_status = VERIFY_SKIPPED
        verify_cmd_field = VERIFY_SKIPPED
        verify_exit_field = None
        ran = False
        note = skip_reason
    else:
        outcome = verify.run_acceptance(
            run_dir, project.verify, timeout=timeout
        )
        ran = outcome.ran
        if not outcome.ran:
            verify_status = VERIFY_SKIPPED
            verify_cmd_field = VERIFY_SKIPPED
            verify_exit_field = None
        else:
            verify_status = "PASSED" if outcome.passed else "FAILED"
            verify_cmd_field = project.verify
            verify_exit_field = outcome.exit_code
        note = outcome.note

    storage.append_event(
        conn,
        task_id,
        "verify",
        {
            "status": verify_status,
            "ran": ran,
            "exit_code": verify_exit_field,
            "note": note,
            "output_tail": outcome.output_tail if outcome is not None else "",
        },
    )

    # ⑧ terminal row + event.
    if verify_status == "FAILED":
        _finish_task(
            conn,
            task_id,
            status=STATUS_FAILED,
            exit_code=exit_code,
            verify_cmd=verify_cmd_field,
            verify_exit=verify_exit_field,
            files_changed=files_changed,
            workdir=run_dir,
            result_path=result_path,
        )
        storage.append_event(
            conn,
            task_id,
            "failed",
            {
                "stage": "verify",
                "verify_exit": verify_exit_field,
                "note": note,
            },
        )
        raise VerifyError(
            f"acceptance command failed (exit {verify_exit_field})",
            hint=f"output: {outcome.output_tail}" if outcome and outcome.output_tail else None,
        )

    _finish_task(
        conn,
        task_id,
        status=STATUS_DONE,
        exit_code=exit_code,
        verify_cmd=verify_cmd_field,
        verify_exit=verify_exit_field,
        files_changed=files_changed,
        workdir=run_dir,
        result_path=result_path,
    )
    storage.append_event(
        conn,
        task_id,
        "done",
        {
            "verify": verify_status,
            "files_changed": files_changed,
            "summary": result.summary,
        },
    )


def _skip_reason(read_only: bool, skip_verify: bool, verify_cmd) -> Optional[str]:
    """Why acceptance is not being run, or None when it should run."""
    if read_only:
        return "read-only run: acceptance skipped"
    if skip_verify:
        return "--no-verify requested: acceptance skipped"
    if not verify_cmd:
        return "no acceptance command configured"
    return None


def _task_cancelled(conn, task_id: str) -> bool:
    """True when `cancel` has already recorded this task as terminal."""
    row = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return row is not None and row[0] == STATUS_CANCELLED


def _finish_task(
    conn,
    task_id: str,
    *,
    status: str,
    exit_code=None,
    verify_cmd=None,
    verify_exit=None,
    files_changed=None,
    workdir=None,
    result_path=None,
) -> None:
    """Patch the terminal columns of a task. Only non-None fields are written.

    A task that `cancel` already marked terminal is left alone: the in-flight
    dispatcher must never overwrite `cancelled` with a later done/failed state.
    """
    if _task_cancelled(conn, task_id):
        return
    fields = {"status": status, "finished_at": storage.now_iso()}
    if exit_code is not None:
        fields["exit_code"] = exit_code
    if verify_cmd is not None:
        fields["verify_cmd"] = verify_cmd
    if verify_exit is not None:
        fields["verify_exit"] = verify_exit
    if files_changed is not None:
        fields["files_changed"] = files_changed
    if workdir is not None:
        fields["workdir"] = workdir
    if result_path is not None:
        fields["result_path"] = result_path
    storage.update_task(conn, task_id, **fields)


# ---------------------------------------------------------------------------
# Adapter execution
# ---------------------------------------------------------------------------


def _terminate_tree(proc) -> None:
    """SIGTERM (then SIGKILL) only the process group this function started.

    `_run_adapter` spawns with `start_new_session=True`, so the child leads its
    own process group; signalling that group reaches the agent and its children
    but nothing else. If the group id ever equaled ours we fall back to
    signalling the child alone, so we can never take down our own process.
    """
    try:
        pgid = os.getpgid(proc.pid)
    except (ProcessLookupError, OSError):
        return

    own_group = os.getpgid(0)
    if pgid == own_group:
        # Should not happen with start_new_session; never risk our own group.
        try:
            proc.terminate()
        except (ProcessLookupError, OSError):
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except (ProcessLookupError, OSError):
                pass
        return

    try:
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, OSError):
        return
    try:
        proc.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, OSError):
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def _wait_group_gone(pgid: int, timeout: float) -> bool:
    """Poll a process group until it is empty, or `timeout` elapses.

    `os.killpg(pgid, 0)` is a pure liveness probe: it raises `ProcessLookupError`
    once no process is left in the group. We cannot `wait()` for a group we may
    not be the parent of, so polling is how the recorded-group path honours the
    same SIGTERM -> grace -> SIGKILL timing as `_terminate_tree`.
    """
    deadline = time.monotonic() + timeout
    while True:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return True
        except OSError:
            # EPERM etc.: the group still exists as far as we can tell.
            pass
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)


def _terminate_recorded_group(pgid) -> None:
    """SIGTERM -> 5s -> SIGKILL exactly the group recorded for a task.

    This is the after-a-restart counterpart of `_terminate_tree`: it takes the
    pgid persisted on the task row (the adapter's own new session — see
    `_execute._record_pgid`) instead of a live `Popen` handle. The discipline is
    identical — signal only that one group, never `pkill`, never a name/brief
    match — and the `pgid == our own group` guard is kept so this can never take
    down the caller. Where `_terminate_tree` falls back to signalling the single
    child it owns, this path has no child handle to fall back to, so it signals
    nothing rather than risk our own process group.
    """
    if pgid is None:
        return
    try:
        own_group = os.getpgid(0)
    except OSError:
        own_group = None
    if own_group is not None and pgid == own_group:
        return
    try:
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, OSError):
        return
    if _wait_group_gone(pgid, TERMINATE_GRACE_SECONDS):
        return
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, OSError):
        return
    _wait_group_gone(pgid, TERMINATE_GRACE_SECONDS)


#: Loopback hosts that must never be sent to a forward proxy: a local service
#: (e.g. a CC Switch endpoint on http://127.0.0.1:15721/v1) is not reachable
#: through a proxy.
_LOCALHOST_NO_PROXY = ("127.0.0.1", "localhost", "::1")

#: Proxy variables whose presence means the child could otherwise be routed.
_PROXY_ENV_NAMES = (
    "http_proxy", "https_proxy", "all_proxy",
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
)


def _ensure_localhost_no_proxy(env: dict) -> dict:
    """Make loopback hosts bypass any proxy, without clobbering the user's.

    Defence: when the parent routes through a proxy (any of http_proxy /
    https_proxy / all_proxy), a request to a local service must still go direct,
    or it is shipped off to the proxy and fails. `no_proxy` and `NO_PROXY` are
    extended with 127.0.0.1, localhost and ::1; existing entries are kept and
    merged — never overwritten — and no other proxy semantics are changed.
    """
    if not any(env.get(name) for name in _PROXY_ENV_NAMES):
        return env
    for name in ("no_proxy", "NO_PROXY"):
        entries = [
            item.strip() for item in (env.get(name) or "").split(",") if item.strip()
        ]
        seen = {item.lower() for item in entries}
        for host in _LOCALHOST_NO_PROXY:
            if host.lower() not in seen:
                entries.append(host)
                seen.add(host.lower())
        env[name] = ",".join(entries)
    return env


def _run_adapter(adapter_obj, *, brief: str, workdir: str, log_path: str,
                 schema_path: Optional[str] = None, read_only: bool = False,
                 on_spawn=None):
    """Spawn the agent CLI, tee output to `log_path`, return (exit_code, out, err).

    * argv is a list and the shell is never used.
    * stdout/stderr are streamed to ``log_path`` line by line as the child runs,
      so the board can watch progress instead of waiting for the process to exit.
    * ``stdin`` is ``/dev/null`` so an agent that reads input can never hang.
    * `adapter_obj.timeout` is enforced; on expiry the process group this call
      created is terminated (SIGTERM then SIGKILL) and a `VerifyError` is raised
      (exit code 71 semantics).
    * ``on_spawn(proc)`` (optional) runs immediately after the child exists and
      before we wait on it — the hook the dispatcher uses to persist the child's
      process-group id for a later ``cancel``.
    """
    try:
        argv = adapter_obj.build_command(
            brief=brief, workdir=workdir, schema_path=schema_path, read_only=read_only
        )
    except (ValueError, TypeError) as exc:
        raise AdapterError(
            f"adapter '{adapter_obj.name}': could not build a command: {exc}"
        )
    if not argv:
        raise AdapterError(f"adapter '{adapter_obj.name}': built an empty command")

    env = {**os.environ, **(adapter_obj.env or {})}
    env = _ensure_localhost_no_proxy(env)
    timeout = adapter_obj.timeout

    os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
    out_chunks = []
    err_chunks = []
    write_lock = threading.Lock()

    sink = open(log_path, "w", encoding="utf-8")
    try:
        try:
            proc = subprocess.Popen(
                argv,
                cwd=workdir,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env,
                start_new_session=True,
            )
        except OSError as exc:
            raise AdapterError(
                f"adapter '{adapter_obj.name}': could not start '{argv[0]}': {exc}"
            )

        if on_spawn is not None:
            # Record the identity before we block on the child, so a cancel from
            # another process can reach the tree even mid-run.
            on_spawn(proc)

        def pump(stream, chunks):
            try:
                for line in stream:
                    with write_lock:
                        sink.write(line)
                        sink.flush()
                    chunks.append(line)
            finally:
                try:
                    stream.close()
                except Exception:
                    pass

        readers = [
            threading.Thread(target=pump, args=(proc.stdout, out_chunks), daemon=True),
            threading.Thread(target=pump, args=(proc.stderr, err_chunks), daemon=True),
        ]
        for reader in readers:
            reader.start()

        timed_out = False
        try:
            exit_code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_tree(proc)
            exit_code = proc.wait()
        for reader in readers:
            reader.join()
    finally:
        sink.close()

    out = "".join(out_chunks)
    err = "".join(err_chunks)
    if timed_out:
        raise VerifyError(
            f"adapter '{adapter_obj.name}': timeout after {timeout}s "
            "(process tree terminated)",
            hint=f"see {log_path}",
        )
    return exit_code, out, err


# ---------------------------------------------------------------------------
# git worktrees
# ---------------------------------------------------------------------------


def _is_git_repo(path: str) -> bool:
    """Read-only probe: is `path` inside a git work tree?"""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=path,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def _worktree_target_path(repo_path: str, task_id: str) -> str:
    """The sibling directory a run's checkout lives in.

    The convention is ``<repo parent>/<repo name>-wt-<task id>`` -- BESIDE the
    repo, never inside it, so a kept checkout can never pollute the project's
    own ``git status``. It is never reused: a task id is unique, and if the exact
    name is somehow already taken (e.g. the same id run twice) a numeric suffix
    keeps the two runs from colliding.
    """
    repo_abs = os.path.abspath(repo_path)
    base = os.path.join(
        os.path.dirname(repo_abs), f"{os.path.basename(repo_abs)}-wt-{task_id}"
    )
    candidate = base
    n = 2
    while os.path.lexists(candidate):
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def _create_worktree(repo_path: str, task_id: str) -> str:
    """`git worktree add --detach` a fresh checkout; return its path.

    The checkout is created directly at the finally-visible path
    (:func:`_worktree_target_path`), so the ``worktree_created`` event, the kept
    location and the printed line all name the same directory.
    """
    path = _worktree_target_path(repo_path, task_id)
    proc = subprocess.run(
        ["git", "worktree", "add", "--detach", path],
        cwd=repo_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if proc.returncode != 0:
        shutil.rmtree(path, ignore_errors=True)
        raise UsageError(
            "could not create a git worktree for this project",
            hint=(proc.stdout or "").strip() or "git worktree add failed",
        )
    return path


def _worktree_change_count(path: str) -> int:
    """How many files ``git status --porcelain`` reports in a worktree.

    Read-only, and reuses the very probe `verify` uses for a task's
    ``files_changed`` field, so the count the message prints matches the audit.
    """
    return verify.detect_changes(path) or 0


def _remove_worktree(repo_path: str, path: str) -> Optional[str]:
    """Best-effort `git worktree remove`; returns an error string on failure."""
    error = None
    try:
        proc = subprocess.run(
            ["git", "worktree", "remove", "--force", path],
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if proc.returncode != 0:
            error = (proc.stdout or "").strip() or (
                f"git worktree remove exited {proc.returncode}"
            )
    except (OSError, subprocess.SubprocessError) as exc:
        error = str(exc)

    # The checkout dir always goes, even when git refused to unregister it.
    shutil.rmtree(path, ignore_errors=True)
    if error is not None:
        try:
            subprocess.run(
                ["git", "worktree", "prune"],
                cwd=repo_path,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.SubprocessError):
            pass
    return error


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


def verify_task(workspace: str, task_id: str) -> verify.VerifyOutcome:
    """Re-run acceptance for an existing task (`taskproof verify <id>`)."""
    conn = storage.connect(storage.db_path(workspace))
    try:
        storage.migrate(conn)
        row = storage.get_task(conn, task_id)
        if row is None:
            raise UsageError(f"no such task: {task_id}")
        project = registry.load(
            registry.workspace_registry_path(workspace)
        ).require(row["project"])
        workdir = row["workdir"] or project.path

        outcome = verify.run_acceptance(workdir, project.verify)
        status = VERIFY_SKIPPED if not outcome.ran else (
            "PASSED" if outcome.passed else "FAILED"
        )
        fields = {"verify_cmd": project.verify if outcome.ran else VERIFY_SKIPPED}
        if outcome.exit_code is not None:
            fields["verify_exit"] = outcome.exit_code
        if outcome.files_changed is not None:
            fields["files_changed"] = outcome.files_changed
        storage.update_task(conn, task_id, **fields)
        storage.append_event(
            conn,
            task_id,
            "verify",
            {
                "status": status,
                "ran": outcome.ran,
                "exit_code": outcome.exit_code,
                "note": outcome.note,
                "violations": outcome.violations,
            },
        )
        return outcome
    finally:
        conn.close()


def task_detail(workspace: str, task_id: str) -> dict:
    """Task row plus its (JSON-decoded) event stream, for `show` and the board."""
    conn = storage.connect(storage.db_path(workspace))
    try:
        storage.migrate(conn)
        row = storage.get_task(conn, task_id)
        task = dict(row) if row is not None else None

        events = []
        for event in storage.list_events(conn, task_id):
            item = dict(event)
            raw = item.get("payload")
            if raw is not None:
                try:
                    item["payload"] = json.loads(raw)
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
            events.append(item)
        return {"task": task, "events": events}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Control: cancel / remove / queue_seq
# ---------------------------------------------------------------------------


def cancel_task(workspace: str, task_id: str) -> dict:
    """Stop a task and record the terminal state `cancelled`.

    * `running` / `verifying`: signal the recorded process group (SIGTERM, then
      SIGKILL after a grace period). `queued`: nothing to kill, just record.
    * The workdir is NEVER touched — matching "a failed dispatch does not roll
      back its workspace".
    * A task already in a terminal state is a readable error, never a silent
      no-op.

    Returns the updated task row.
    """
    conn = storage.connect(storage.db_path(workspace))
    try:
        storage.migrate(conn)
        row = storage.get_task(conn, task_id)
        if row is None:
            raise TaskNotFoundError(f"no such task: {task_id}")
        status = row["status"]
        if status in TERMINAL_STATUSES:
            raise TaskStateError(
                f"task {task_id} is already {status}; nothing to cancel"
            )
        if status not in (STATUS_QUEUED, STATUS_RUNNING, STATUS_VERIFYING):
            raise TaskStateError(
                f"task {task_id} cannot be cancelled from state {status}"
            )

        pgid = row["pgid"]
        pid = row["pid"]
        # Record the terminal state BEFORE signalling. That way the in-flight
        # dispatcher observes `cancelled` (via `_task_cancelled`) before its
        # adapter dies, so it returns without appending a contradictory
        # `failed`/`timeout` event for a task the user deliberately stopped.
        storage.update_task(
            conn,
            task_id,
            status=STATUS_CANCELLED,
            finished_at=storage.now_iso(),
        )
        storage.append_event(
            conn,
            task_id,
            "cancelled",
            {"pid": pid, "pgid": pgid, "was": status},
        )
        if status in (STATUS_RUNNING, STATUS_VERIFYING) and pgid is not None:
            # Only the group the adapter created; unrelated processes are safe.
            _terminate_recorded_group(pgid)
        return dict(storage.get_task(conn, task_id))
    finally:
        conn.close()


def _kept_worktrees(conn, task_id: str):
    """Every kept-worktree payload for a task, newest first.

    A run that left changes behind appends one ``worktree`` event carrying its
    ``path`` and ``changed`` count; `rm` reads those back (before deleting the
    events) so it can clean up the directories too.
    """
    found = []
    for row in conn.execute(
        "SELECT payload FROM events WHERE task_id = ? AND event = 'worktree' "
        "ORDER BY id DESC",
        (task_id,),
    ):
        text = row[0]
        try:
            payload = json.loads(text) if text else {}
        except (json.JSONDecodeError, TypeError, ValueError):
            payload = {}
        if isinstance(payload, dict) and payload.get("path"):
            found.append(payload)
    return found


def _discard_kept_worktree(payload: dict) -> None:
    """Delete a worktree a run kept, as `rm <id>` requires.

    The tradeoff: `rm` owns the whole task, so the unrecoverable work it kept on
    disk goes with it. Unregister via git when the source repo is known (best
    effort), then remove the directory either way.
    """
    path = payload.get("path")
    if not path:
        return
    repo = payload.get("repo")
    if repo and os.path.isdir(repo):
        _remove_worktree(repo, path)
    else:
        shutil.rmtree(path, ignore_errors=True)


def remove_task(workspace: str, task_id: str) -> str:
    """Delete a terminal task's row, its `events` rows, and any kept worktree.

    Non-terminal tasks are refused with a hint to cancel first. The append-only
    JSONL audit stream is intentionally left in place (see `storage.delete_task`).
    Returns the removed id.
    """
    conn = storage.connect(storage.db_path(workspace))
    try:
        storage.migrate(conn)
        row = storage.get_task(conn, task_id)
        if row is None:
            raise TaskNotFoundError(f"no such task: {task_id}")
        if row["status"] not in TERMINAL_STATUSES:
            raise TaskStateError(
                f"task {task_id} is {row['status']}; cancel it before removing",
                hint=f"taskproof cancel {task_id}",
            )
        # A kept worktree is part of the task `rm` is discarding; snapshot the
        # paths before `delete_task` wipes the events that name them.
        kept_worktrees = _kept_worktrees(conn, task_id)
        storage.delete_task(conn, task_id)
        for payload in kept_worktrees:
            _discard_kept_worktree(payload)
        return task_id
    finally:
        conn.close()


def set_queue_seq(workspace: str, task_id: str, queue_seq) -> dict:
    """Set the explicit queue order of a task that is still `queued`.

    Field-level maintenance, not a fourth action: same discipline as a registry
    PATCH. Editing the order of a task that already left the queue is refused so
    a stale UI cannot reorder history. Returns the updated task row.
    """
    conn = storage.connect(storage.db_path(workspace))
    try:
        storage.migrate(conn)
        row = storage.get_task(conn, task_id)
        if row is None:
            raise TaskNotFoundError(f"no such task: {task_id}")
        if row["status"] != STATUS_QUEUED:
            raise TaskStateError(
                f"task {task_id} is {row['status']}; "
                "queue_seq is only editable while queued"
            )
        storage.update_task(conn, task_id, queue_seq=queue_seq)
        storage.append_event(conn, task_id, "queue_seq", {"queue_seq": queue_seq})
        return dict(storage.get_task(conn, task_id))
    finally:
        conn.close()


def summary_counts(workspace: str, conn) -> dict:
    """Counts per status — the one query the dashboard leans on.

    Every known status is present (0 when it has no rows) so the board can draw
    a stable set of columns without special-casing a missing bucket.
    """
    counts = {status: 0 for status in _ALL_STATUSES}
    for row in conn.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status"):
        counts[row[0]] = int(row[1])
    return counts
