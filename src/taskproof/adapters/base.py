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

import json
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from ..models import AdapterResult


class ResultParseError(Exception):
    """The adapter ran but its result could not be understood."""


class Adapter(ABC):
    """Base class for agent CLI adapters."""

    #: Name used in the registry and on the command line.
    name: str = ""

    #: Executable looked up on PATH by `adapters.available()` / `preflight()`.
    binary: str = ""

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

    def degraded_result(self, *, exit_code: int, stdout: str, stderr: str,
                        result_path: Optional[str]) -> AdapterResult:
        """Stdout-only fallback shared by adapters without structured output.

        Salvages a JSON object from stdout when possible, otherwise keeps the
        tail of the text as the summary. ALWAYS sets `parse_degraded=True`
        because nothing here is schema-constrained. Raises `ResultParseError`
        when there is nothing at all to salvage (the caller must treat that as
        an adapter failure, exit 70 — never a silent success).
        """
        if not stdout or not stdout.strip():
            raise ResultParseError(
                f"{self.name}: produced no output to parse"
            )
        try:
            decoded = extract_json(stdout)
        except ResultParseError:
            decoded = None
        payload = decoded if isinstance(decoded, dict) else None
        return AdapterResult(
            exit_code=exit_code,
            summary=_summarize(decoded, stdout),
            payload=payload,
            raw_stdout=stdout,
            raw_stderr=stderr,
            parse_degraded=True,
            result_path=result_path,
        )


# ---------------------------------------------------------------------------
# JSON recovery
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"```[ \t]*([A-Za-z0-9_+-]*)[ \t]*\r?\n?(.*?)```", re.DOTALL)


def extract_json(text: str) -> Any:
    """Best-effort JSON recovery used by adapters.

    Order of attempts:
      1. the whole string parses
      2. a fenced block (```json ... ``` or ``` ... ```) parses
      3. the first balanced `{...}` object parses

    Returns the decoded object, or raises ResultParseError.
    """
    if text is None:
        raise ResultParseError("no result to parse")
    stripped = text.strip()
    if not stripped:
        raise ResultParseError("empty result")

    # 1. the whole string is JSON
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        pass

    # 2. a fenced block
    for match in _FENCE_RE.finditer(stripped):
        block = match.group(2).strip()
        if not block:
            continue
        try:
            return json.loads(block)
        except (json.JSONDecodeError, ValueError):
            pass
        balanced = _first_balanced_object(block)
        if balanced is not _MISS:
            return balanced

    # 3. the first balanced {...} object anywhere in the string
    balanced = _first_balanced_object(stripped)
    if balanced is not _MISS:
        return balanced

    raise ResultParseError("could not extract JSON from result")


class _Missing:
    """Sentinel so `None` / `0` / `False` are still valid decoded values."""


_MISS = _Missing()


def _first_balanced_object(text: str):
    """Decode the first brace-balanced `{...}` object, or return `_MISS`.

    String literals and escapes are respected so a `}` inside a JSON string
    does not close the object early.
    """
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
            else:
                if char == '"':
                    in_string = True
                elif char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = text[start:index + 1]
                        try:
                            return json.loads(candidate)
                        except (json.JSONDecodeError, ValueError):
                            break  # start over from the next '{'
        start = text.find("{", start + 1)
    return _MISS


def _summarize(payload: Any, text: str, tail: int = 40) -> str:
    """Human-readable one-liner: prefer a summary field, else tail the text."""
    if isinstance(payload, dict):
        for key in ("summary", "message", "result", "text"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return json.dumps(payload, ensure_ascii=False)
    lines: List[str] = [line for line in text.splitlines() if line.strip()]
    return "\n".join(lines[-tail:])
