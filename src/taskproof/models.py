"""Plain data carriers.

Deliberately dependency-free dataclasses (no ORM, no pydantic) — the package
promises standard library only.
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

# Task lifecycle. Terminal states: DONE, FAILED, BLOCKED, TIMEOUT, CANCELLED.
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_VERIFYING = "verifying"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_BLOCKED = "blocked"
STATUS_TIMEOUT = "timeout"
STATUS_CANCELLED = "cancelled"

TERMINAL_STATUSES = (
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_BLOCKED,
    STATUS_TIMEOUT,
    STATUS_CANCELLED,
)


@dataclass
class Project:
    """One registry entry — see examples/projects.example.yaml."""

    id: str
    path: str
    group: str = "default"
    aliases: List[str] = field(default_factory=list)
    verify: Optional[str] = None
    verify_kind: str = "none"  # check | build | none
    forbidden_paths: List[str] = field(default_factory=list)
    auto_registered: bool = False
    #: Structured-result contract: "default" (package-shipped schema), "none"
    #: (fall back to free text, never silent), or an absolute path to a custom
    #: JSON Schema. See `registry.result_schema_path`.
    result_schema: str = "default"


@dataclass
class Task:
    """One dispatched unit of work. Mirrors the `tasks` table."""

    id: str
    project: str
    group: str
    brief: str
    status: str = STATUS_QUEUED
    adapter: str = "codex"
    model: Optional[str] = None
    reasoning: Optional[str] = None
    attempt: int = 1
    exit_code: Optional[int] = None
    pid: Optional[int] = None
    workdir: Optional[str] = None
    result_path: Optional[str] = None
    verify_cmd: Optional[str] = None
    verify_exit: Optional[int] = None
    files_changed: Optional[int] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

    def to_row(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Claim:
    """A held concurrency slot. `scope` is either `group:<name>` or `global`."""

    scope: str
    task_id: str
    pid: Optional[int]
    claimed_at: str
    expires_at: str


@dataclass
class AdapterResult:
    """Normalised outcome of one adapter invocation.

    `summary` is the agent's own claim — it is displayed but NEVER treated as
    proof of success. Only the independently run acceptance command decides.
    """

    exit_code: int
    summary: str = ""
    payload: Optional[Dict[str, Any]] = None
    files_changed: Optional[int] = None
    raw_stdout: str = ""
    raw_stderr: str = ""
    parse_degraded: bool = False
    result_path: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.exit_code == 0
