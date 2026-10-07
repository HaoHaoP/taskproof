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
        raise NotImplementedError("card: registry")

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


def load(path: str) -> Registry:
    """Parse and validate a registry file."""
    raise NotImplementedError("card: registry")


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
