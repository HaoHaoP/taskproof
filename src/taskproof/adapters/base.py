"""Adapter contract.

An adapter is one command template plus one result-parsing convention. It knows
how to invoke a coding agent CLI and how to salvage a structured outcome from
its output. It knows nothing about concurrency, verification or storage.

The contract exists because agent CLIs lie, crash, and wrap their output in
markdown. Documented incidents that shaped it:

  * result JSON wrapped in a ```json fence -> structured parse failed and the
    whole run looked like it had done nothing
  * "I verified this in the browser, screenshot attached" with zero browser
    activity in the event stream -> hence: the adapter's summary is reported,
    never trusted
  * an out-of-scope HTTP login attempt -> hence: `forbidden_paths` are checked
    after the run, and adapters are invoked in the narrowest sandbox they offer
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from ..models import AdapterResult


class ResultParseError(Exception):
    """The adapter ran but its result could not be understood."""


class Adapter(ABC):
    """Base class for agent CLI adapters."""

    #: Name used in the registry and on the command line.
    name: str = ""

    #: True when the CLI can be constrained to a machine-readable result.
    supports_schema = False

    #: True when the CLI offers a sandbox / approval mode worth using.
    supports_sandbox = False

    def __init__(self, *, model: Optional[str] = None, reasoning: Optional[str] = None,
                 timeout: int = 1800, env: Optional[Dict[str, str]] = None):
        self.model = model
        self.reasoning = reasoning
        self.timeout = timeout
        self.env = env or {}

    # -- required ---------------------------------------------------------

    @abstractmethod
    def build_command(self, *, brief: str, workdir: str,
                      schema_path: Optional[str] = None,
                      read_only: bool = False) -> list:
        """Return argv for one invocation.

        Must not include a shell: pass a list, never `shell=True`.
        """

    @abstractmethod
    def parse_result(self, *, exit_code: int, stdout: str, stderr: str,
                     result_path: Optional[str]) -> AdapterResult:
        """Normalise the CLI's outcome.

        Implementations MUST tolerate:
          * a markdown code fence around the JSON payload
          * a missing or empty result file
          * trailing noise on stdout after the payload

        Degrading to a summary parsed from stdout is allowed and must set
        `parse_degraded=True`. Raising ResultParseError is allowed, and must be
        surfaced as an adapter failure (exit 70) — never silently treated as
        success.
        """

    # -- optional ---------------------------------------------------------

    def preflight(self) -> Optional[str]:
        """Return a human-readable problem if this CLI is unusable, else None.

        Used by `taskproof doctor`. Must not execute the agent.
        """
        return None

    #: Extra context appended to the brief, per CLI.
    prompt_preamble: str = ""

    def full_prompt(self, brief: str) -> str:
        return f"{self.prompt_preamble}{brief}" if self.prompt_preamble else brief


def extract_json(text: str) -> Any:
    """Best-effort JSON recovery used by adapters.

    Order of attempts:
      1. the whole string parses
      2. a fenced block (```json ... ``` or ``` ... ```) parses
      3. the first balanced `{...}` object parses

    Returns the decoded object, or raises ResultParseError.
    """
    raise NotImplementedError("card: adapters-core")
