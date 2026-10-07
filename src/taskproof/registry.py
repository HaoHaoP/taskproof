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

Resolution accepts an id, an alias, or a filesystem path.
"""

import os
import tomllib
from typing import List, Optional

from .errors import RegistryError
from .models import Project

DEFAULT_REGISTRY_NAME = "projects.toml"


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
