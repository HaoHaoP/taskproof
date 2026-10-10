"""Project + taskgroup registry.

Format: TOML, parsed with the standard library (`tomllib`, Python 3.11+).
Not YAML — YAML would require PyYAML, and this package is standard-library only.

The registry is CONFIGURATION: human-editable, meant to be committed to the
user's own repository. Runtime state lives in SQLite (see storage.py).

Two layers
----------
* ``[[project]]`` — a repository / filter unit: ``id``, ``path``, ``aliases``.
  Optional on its own: it is the shared identity a lane hangs off.
* ``[[taskgroup]]`` — one lane ("道") a task is dispatched onto: ``id``,
  ``project`` (owning project), ``path`` (defaults to the project path),
  ``aliases``, ``group`` (concurrency lock; defaults to the taskgroup id),
  ``verify``, ``verify_kind``, ``forbidden_paths``, ``result_schema``.

A legacy ``[[project]]`` block that carries any lane field (``verify``,
``verify_kind``, ``forbidden_paths`` or ``result_schema``) is read as a
same-named project *plus* a same-named lane, so older files keep working with
zero migration.

Example
-------
    [defaults]
    concurrency = 3
    timeout = 1800

    # A repo with a single lane: the lane may omit `path` and `project`.
    [[taskgroup]]
    id = "my-app"
    path = "/home/me/code/my-app"
    aliases = ["app"]
    verify = "npm run build"
    verify_kind = "build"
    forbidden_paths = [".git/", "dist/"]
    result_schema = "default"   # "default" | "none" | "/abs/path.json"

    # A repo with two lanes; the project owns the shared default path.
    [[project]]
    id = "api"
    path = "/home/me/code/api"

    [[taskgroup]]
    id = "api-main"
    project = "api"
    verify = "make check"
    verify_kind = "check"

    [[taskgroup]]
    id = "api-docs"
    project = "api"
    path = "/home/me/code/api/site"
    verify = "npm test"

Resolution accepts a taskgroup id/alias/path, then a project id/alias/path
(only when the project has exactly one lane).
"""

import hashlib
import json
import os
import re
import tempfile
import threading
import tomllib
from typing import List, Optional

from . import concurrency, verify
from .errors import RegistryError
from .models import Project, Taskgroup

DEFAULT_REGISTRY_NAME = "projects.toml"

#: Package-shipped default structured-result contract (`schemas/result.json`).
#: Resolved relative to this file so the path is correct whether the package is
#: run from a source checkout or installed from a wheel.
BUILTIN_RESULT_SCHEMA = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "schemas", "result.json"
)

#: `result_schema` values that are settings rather than filesystem paths.
RESULT_SCHEMA_DEFAULT = "default"
RESULT_SCHEMA_NONE = "none"

#: The only accepted values for a taskgroup's ``workspace`` field. The default
#: deliberately stays ``"none"``: existing acceptance commands commonly contain
#: absolute paths to the main checkout, and silently changing their cwd to a
#: worktree would make those checks pass against the wrong tree.
VALID_WORKSPACE_MODES = ("none", "worktree")

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

#: A probe may compile a real repository. Keep it bounded so neither the CLI
#: nor the API can hang forever on a broken acceptance command.
_PROBE_TIMEOUT = 600

_WRITE_LOCK = threading.Lock()
_PROJECT_HEADER_RE = re.compile(
    r"^\s*\[\[\s*project\s*\]\]\s*(?:#.*)?(?:\r?\n)?$"
)
_TASKGROUP_HEADER_RE = re.compile(
    r"^\s*\[\[\s*taskgroup\s*\]\]\s*(?:#.*)?(?:\r?\n)?$"
)
_TABLE_HEADER_RE = re.compile(r"^\s*\[\[?[^\]]+\]\]?\s*(?:#.*)?(?:\r?\n)?$")
_KEY_RE = re.compile(r"^\s*[A-Za-z0-9_-]+\s*=")

#: Any of these on a `[[project]]` block means it is really a lane: it is read
#: as a project + a same-named taskgroup (zero-migration compatibility).
_LANE_FIELDS = (
    "verify",
    "verify_kind",
    "forbidden_paths",
    "result_schema",
    "workspace",
    "link",
)


class RegistryConflictError(RegistryError):
    """The caller's expected hash no longer matches the registry on disk."""

    def __init__(self, current_hash, content, projects):
        super().__init__("registry changed on disk")
        self.current_hash = current_hash
        self.content = content
        self.projects = projects


class RegistryNotFoundError(RegistryError):
    """The requested project id is not present in the registry."""


def builtin_result_schema_path() -> str:
    """Absolute path to the package-shipped default result schema."""
    return BUILTIN_RESULT_SCHEMA


def result_schema_path(taskgroup: Taskgroup) -> Optional[str]:
    """Resolve a taskgroup's `result_schema` setting to an argv-ready path.

    * omitted / ``"default"`` -> the package-shipped ``schemas/result.json``
    * ``"none"``              -> ``None`` (structured result disabled)
    * any other string        -> the absolute path validated at load time

    Returning ``None`` is the ONLY way structured output is turned off, and it
    is always paired with an explicit event at dispatch time — a run never
    silently falls back to free text.
    """
    value = taskgroup.result_schema
    if value == RESULT_SCHEMA_NONE:
        return None
    if not value or value == RESULT_SCHEMA_DEFAULT:
        return BUILTIN_RESULT_SCHEMA
    return value


def infer_verify(path: str):
    """Return (command, verify_kind) for the first recognised build file."""
    for name, command, kind in _BUILD_FILES:
        if os.path.isfile(os.path.join(path, name)):
            return command, kind
    return None, "none"


def probe_repository(path: str) -> dict:
    """Build the registration draft for one repository without writing state.

    The CLI and the API both use this so "what register would infer" cannot
    drift between the two entry points. The draft is a ``[[taskgroup]]`` block:
    it carries no ``project``, so it stands up a same-named project (the compat
    rule). The taskgroup's lock defaults to its own id.
    """
    path = os.path.abspath(os.path.expanduser(path))
    taskgroup_id = os.path.basename(os.path.normpath(path)) or path
    command, kind = infer_verify(path)
    probe = None
    probe_exit = None
    if command is not None:
        outcome = verify.run_acceptance(path, command, timeout=_PROBE_TIMEOUT)
        probe = "passed" if outcome.passed else "failed"
        probe_exit = outcome.exit_code
    return {
        "id": taskgroup_id,
        "path": path,
        "verify": command,
        "verify_kind": kind,
        "probe": probe,
        "probe_exit": probe_exit,
        "aliases": [],
        "forbidden_paths": [],
    }


def _read_bytes(path: str) -> bytes:
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError as exc:
        raise RegistryError(f"cannot read registry {path}: {exc}")


def registry_hash(path: str) -> str:
    """SHA-256 of the registry's raw bytes, lowercase hexadecimal."""
    return hashlib.sha256(_read_bytes(path)).hexdigest()


def registry_metadata(path: str) -> dict:
    """Path, content hash and mtime for the optimistic-write protocol."""
    data = _read_bytes(path)
    stat = os.stat(path)
    return {
        "path": path,
        "hash": hashlib.sha256(data).hexdigest(),
        "mtime": stat.st_mtime,
    }


def _probe_flags_from(data: dict) -> dict:
    flags = {}
    for table in ("project", "taskgroup"):
        for entry in data.get(table, []) or []:
            if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
                continue
            values = {}
            if "probe" in entry:
                values["probe"] = entry["probe"]
            if "probe_exit" in entry:
                values["probe_exit"] = entry["probe_exit"]
            if values:
                flags[entry["id"]] = values
    return flags


def read_probe_flags(path: str) -> dict:
    """Return raw probe metadata keyed by block id.

    ``registry.load`` intentionally keeps only fields it understands; probe
    results are human/API metadata, so they are read from the TOML source just
    like ``cli._read_probe_flags`` does. Both ``[[project]]`` (legacy) and
    ``[[taskgroup]]`` blocks are consulted.
    """
    try:
        with open(path, "rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return _probe_flags_from(data)


class Registry:
    """Loaded registry: projects + taskgroups + global defaults."""

    def __init__(
        self,
        projects: List[Project],
        taskgroups: List[Taskgroup],
        defaults: dict,
        source: Optional[str] = None,
    ):
        self.projects = projects
        self.taskgroups = taskgroups
        self.defaults = defaults or {}
        self.source = source

    # -- lookup -----------------------------------------------------------

    def lanes_for(self, project_id: str) -> List[Taskgroup]:
        """Every taskgroup that hangs off ``project_id``, in file order."""
        return [tg for tg in self.taskgroups if tg.project == project_id]

    def _lane_for_project(self, project: Project) -> Optional[Taskgroup]:
        lanes = self.lanes_for(project.id)
        if len(lanes) == 1:
            return lanes[0]
        if not lanes:
            return None
        ids = ", ".join(tg.id for tg in lanes)
        raise RegistryError(
            f"project '{project.id}' has multiple taskgroups: {ids}",
            hint="pick one taskgroup id, alias or path",
        )

    @staticmethod
    def _single_or_ambiguous(matches, label="taskgroups"):
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            ids = ", ".join(item.id for item in matches)
            raise RegistryError(
                f"path matches multiple {label}: {ids}",
                hint="use a taskgroup id, alias or path",
            )
        return None

    def by_id(self, key: str) -> Optional[Taskgroup]:
        """Resolve to a taskgroup: id, alias, path, then owning project.

        Taskgroups win. A project key resolves only when the project has
        exactly one lane; a project with several lanes is an error that lists
        them, so a bare project id is never silently mis-dispatched.
        """
        if not isinstance(key, str) or not key:
            return None
        for tg in self.taskgroups:
            if tg.id == key:
                return tg
        for tg in self.taskgroups:
            if key in tg.aliases:
                return tg
        found = self._single_or_ambiguous([tg for tg in self.taskgroups if tg.path == key])
        if found is not None:
            return found
        for project in self.projects:
            if project.id == key:
                return self._lane_for_project(project)
        for project in self.projects:
            if key in project.aliases:
                return self._lane_for_project(project)
        project = self._single_or_ambiguous(
            [p for p in self.projects if p.path == key], label="projects"
        )
        if project is not None:
            return self._lane_for_project(project)
        # A path may be spelled differently (trailing slash, `~`, `..`);
        # compare normalised absolute forms as a fallback.
        if os.path.isabs(key):
            norm = os.path.normpath(key)
            found = self._single_or_ambiguous(
                [tg for tg in self.taskgroups if os.path.normpath(tg.path) == norm]
            )
            if found is not None:
                return found
            project = self._single_or_ambiguous(
                [p for p in self.projects if os.path.normpath(p.path) == norm],
                label="projects",
            )
            if project is not None:
                return self._lane_for_project(project)
        return None

    def require(self, key: str) -> Taskgroup:
        taskgroup = self.by_id(key)
        if taskgroup is None:
            known = sorted({p.id for p in self.projects} | {t.id for t in self.taskgroups})
            raise RegistryError(
                f"project not found: {key}",
                hint=f"registered projects: {', '.join(known) or '(none)'}",
            )
        return taskgroup

    # -- defaults ---------------------------------------------------------

    @property
    def concurrency(self) -> int:
        # The effective global cap: `[defaults] concurrency` when set, otherwise
        # the machine fallback (card 42). Use `concurrency.resolve(...)` when the
        # source has to be shown too.
        return concurrency.resolve(self.defaults).value

    @property
    def timeout(self) -> int:
        return int(self.defaults.get("timeout", 1800))


#: Scope-source labels. The CLI prints these verbatim, so they are part of the
#: human contract (see docs: the scope must always be visible).
SCOPE_FROM_PROJECT = "来自 --project"
SCOPE_FROM_ALL = "来自 --all"
SCOPE_FROM_CWD = "来自 cwd"
SCOPE_OUTSIDE = "cwd 不在任何已登记仓库内"


def resolve_scope(reg, *, explicit_project=None, force_all=False, cwd=None):
    """Map the caller's context to one taskgroup (or all), plus a source label.

    Returns ``(taskgroup_id_or_None, source_label)``. ``None`` means "all
    projects". Priority is fixed and deliberately boring:

        ``--project`` > ``--all`` > cwd inference > all (when cwd is outside)

    cwd inference matches a registered taskgroup when the working directory is
    that lane's path *or* a descendant. Symlinks are resolved first (macOS
    spells ``/tmp`` and ``/private/tmp`` differently), and the *longest*
    matching lane path wins so a nested checkout beats its parent repo. When
    two lanes match at the same depth the choice is ambiguous and refused, with
    the candidates named.
    """
    if explicit_project:
        taskgroup = reg.by_id(explicit_project) if reg is not None else None
        return (
            taskgroup.id if taskgroup is not None else explicit_project,
            SCOPE_FROM_PROJECT,
        )
    if force_all:
        return None, SCOPE_FROM_ALL

    if cwd is None:
        cwd = os.getcwd()
    target = os.path.realpath(cwd)
    candidates = []
    best_len = -1
    for taskgroup in (reg.taskgroups if reg is not None else []):
        taskgroup_path = os.path.realpath(taskgroup.path)
        if target == taskgroup_path or target.startswith(taskgroup_path + os.sep):
            length = len(taskgroup_path)
            if length > best_len:
                best_len = length
                candidates = [taskgroup]
            elif length == best_len:
                candidates.append(taskgroup)
    if len(candidates) == 1:
        return candidates[0].id, SCOPE_FROM_CWD
    if len(candidates) > 1:
        ids = ", ".join(tg.id for tg in candidates)
        raise RegistryError(
            f"cwd matches multiple taskgroups: {ids}",
            hint="pass --project to pick one",
        )
    return None, SCOPE_OUTSIDE


VALID_VERIFY_KINDS = ("check", "build", "none")


def _require_field(entry: dict, field: str, kind: str, index: int, source: str) -> str:
    value = entry.get(field)
    if not isinstance(value, str) or not value.strip():
        raise RegistryError(
            f"{source}: {kind} #{index + 1} is missing a non-empty '{field}'"
        )
    return value


def _load_string_array(value, field: str, label: str, source: str) -> list:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise RegistryError(
            f"{source}: {label} field '{field}' must be an array of strings"
        )
    return list(value)


def _load_group(entry: dict, default: str, label: str, source: str) -> str:
    """Read a lock name, treating missing/empty/blank as the lane's own id."""
    group = entry.get("group")
    if group is None:
        return default
    if not isinstance(group, str):
        raise RegistryError(f"{source}: {label} field 'group' must be a string")
    group = group.strip()
    return group or default


def _validated_link_paths(value, field: str, label: str, source: str) -> list:
    """Validate a registry ``link`` array and return it unchanged.

    Link paths are relative to the workspace root, never to the lane path.
    They must remain inside that root: absolute paths and any ``..`` segment
    are configuration errors rather than something to normalise silently.
    """
    paths = _load_string_array(value, field, label, source)
    for item in paths:
        if not item.strip():
            raise RegistryError(
                f"{source}: {label} field '{field}' entries must be non-empty"
            )
        if os.path.isabs(item):
            raise RegistryError(
                f"{source}: {label} field '{field}' entries must be relative: "
                f"{item!r}"
            )
        if ".." in item.split("/"):
            raise RegistryError(
                f"{source}: {label} field '{field}' entries must not contain "
                f"'..' segments: {item!r}"
            )
    return paths


def _load_lane_fields(
    entry: dict, label: str, source: str, default_group: str
) -> dict:
    """Validate and canonicalise the lane fields shared by both block kinds."""
    result_schema = entry.get("result_schema", RESULT_SCHEMA_DEFAULT)
    if not isinstance(result_schema, str):
        raise RegistryError(
            f"{source}: {label} result_schema must be a string "
            f"(got {type(result_schema).__name__})"
        )
    result_schema = result_schema.strip()
    if result_schema not in (RESULT_SCHEMA_DEFAULT, RESULT_SCHEMA_NONE):
        # Anything else is an absolute path to a custom schema. A missing
        # path is a hard error: silently falling back to the default would
        # change the result contract behind the user's back.
        if not os.path.isabs(result_schema):
            raise RegistryError(
                f"{source}: {label} result_schema must be "
                f"'default', 'none', or an absolute path: {result_schema!r}"
            )
        if not os.path.isfile(result_schema):
            raise RegistryError(
                f"{source}: {label} result_schema file not found: {result_schema}"
            )

    verify_value = entry.get("verify")
    if verify_value is not None and not isinstance(verify_value, str):
        raise RegistryError(f"{source}: {label} field 'verify' must be a string or null")
    if isinstance(verify_value, str) and not verify_value.strip():
        verify_value = None

    verify_kind = entry.get("verify_kind", "none")
    if verify_kind not in VALID_VERIFY_KINDS:
        raise RegistryError(
            f"{source}: {label} has invalid verify_kind "
            f"{verify_kind!r} (expected one of {', '.join(VALID_VERIFY_KINDS)})"
        )
    if verify_value is None:
        # No acceptance command => the task is SKIPPED, never "passed".
        verify_kind = "none"

    forbidden_paths = _load_string_array(
        entry.get("forbidden_paths"), "forbidden_paths", label, source
    )

    workspace = entry.get("workspace", "none")
    if not isinstance(workspace, str):
        raise RegistryError(
            f"{source}: {label} field 'workspace' must be a string "
            f"(got {type(workspace).__name__})"
        )
    workspace = workspace.strip()
    if workspace not in VALID_WORKSPACE_MODES:
        raise RegistryError(
            f"{source}: {label} has invalid workspace {workspace!r} "
            f"(expected one of {', '.join(VALID_WORKSPACE_MODES)})"
        )

    link = _validated_link_paths(entry.get("link"), "link", label, source)
    if link and workspace != "worktree":
        raise RegistryError(
            f"{source}: {label} field 'link' is only valid when "
            "workspace = 'worktree'"
        )

    return {
        "group": _load_group(entry, default_group, label, source),
        "verify": verify_value,
        "verify_kind": verify_kind,
        "forbidden_paths": forbidden_paths,
        "auto_registered": bool(entry.get("auto_registered", False)),
        "result_schema": result_schema,
        "workspace": workspace,
        "link": link,
    }


def load(path: str) -> Registry:
    """Parse and validate a registry file.

    Accepts both block kinds and applies the zero-migration compat rule: a
    ``[[project]]`` carrying any lane field becomes a project + same-named
    taskgroup. A taskgroup that names an unknown project is a hard error.
    """
    if not os.path.exists(path):
        raise RegistryError(f"registry not found: {path}")
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        # tomllib appends "at line N, column M" to its message when it can.
        raise RegistryError(f"invalid TOML in {path}: {exc}")
    except OSError as exc:
        raise RegistryError(f"cannot read registry {path}: {exc}")

    raw_projects = data.get("project", [])
    if not isinstance(raw_projects, list):
        raise RegistryError(f"{path}: 'project' must be an array of tables")
    raw_taskgroups = data.get("taskgroup", [])
    if not isinstance(raw_taskgroups, list):
        raise RegistryError(f"{path}: 'taskgroup' must be an array of tables")

    projects: List[Project] = []
    project_by_id = {}
    legacy_lanes = []
    for index, entry in enumerate(raw_projects):
        if not isinstance(entry, dict):
            raise RegistryError(f"{path}: project #{index + 1} is not a table")
        project_id = _require_field(entry, "id", "project", index, path)
        if project_id in project_by_id:
            raise RegistryError(f"{path}: duplicate project id: {project_id}")
        project_path = entry.get("path")
        if not isinstance(project_path, str) or not project_path.strip():
            raise RegistryError(
                f"{path}: project #{index + 1} is missing a non-empty 'path'"
            )
        if not os.path.isabs(project_path):
            raise RegistryError(
                f"{path}: project '{project_id}' path must be absolute: {project_path}"
            )
        aliases = _load_string_array(
            entry.get("aliases"), "aliases", f"project '{project_id}'", path
        )
        project = Project(id=project_id, path=project_path, aliases=aliases)
        projects.append(project)
        project_by_id[project_id] = project
        if any(field in entry for field in _LANE_FIELDS):
            # Zero-migration compat: this block is a project + a same-named lane.
            lane = _load_lane_fields(
                entry, f"project '{project_id}'", path, default_group=project_id
            )
            legacy_lanes.append((project_id, project_path, lane))

    # Explicit taskgroups are validated against every project we have seen,
    # including the implicit ones created by self-contained taskgroups.
    taskgroups: List[Taskgroup] = []
    taskgroup_ids = {}
    for project_id, project_path, lane in legacy_lanes:
        taskgroups.append(
            Taskgroup(
                id=project_id,
                project=project_id,
                path=project_path,
                aliases=[],
                **lane,
            )
        )
        taskgroup_ids[project_id] = True

    taskgroup_meta = []
    for index, entry in enumerate(raw_taskgroups):
        if not isinstance(entry, dict):
            raise RegistryError(f"{path}: taskgroup #{index + 1} is not a table")
        taskgroup_id = _require_field(entry, "id", "taskgroup", index, path)
        if taskgroup_id in taskgroup_ids:
            raise RegistryError(f"{path}: duplicate taskgroup id: {taskgroup_id}")
        taskgroup_ids[taskgroup_id] = True
        project_field = entry.get("project")
        explicit = isinstance(project_field, str) and bool(project_field.strip())
        owning = project_field.strip() if explicit else taskgroup_id
        taskgroup_meta.append((entry, taskgroup_id, owning, explicit))

    implicit_paths = {}
    for entry, taskgroup_id, owning, explicit in taskgroup_meta:
        if explicit or owning in project_by_id:
            continue
        own_path = entry.get("path")
        if not isinstance(own_path, str) or not own_path.strip():
            raise RegistryError(
                f"{path}: taskgroup '{taskgroup_id}' is self-contained "
                "(no 'project') and needs an absolute 'path'"
            )
        if not os.path.isabs(own_path):
            raise RegistryError(
                f"{path}: taskgroup '{taskgroup_id}' path must be absolute: {own_path}"
            )
        implicit_paths[owning] = own_path

    for entry, taskgroup_id, owning, explicit in taskgroup_meta:
        if explicit and owning not in project_by_id and owning not in implicit_paths:
            raise RegistryError(
                f"{path}: taskgroup '{taskgroup_id}' references unknown project '{owning}'"
            )

    for implicit_id, implicit_path in implicit_paths.items():
        project = Project(id=implicit_id, path=implicit_path, aliases=[])
        projects.append(project)
        project_by_id[implicit_id] = project

    for entry, taskgroup_id, owning, explicit in taskgroup_meta:
        lane = _load_lane_fields(
            entry, f"taskgroup '{taskgroup_id}'", path, default_group=taskgroup_id
        )
        aliases = _load_string_array(
            entry.get("aliases"), "aliases", f"taskgroup '{taskgroup_id}'", path
        )
        taskgroup_path = entry.get("path")
        if isinstance(taskgroup_path, str) and taskgroup_path.strip():
            if not os.path.isabs(taskgroup_path):
                raise RegistryError(
                    f"{path}: taskgroup '{taskgroup_id}' path must be absolute: "
                    f"{taskgroup_path}"
                )
            resolved_path = taskgroup_path
        else:
            resolved_path = project_by_id[owning].path
        taskgroups.append(
            Taskgroup(
                id=taskgroup_id,
                project=owning,
                path=resolved_path,
                aliases=aliases,
                **lane,
            )
        )

    defaults = data.get("defaults", {})
    if not isinstance(defaults, dict):
        raise RegistryError(f"{path}: 'defaults' must be a table")
    return Registry(projects, taskgroups, defaults, source=path)


def workspace_registry_path(workspace: str) -> str:
    return os.path.join(workspace, DEFAULT_REGISTRY_NAME)


# ---------------------------------------------------------------------------
# Surgical registry writes
# ---------------------------------------------------------------------------

#: Keys `update_project` may change on a `[[taskgroup]]` block. `id` is the
#: identity, so it is not mutable; `group` is an editable lock name.
_TASKGROUP_MUTABLE_FIELDS = (
    "project",
    "path",
    "aliases",
    "group",
    "verify",
    "verify_kind",
    "forbidden_paths",
    "result_schema",
)

#: Keys `update_project` may change on a `[[project]]` block. A legacy block can
#: still carry lane fields (that is exactly what makes it dispatchable), and a
#: surgical update must keep that ability; `id` stays immutable.
_PROJECT_MUTABLE_FIELDS = (
    "path",
    "aliases",
    "group",
    "verify",
    "verify_kind",
    "forbidden_paths",
    "result_schema",
)


def taskgroup_record(taskgroup: Taskgroup, probe_flags: Optional[dict] = None) -> dict:
    """JSON-shaped lane data shared by list/create/update responses.

    Shape is the historical ``project`` record: every old key is present, plus
    the new ``project`` (owning project id) field. The API keeps one row per
    lane so the dashboard's ``?project=`` filter is unchanged.
    """
    flags = (probe_flags or {}).get(taskgroup.id) or {}
    probe = flags.get("probe")
    probe_exit = flags.get("probe_exit")
    if probe is None and taskgroup.verify_kind == "none":
        probe = "none"
    # Older CLI registrations wrote only `probe = "passed"`. That verdict can
    # only mean exit 0, so the API can report the missing exit code truthfully.
    if probe == "passed" and probe_exit is None:
        probe_exit = 0
    return {
        "id": taskgroup.id,
        "project": taskgroup.project,
        "path": taskgroup.path,
        "group": taskgroup.group,
        "aliases": list(taskgroup.aliases),
        "verify": taskgroup.verify,
        "verify_kind": taskgroup.verify_kind,
        "forbidden_paths": list(taskgroup.forbidden_paths),
        "result_schema": taskgroup.result_schema,
        "auto_registered": bool(taskgroup.auto_registered),
        "probe": probe,
        "probe_exit": probe_exit,
    }


#: Kept for callers that still spell the record after the old model name.
project_record = taskgroup_record


def _toml_string(value) -> str:
    # JSON strings are valid TOML basic strings for the values used here; using
    # json.dumps also handles quotes, backslashes and control characters.
    return json.dumps(str(value), ensure_ascii=False)


def _array_literal(values) -> str:
    return "[" + ", ".join(_toml_string(value) for value in values) + "]"


def _as_nonempty_string(value, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RegistryError(f"field '{field}' must be a non-empty string")
    return value


def _string_list(value, field: str):
    if value is None:
        return []
    if not isinstance(value, list):
        raise RegistryError(f"field '{field}' must be an array of strings")
    for item in value:
        if not isinstance(item, str):
            raise RegistryError(f"field '{field}' must be an array of strings")
    return list(value)


def _normalise_group(entry: dict, default: str) -> str:
    group = entry.get("group")
    if group is None or group == "":
        return default
    if not isinstance(group, str):
        raise RegistryError("field 'group' must be a string")
    group = group.strip()
    return group or default


def _normalise_lane_fields(entry: dict, label: str, default_group: str) -> dict:
    verify_value = entry.get("verify")
    if verify_value is not None and not isinstance(verify_value, str):
        raise RegistryError("field 'verify' must be a string or null")
    verify_value = verify_value.strip() if isinstance(verify_value, str) else None
    if not verify_value:
        verify_value = None

    verify_kind = entry.get("verify_kind", "none")
    if verify_kind is None:
        verify_kind = "none"
    if verify_kind not in VALID_VERIFY_KINDS:
        raise RegistryError(
            f"'{label}' has invalid verify_kind {verify_kind!r} "
            f"(expected one of {', '.join(VALID_VERIFY_KINDS)})"
        )
    if verify_value is None:
        verify_kind = "none"

    forbidden_paths = _string_list(entry.get("forbidden_paths"), "forbidden_paths")

    result_schema = entry.get("result_schema", RESULT_SCHEMA_DEFAULT)
    if result_schema is None or result_schema == "":
        result_schema = RESULT_SCHEMA_DEFAULT
    if not isinstance(result_schema, str):
        raise RegistryError("field 'result_schema' must be a string")
    if result_schema not in (RESULT_SCHEMA_DEFAULT, RESULT_SCHEMA_NONE):
        if not os.path.isabs(result_schema):
            raise RegistryError(
                "field 'result_schema' must be 'default', 'none', "
                "or an absolute path"
            )
        if not os.path.isfile(result_schema):
            raise RegistryError(f"result_schema file not found: {result_schema}")

    probe = entry.get("probe")
    if probe is not None and not isinstance(probe, str):
        raise RegistryError("field 'probe' must be a string")
    probe_exit = entry.get("probe_exit")
    if probe_exit is not None:
        if isinstance(probe_exit, bool) or not isinstance(probe_exit, int):
            raise RegistryError("field 'probe_exit' must be an integer")

    return {
        "group": _normalise_group(entry, default_group),
        "verify": verify_value,
        "verify_kind": verify_kind,
        "forbidden_paths": forbidden_paths,
        "result_schema": result_schema,
        "probe": probe,
        "probe_exit": probe_exit,
    }


def _normalise_project(entry: dict) -> dict:
    """Validate and canonicalise one `[[project]]` block before rendering."""
    if not isinstance(entry, dict):
        raise RegistryError("project entry must be a table")
    project_id = _as_nonempty_string(entry.get("id"), "id")
    path = _as_nonempty_string(entry.get("path"), "path")
    if not os.path.isabs(path):
        raise RegistryError(f"project '{project_id}' path must be absolute: {path}")
    aliases = _string_list(entry.get("aliases"), "aliases")
    lane = _normalise_lane_fields(entry, project_id, default_group=project_id)
    return {"id": project_id, "path": path, "aliases": aliases, **lane}


def _normalise_taskgroup(entry: dict, project_path: Optional[str] = None) -> dict:
    """Validate and canonicalise one `[[taskgroup]]` block before rendering."""
    if not isinstance(entry, dict):
        raise RegistryError("taskgroup entry must be a table")
    taskgroup_id = _as_nonempty_string(entry.get("id"), "id")
    project = entry.get("project")
    if project is None or project == "":
        project = taskgroup_id
    project = _as_nonempty_string(project, "project")

    path = entry.get("path")
    if path is None or path == "":
        path = project_path
    if path is not None:
        path = _as_nonempty_string(path, "path")
        if not os.path.isabs(path):
            raise RegistryError(
                f"taskgroup '{taskgroup_id}' path must be absolute: {path}"
            )

    aliases = _string_list(entry.get("aliases"), "aliases")
    lane = _normalise_lane_fields(
        entry, taskgroup_id, default_group=taskgroup_id
    )
    return {
        "id": taskgroup_id,
        "project": project,
        "path": path,
        "aliases": aliases,
        **lane,
    }


def _format_taskgroup_block(taskgroup: dict) -> str:
    lines = [
        "[[taskgroup]]",
        f"id = {_toml_string(taskgroup['id'])}",
    ]
    if taskgroup["project"] != taskgroup["id"]:
        lines.append(f"project = {_toml_string(taskgroup['project'])}")
    if taskgroup["path"] is not None:
        lines.append(f"path = {_toml_string(taskgroup['path'])}")
    if taskgroup["aliases"]:
        lines.append(f"aliases = {_array_literal(taskgroup['aliases'])}")
    if taskgroup["group"] != taskgroup["id"]:
        lines.append(f"group = {_toml_string(taskgroup['group'])}")
    if taskgroup["verify"]:
        lines.append(f"verify = {_toml_string(taskgroup['verify'])}")
    lines.append(f"verify_kind = {_toml_string(taskgroup['verify_kind'])}")
    if taskgroup["forbidden_paths"]:
        lines.append(
            f"forbidden_paths = {_array_literal(taskgroup['forbidden_paths'])}"
        )
    if taskgroup["result_schema"] != RESULT_SCHEMA_DEFAULT:
        lines.append(f"result_schema = {_toml_string(taskgroup['result_schema'])}")
    if taskgroup["probe"] is not None:
        lines.append(f"probe = {_toml_string(taskgroup['probe'])}")
    if taskgroup["probe_exit"] is not None:
        lines.append(f"probe_exit = {taskgroup['probe_exit']}")
    return "\n".join(lines) + "\n"


def _render_value(key: str, value) -> str:
    if key in ("aliases", "forbidden_paths"):
        return _array_literal(value)
    if key == "probe_exit":
        return str(value)
    return _toml_string(value)


def _block_kind(line: str) -> Optional[str]:
    if _TASKGROUP_HEADER_RE.match(line):
        return "taskgroup"
    if _PROJECT_HEADER_RE.match(line):
        return "project"
    return None


def _block_entry(lines, start: int, end: int) -> Optional[dict]:
    text = "".join(lines[start:end])
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return None
    for table in ("taskgroup", "project"):
        entries = data.get(table, []) or []
        if entries and isinstance(entries[0], dict):
            return entries[0]
    return None


def _block_spans(lines):
    """Every ``[[project]]`` / ``[[taskgroup]]`` block, in file order.

    Each span carries its kind, its parsed ``id`` and the parsed entry. Both
    kinds live in one list so an id can be located without relying on the
    per-table ordering tomllib loses.
    """
    spans = []
    for index, line in enumerate(lines):
        kind = _block_kind(line)
        if kind is None:
            continue
        end = len(lines)
        for probe in range(index + 1, len(lines)):
            if _TABLE_HEADER_RE.match(lines[probe]):
                end = probe
                break
        entry = _block_entry(lines, index, end)
        entry_id = entry.get("id") if isinstance(entry, dict) else None
        spans.append(
            {
                "start": index,
                "end": end,
                "kind": kind,
                "id": entry_id,
                "data": entry if isinstance(entry, dict) else {},
            }
        )
    return spans


def _find_block(spans, entry_id: str):
    """Locate a block by id, preferring a ``[[taskgroup]]`` over a project."""
    for span in spans:
        if span["kind"] == "taskgroup" and span["id"] == entry_id:
            return span
    for span in spans:
        if span["kind"] == "project" and span["id"] == entry_id:
            return span
    return None


def _parsed_data(text: str) -> dict:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise RegistryError(f"invalid TOML: {exc}")
    for table in ("project", "taskgroup"):
        entries = data.get(table, [])
        if not isinstance(entries, list):
            raise RegistryError(f"'{table}' must be an array of tables")
    return data


def _raw_block_count(data: dict) -> int:
    return len(data.get("project", []) or []) + len(data.get("taskgroup", []) or [])


def _raw_block_ids(data: dict) -> list:
    ids = []
    for table in ("project", "taskgroup"):
        for entry in data.get(table, []) or []:
            if isinstance(entry, dict):
                ids.append(entry.get("id"))
    return ids


def _set_key(lines, start: int, end: int, key: str, rendered, *, remove=False):
    """Replace/add/remove one top-level key within a block.

    Returns the updated block end. Only lines in the target block are touched.
    """
    key_index = None
    insertion_at = start + 1
    for index in range(start + 1, end):
        line = lines[index]
        if _TABLE_HEADER_RE.match(line):
            break
        if _KEY_RE.match(line):
            insertion_at = index + 1
            stripped = line.lstrip()
            if stripped.split("=", 1)[0].strip() == key:
                key_index = index
                break

    if remove:
        if key_index is None:
            return end
        del lines[key_index]
        return end - 1

    if key_index is not None:
        line = lines[key_index]
        newline = "\r\n" if line.endswith("\r\n") else ("\n" if line.endswith("\n") else "")
        indent = line[: len(line) - len(line.lstrip())]
        lines[key_index] = f"{indent}{key} = {rendered}{newline}"
        return end

    newline = "\r\n" if any(line.endswith("\r\n") for line in lines) else "\n"
    lines.insert(insertion_at, f"{key} = {rendered}{newline}")
    return end + 1


def _strip_owned_comments(lines, start: int) -> int:
    """Move a block start upwards over comments not separated by a blank line."""
    while start > 0:
        line = lines[start - 1]
        if line.strip().startswith("#"):
            start -= 1
            continue
        break
    return start


def _block_content_end(lines, start: int, end: int) -> int:
    """Index just past the last key line of a block.

    Lines after that are left alone. A comment run touching the *next* block's
    header belongs to that block; a blank-separated run is its upstream note.
    Deleting this block must not take either with it.
    """
    last = start
    for index in range(start + 1, end):
        line = lines[index]
        if _TABLE_HEADER_RE.match(line):
            break
        if _KEY_RE.match(line):
            last = index
    return last + 1


def _conflict(path: str, data: bytes) -> RegistryConflictError:
    try:
        lanes = [taskgroup_record(tg) for tg in load(path).taskgroups]
    except RegistryError:
        lanes = []
    return RegistryConflictError(
        hashlib.sha256(data).hexdigest(),
        data.decode("utf-8", errors="replace"),
        lanes,
    )


def _check_expected(path: str, data: bytes, expected_hash: str):
    if not isinstance(expected_hash, str) or not expected_hash:
        raise RegistryError("expected_hash is required")
    current_hash = hashlib.sha256(data).hexdigest()
    if expected_hash != current_hash:
        raise _conflict(path, data)
    return current_hash


def _atomic_replace(path: str, text: str, *, expected_blocks: int, expected_id=None):
    # Parse before creating a temp file so obvious failures never touch disk.
    data = _parsed_data(text)
    ids = _raw_block_ids(data)
    if len(ids) != expected_blocks:
        raise RegistryError(
            f"registry block count changed: expected {expected_blocks}, got {len(ids)}"
        )
    if expected_id is not None and expected_id not in ids:
        raise RegistryError(f"block id missing after write: {expected_id}")

    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    file_descriptor, temp_path = tempfile.mkstemp(
        prefix=".projects.", suffix=".tmp", dir=directory
    )
    os.close(file_descriptor)
    try:
        with open(temp_path, "wb") as handle:
            handle.write(text.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())

        # `load` is the same validator used by every read path, so a write can
        # never leave a file that the rest of taskproof refuses to parse.
        load(temp_path)

        try:
            os.chmod(temp_path, os.stat(path).st_mode & 0o7777)
        except OSError:
            pass
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def append_taskgroup(path: str, expected_hash: str, entry: dict):
    """Append one ``[[taskgroup]]`` block, preserving every existing byte.

    A taskgroup with no ``project`` stands up a same-named project (the compat
    rule), so ``taskproof register`` stays a one-block write. The candidate is
    still validated by ``load`` before it replaces the file.
    """
    with _WRITE_LOCK:
        data = _read_bytes(path)
        _check_expected(path, data, expected_hash)
        text = data.decode("utf-8")
        parsed = _parsed_data(text)
        count = _raw_block_count(parsed)
        normalised = _normalise_taskgroup(entry)
        if text and not text.endswith("\n"):
            text += "\n"
        candidate = text + ("\n" if text else "") + _format_taskgroup_block(normalised)
        _atomic_replace(
            path,
            candidate,
            expected_blocks=count + 1,
            expected_id=normalised["id"],
        )
        return normalised


def update_project(path: str, entry_id: str, expected_hash: str, changes: dict):
    """Update only the named keys in one block (``[[taskgroup]]`` or ``[[project]]``).

    Surgical: only the lines for the named keys move, so hand-written comments,
    unknown keys and every other block survive byte-for-byte. The candidate is
    validated (and the expected hash re-checked) before an atomic replace.
    """
    if not isinstance(entry_id, str) or not entry_id:
        raise RegistryError("project id is required")
    everywhere = set(_TASKGROUP_MUTABLE_FIELDS) | set(_PROJECT_MUTABLE_FIELDS)
    unknown = set(changes) - everywhere
    if unknown:
        raise RegistryError(f"unsupported project field(s): {', '.join(sorted(unknown))}")

    with _WRITE_LOCK:
        data = _read_bytes(path)
        _check_expected(path, data, expected_hash)
        text = data.decode("utf-8")
        lines = text.splitlines(keepends=True)
        parsed = _parsed_data(text)
        count = _raw_block_count(parsed)
        spans = _block_spans(lines)
        target = _find_block(spans, entry_id)
        if target is None:
            raise RegistryNotFoundError(f"project not found: {entry_id}")

        allowed = (
            _TASKGROUP_MUTABLE_FIELDS
            if target["kind"] == "taskgroup"
            else _PROJECT_MUTABLE_FIELDS
        )
        unknown = set(changes) - set(allowed)
        if unknown:
            raise RegistryError(
                f"unsupported {target['kind']} field(s): {', '.join(sorted(unknown))}"
            )

        merged = dict(target["data"])
        merged.update(changes)
        if target["kind"] == "taskgroup":
            normalised = _normalise_taskgroup(merged)
        else:
            normalised = _normalise_project(merged)

        start, end = target["start"], target["end"]
        for key in changes:
            value = changes[key]
            if value is None:
                end = _set_key(lines, start, end, key, None, remove=True)
                continue
            end = _set_key(lines, start, end, key, _render_value(key, normalised[key]))

        if (
            "verify" in changes
            and changes["verify"] is None
            and "verify_kind" not in changes
        ):
            end = _set_key(
                lines, start, end, "verify_kind", _render_value("verify_kind", "none")
            )

        candidate = "".join(lines)
        _atomic_replace(
            path,
            candidate,
            expected_blocks=count,
            expected_id=entry_id,
        )
        return normalised


def delete_project(path: str, entry_id: str, expected_hash: str):
    """Delete one block (``[[taskgroup]]`` or ``[[project]]``) and its comments."""
    with _WRITE_LOCK:
        data = _read_bytes(path)
        _check_expected(path, data, expected_hash)
        text = data.decode("utf-8")
        lines = text.splitlines(keepends=True)
        parsed = _parsed_data(text)
        count = _raw_block_count(parsed)
        spans = _block_spans(lines)
        target = _find_block(spans, entry_id)
        if target is None:
            raise RegistryNotFoundError(f"project not found: {entry_id}")

        start, end = target["start"], target["end"]
        owned_start = _strip_owned_comments(lines, start)
        body_end = _block_content_end(lines, start, end)
        del lines[owned_start:body_end]
        candidate = "".join(lines)
        _atomic_replace(
            path,
            candidate,
            expected_blocks=count - 1,
        )
        return entry_id


# ---------------------------------------------------------------------------
# `[defaults]` writer (card 42) — surgical, comment-preserving.
# ---------------------------------------------------------------------------
#
# `taskproof config --concurrency N` / `--timeout N` must NOT round-trip the
# registry through a TOML renderer: that drops trailing comments such as
#     `concurrency = 3   # global cap on simultaneous tasks`
# Instead we locate the one assignment for the key inside `[defaults]` and swap
# only its numeric value, keeping the key, the `=` spacing, the trailing comment
# and the line ending byte-for-byte. Adding a key the table lacks inserts a
# single line; everything else — blank lines, `[[project]]` / `[[taskgroup]]`
# blocks, every comment and every other key — is carried through verbatim.
#
# The final write rides the same `tempfile.mkstemp` + `os.replace` path as the
# block CRUD (`_atomic_replace`), so a crash mid-write can never truncate the
# registry and a candidate the loader rejects never reaches disk.

_DEFAULTS_HEADER_RE = re.compile(r"^\s*\[defaults\]\s*(?:#.*)?(?:\r?\n)?$")
_DEFAULTS_KEYS = ("concurrency", "timeout")
_ASSIGN_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<key>[A-Za-z0-9_-]+)\s*=")


def _defaults_span(lines):
    """``(start, end)`` line indices of the `[defaults]` table, or ``None``.

    ``end`` is the next table header (any `[...]` / `[[...]]`) or EOF, so the
    scan never strays into a `[[project]]` / `[[taskgroup]]` block.
    """
    for index, line in enumerate(lines):
        if _DEFAULTS_HEADER_RE.match(line):
            end = len(lines)
            for probe in range(index + 1, len(lines)):
                if _TABLE_HEADER_RE.match(lines[probe]):
                    end = probe
                    break
            return index, end
    return None


def _swap_default_value(line: str, value: int) -> str:
    """Return ``line`` with only the numeric value swapped for ``value``.

    Keeps the key, the ``=`` spacing, any trailing comment and the line ending.
    """
    body, eol = line, ""
    if body.endswith("\r\n"):
        body, eol = body[:-2], "\r\n"
    elif body.endswith("\n"):
        body, eol = body[:-1], "\n"
    head, sep, tail = body.partition("=")
    comment = ""
    if "#" in tail:
        tail, _, comment = tail.partition("#")
        comment = "#" + comment
    lead = tail[: len(tail) - len(tail.lstrip())]
    gap = tail[len(tail.rstrip()):]
    return f"{head}{sep}{lead}{value}{gap}{comment}{eol}"


def _upsert_default(lines, key: str, value: int) -> None:
    """Replace, or else add, ``key``'s assignment inside `[defaults]`."""
    span = _defaults_span(lines)
    if span is None:
        newline = "\r\n" if any(line.endswith("\r\n") for line in lines) else "\n"
        if lines and not lines[-1].endswith(("\n", "\r")):
            lines[-1] += newline
        if lines and lines[-1].strip():
            lines.append(newline)
        lines.append(f"[defaults]{newline}")
        lines.append(f"{key} = {value}{newline}")
        return

    start, end = span
    insert_at = start + 1
    indent = ""
    for index in range(start + 1, end):
        match = _ASSIGN_RE.match(lines[index])
        if match is None:
            continue
        if match.group("key") == key:
            lines[index] = _swap_default_value(lines[index], value)
            return
        insert_at = index + 1
        indent = match.group("indent")
    newline = "\r\n" if any(line.endswith("\r\n") for line in lines) else "\n"
    lines.insert(insert_at, f"{indent}{key} = {value}{newline}")


def set_default(path: str, key: str, value, *, expected_hash: Optional[str] = None) -> int:
    """Set one `[defaults]` key in place, preserving every other byte.

    Returns the integer written. Validates the key and the value here (the CLI
    rejects out-of-range values first, so the error a caller actually sees names
    the usable range). Creates the sample registry when the file is missing.
    """
    if key not in _DEFAULTS_KEYS:
        raise RegistryError(f"unknown default key: {key}")
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise RegistryError(f"{key} must be an integer")
    if number < 1:
        raise RegistryError(f"{key} must be >= 1")
    with _WRITE_LOCK:
        if os.path.exists(path):
            data = _read_bytes(path)
            if expected_hash is not None:
                _check_expected(path, data, expected_hash)
            text = data.decode("utf-8")
            parsed = _parsed_data(text)
            count = _raw_block_count(parsed)
        else:
            text = SAMPLE_REGISTRY
            count = 0
        lines = text.splitlines(keepends=True)
        _upsert_default(lines, key, number)
        candidate = "".join(lines)
        _atomic_replace(path, candidate, expected_blocks=count)
        return number


#: What a brand-new workspace starts from. Deliberately holds no blocks.
#:
#: An example entry used to be seeded here, pointing at `/absolute/path/to/my-app`.
#: Its path was a placeholder, so `taskproof projects` -- and the dashboard --
#: listed a repository that did not exist until someone deleted the block. A
#: fresh registry that is honestly empty is better than one that lies.
#: The format lives in `examples/projects.example.toml` and `docs/REGISTRY.md`.
SAMPLE_REGISTRY = """\
# taskproof registry
#
# Two layers: a [[project]] names a repository, and one or more [[taskgroup]]
# lanes hang off it with their own acceptance command. `taskproof register`
# writes a [[taskgroup]]; a legacy [[project]] block that carries verify /
# verify_kind / forbidden_paths / result_schema is still read as a same-named
# project + lane (zero migration).
#
# No projects yet: `taskproof register <path>` appends one.
# A commented, complete example: examples/projects.example.toml
# Field reference: docs/REGISTRY.md

[defaults]
# Global cap on simultaneous tasks. Left unset, taskproof auto-detects it from
# this machine (clamp(2, cores // 4, 6); 2 when RAM < 8 GB). Uncomment and edit
# to pin an explicit value, or use `taskproof config --concurrency N`.
# concurrency = 3
timeout = 1800    # seconds before a task is judged stuck
"""
