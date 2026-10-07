"""Adapter registry.

`get(name)` resolves a built-in adapter or a `custom:<cmd>` fallback.

The resolution order matters: a registry entry saying `custom:my-agent --flag`
always wins over any built-in of the same prefix, and an unknown bare name is a
usage error rather than a silent fallback — silently running the wrong agent is
exactly the class of failure this project exists to prevent.
"""

from typing import Dict, Type

from ..errors import UsageError
from .base import Adapter

_BUILTINS: Dict[str, str] = {
    # name -> module attribute path, resolved lazily in get()
    "codex": "codex",
    "claude": "claude",
    "gemini": "gemini",
    "opencode": "opencode",
}

#: Every adapter name this build knows about (used by doctor / --help).
KNOWN = tuple(sorted(_BUILTINS)) + ("custom:<cmd>",)


def available() -> list:
    """Names whose CLI is actually present on PATH (does not execute them)."""
    raise NotImplementedError("card: adapters-core")


def get(name, **kwargs) -> Adapter:
    """Instantiate an adapter by name.

    `name` may be:
      * a built-in name (`codex`, `claude`, ...)
      * `custom:<shell command>` — the command is templated, not executed here

    Unknown bare names raise UsageError (exit 64).
    """
    raise NotImplementedError("card: adapters-core")


def load_class(module_name: str) -> Type[Adapter]:
    raise NotImplementedError("card: adapters-core")
