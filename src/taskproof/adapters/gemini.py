"""Gemini CLI adapter — NOT tested on this machine (gemini not installed).

Command shape (non-interactive prompt):

    gemini -p "<prompt>" [-m <model>] [--approval-mode plan|auto_edit]

`read_only=True` maps to `--approval-mode plan`. No structured schema output
is assumed, so `supports_schema = False`; parsing degrades to stdout and sets
`parse_degraded=True` always.
"""

import shutil
from typing import Optional

from ..models import AdapterResult
from .base import Adapter


class GeminiAdapter(Adapter):
    name = "gemini"
    binary = "gemini"
    supports_schema = False
    supports_sandbox = True

    def build_command(self, *, brief: str, workdir: str,
                      schema_path: Optional[str] = None,
                      read_only: bool = False) -> list:
        argv = ["gemini", "-p", self.full_prompt(brief)]
        if self.model:
            argv += ["-m", self.model]
        # `plan` approval mode refuses side effects (read-only).
        argv += ["--approval-mode", "plan" if read_only else "auto_edit"]
        return argv

    def parse_result(self, *, exit_code: int, stdout: str, stderr: str,
                     result_path: Optional[str]) -> AdapterResult:
        return self.degraded_result(
            exit_code=exit_code, stdout=stdout, stderr=stderr,
            result_path=result_path,
        )

    def preflight(self) -> Optional[str]:
        if shutil.which(self.binary) is None:
            return "gemini CLI not found on PATH (adapter not tested on this machine)"
        return None
