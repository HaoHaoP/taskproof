"""Plain data carriers.

Deliberately dependency-free dataclasses (no ORM, no pydantic) — the package
promises standard library only.
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

# Task lifecycle. Terminal states: DONE, FAILED, BLOCKED, TIMEOUT, CANCELLED.
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
    """A repository / filter unit: where the work happens and what to call it.

    A project is *not* dispatchable on its own — it is the shared identity and
    default path that one or more :class:`Taskgroup` lanes hang off. Renaming a
    project (or adding a lane) never splits its history.
    """

    id: str
    path: str
    aliases: List[str] = field(default_factory=list)


@dataclass
class Taskgroup:
    """One lane ("道"): the unit a task is dispatched onto.

    It owns the acceptance command, the forbidden-path rules and the structured
    result contract; ``path`` defaults to the owning project's path but may
    point anywhere (an independent clone, a subdirectory, ...).
    """

    id: str
    project: str
    path: str
    aliases: List[str] = field(default_factory=list)
    verify: Optional[str] = None
    verify_kind: str = "none"  # check | build | none
    forbidden_paths: List[str] = field(default_factory=list)
    auto_registered: bool = False
    #: Structured-result contract: "default" (package-shipped schema), "none"
    #: (fall back to free text, never silent), or an absolute path to a custom
    #: JSON Schema. See `registry.result_schema_path`.
    result_schema: str = "default"
    #: Concurrency lock name. Empty means this lane's own id; loading fills the
    #: default in so callers never need to special-case an unset value.
    group: str = ""

    def __post_init__(self):
        if not isinstance(self.group, str) or not self.group.strip():
            self.group = self.id


@dataclass
class Task:
    """One dispatched unit of work. Mirrors the `tasks` table."""

    id: str
    project: str
    group: str
    brief: str
    status: str = STATUS_RUNNING
    adapter: str = "codex"
    model: Optional[str] = None
    reasoning: Optional[str] = None
    attempt: int = 1
    exit_code: Optional[int] = None
    pid: Optional[int] = None
    #: Process-group id that locates the whole adapter tree (`_run_adapter`
    #: spawns it with ``start_new_session=True``, so this is the adapter's own
    #: session/group, not the dispatching process' group). `cancel` signals
    #: exactly this group.
    pgid: Optional[int] = None
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
