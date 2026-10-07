"""Custom command adapter — `custom:<command template>`.

The template is tokenised with `shlex.split` (shell-style quoting, but no
shell is ever spawned). Two placeholders are substituted, per token, AFTER
tokenisation so a prompt containing spaces/quotes stays a single argv element
and cannot be re-interpreted as shell syntax:

    {prompt}    the full brief (adapter `prompt_preamble` included)
    {workdir}   the directory the task runs in

Example registry value:

    custom:my-agent --cwd {workdir} --task {prompt}

There is no structured-output convention for an arbitrary command, so
`supports_schema = False` and `parse_result` always degrades: it salvages a
JSON object from stdout when present, otherwise keeps the tail of the text,
and sets `parse_degraded=True`.
"""

import shlex
from typing import Optional

from ..models import AdapterResult
from .base import Adapter


class CustomAdapter(Adapter):
    name = "custom"
    supports_schema = False
    supports_sandbox = False

    def __init__(self, command: str = "", *, model: Optional[str] = None,
                 reasoning: Optional[str] = None, timeout: int = 1800,
                 env: Optional[dict] = None):
        super().__init__(model=model, reasoning=reasoning, timeout=timeout, env=env)
        #: The raw template (everything after the `custom:` prefix).
        self.command = command

    def build_command(self, *, brief: str, workdir: str,
                      schema_path: Optional[str] = None,
                      read_only: bool = False) -> list:
        # `schema_path` / `read_only` are not expressible for an arbitrary
        # command; they are accepted for interface compatibility and ignored.
        prompt = self.full_prompt(brief)
        argv = []
        for token in shlex.split(self.command):
            argv.append(token.replace("{workdir}", workdir).replace("{prompt}", prompt))
        return argv

    def parse_result(self, *, exit_code: int, stdout: str, stderr: str,
                     result_path: Optional[str]) -> AdapterResult:
        return self.degraded_result(
            exit_code=exit_code, stdout=stdout, stderr=stderr,
            result_path=result_path,
        )

    def preflight(self) -> Optional[str]:
        # An arbitrary command cannot be validated without running it (which
        # we never do here). Report nothing; `doctor` shows the template.
        return None
