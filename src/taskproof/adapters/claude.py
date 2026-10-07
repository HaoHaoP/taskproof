"""Claude Code CLI adapter — NOT tested on this machine (claude not installed).

Command shape (print mode, JSON output):

    claude -p "<prompt>" [--model <m>] [--permission-mode plan|acceptEdits]

`read_only=True` maps to `--permission-mode plan`, the non-mutating mode.
Result parsing degrades to stdout: `parse_degraded=True` always. The Claude
`--output-format json` envelope is not a JSON Schema, so `supports_schema`
stays False.
"""

import shutil
from typing import Optional

from ..models import AdapterResult
from .base import Adapter


class ClaudeAdapter(Adapter):
    name = "claude"
    binary = "claude"
    supports_schema = False
    supports_sandbox = True

    def build_command(self, *, brief: str, workdir: str,
                      schema_path: Optional[str] = None,
                      read_only: bool = False) -> list:
        argv = ["claude", "-p", self.full_prompt(brief)]
        if self.model:
            argv += ["--model", self.model]
        # read-only is the "plan" permission mode (no edits).
        argv += ["--permission-mode", "plan" if read_only else "acceptEdits"]
        return argv

    def parse_result(self, *, exit_code: int, stdout: str, stderr: str,
                     result_path: Optional[str]) -> AdapterResult:
        return self.degraded_result(
            exit_code=exit_code, stdout=stdout, stderr=stderr,
            result_path=result_path,
        )

    def preflight(self) -> Optional[str]:
        if shutil.which(self.binary) is None:
            return "claude CLI not found on PATH (adapter not tested on this machine)"
        return None
