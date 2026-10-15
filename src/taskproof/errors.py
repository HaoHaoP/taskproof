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
#: sysexits' EX_CONFIG: the declaration is understood, the environment cannot
#: satisfy it. Here: the registry and the repository disagree about reality.
EXIT_PRECONDITION = 78


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


class PreconditionError(TaskproofError):
    """What the registry declares and what the repository really is disagree.

    Raised before the card exists — before a task row, before a concurrency
    slot — so a refusal leaves no ledger trace at all. The same idea as
    sysexits' ``EX_CONFIG`` (78): the configuration is readable and well formed,
    but it cannot be honoured right now. Concretely, a lane that declares
    ``branch = X`` and finds a different branch checked out, a missing branch,
    or no repository at all. -> 78
    """

    exit_code = EXIT_PRECONDITION
