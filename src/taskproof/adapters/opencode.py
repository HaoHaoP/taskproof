"""OpenCode CLI adapter — NOT tested on this machine (opencode not installed).

Command shape:

    opencode run "<prompt>" [--model <m>] [--agent plan]

OpenCode has no dedicated read-only flag; `read_only=True` selects the `plan`
agent, which does not write files. No schema-constrained output, so
`supports_schema = False`; parsing degrades to stdout with
`parse_degraded=True`.
"""

import shutil
from typing import Optional

from ..models import AdapterResult
from .base import Adapter


class OpenCodeAdapter(Adapter):
    name = "opencode"
    binary = "opencode"
    supports_schema = False
    supports_sandbox = True

    def build_command(self, *, brief: str, workdir: str,
                      schema_path: Optional[str] = None,
                      read_only: bool = False) -> list:
        argv = ["opencode", "run", self.full_prompt(brief)]
        if self.model:
            argv += ["--model", self.model]
        if read_only:
            argv += ["--agent", "plan"]
        return argv

    def parse_result(self, *, exit_code: int, stdout: str, stderr: str,
                     result_path: Optional[str]) -> AdapterResult:
        return self.degraded_result(
            exit_code=exit_code, stdout=stdout, stderr=stderr,
            result_path=result_path,
        )

    def preflight(self) -> Optional[str]:
        if shutil.which(self.binary) is None:
            return "opencode CLI not found on PATH (adapter not tested on this machine)"
        return None
