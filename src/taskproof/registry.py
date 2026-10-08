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

import hashlib
import json
import os
import re
import tempfile
import threading
import tomllib
from typing import List, Optional

from . import verify
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
_TABLE_HEADER_RE = re.compile(r"^\s*\[\[?[^\]]+\]\]?\s*(?:#.*)?(?:\r?\n)?$")
_KEY_RE = re.compile(r"^\s*[A-Za-z0-9_-]+\s*=")


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


def infer_verify(path: str):
    """Return (command, verify_kind) for the first recognised build file."""
    for name, command, kind in _BUILD_FILES:
        if os.path.isfile(os.path.join(path, name)):
            return command, kind
    return None, "none"


def probe_repository(path: str) -> dict:
    """Build the registration draft for one repository without writing state.

    The CLI and the API both use this so "what register would infer" cannot
    drift between the two entry points.
    """
    path = os.path.abspath(os.path.expanduser(path))
    project_id = os.path.basename(os.path.normpath(path)) or path
    command, kind = infer_verify(path)
    probe = None
    probe_exit = None
    if command is not None:
        outcome = verify.run_acceptance(path, command, timeout=_PROBE_TIMEOUT)
        probe = "passed" if outcome.passed else "failed"
        probe_exit = outcome.exit_code
    return {
        "id": project_id,
        "path": path,
        "group": project_id,
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


def read_probe_flags(path: str) -> dict:
    """Return raw probe metadata keyed by project id.

    ``registry.load`` intentionally keeps only fields it understands; probe
    results are human/API metadata, so they are read from the TOML source just
    like ``cli._read_probe_flags`` does.
    """
    flags = {}
    try:
        with open(path, "rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return flags
    for entry in data.get("project", []) or []:
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


# ---------------------------------------------------------------------------
# Surgical registry writes
# ---------------------------------------------------------------------------

_MUTABLE_FIELDS = (
    "aliases",
    "group",
    "verify",
    "verify_kind",
    "forbidden_paths",
    "result_schema",
)


def project_record(project: Project, probe_flags: Optional[dict] = None) -> dict:
    """JSON-shaped project data shared by list/create/update responses."""
    flags = (probe_flags or {}).get(project.id) or {}
    probe = flags.get("probe")
    probe_exit = flags.get("probe_exit")
    if probe is None and project.verify_kind == "none":
        probe = "none"
    # Older CLI registrations wrote only `probe = "passed"`. That verdict can
    # only mean exit 0, so the API can report the missing exit code truthfully.
    if probe == "passed" and probe_exit is None:
        probe_exit = 0
    return {
        "id": project.id,
        "path": project.path,
        "group": project.group,
        "aliases": list(project.aliases),
        "verify": project.verify,
        "verify_kind": project.verify_kind,
        "forbidden_paths": list(project.forbidden_paths),
        "result_schema": project.result_schema,
        "auto_registered": bool(project.auto_registered),
        "probe": probe,
        "probe_exit": probe_exit,
    }


def _toml_string(value) -> str:
    # JSON strings are valid TOML basic strings for the values used here; using
    # json.dumps also handles quotes, backslashes and control characters.
    return json.dumps(str(value), ensure_ascii=False)


def _array_literal(values) -> str:
    return "[" + ", ".join(_toml_string(value) for value in values) + "]"


def _as_nonempty_string(value, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RegistryError(f"project field '{field}' must be a non-empty string")
    return value


def _string_list(value, field: str):
    if value is None:
        return []
    if not isinstance(value, list):
        raise RegistryError(f"project field '{field}' must be an array of strings")
    for item in value:
        if not isinstance(item, str):
            raise RegistryError(f"project field '{field}' must be an array of strings")
    return list(value)


def _normalise_project(entry: dict) -> dict:
    """Validate and canonicalise one project entry before rendering it."""
    if not isinstance(entry, dict):
        raise RegistryError("project entry must be a table")
    project_id = _as_nonempty_string(entry.get("id"), "id")
    path = _as_nonempty_string(entry.get("path"), "path")
    if not os.path.isabs(path):
        raise RegistryError(f"project '{project_id}' path must be absolute: {path}")

    group = entry.get("group")
    if group is None:
        group = project_id
    group = _as_nonempty_string(group, "group")

    aliases = _string_list(entry.get("aliases"), "aliases")
    forbidden_paths = _string_list(entry.get("forbidden_paths"), "forbidden_paths")

    verify_value = entry.get("verify")
    if verify_value is not None and not isinstance(verify_value, str):
        raise RegistryError("project field 'verify' must be a string or null")
    verify_value = verify_value.strip() if isinstance(verify_value, str) else None
    if not verify_value:
        verify_value = None

    verify_kind = entry.get("verify_kind", "none")
    if verify_kind is None:
        verify_kind = "none"
    if verify_kind not in VALID_VERIFY_KINDS:
        raise RegistryError(
            f"project '{project_id}' has invalid verify_kind {verify_kind!r} "
            f"(expected one of {', '.join(VALID_VERIFY_KINDS)})"
        )
    if verify_value is None:
        verify_kind = "none"

    result_schema = entry.get("result_schema", RESULT_SCHEMA_DEFAULT)
    if result_schema is None or result_schema == "":
        result_schema = RESULT_SCHEMA_DEFAULT
    if not isinstance(result_schema, str):
        raise RegistryError("project field 'result_schema' must be a string")
    if result_schema not in (RESULT_SCHEMA_DEFAULT, RESULT_SCHEMA_NONE):
        if not os.path.isabs(result_schema):
            raise RegistryError(
                "project field 'result_schema' must be 'default', 'none', "
                "or an absolute path"
            )
        if not os.path.isfile(result_schema):
            raise RegistryError(
                f"result_schema file not found: {result_schema}"
            )

    probe = entry.get("probe")
    if probe is not None and not isinstance(probe, str):
        raise RegistryError("project field 'probe' must be a string")
    probe_exit = entry.get("probe_exit")
    if probe_exit is not None:
        if isinstance(probe_exit, bool) or not isinstance(probe_exit, int):
            raise RegistryError("project field 'probe_exit' must be an integer")

    return {
        "id": project_id,
        "path": path,
        "group": group,
        "aliases": aliases,
        "verify": verify_value,
        "verify_kind": verify_kind,
        "forbidden_paths": forbidden_paths,
        "result_schema": result_schema,
        "probe": probe,
        "probe_exit": probe_exit,
    }


def _format_project_block(project: dict) -> str:
    lines = [
        "[[project]]",
        f"id = {_toml_string(project['id'])}",
        f"path = {_toml_string(project['path'])}",
        f"group = {_toml_string(project['group'])}",
    ]
    if project["verify"]:
        lines.append(f"verify = {_toml_string(project['verify'])}")
        lines.append(f"verify_kind = {_toml_string(project['verify_kind'])}")
    else:
        lines.append('verify_kind = "none"')
    if project["aliases"]:
        lines.append(f"aliases = {_array_literal(project['aliases'])}")
    if project["forbidden_paths"]:
        lines.append(
            f"forbidden_paths = {_array_literal(project['forbidden_paths'])}"
        )
    if project["result_schema"] != RESULT_SCHEMA_DEFAULT:
        lines.append(f"result_schema = {_toml_string(project['result_schema'])}")
    if project["probe"] is not None:
        lines.append(f"probe = {_toml_string(project['probe'])}")
    if project["probe_exit"] is not None:
        lines.append(f"probe_exit = {project['probe_exit']}")
    return "\n".join(lines) + "\n"


def _render_value(key: str, value) -> str:
    if key in ("aliases", "forbidden_paths"):
        return _array_literal(value)
    if key == "probe_exit":
        return str(value)
    return _toml_string(value)


def _project_spans(lines):
    starts = [index for index, line in enumerate(lines) if _PROJECT_HEADER_RE.match(line)]
    spans = []
    for start in starts:
        end = len(lines)
        for index in range(start + 1, len(lines)):
            if _TABLE_HEADER_RE.match(lines[index]):
                end = index
                break
        spans.append((start, end))
    return spans


def _parsed_data(text: str) -> dict:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise RegistryError(f"invalid TOML: {exc}")
    projects = data.get("project", [])
    if not isinstance(projects, list):
        raise RegistryError("'project' must be an array of tables")
    return data


def _find_project_index(projects, project_id: str) -> int:
    for index, entry in enumerate(projects):
        if isinstance(entry, dict) and entry.get("id") == project_id:
            return index
    raise RegistryNotFoundError(f"project not found: {project_id}")


def _set_key(lines, start: int, end: int, key: str, rendered, *, remove=False):
    """Replace/add/remove one top-level key within a project block.

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
    """Index just past the last key line of a project block.

    Lines after that are left alone. A comment run touching the *next* project's
    header belongs to that project; a blank-separated run is its upstream note.
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
        projects = [project_record(project) for project in load(path).projects]
    except RegistryError:
        projects = []
    return RegistryConflictError(
        hashlib.sha256(data).hexdigest(),
        data.decode("utf-8", errors="replace"),
        projects,
    )


def _check_expected(path: str, data: bytes, expected_hash: str):
    if not isinstance(expected_hash, str) or not expected_hash:
        raise RegistryError("expected_hash is required")
    current_hash = hashlib.sha256(data).hexdigest()
    if expected_hash != current_hash:
        raise _conflict(path, data)
    return current_hash


def _atomic_replace(path: str, text: str, *, expected_count: int, expected_id=None):
    # Parse before creating a temp file so obvious failures never touch disk.
    data = _parsed_data(text)
    projects = data.get("project", [])
    if len(projects) != expected_count:
        raise RegistryError(
            f"registry project count changed: expected {expected_count}, got {len(projects)}"
        )
    if expected_id is not None:
        ids = [entry.get("id") for entry in projects if isinstance(entry, dict)]
        if expected_id not in ids:
            raise RegistryError(f"project id missing after write: {expected_id}")

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
        loaded = load(temp_path)
        if len(loaded.projects) != expected_count:
            raise RegistryError("registry project count changed after validation")
        if expected_id is not None and not any(
            project.id == expected_id for project in loaded.projects
        ):
            raise RegistryError(f"project id missing after validation: {expected_id}")

        try:
            os.chmod(temp_path, os.stat(path).st_mode & 0o7777)
        except OSError:
            pass
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def append_project(path: str, expected_hash: str, project: dict):
    """Append one project block, preserving every existing byte."""
    with _WRITE_LOCK:
        data = _read_bytes(path)
        _check_expected(path, data, expected_hash)
        text = data.decode("utf-8")
        parsed = _parsed_data(text)
        projects = parsed.get("project", [])
        normalised = _normalise_project(project)
        if any(
            isinstance(entry, dict) and entry.get("id") == normalised["id"]
            for entry in projects
        ):
            raise RegistryError(f"project id already registered: {normalised['id']}")
        if text and not text.endswith("\n"):
            text += "\n"
        candidate = text + ("\n" if text else "") + _format_project_block(normalised)
        _atomic_replace(
            path,
            candidate,
            expected_count=len(projects) + 1,
            expected_id=normalised["id"],
        )
        return normalised


def update_project(path: str, project_id: str, expected_hash: str, changes: dict):
    """Update only the named keys in one project block."""
    unknown = set(changes) - set(_MUTABLE_FIELDS)
    if unknown:
        raise RegistryError(f"unsupported project field(s): {', '.join(sorted(unknown))}")
    if not isinstance(project_id, str) or not project_id:
        raise RegistryError("project id is required")

    with _WRITE_LOCK:
        data = _read_bytes(path)
        _check_expected(path, data, expected_hash)
        text = data.decode("utf-8")
        lines = text.splitlines(keepends=True)
        parsed = _parsed_data(text)
        projects = parsed.get("project", [])
        spans = _project_spans(lines)
        if len(spans) != len(projects):
            raise RegistryError("cannot locate project blocks in registry")

        index = _find_project_index(projects, project_id)
        start, end = spans[index]
        merged = dict(projects[index])
        merged.update(changes)
        normalised = _normalise_project(merged)

        for key in _MUTABLE_FIELDS:
            if key not in changes:
                continue
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
            end = _set_key(lines, start, end, "verify_kind", _render_value("verify_kind", "none"))

        candidate = "".join(lines)
        _atomic_replace(
            path,
            candidate,
            expected_count=len(projects),
            expected_id=project_id,
        )
        return normalised


def delete_project(path: str, project_id: str, expected_hash: str):
    """Delete one project block and the comments that belong to it."""
    with _WRITE_LOCK:
        data = _read_bytes(path)
        _check_expected(path, data, expected_hash)
        text = data.decode("utf-8")
        lines = text.splitlines(keepends=True)
        parsed = _parsed_data(text)
        projects = parsed.get("project", [])
        spans = _project_spans(lines)
        if len(spans) != len(projects):
            raise RegistryError("cannot locate project blocks in registry")

        index = _find_project_index(projects, project_id)
        start, end = spans[index]
        owned_start = _strip_owned_comments(lines, start)
        body_end = _block_content_end(lines, start, end)
        del lines[owned_start:body_end]
        candidate = "".join(lines)
        _atomic_replace(
            path,
            candidate,
            expected_count=len(projects) - 1,
        )
        return project_id


#: What a brand-new workspace starts from. Deliberately holds no projects.
#:
#: An example entry used to be seeded here, pointing at `/absolute/path/to/my-app`.
#: Its path was a placeholder, so `taskproof projects` -- and the dashboard --
#: listed a repository that did not exist until someone deleted the block. A
#: fresh registry that is honestly empty is better than one that lies.
#: The format lives in `examples/projects.example.toml` and `docs/REGISTRY.md`.
SAMPLE_REGISTRY = """\
# taskproof project registry
#
# One [[project]] block per repository. Paths are absolute.
# `group` controls serialisation: only one task per group runs at a time.
#
# No projects yet: `taskproof register <path>` appends one.
# A commented, complete example: examples/projects.example.toml
# Field reference: docs/REGISTRY.md

[defaults]
concurrency = 3   # global cap on simultaneous tasks
timeout = 1800    # seconds before a task is judged stuck
"""
