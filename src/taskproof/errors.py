"""Exit codes and the error hierarchy.

The exit codes are part of the public contract: callers (agents, scripts, humans)
must be able to distinguish "the agent failed" from "the agent succeeded but
verification failed" without parsing stdout.

Keep this table in sync with docs/DESIGN.md.
"""

EXIT_OK = 0
EXIT_REGISTRY = 2
EXIT_USAGE = 64
EXIT_ADAPTER = 70
EXIT_VERIFY = 71
EXIT_CONCURRENCY = 75


class TaskproofError(Exception):
    """Base class. Carries the process exit code this failure maps to."""

    exit_code = 1

    def __init__(self, message, *, hint=None):
        super().__init__(message)
        self.hint = hint


class UsageError(TaskproofError):
    """Bad invocation — wrong flags, unreadable input. -> 64"""

    exit_code = EXIT_USAGE


class RegistryError(TaskproofError):
    """Project not found, registry malformed, missing acceptance command. -> 2"""

    exit_code = EXIT_REGISTRY


class AdapterError(TaskproofError):
    """The agent CLI failed to run, or its result could not be parsed. -> 70"""

    exit_code = EXIT_ADAPTER


class VerifyError(TaskproofError):
    """Acceptance command or artifact self-check failed. -> 71"""

    exit_code = EXIT_VERIFY


class ConcurrencyError(TaskproofError):
    """Same-group serialisation or the global cap blocked this dispatch. -> 75"""

    exit_code = EXIT_CONCURRENCY
