"""Acceptance verification — the part that does not trust the worker.

Rules
-----
1. The agent's self-report is NEVER evidence. Only this module decides success.
2. The acceptance command comes from the registry, and is run by taskproof in
   the project workdir after the adapter exits.
3. Artifact self-check: if the run claims to have changed files, the worktree is
   inspected to confirm it. (One observed failure mode: an agent reported
   success while the tree was untouched.)
4. Forbidden paths are checked AFTER the run — a violation fails the task even
   if the agent reported success.
"""

import subprocess
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class VerifyOutcome:
    ran: bool
    passed: bool
    exit_code: Optional[int] = None
    command: Optional[str] = None
    output_tail: str = ""
    violations: List[str] = field(default_factory=list)
    files_changed: Optional[int] = None
    note: str = ""


def run_acceptance(
    workdir: str,
    command: Optional[str],
    *,
    timeout: int = 1800,
    env: Optional[dict] = None,
    tail_lines: int = 40,
) -> VerifyOutcome:
    """Run the registry's acceptance command.

    * `command` empty/None -> `ran=False, passed=True, note="no acceptance command"`.
      Skipping is not a pass; the caller must surface that distinction.
    * Output is truncated to the last `tail_lines` for the ledger.
    * A timeout is a FAILURE, not an error: exit code is recorded as None and
      `note` says so.
    """
    raise NotImplementedError("card: verify")


def detect_changes(workdir: str) -> Optional[int]:
    """Count changed files in the worktree (git only; None when not a repo).

    Read-only: `git status --porcelain` and nothing else. taskproof never runs
    a git write command.
    """
    raise NotImplementedError("card: verify")


def check_forbidden(workdir: str, forbidden_paths: List[str], changed_files: List[str]) -> List[str]:
    """Return the subset of `changed_files` that violates `forbidden_paths`.

    Matching is on normalised relative paths and must catch a change nested
    under a forbidden directory (e.g. `dist/app.js` for `dist/`).
    """
    raise NotImplementedError("card: verify")


def changed_files(workdir: str) -> List[str]:
    """Relative paths reported by `git status --porcelain` (read-only)."""
    raise NotImplementedError("card: verify")
