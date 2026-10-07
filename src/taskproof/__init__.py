"""taskproof — a conveyor belt for AI coding agents.

It does not decide what to do. It guarantees that what was dispatched gets
independently verified and recorded.
"""

import sys

__version__ = "0.0.1"

# Fail early and in plain language. Without this, running from a source checkout
# under an older interpreter surfaces as `ModuleNotFoundError: No module named
# 'tomllib'` from somewhere deep in the registry loader — which says nothing
# about the real problem (the interpreter is too old).
if sys.version_info < (3, 11):
    raise RuntimeError(
        "taskproof requires Python 3.11 or newer: the project registry is parsed "
        f"with the standard library's tomllib. This interpreter is {sys.version.split()[0]}. "
        "Use a newer Python, or install the packaged version with "
        "`pipx install taskproof` (which will refuse incompatible interpreters for you)."
    )
