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
from .errors import EXIT_VERIFY, AdapterError, ConcurrencyError, UsageError, VerifyError
from .models import (
    STATUS_BLOCKED,
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_FAILED,
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


def _cap_aware_refusal(exc: ConcurrencyError, setting) -> ConcurrencyError:
    """Point a GLOBAL-cap refusal at its value, its source, and its ways out.

    A same-group refusal is returned untouched: the honest hint there stays
    "wait your turn". ``concurrency`` already phrases the two cases distinctly
    ("global cap reached" vs "group '<g>' is busy") — the same signal the REST
    layer turns into its ``reason`` field — so the reroute needs no change to
    the concurrency module, and both the CLI ``run`` and the REST create paths
    get it because both go through this module.

    For a global-cap refusal we append the *effective* cap and where it came
    from (card 42: ``上限 3，来源：自动探测 14 核 ÷ 4``) and name the exits —
    ``run --cap N`` / ``taskproof config --concurrency N`` — so the operator is
    never told "no" without a next step.
    """
    if str(exc).startswith("global cap"):
        return ConcurrencyError(
            f"{exc}（上限 {setting.value}，来源：{concurrency.source_label(setting)}）",
            hint=(
                "临时抬高（run --cap N）／"
                "改配置（taskproof config --concurrency N）"
            ),
        )
    return exc


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
    rerun_of: Optional[str] = None,
    cap: Optional[int] = None,
) -> str:
    """Run one task end to end and return its id.

    ``rerun_of`` names the terminal card this run is a fresh copy of; when set,
    the new card gets a ``rerun`` event carrying ``rerun_of`` and the old card
    gets one carrying ``rerun_as``, both written before the adapter runs so the
    link survives even a failed rerun. ``taskproof rerun`` is the only caller.

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

    # ① resolve the taskgroup. A missing/unknown key is a RegistryError (exit 2).
    reg = registry.load(registry.workspace_registry_path(workspace))
    taskgroup = reg.require(project_key)

    effective_timeout = timeout if timeout is not None else reg.timeout

    # The effective global cap for this dispatch, with its source (card 42). A
    # `--cap N` is a one-off override: it rides the event stream but is never
    # written to the registry.
    setting = concurrency.resolve(reg.defaults, cap)

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

        # ③ claim the group slot + a slot under the global cap. A refusal is a
        # ConcurrencyError (exit 75) and no task row is written.
        ttl = max(1, int(effective_timeout)) + 60
        try:
            scopes = concurrency.acquire(
                conn, task_id, taskgroup.group, cap=setting.value, ttl=ttl
            )
        except ConcurrencyError as exc:
            raise _cap_aware_refusal(exc, setting) from None

        # ⑨ Whatever happens below — success, a recorded failure, or a raised
        # error — the exact credential from ③ is released. `release` verifies the
        # ownership token, so this can only ever drop our own claim.
        try:
            # ④ the task row + the `started` event.
            task = Task(
                id=task_id,
                project=taskgroup.id,
                group=taskgroup.group,
                brief=brief,
                status=STATUS_RUNNING,
                adapter=adapter,
                model=model,
                reasoning=reasoning,
                pid=os.getpid(),
                created_at=storage.now_iso(),
                started_at=storage.now_iso(),
            )
            storage.insert_task(conn, task)
            storage.append_event(
                conn,
                task_id,
                "started",
                {
                    "project": taskgroup.id,
                    "group": taskgroup.group,
                    "adapter": adapter,
                    "read_only": read_only,
                    "worktree": worktree,
                    "skip_verify": skip_verify,
                    # The hard timeout this run enforces. It has no column, so it
                    # rides in the event: `rerun` reads it back to reuse the same
                    # flag (See `_run_options`).
                    "timeout": effective_timeout,
                    # The effective global cap *and its source* (card 42), so the
                    # event stream can explain why a card was admitted — e.g. a
                    # one-off `--cap 5` that let a fourth card run.
                    "cap": setting.value,
                    "cap_source": setting.source,
                },
            )

            if rerun_of:
                _link_rerun(conn, task_id, rerun_of)

            _execute_claimed(
                conn,
                task_id=task_id,
                taskgroup=taskgroup,
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
    taskgroup,
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

    The row is already `running` and holds a slot. Owns the whole worktree
    lifecycle (create -> execute -> keep-if-changed / remove-if-clean) and
    raises whatever `_execute` raises; it never touches the concurrency claim,
    which stays the caller's.
    """
    worktree_path = None
    run_dir = taskgroup.path
    try:
        # A lane that declares `workspace = "worktree"` wins over the one-time
        # `--worktree` flag: it already IS the long-lived checkout, so creating a
        # second one-off worktree would be wrong. The workspace is created or
        # reused here -- the first moment a card actually has a slot and is about
        # to run, never merely by editing the registry.
        if taskgroup.workspace == "worktree":
            _, run_dir = _ensure_lane_workspace(
                conn, task_id, taskgroup, worktree_flag=worktree
            )
        elif worktree:
            if not _is_git_repo(taskgroup.path):
                raise UsageError(
                    f"--worktree needs a git repository, but {taskgroup.path} "
                    "is not one",
                    hint="run without --worktree, or point the registry at a git checkout",
                )
            worktree_path = _create_worktree(taskgroup.path, task_id)
            run_dir = worktree_path
            storage.append_event(conn, task_id, "worktree_created", {"path": run_dir})

        # Land the run directory on the row the moment it is final -- after a
        # worktree has resolved its path, before the adapter spawns. Without it
        # the row carried NULL workdir for the whole run and the live
        # `files_changed_live` probe had nothing to look at.
        storage.update_task(conn, task_id, workdir=run_dir)

        _execute(
            conn,
            task_id=task_id,
            taskgroup=taskgroup,
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
                        "repo": taskgroup.path,
                    },
                )
            else:
                error = _remove_worktree(taskgroup.path, worktree_path)
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


def _link_rerun(conn, new_id: str, old_id: str) -> None:
    """Record the two-way link between a rerun and the card it was copied from.

    Written through `storage.append_event`, so it lands in BOTH the `events`
    table and the JSONL audit stream — `taskproof log <id> --json` reads the
    stream, which is why the link has to be an event and not a column. The new
    card carries ``rerun_of``, the old card carries ``rerun_as``.
    """
    storage.append_event(conn, new_id, "rerun", {"rerun_of": old_id})
    storage.append_event(conn, old_id, "rerun", {"rerun_as": new_id})


def _run_options(conn, task_id: str) -> dict:
    """Recover the run flags a task carried, for `rerun` to reuse.

    A card born running records read_only / worktree / skip_verify / timeout on
    its `started` event. The events are read oldest-first and merged, so the
    newest value of each key wins.

    A flag missing from every event is simply absent; `rerun` then applies the
    documented default (read_only / worktree / skip_verify false; timeout =
    the registry timeout). A row written by an older build that recorded no
    flags yields `{}` and reruns with those same defaults.
    """
    options: dict = {}
    rows = conn.execute(
        "SELECT payload FROM events WHERE task_id = ? "
        "AND event = 'started' ORDER BY id ASC",
        (task_id,),
    ).fetchall()
    for row in rows:
        text = row[0]
        try:
            payload = json.loads(text) if text else {}
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        for key in ("read_only", "worktree", "skip_verify", "timeout"):
            if payload.get(key) is not None:
                options[key] = payload[key]
    return options



def _execute(
    conn,
    *,
    task_id: str,
    taskgroup,
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

    # Resolve the structured-result contract for THIS taskgroup: the taskgroup
    # setting wins, otherwise the package default. `None` means structured
    # output is disabled — that is recorded rather than done silently, so a
    # free-text result can always be explained after the fact.
    schema_path = registry.result_schema_path(taskgroup)
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
    # Snapshot both sides of the run before launching the adapter. The git
    # change list is naturally a current-state snapshot, but the gate needs a
    # difference: pre-existing dirty/untracked paths are not the adapter's
    # work. The protected-path snapshots remain the backstop for ignored paths
    # and `.git/`.
    git_rules = []
    file_rules = []
    presence_rules = []
    for raw in taskgroup.forbidden_paths or []:
        # Keep the historical untyped `.git/` spelling working: it has always
        # meant the state probe since card 30. An explicit `file:.git/` opts
        # back into the file fingerprint signal.
        if verify.is_git_forbidden_rule(run_dir, raw):
            git_rules.append(raw)
            continue
        rule = verify.parse_forbidden_rule(raw)
        if rule is None:
            continue
        if rule.kind == "git":
            git_rules.append(raw)
        elif rule.kind == "presence":
            presence_rules.append(rule)
        else:
            file_rules.append(rule)

    forbidden_before, file_before_truncated = verify.snapshot_forbidden(
        run_dir, [rule.path for rule in file_rules]
    )
    presence_before, presence_before_truncated = verify.snapshot_forbidden(
        run_dir, [rule.path for rule in presence_rules]
    )
    git_state_before = verify.git_state_snapshot(run_dir) if git_rules else {}
    changed_before = verify.changed_files_snapshot(run_dir)

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
    forbidden_after, file_after_truncated = verify.snapshot_forbidden(
        run_dir, [rule.path for rule in file_rules]
    )
    presence_after, presence_after_truncated = verify.snapshot_forbidden(
        run_dir, [rule.path for rule in presence_rules]
    )
    # Take the git-state probe before our own `git status` snapshots: that call
    # can refresh `.git/index`, which a state-only `.git/` rule must not read as
    # the agent's doing (same reason the fingerprint snapshot runs first).
    git_state_after = verify.git_state_snapshot(run_dir) if git_rules else {}
    changed_after = verify.changed_files_snapshot(run_dir)
    forbidden_truncated = (
        file_before_truncated
        or file_after_truncated
        or presence_before_truncated
        or presence_after_truncated
    )

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
    changed = verify.diff_changed_files(changed_before, changed_after)
    files_changed = verify.detect_changes(run_dir)
    # Three independent signals:
    #   file       -> git status difference + size:mtime_ns fingerprints
    #   presence   -> before/after file-set membership only
    #   git-state  -> HEAD/refs/stash snapshot
    file_snapshot_changes = verify.diff_snapshots(
        forbidden_before, forbidden_after
    )
    presence_changes = verify.diff_presence_snapshots(
        presence_before, presence_after
    )
    git_state_changes = (
        verify.diff_snapshots(git_state_before, git_state_after) if git_rules else []
    )

    violations = []
    if git_state_changes:
        for raw in git_rules:
            label = ".git" if verify.is_git_forbidden_rule(run_dir, raw) else str(raw)
            violations.append(
                {"rule": label, "kind": "git-state", "changed": git_state_changes}
            )
    for rule in file_rules:
        rule_paths = sorted(
            set(verify.check_forbidden(run_dir, [rule.path], changed))
            | set(
                verify.check_forbidden(
                    run_dir, [rule.path], file_snapshot_changes
                )
            )
        )
        if rule_paths:
            violations.append(
                {"rule": rule.raw, "kind": "file", "paths": rule_paths}
            )
    for rule in presence_rules:
        rule_paths = verify.check_forbidden(
            run_dir, [rule.path], presence_changes
        )
        if rule_paths:
            violations.append(
                {"rule": rule.raw, "kind": "presence", "paths": rule_paths}
            )

    violation_paths = sorted(
        {
            path
            for entry in violations
            for path in (entry.get("changed") or entry.get("paths") or [])
        }
    )
    if violations:
        # A protected path was touched. This is a fact about the run, not a
        # verdict that the work is bad — so record it and DO NOT short-circuit.
        # Acceptance still runs below (⑦) and a human decides in layer 3
        # (`accept`), not this pipeline. The offending paths go into the audit
        # stream here, untouched, exactly as before.
        storage.append_event(
            conn,
            task_id,
            "forbidden",
            {
                "violations": violations,
                # Flat, backwards-compatible list for older boards/callers.
                "paths": violation_paths,
                "rules": list(taskgroup.forbidden_paths),
                # True when a protected tree was too large to walk fully, so the
                # guarantee for that rule was partial.
                "snapshot_truncated": forbidden_truncated,
            },
        )

    # ⑦ acceptance, run in the PROJECT workdir — never the workspace. A run that
    # is skipped (read-only, --no-verify, or no configured command) is recorded
    # as SKIPPED, never as a pass.
    skip_reason = _skip_reason(read_only, skip_verify, taskgroup.verify)
    outcome = None
    if skip_reason is not None:
        verify_status = VERIFY_SKIPPED
        verify_cmd_field = VERIFY_SKIPPED
        verify_exit_field = None
        ran = False
        note = skip_reason
    else:
        # ⑦a Flip the card to `verifying` for the whole acceptance window, before
        # the command starts. Acceptance can run for seconds to minutes and the
        # phase has to be visible while it does; writing it before
        # `run_acceptance` also means a spawn failure or a hung check is still
        # recorded as `verifying` rather than a stale `running`.
        storage.update_task(conn, task_id, status=STATUS_VERIFYING)
        storage.append_event(
            conn, task_id, "verifying", {"command": taskgroup.verify}
        )
        outcome = verify.run_acceptance(
            run_dir, taskgroup.verify, timeout=timeout
        )
        ran = outcome.ran
        if not outcome.ran:
            verify_status = VERIFY_SKIPPED
            verify_cmd_field = VERIFY_SKIPPED
            verify_exit_field = None
        else:
            verify_status = "PASSED" if outcome.passed else "FAILED"
            verify_cmd_field = taskgroup.verify
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

    # ⑧ terminal row + event. Two *facts* may be in play — a protected path
    # moved, and/or acceptance failed — and the ledger must carry both, so the
    # rule is: a violation outranks a red acceptance (a human reviews the
    # boundary breach), a red acceptance is a plain `failed`, and a clean green
    # run is `done`. Every branch has already written the `verify` event above,
    # so whichever terminal we pick here, the acceptance result is not lost.
    common = dict(
        exit_code=exit_code,
        verify_cmd=verify_cmd_field,
        verify_exit=verify_exit_field,
        files_changed=files_changed,
        workdir=run_dir,
        result_path=result_path,
    )

    if violations:
        # A protected path was touched: `blocked` (= human review), NOT a
        # failure of the work. The exit code stays 71 (VerifyError, below) even
        # though the terminal state is blocked — "what the task is recorded as"
        # and "how this command ended" are deliberately different values.
        # Layer 3's `accept <id>` is what clears a blocked card; this pipeline
        # never auto-promotes it to `done`, even when acceptance passed.
        _finish_task(conn, task_id, status=STATUS_BLOCKED, **common)
        storage.append_event(
            conn,
            task_id,
            "blocked",
            {
                "stage": "forbidden",
                "violations": violations,
                "paths": violation_paths,
                # Both facts survive in the ledger: the breach and the verdict.
                "verify": verify_status,
                "verify_exit": verify_exit_field,
            },
        )
        raise VerifyError(
            f"forbidden path(s) changed: {', '.join(violation_paths)}",
            hint="the task touched a path the registry protects",
        )

    if verify_status == "FAILED":
        _finish_task(conn, task_id, status=STATUS_FAILED, **common)
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

    _finish_task(conn, task_id, status=STATUS_DONE, **common)
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
# Taskgroup workspaces
#
# A lane may declare `workspace = "worktree"`: instead of running in the main
# checkout, taskproof lazily creates ONE long-lived git worktree beside the
# repo and reuses it for every card on that lane. It is never removed
# automatically -- `taskproof workspace-rm <lane>` is the only way out. This is
# deliberately a per-lane opt-in; the default (`workspace = "none"`) keeps the
# historical in-place behaviour.
# ---------------------------------------------------------------------------

#: Build file -> dependency directory to symlink from the main checkout into a
#: lane workspace. Mirrors `registry.infer_verify`: a short, opinionated list,
#: not a general-purpose detector. Python virtual environments are deliberately
#: NOT here: `pyvenv.cfg` and the console-script shebangs under `bin/` record
#: absolute paths, so a symlinked venv would resolve back to the main tree (or
#: break outright) instead of isolating the run.
_DEPENDENCY_LINKS = (
    ("package.json", "node_modules"),
    ("Cargo.toml", "target"),
)


def _git_toplevel(path: str) -> Optional[str]:
    """Absolute git repository root containing ``path``, or None.

    Read-only probe. A ``path`` that is not inside a work tree (or where git is
    unavailable) yields None rather than raising, so callers can decide.
    """
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=path,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    root = proc.stdout.strip()
    return root or None


def _git_worktree_paths(repo_root: str) -> list:
    """Every checkout path git has registered for ``repo_root`` (realpath'd)."""
    try:
        proc = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []
    paths = []
    for line in proc.stdout.splitlines():
        if line.startswith("worktree "):
            paths.append(os.path.realpath(line[len("worktree "):].strip()))
    return paths


def _lane_workspace_path(lane, repo_root: str) -> str:
    """The sibling directory a lane's long-lived workspace lives in.

    ``<repo root name>-ws-<lane id>`` BESIDE the repo root, never inside it, so
    a workspace can never pollute the main checkout's ``git status``.
    """
    repo_abs = os.path.abspath(repo_root)
    return os.path.join(
        os.path.dirname(repo_abs), f"{os.path.basename(repo_abs)}-ws-{lane.id}"
    )


def _lane_run_dir(lane, repo_root: str, workspace_root: str) -> str:
    """Where inside the workspace this lane's cards run.

    A ``path`` under the repo root maps to the same relative location inside the
    workspace; a ``path`` that IS the repo root (or outside it, e.g. its own
    independent clone) runs at the workspace root.
    """
    repo = os.path.realpath(repo_root)
    lane_path = os.path.realpath(lane.path)
    if lane_path == repo:
        return workspace_root
    try:
        common = os.path.commonpath([repo, lane_path])
    except ValueError:  # different drives on Windows
        return workspace_root
    if common == repo:
        rel = os.path.relpath(lane_path, repo)
        if rel and rel != ".":
            return os.path.join(workspace_root, rel)
    return workspace_root


def _probe_dependency_links(lane, repo_root: Optional[str] = None) -> list:
    """Dependency directories to symlink in, inferred from build files.

    Detection mirrors ``registry.infer_verify`` (a marker file in the lane path),
    but the returned path is workspace-root-relative -- the same base an explicit
    ``link`` uses -- so a subdirectory lane links ``<lane rel>/node_modules``
    rather than the repository root's copy.
    """
    prefix = ""
    if repo_root:
        rel = os.path.relpath(os.path.realpath(lane.path), os.path.realpath(repo_root))
        if rel not in (".", ""):
            prefix = rel
    found = []
    for marker, link in _DEPENDENCY_LINKS:
        if os.path.isfile(os.path.join(lane.path, marker)):
            found.append(os.path.join(prefix, link) if prefix else link)
    return found


def _lane_links(lane, repo_root: Optional[str] = None) -> list:
    """The relative paths to symlink from the main tree into the workspace.

    An explicit ``link`` wins; otherwise the build-file probe supplies the
    defaults (``package.json`` -> ``node_modules``, ``Cargo.toml`` -> ``target``).
    """
    if lane.link:
        return list(lane.link)
    return _probe_dependency_links(lane, repo_root)


def _ensure_links(repo_root: str, workspace_root: str, links) -> list:
    """Idempotently symlink ``links`` from the main tree into the workspace.

    Each target is ``<workspace>/<rel>`` pointing at ``<repo root>/<rel>`` --
    the main checkout's copy, so dependencies are shared rather than reinstalled.
    An existing target (symlink or real directory) is left untouched. Returns the
    links this call actually created; no package manager is ever invoked.
    """
    created = []
    for rel in links:
        target = os.path.join(workspace_root, rel)
        if os.path.lexists(target):
            continue
        parent = os.path.dirname(target)
        if parent:
            os.makedirs(parent, exist_ok=True)
        os.symlink(os.path.join(repo_root, rel), target)
        created.append(rel)
    return created


def _worktree_add(repo_root: str, path: str, lane) -> None:
    """``git worktree add --detach`` a fresh, long-lived lane workspace."""
    proc = subprocess.run(
        ["git", "worktree", "add", "--detach", path],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if proc.returncode != 0:
        shutil.rmtree(path, ignore_errors=True)
        raise UsageError(
            f"could not create a git worktree for lane '{lane.id}'",
            hint=(proc.stdout or "").strip()
            or "git worktree add failed (is the repo clean?)",
        )


def _ensure_lane_workspace(conn, task_id: str, lane, *, worktree_flag: bool = False):
    """Create-or-reuse ``lane``'s long-lived workspace; return (root, run_dir).

    Called only once a card actually has a slot and is about to run, so simply
    editing the registry never builds anything. A workspace is created once and
    reused forever after; a directory that exists but is not a worktree of the
    same repo is a hard error with the `workspace-rm` remedy. ``worktree_flag``
    is the one-time ``--worktree`` argument: when set it is ignored, because the
    lane workspace already is the long-lived checkout.
    """
    if not _is_git_repo(lane.path):
        raise UsageError(
            f"workspace = \"worktree\" needs a git repository, but {lane.path} "
            "is not one",
            hint='set workspace = "none" for this lane, or point it at a git checkout',
        )
    repo_root = _git_toplevel(lane.path)
    if not repo_root:
        raise UsageError(
            f"could not find a git repository root for lane '{lane.id}' "
            f"(path {lane.path})",
        )
    repo_root = os.path.realpath(repo_root)
    workspace_root = _lane_workspace_path(lane, repo_root)

    created = False
    if os.path.lexists(workspace_root):
        if os.path.realpath(workspace_root) not in _git_worktree_paths(repo_root):
            raise UsageError(
                f"{workspace_root} already exists but is not a worktree of "
                f"{repo_root}",
                hint=f"taskproof workspace-rm {lane.id}",
            )
    else:
        _worktree_add(repo_root, workspace_root, lane)
        created = True

    links = _ensure_links(repo_root, workspace_root, _lane_links(lane, repo_root))
    run_dir = _lane_run_dir(lane, repo_root, workspace_root)

    payload = {"path": workspace_root, "repo": repo_root, "links": links}
    if worktree_flag:
        payload["worktree_flag_ignored"] = True
        payload["note"] = (
            "using the lane workspace; --worktree is ignored while "
            'workspace = "worktree"'
        )
    if created:
        storage.append_event(conn, task_id, "workspace_created", payload)
    else:
        payload["reused"] = True
        storage.append_event(conn, task_id, "workspace", payload)
    return workspace_root, run_dir


def _worktree_changes_list(path: str, *, links=()) -> list:
    """``git status --porcelain`` lines for a workspace (empty on any failure).

    ``links`` are the dependency symlinks taskproof itself created; they are
    excluded so a freshly-built workspace counts as clean instead of being
    flagged as dirty (an untracked ``node_modules`` symlink in a repo that does
    not gitignore it is taskproof's plumbing, not the adapter's work).

    ``--untracked-files=all`` is essential, not cosmetic: by default git
    collapses a wholly-untracked directory to ``?? desktop/``, which would hide
    a link like ``desktop/node_modules`` behind its parent and defeat the
    exclusion (and equally hide the adapter's own new files).
    """
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=path,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []
    excluded = [item.rstrip("/") for item in links if item]
    result = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        candidate = line[3:].strip().strip('"') if len(line) > 3 else ""
        if any(
            candidate == item or candidate.startswith(item + "/")
            for item in excluded
        ):
            continue
        result.append(line)
    return result


def _unmerged_commits(path: str, repo_root: Optional[str] = None) -> list:
    """Commits in a workspace that the main checkout has not merged.

    A lane workspace is created ``--detach``, so any commit the adapter makes
    lives off-branch: exactly the "not merged anywhere" work an operator must be
    warned about before deleting. The exclusion base is the source repo's HEAD,
    so a clean, freshly-checked-out workspace lists none while a commit the
    adapter made (even on its own branch) is listed. ``--not --all`` cannot be
    used: git's ``--all`` includes HEAD itself, which would hide every commit.
    """
    args = ["git", "log", "--oneline", "--no-decorate", "HEAD"]
    base = None
    if repo_root:
        try:
            probe = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            if probe.returncode == 0 and probe.stdout.strip():
                base = probe.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            base = None
    if base:
        args += ["--not", base]
    else:
        args += ["--not", "--branches", "--tags", "--remotes"]
    try:
        proc = subprocess.run(
            args,
            cwd=path,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []
    return [line for line in proc.stdout.splitlines() if line.strip()]


def _lane_workspace_status(lane) -> dict:
    """Read-only evidence about one lane's long-lived workspace."""
    repo_root = _git_toplevel(lane.path) if os.path.isdir(lane.path) else None
    repo_root = os.path.realpath(repo_root) if repo_root else None
    ws_path = _lane_workspace_path(lane, repo_root) if repo_root else None
    exists = bool(ws_path) and os.path.isdir(ws_path)
    links = _lane_links(lane, repo_root)
    changed_files = _worktree_changes_list(ws_path, links=links) if exists else []
    unmerged = _unmerged_commits(ws_path, repo_root) if exists else []
    return {
        "id": lane.id,
        "project": lane.project,
        "path": lane.path,
        "repo": repo_root,
        "workspace": ws_path,
        "exists": exists,
        "changed_files": changed_files,
        "changed": len(changed_files),
        "unmerged_commits": unmerged,
        "unmerged": len(unmerged),
        "links": links,
    }


def lane_workspace_status(workspace: str, lane_key: str) -> dict:
    """Status of one lane's long-lived workspace (`taskproof workspace-rm`)."""
    reg = registry.load(registry.workspace_registry_path(workspace))
    return _lane_workspace_status(reg.require(lane_key))


def list_workspaces(workspace: str) -> list:
    """Every lane that declares ``workspace = "worktree"``, with its status."""
    reg = registry.load(registry.workspace_registry_path(workspace))
    return [
        _lane_workspace_status(lane)
        for lane in reg.taskgroups
        if lane.workspace == "worktree"
    ]


def remove_workspace(workspace: str, lane_key: str, *, force: bool = False) -> dict:
    """Delete a lane's long-lived workspace, refusing when it holds work.

    Uncommitted changes or commits that exist on no ref make this refuse unless
    ``force`` is set; the refusal names the files/commits so nothing is deleted
    blind. Either way the git worktree is unregistered first
    (``git worktree remove --force``) with a directory fallback, and a
    ``workspace_removed`` event records the outcome.
    """
    reg = registry.load(registry.workspace_registry_path(workspace))
    lane = reg.require(lane_key)
    if lane.workspace != "worktree":
        raise UsageError(
            f"lane '{lane.id}' does not declare a workspace "
            '(workspace = "worktree")',
            hint="nothing to remove; see `taskproof workspaces`",
        )
    repo_root = _git_toplevel(lane.path) if os.path.isdir(lane.path) else None
    if not repo_root:
        raise UsageError(
            f"lane '{lane.id}' path {lane.path} is not a git repository",
        )
    repo_root = os.path.realpath(repo_root)
    ws_path = _lane_workspace_path(lane, repo_root)

    if not os.path.lexists(ws_path):
        return {
            "path": ws_path,
            "repo": repo_root,
            "removed": False,
            "forced": False,
            "changed_files": [],
            "unmerged_commits": [],
        }

    changed = _worktree_changes_list(ws_path, links=_lane_links(lane, repo_root))
    unmerged = _unmerged_commits(ws_path, repo_root)
    dirty = bool(changed or unmerged)
    if dirty and not force:
        detail = "; ".join(
            part
            for part in (
                "uncommitted: " + ", ".join(changed) if changed else "",
                "unmerged: " + ", ".join(unmerged) if unmerged else "",
            )
            if part
        )
        raise UsageError(
            f"workspace {ws_path} still holds work ({detail}); refusing to "
            "remove",
            hint="re-run with --force to delete it anyway",
        )

    error = _remove_worktree(repo_root, ws_path)
    result = {
        "path": ws_path,
        "repo": repo_root,
        "removed": True,
        "forced": bool(force and dirty),
        "changed_files": changed,
        "unmerged_commits": unmerged,
    }
    if error:
        result["error"] = error

    conn = storage.connect(storage.db_path(workspace))
    try:
        storage.migrate(conn)
        payload = {"path": ws_path, "repo": repo_root}
        if force and dirty:
            payload["forced"] = True
            payload["note"] = "removed while dirty / with unmerged commits"
        storage.append_event(conn, None, "workspace_removed", payload)
    finally:
        conn.close()
    return result


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
        taskgroup = registry.load(
            registry.workspace_registry_path(workspace)
        ).require(row["project"])
        workdir = row["workdir"] or taskgroup.path

        outcome = verify.run_acceptance(workdir, taskgroup.verify)
        status = VERIFY_SKIPPED if not outcome.ran else (
            "PASSED" if outcome.passed else "FAILED"
        )
        fields = {"verify_cmd": taskgroup.verify if outcome.ran else VERIFY_SKIPPED}
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
# Control: cancel / remove
# ---------------------------------------------------------------------------


def cancel_task(workspace: str, task_id: str) -> dict:
    """Stop a task and record the terminal state `cancelled`.

    * `running` / `verifying`: signal the recorded process group (SIGTERM, then
      SIGKILL after a grace period).
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
        if status not in (STATUS_RUNNING, STATUS_VERIFYING):
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


#: `verify` labels carried by an `accepted` event. They describe the acceptance
#: result the human accepted the breach *alongside*, not a fresh verdict.
_VERIFY_PASSED = "passed"
_VERIFY_FAILED = "failed"
_VERIFY_SKIPPED = "skipped"


def _violation_summary(conn, task_id: str) -> dict:
    """The breach an `accept` confirms: the rules and the paths they hit.

    Read from the card's own `forbidden` / `blocked` events, so the `accepted`
    event carries the facts the human actually looked at rather than a
    re-derivation from the registry.
    """
    summary = {"rules": [], "paths": [], "violations": []}
    for name in ("forbidden", "blocked"):
        row = conn.execute(
            "SELECT payload FROM events WHERE task_id = ? AND event = ? "
            "ORDER BY id DESC LIMIT 1",
            (task_id, name),
        ).fetchone()
        if row is None or row[0] is None:
            continue
        try:
            payload = json.loads(row[0])
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        if not summary["violations"] and isinstance(payload.get("violations"), list):
            summary["violations"] = payload["violations"]
        if not summary["rules"] and isinstance(payload.get("rules"), list):
            summary["rules"] = list(payload["rules"])
        if not summary["paths"] and isinstance(payload.get("paths"), list):
            summary["paths"] = list(payload["paths"])
    # A `blocked` event may carry only the per-violation detail; derive the rule
    # list from it so `rules` is never empty when a breach was recorded.
    if not summary["rules"]:
        summary["rules"] = sorted(
            {
                entry.get("rule")
                for entry in summary["violations"]
                if isinstance(entry, dict) and entry.get("rule")
            }
        )
    return summary


#: How much of the agent's own last summary the `accepted` event carries. The
#: summary is context for a human sign-off, never a verdict — a tail is enough.
_SUMMARY_TAIL_CHARS = 500


def _last_summary(conn, task_id: str) -> Optional[str]:
    """The agent's own last summary, newest first, or None when there is none.

    `adapter` carries the agent's claim right after it exits; a clean `done`
    carries it again. A failed *acceptance* records no summary (only the
    verdict), so this is best-effort context, not a required field.
    """
    for name in ("adapter", "done"):
        row = conn.execute(
            "SELECT payload FROM events WHERE task_id = ? AND event = ? "
            "ORDER BY id DESC LIMIT 1",
            (task_id, name),
        ).fetchone()
        if row is None or row[0] is None:
            continue
        try:
            payload = json.loads(row[0])
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        if isinstance(payload, dict):
            text = payload.get("summary")
            if isinstance(text, str) and text.strip():
                return text
    return None


def accept_task(
    workspace: str, task_id: str, *, by: str = "cli", note: Optional[str] = None
) -> dict:
    """Clear a `blocked` or `failed` card — the human disposition of one run.

    `blocked` (a boundary breach) is accepted with or without a note, exactly as
    it always has been: a green acceptance earns `done`, a red or skipped one
    earns `failed`. `failed` (the adapter failed, or acceptance ran and went red)
    may also be accepted, but ONLY with a non-empty ``note``: closing a failed
    card is a human sign-off, and the reason must survive in the ledger.

    `accept` is a human **registration**, not a verdict: it never re-runs
    acceptance and never rewrites `verify_*`. Whatever the run recorded when it
    stopped stays authoritative; a failed card is promoted to `done` only because
    a human judged the recorded failure a false red, and that judgement is kept
    in the `accepted` event alongside the evidence the human saw.

    Every other status (running / verifying / done / timeout /
    cancelled) is refused with a readable `TaskStateError`, so `accept` can never
    silently re-close a card. The card's `verify_*` columns and `finished_at` are
    left untouched — the run's own facts do not change because a human later
    signed off. Returns the updated task row.
    """
    note_text = note if isinstance(note, str) else None
    note_present = bool(note_text and note_text.strip())
    conn = storage.connect(storage.db_path(workspace))
    try:
        storage.migrate(conn)
        row = storage.get_task(conn, task_id)
        if row is None:
            raise TaskNotFoundError(f"no such task: {task_id}")
        status = row["status"]
        if status not in (STATUS_BLOCKED, STATUS_FAILED):
            raise TaskStateError(
                f"task {task_id} is {status}; "
                "only a blocked or failed task can be accepted"
            )
        if status == STATUS_FAILED and not note_present:
            # A failed card is closed by human judgement, not by a fresh verdict,
            # so the reason MUST be on the record. Refuse before touching the row.
            raise UsageError(
                "accepting a failed task requires a note: "
                "人工收尾必须留说明",
                hint=(
                    "accept is a human registration, not a verdict; pass "
                    '--note "why this failure is being cleared"'
                ),
            )

        verify_exit = row["verify_exit"]
        if verify_exit == 0:
            verify_label = _VERIFY_PASSED
        elif verify_exit is None:
            verify_label = _VERIFY_SKIPPED
        else:
            verify_label = _VERIFY_FAILED
        if status == STATUS_FAILED:
            # A human signed the red off as a false negative: the recorded facts
            # stay, the terminal state becomes `done`.
            new_status = STATUS_DONE
        else:
            # `blocked` keeps following its acceptance result, exactly as before.
            new_status = STATUS_DONE if verify_exit == 0 else STATUS_FAILED

        payload = {
            "by": by,
            "verify": verify_label,
            "verify_exit": verify_exit,
            "from": status,
            "to": new_status,
            # The evidence the human actually saw when signing off.
            "files_changed": row["files_changed"],
            # The note is stored verbatim (None for a blocked card with no note).
            "note": note_text,
        }
        if status == STATUS_BLOCKED:
            summary = _violation_summary(conn, task_id)
            payload["rules"] = summary["rules"]
            payload["paths"] = summary["paths"]
            payload["violations"] = summary["violations"]
        else:
            agent_summary = _last_summary(conn, task_id)
            if agent_summary:
                payload["summary"] = agent_summary[:_SUMMARY_TAIL_CHARS]

        storage.update_task(conn, task_id, status=new_status)
        storage.append_event(conn, task_id, "accepted", payload)
        return dict(storage.get_task(conn, task_id))
    finally:
        conn.close()


def rerun_task(workspace: str, task_id: str) -> str:
    """Start a fresh card from a terminal one, linked both ways in the ledger.

    The new card reuses the old card's brief and run flags (adapter / model /
    reasoning / timeout / read_only / worktree / skip_verify), recovered from
    its row and its events by :func:`_run_options`. A flag the ledger never
    captured falls back to the documented default (see `_run_options`).

    Only a terminal card may be rerun, `blocked` included; a non-terminal card
    is refused so two attempts of the same work can never overlap. The new card
    goes down the normal ``dispatch`` path and gets ``rerun_of`` while the old
    card gets ``rerun_as``. Returns the new task id.
    """
    conn = storage.connect(storage.db_path(workspace))
    try:
        storage.migrate(conn)
        row = storage.get_task(conn, task_id)
        if row is None:
            raise TaskNotFoundError(f"no such task: {task_id}")
        if row["status"] not in TERMINAL_STATUSES:
            raise TaskStateError(
                f"task {task_id} is {row['status']}; "
                "only a terminal task can be rerun"
            )
        options = _run_options(conn, task_id)
        old = dict(row)
    finally:
        conn.close()

    return dispatch(
        workspace,
        old["project"],
        old["brief"],
        adapter=old["adapter"] or "codex",
        model=old["model"],
        reasoning=old["reasoning"],
        read_only=bool(options.get("read_only")),
        worktree=bool(options.get("worktree")),
        skip_verify=bool(options.get("skip_verify")),
        timeout=options.get("timeout"),
        rerun_of=task_id,
    )


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



def summary_counts(workspace: str, conn) -> dict:
    """Counts per status — the one query the dashboard leans on.

    Every known status is present (0 when it has no rows) so the board can draw
    a stable set of columns without special-casing a missing bucket.
    """
    counts = {status: 0 for status in _ALL_STATUSES}
    for row in conn.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status"):
        counts[row[0]] = int(row[1])
    return counts
