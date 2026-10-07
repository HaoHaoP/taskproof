"""Project registry.

Format: TOML, parsed with the standard library (`tomllib`, Python 3.11+).
Not YAML — YAML would require PyYAML, and this package is standard-library only.

The registry is CONFIGURATION: human-editable, meant to be committed to the
user's own repository. Runtime state lives in SQLite (see storage.py).

Example
-------
    [defaults]
    concurrency = 3
    timeout = 1800

    [[project]]
    id = "my-app"
    path = "/home/me/code/my-app"
    group = "my-app"
    aliases = ["app"]
    verify = "npm run build"
    verify_kind = "build"
    forbidden_paths = [".git/", "dist/"]
    result_schema = "default"   # "default" | "none" | "/abs/path.json"

Resolution accepts an id, an alias, or a filesystem path.
"""

import os
import tomllib
from typing import List, Optional

from .errors import RegistryError
from .models import Project

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


def builtin_result_schema_path() -> str:
    """Absolute path to the package-shipped default result schema."""
    return BUILTIN_RESULT_SCHEMA


def result_schema_path(project: Project) -> Optional[str]:
    """Resolve a project's `result_schema` setting to an argv-ready path.

    * omitted / ``"default"`` -> the package-shipped ``schemas/result.json``
    * ``"none"``              -> ``None`` (structured result disabled)
    * any other string        -> the absolute path validated at load time

    Returning ``None`` is the ONLY way structured output is turned off, and it
    is always paired with an explicit event at dispatch time — a run never
    silently falls back to free text.
    """
    value = project.result_schema
    if value == RESULT_SCHEMA_NONE:
        return None
    if not value or value == RESULT_SCHEMA_DEFAULT:
        return BUILTIN_RESULT_SCHEMA
    return value


class Registry:
    """Loaded registry: projects plus global defaults."""

    def __init__(self, projects: List[Project], defaults: dict, source: Optional[str] = None):
        self.projects = projects
        self.defaults = defaults or {}
        self.source = source

    # -- lookup -----------------------------------------------------------

    def by_id(self, key: str) -> Optional[Project]:
        """Resolve by exact id, then by alias, then by path."""
        for project in self.projects:
            if project.id == key:
                return project
        for project in self.projects:
            if key in project.aliases:
                return project
        for project in self.projects:
            if project.path == key:
                return project
        # A path may be spelled differently (trailing slash, `~`, `..`);
        # compare normalised absolute forms as a fallback.
        if os.path.isabs(key):
            norm = os.path.normpath(key)
            for project in self.projects:
                if os.path.normpath(project.path) == norm:
                    return project
        return None

    def require(self, key: str) -> Project:
        proj = self.by_id(key)
        if proj is None:
            known = ", ".join(sorted(p.id for p in self.projects)) or "(none)"
            raise RegistryError(
                f"project not found: {key}",
                hint=f"registered projects: {known}",
            )
        return proj

    # -- defaults ---------------------------------------------------------

    @property
    def concurrency(self) -> int:
        return int(self.defaults.get("concurrency", 3))

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
    """Map the caller's context to one project (or all), plus a source label.

    Returns ``(project_id_or_None, source_label)``. ``None`` means "all
    projects". Priority is fixed and deliberately boring:

        ``--project`` > ``--all`` > cwd inference > all (when cwd is outside)

    cwd inference matches a registered project when the working directory is
    that project's directory *or* a descendant. Symlinks are resolved first
    (macOS spells ``/tmp`` and ``/private/tmp`` differently), and the *longest*
    matching project path wins so a nested project beats its parent repo.
    """
    if explicit_project:
        project = reg.by_id(explicit_project) if reg is not None else None
        return (project.id if project is not None else explicit_project), SCOPE_FROM_PROJECT
    if force_all:
        return None, SCOPE_FROM_ALL

    if cwd is None:
        cwd = os.getcwd()
    target = os.path.realpath(cwd)
    best = None
    best_len = -1
    for project in (reg.projects if reg is not None else []):
        project_path = os.path.realpath(project.path)
        if target == project_path or target.startswith(project_path + os.sep):
            if len(project_path) > best_len:
                best_len = len(project_path)
                best = project
    if best is not None:
        return best.id, SCOPE_FROM_CWD
    return None, SCOPE_OUTSIDE


VALID_VERIFY_KINDS = ("check", "build", "none")


def _require(entry: dict, field: str, index: int, source: str) -> str:
    value = entry.get(field)
    if not isinstance(value, str) or not value.strip():
        raise RegistryError(
            f"{source}: project #{index + 1} is missing a non-empty '{field}'"
        )
    return value


def load(path: str) -> Registry:
    """Parse and validate a registry file."""
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

    projects: List[Project] = []
    seen: dict = {}
    for index, entry in enumerate(raw_projects):
        if not isinstance(entry, dict):
            raise RegistryError(f"{path}: project #{index + 1} is not a table")
        project_id = _require(entry, "id", index, path)
        project_path = _require(entry, "path", index, path)
        if not os.path.isabs(project_path):
            raise RegistryError(
                f"{path}: project '{project_id}' path must be absolute: {project_path}"
            )
        if project_id in seen:
            raise RegistryError(f"{path}: duplicate project id: {project_id}")
        seen[project_id] = True

        result_schema = entry.get("result_schema", RESULT_SCHEMA_DEFAULT)
        if not isinstance(result_schema, str):
            raise RegistryError(
                f"{path}: project '{project_id}' result_schema must be a string "
                f"(got {type(result_schema).__name__})"
            )
        result_schema = result_schema.strip()
        if result_schema not in (RESULT_SCHEMA_DEFAULT, RESULT_SCHEMA_NONE):
            # Anything else is an absolute path to a custom schema. A missing
            # path is a hard error: silently falling back to the default would
            # change the result contract behind the user's back.
            if not os.path.isabs(result_schema):
                raise RegistryError(
                    f"{path}: project '{project_id}' result_schema must be "
                    f"'default', 'none', or an absolute path: {result_schema!r}"
                )
            if not os.path.isfile(result_schema):
                raise RegistryError(
                    f"{path}: project '{project_id}' result_schema file not "
                    f"found: {result_schema}"
                )

        verify = entry.get("verify")
        if isinstance(verify, str) and not verify.strip():
            verify = None
        verify_kind = entry.get("verify_kind", "none")
        if verify_kind not in VALID_VERIFY_KINDS:
            raise RegistryError(
                f"{path}: project '{project_id}' has invalid verify_kind "
                f"{verify_kind!r} (expected one of {', '.join(VALID_VERIFY_KINDS)})"
            )
        if verify is None:
            # No acceptance command => the task is SKIPPED, never "passed".
            verify_kind = "none"

        projects.append(
            Project(
                id=project_id,
                path=project_path,
                group=entry.get("group") or "default",
                aliases=list(entry.get("aliases") or []),
                verify=verify,
                verify_kind=verify_kind,
                forbidden_paths=list(entry.get("forbidden_paths") or []),
                auto_registered=bool(entry.get("auto_registered", False)),
                result_schema=result_schema,
            )
        )

    defaults = data.get("defaults", {})
    if not isinstance(defaults, dict):
        raise RegistryError(f"{path}: 'defaults' must be a table")
    return Registry(projects, defaults, source=path)


def workspace_registry_path(workspace: str) -> str:
    return os.path.join(workspace, DEFAULT_REGISTRY_NAME)


SAMPLE_REGISTRY = """\
# taskproof project registry
#
# One [[project]] block per repository. Paths are absolute.
# `group` controls serialisation: only one task per group runs at a time.

[defaults]
concurrency = 3   # global cap on simultaneous tasks
timeout = 1800    # seconds before a task is judged stuck

[[project]]
id = "my-app"
path = "/absolute/path/to/my-app"
group = "my-app"
aliases = ["app"]
verify = "npm run build"
verify_kind = "build"
forbidden_paths = [".git/"]
"""
