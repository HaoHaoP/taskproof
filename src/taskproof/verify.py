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
   if the agent reported success. The check does not rely on the git change list
   alone: git cannot see inside `.git/` and omits every ignored path, so the
   declared paths are fingerprinted before and after the run as well.
"""

import os
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


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


def _tail(text: str, lines: int) -> str:
    """Last `lines` lines of `text` (no trailing newline). Long output must
    never be dumped wholesale into the ledger."""
    if not text:
        return ""
    if not lines or lines <= 0:
        return text
    return "\n".join(text.splitlines()[-lines:])


def _as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


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
    if command is None or not str(command).strip():
        # Skipping is NOT passing: ran=False lets the caller record SKIPPED
        # rather than DONE even though `passed` is trivially true.
        return VerifyOutcome(ran=False, passed=True, note="no acceptance command")

    command = str(command)
    # Registry acceptance commands are shell one-liners ("exit 0",
    # "for i in $(seq 1 200); do ...; done", "npm run build && npm test") that
    # need real shell features. We therefore choose the EXPLICIT shell string
    # form, `/bin/sh -c <command>`, over `shlex.split`. This keeps argv a list
    # (no `shell=True`), makes the use of a shell visible and auditable, and is
    # required because shell builtins like `exit` are not executables.
    argv = ["/bin/sh", "-c", command]

    run_env = None
    if env:
        # Merge so the command still inherits PATH etc.
        run_env = {**os.environ, **env}

    try:
        proc = subprocess.run(
            argv,
            cwd=workdir,
            env=run_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return VerifyOutcome(
            ran=True,
            passed=False,
            exit_code=None,
            command=command,
            output_tail=_tail(_as_text(exc.output), tail_lines),
            note=f"acceptance timeout: command exceeded {timeout}s (treated as failure)",
        )
    except FileNotFoundError as exc:
        return VerifyOutcome(
            ran=True,
            passed=False,
            exit_code=None,
            command=command,
            note=f"acceptance command could not run: {exc}",
        )

    output = proc.stdout or ""
    passed = proc.returncode == 0
    note = "" if passed else f"acceptance command exited {proc.returncode}"
    return VerifyOutcome(
        ran=True,
        passed=passed,
        exit_code=proc.returncode,
        command=command,
        output_tail=_tail(output, tail_lines),
        note=note,
    )


def _git_porcelain(workdir: str) -> Optional[str]:
    """Read-only `git status --porcelain`; None when workdir is not a repo."""
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=workdir,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def detect_changes(workdir: str) -> Optional[int]:
    """Count changed files in the worktree (git only; None when not a repo).

    Read-only: `git status --porcelain` and nothing else. taskproof never runs
    a git write command.
    """
    porcelain = _git_porcelain(workdir)
    if porcelain is None:
        return None
    return len([line for line in porcelain.splitlines() if line.strip()])


def changed_files(workdir: str) -> List[str]:
    """Relative paths reported by `git status --porcelain` (read-only)."""
    porcelain = _git_porcelain(workdir)
    if not porcelain:
        return []

    files: List[str] = []
    for line in porcelain.splitlines():
        if not line.strip():
            continue
        # Format: two status columns, a space, then the path.
        path = line[3:] if len(line) > 3 else line.strip()
        # Renames/copies read "R  old -> new"; we care about the new path.
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        path = path.strip().strip('"')
        files.append(path)
    return files


def _normalise(workdir: str, path: str) -> str:
    """Normalise a path to a POSIX-style relative path from `workdir`.

    Handles relative (`dist/x`), `./`-prefixed (`./dist/x`) and absolute
    (`/repo/dist/x`) spellings so they all compare on the same footing.
    """
    text = str(path).replace("\\", "/")
    base = os.path.abspath(workdir)
    if os.path.isabs(text):
        try:
            text = os.path.relpath(os.path.normpath(text), base)
        except ValueError:
            # Different drive (Windows); fall through using the raw text.
            pass
    normalised = os.path.normpath(text).replace(os.sep, "/")
    # Strip any leading "./" that survived normpath (e.g. on odd inputs).
    while normalised.startswith("./"):
        normalised = normalised[2:]
    if normalised == ".":
        normalised = ""
    return normalised


def check_forbidden(workdir: str, forbidden_paths: List[str],
                    changed_files: List[str]) -> List[str]:
    """Return the subset of `changed_files` that violates `forbidden_paths`.

    Matching is on normalised relative paths and must catch a change nested
    under a forbidden directory (e.g. `dist/app.js` for `dist/`). A rule that
    ends with `/` is a directory rule (matches the directory and everything
    below it); a rule without a trailing slash must match that exact path.
    """
    rules = []
    for raw in forbidden_paths or []:
        if raw is None:
            continue
        rule_text = str(raw).replace("\\", "/")
        is_dir = rule_text.endswith("/")
        rule_path = _normalise(workdir, rule_text)
        if not rule_path:
            continue
        rules.append((rule_path, is_dir))

    violations: List[str] = []
    for original in changed_files or []:
        candidate = _normalise(workdir, original)
        for rule_path, is_dir in rules:
            if is_dir:
                if candidate == rule_path or candidate.startswith(rule_path + "/"):
                    violations.append(original)
                    break
            else:
                if candidate == rule_path:
                    violations.append(original)
                    break
    return violations


# ---------------------------------------------------------------------------
# Forbidden paths, part two: watching what git cannot see.
#
# `check_forbidden` matches against the `git status` change list, which is a
# cheap and good change detector but a blind one for two whole classes of path:
#
#   * nothing inside `.git/` is ever reported -- git does not list its own
#     directory;
#   * every ignored path is omitted -- and build output and dependency
#     directories are exactly the ignored ones.
#
# This was measured, not assumed. With `forbidden_paths = ["dist/"]` and `dist/`
# in `.gitignore`, an adapter wrote `dist/app.js` and the run was recorded as
# `done`. The same happened for `.git/`. Those rules, and `node_modules/`, are
# what the shipped example declares -- so the guard was inert for the three
# paths people most expect it to cover.
#
# So the declared paths are also fingerprinted before and after the run. That
# costs one walk of the declared set and nothing else.
# ---------------------------------------------------------------------------

#: Above this many entries a rule's walk stops and only its root is compared.
#: Reported in the audit event when it happens, so a partial guarantee is
#: visible rather than implied.
SNAPSHOT_LIMIT = 20000


def _fingerprint(path: str) -> str:
    try:
        stat = os.stat(path)
    except OSError:
        return "gone"
    return f"{stat.st_size}:{stat.st_mtime_ns}"


def snapshot_forbidden(
    workdir: str, forbidden_paths: List[str]
) -> Tuple[Dict[str, str], bool]:
    """Fingerprint everything at or under each forbidden rule.

    Returns `(entries, truncated)`. A rule whose path does not exist yet is
    skipped rather than recorded: if the run creates it, that shows up as an
    addition in the diff, which is the point.
    """
    entries: Dict[str, str] = {}
    truncated = False

    for raw in forbidden_paths or []:
        if raw is None:
            continue
        rule_path = _normalise(workdir, str(raw))
        if not rule_path:
            continue
        target = os.path.join(workdir, rule_path)

        if os.path.isfile(target):
            entries[rule_path] = _fingerprint(target)
            continue
        if not os.path.isdir(target):
            continue

        for root, dirs, names in os.walk(target):
            dirs.sort()
            for name in sorted(names):
                if len(entries) >= SNAPSHOT_LIMIT:
                    truncated = True
                    return entries, truncated
                full = os.path.join(root, name)
                entries[_normalise(workdir, full)] = _fingerprint(full)

    return entries, truncated


def diff_snapshots(before: Dict[str, str], after: Dict[str, str]) -> List[str]:
    """Paths under a protected rule that appeared, changed or disappeared."""
    changed = set()
    for key, fingerprint in after.items():
        if before.get(key) != fingerprint:
            changed.add(key)
    for key in before:
        if key not in after:
            changed.add(key)
    return sorted(changed)
