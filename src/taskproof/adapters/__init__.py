"""Adapter registry.

`get(name)` resolves a built-in adapter or a `custom:<cmd>` fallback.

The resolution order matters: a registry entry saying `custom:my-agent --flag`
always wins over any built-in of the same prefix, and an unknown bare name is a
usage error rather than a silent fallback — silently running the wrong agent is
exactly the class of failure this project exists to prevent.
"""

import importlib
import shutil
from typing import Dict, List, Type

from ..errors import UsageError
from .base import Adapter
from .custom import CustomAdapter

_BUILTINS: Dict[str, str] = {
    # name -> module attribute path, resolved lazily in get()
    "codex": "codex",
    "claude": "claude",
    "gemini": "gemini",
    "opencode": "opencode",
}

#: Every adapter name this build knows about (used by doctor / --help).
KNOWN = tuple(sorted(_BUILTINS)) + ("custom:<cmd>",)


def load_class(module_name: str) -> Type[Adapter]:
    """Import `taskproof.adapters.<module_name>` and return its Adapter class.

    Kept as a function so `get()` can resolve built-ins lazily: importing a
    module never executes the CLI it wraps.
    """
    try:
        module = importlib.import_module(f".{module_name}", __package__)
    except ImportError as exc:
        raise UsageError(
            f"adapter module not available: {module_name} ({exc})",
            hint=f"known adapters: {', '.join(KNOWN)}",
        )
    candidates = [
        obj
        for obj in vars(module).values()
        if isinstance(obj, type)
        and issubclass(obj, Adapter)
        and obj is not Adapter
        and obj.__module__ == module.__name__
    ]
    if not candidates:
        raise UsageError(f"adapter module '{module_name}' defines no Adapter subclass")
    # Deterministic: prefer the conventional `<Name>Adapter` class.
    candidates.sort(key=lambda cls: (not cls.__name__.endswith("Adapter"), cls.__name__))
    return candidates[0]


def available() -> List[str]:
    """Names whose CLI is actually present on PATH (does not execute them)."""
    found: List[str] = []
    for name, module_name in _BUILTINS.items():
        try:
            adapter_cls = load_class(module_name)
        except UsageError:
            continue
        binary = getattr(adapter_cls, "binary", "") or name
        if shutil.which(binary):
            found.append(name)
    return found


def get(name, **kwargs) -> Adapter:
    """Instantiate an adapter by name.

    `name` may be:
      * a built-in name (`codex`, `claude`, ...)
      * `custom:<shell command>` — the command is templated, not executed here

    Unknown bare names raise UsageError (exit 64).
    """
    if not isinstance(name, str) or not name.strip():
        raise UsageError("adapter name is required")
    name = name.strip()

    if name.startswith("custom:"):
        command = name[len("custom:"):].strip()
        if not command:
            raise UsageError(
                "custom adapter needs a command",
                hint="usage: custom:<command template with {prompt} / {workdir}>",
            )
        return CustomAdapter(command, **kwargs)

    if name in _BUILTINS:
        return load_class(_BUILTINS[name])(**kwargs)

    raise UsageError(
        f"unknown adapter: {name}",
        hint=f"known adapters: {', '.join(KNOWN)}",
    )
