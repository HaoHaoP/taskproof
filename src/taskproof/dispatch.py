"""The dispatch pipeline.

    resolve project -> take concurrency slots -> run adapter -> parse result
        -> check forbidden paths -> run acceptance -> record -> release slots

Every step appends to the audit stream, so a crashed run is reconstructable
from `events-*.jsonl` alone.

What this module deliberately does NOT do: decide whether the agent's claim is
true. The acceptance command in `verify.py` decides that.
"""

import os
import subprocess
from typing import Optional

from . import concurrency, ledger, registry, storage, verify
from .adapters import get as get_adapter
from .errors import AdapterError, TaskproofError, VerifyError
from .models import (
    STATUS_BLOCKED,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_RUNNING,
    STATUS_VERIFYING,
    Task,
)


def prepare_workspace(workspace: str) -> None:
    """Create the workspace, database and audit directory if missing."""
    raise NotImplementedError("card: dispatch")


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
) -> str:
    """Run one task end to end. Returns the task id.

    Raises the typed errors in `errors.py` so the CLI can map them to exit codes:
      ConcurrencyError -> 75, AdapterError -> 70, VerifyError -> 71, RegistryError -> 2

    Rules that must survive any refactor:
      * the acceptance command runs in the PROJECT workdir, never the workspace
      * `skip_verify` records verify as SKIPPED, never as passed
      * slots are released on every exit path, including exceptions
      * only processes this function spawned are ever terminated
    """
    raise NotImplementedError("card: dispatch")


def _run_adapter(adapter_obj, *, brief: str, workdir: str, log_path: str,
                 schema_path: Optional[str] = None, read_only: bool = False):
    """Spawn the agent CLI, tee output to `log_path`, return (exit_code, out, err).

    Must not use shell=True. Must enforce `adapter_obj.timeout` and, on expiry,
    terminate only the process tree it started.
    """
    raise NotImplementedError("card: dispatch")


def verify_task(workspace: str, task_id: str) -> verify.VerifyOutcome:
    """Re-run acceptance for an existing task (`taskproof verify <id>`)."""
    raise NotImplementedError("card: dispatch")


def task_detail(workspace: str, task_id: str) -> dict:
    """Task row plus its event stream, for `show` and the board's detail view."""
    raise NotImplementedError("card: dispatch")


def summary_counts(workspace: str, conn) -> dict:
    """Counts per status — the one query the dashboard leans on."""
    raise NotImplementedError("card: storage-crud")
