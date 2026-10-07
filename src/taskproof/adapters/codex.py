"""Codex CLI adapter — the one built-in tested on this machine.

Verified against `codex-cli 0.160.0`. The relevant lines from `codex exec
--help` are:

    Usage: codex exec [OPTIONS] [PROMPT]
    -m, --model <MODEL>
    -c, --config <key=value>
    -s, --sandbox <SANDBOX_MODE>
        [possible values: read-only, workspace-write, danger-full-access]
    -C, --cd <DIR>
    --output-schema <FILE>   Path to a JSON Schema file describing the model's
                             final response shape
    -o, --output-last-message <FILE>
                             Specifies file where the last message from the
                             agent should be written

Command shape (from the real dispatch scripts):

    codex exec -C <workdir> --sandbox read-only|workspace-write \\
        --output-schema <schema.json> -o <result.json> \\
        [--model <m>] [-c model_reasoning_effort=<r>] "<prompt>"

The result file named by `-o` is read first; if it is missing (or holds no
JSON) the adapter degrades to scraping stdout and sets `parse_degraded=True`.
"""

import os
import shutil
import tempfile
from typing import List, Optional

from ..models import AdapterResult
from .base import Adapter, ResultParseError, _summarize, extract_json


class CodexAdapter(Adapter):
    name = "codex"
    binary = "codex"
    supports_schema = True
    supports_sandbox = True

    def __init__(self, *, model: Optional[str] = None, reasoning: Optional[str] = None,
                 timeout: int = 1800, env: Optional[dict] = None,
                 result_path: Optional[str] = None):
        super().__init__(model=model, reasoning=reasoning, timeout=timeout, env=env)
        #: Where `codex -o` writes the last message. Callers may set it; when
        #: left None `build_command` allocates a per-run temp file.
        self.result_path = result_path
        self._seq = 0

    def _allocate_result_path(self) -> str:
        self._seq += 1
        return os.path.join(
            tempfile.gettempdir(),
            f"taskproof-codex-{os.getpid()}-{self._seq}.json",
        )

    def build_command(self, *, brief: str, workdir: str,
                      schema_path: Optional[str] = None,
                      read_only: bool = False) -> list:
        if self.result_path is None:
            self.result_path = self._allocate_result_path()

        # argv list, never a shell string: the prompt is passed as one element
        # and can never inject a `;`/`&&`/backtick into a shell.
        argv: List[str] = ["codex", "exec"]
        argv += ["-C", workdir]
        # read-only vs workspace-write is the whole point of the sandbox flag.
        argv += ["--sandbox", "read-only" if read_only else "workspace-write"]
        if schema_path:
            argv += ["--output-schema", schema_path]
        argv += ["-o", self.result_path]
        if self.model:
            argv += ["--model", self.model]
        if self.reasoning:
            argv += ["-c", f"model_reasoning_effort={self.reasoning}"]
        argv += [self.full_prompt(brief)]
        return argv

    def parse_result(self, *, exit_code: int, stdout: str, stderr: str,
                     result_path: Optional[str]) -> AdapterResult:
        path = result_path or self.result_path

        payload = None
        raw = ""
        if path and os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as handle:
                    raw = handle.read()
            except OSError:
                raw = ""
        if raw.strip():
            try:
                payload = extract_json(raw)
            except ResultParseError:
                payload = None

        if payload is not None:
            # A structured result came back from the `-o` file. A fenced file is
            # still the structured result (extract_json unwraps it), so this is
            # NOT flagged as degraded.
            return AdapterResult(
                exit_code=exit_code,
                summary=_summarize(payload, raw),
                payload=payload if isinstance(payload, dict) else None,
                raw_stdout=stdout,
                raw_stderr=stderr,
                parse_degraded=False,
                result_path=path,
            )

        # Result file missing/empty/unparseable -> salvage stdout if we can.
        if stdout and stdout.strip():
            decoded = None
            try:
                decoded = extract_json(stdout)
            except ResultParseError:
                decoded = None
            return AdapterResult(
                exit_code=exit_code,
                summary=_summarize(decoded, stdout),
                payload=decoded if isinstance(decoded, dict) else None,
                raw_stdout=stdout,
                raw_stderr=stderr,
                parse_degraded=True,
                result_path=path,
            )

        raise ResultParseError(
            f"codex: no parseable result (result_path={path!r}, empty stdout)"
        )

    def preflight(self) -> Optional[str]:
        if shutil.which(self.binary) is None:
            return (
                "codex CLI not found on PATH — install codex-cli, or use "
                "custom:<cmd> pointing at your agent"
            )
        return None
