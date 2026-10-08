#!/usr/bin/env python3
"""Generate the cross-language enum contract from the Python constants.

The TypeScript side must never hand-copy these words. A status that exists in
Python but not in the frontend means tasks silently vanish from the board --
exactly the failure the Python board already guards against by folding unknown
statuses into ``failed``.

    PYTHONPATH=src python3 tools/gen_contract.py           # write
    PYTHONPATH=src python3 tools/gen_contract.py --check    # exit 1 on drift

CI runs ``--check``: the checked-in artefact and the Python constants cannot
drift apart without the build going red.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, os.pardir, "src"))

from taskproof import errors, models, registry  # noqa: E402

#: Output path, relative to the repository root. The desktop package imports
#: this file directly, so it must be JSON and must be checked in.
DEFAULT_OUT = os.path.join("contract", "enums.json")

#: Canonical lifecycle order. The board groups these into columns; the contract
#: only fixes the vocabulary and which states are terminal.
STATUS_ORDER = (
    models.STATUS_QUEUED,
    models.STATUS_RUNNING,
    models.STATUS_VERIFYING,
    models.STATUS_DONE,
    models.STATUS_FAILED,
    models.STATUS_BLOCKED,
    models.STATUS_TIMEOUT,
    models.STATUS_CANCELLED,
)

EXIT_MEANINGS = (
    (errors.EXIT_OK, "success"),
    (errors.EXIT_REGISTRY, "registry"),
    (errors.EXIT_USAGE, "usage"),
    (errors.EXIT_ADAPTER, "adapter"),
    (errors.EXIT_VERIFY, "verify"),
    (errors.EXIT_CONCURRENCY, "concurrency"),
)


def build() -> dict:
    declared = [s for s in STATUS_ORDER]
    known = {
        value
        for name, value in vars(models).items()
        if name.startswith("STATUS_") and isinstance(value, str)
    }
    missing = sorted(known - set(declared))
    if missing:  # a new lifecycle state must not be forgotten here
        raise SystemExit(
            "gen_contract: models declares statuses the contract does not list: "
            + ", ".join(missing)
        )
    return {
        "generated_by": "tools/gen_contract.py",
        "note": "generated from the Python constants; run --check in CI",
        "statuses": [
            {"id": s, "terminal": s in models.TERMINAL_STATUSES} for s in declared
        ],
        "verify_kinds": list(registry.VALID_VERIFY_KINDS),
        "exit_codes": [{"code": c, "meaning": m} for c, m in EXIT_MEANINGS],
    }


def render(payload: dict) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail on drift")
    parser.add_argument("--out", default=None, help=f"output path (default {DEFAULT_OUT})")
    args = parser.parse_args()

    root = os.path.dirname(_HERE)
    out = args.out or os.path.join(root, DEFAULT_OUT)
    text = render(build())

    if args.check:
        try:
            current = open(out, encoding="utf-8").read()
        except OSError as exc:
            print(f"gen_contract: cannot read {out}: {exc}", file=sys.stderr)
            return 1
        if current != text:
            print(
                f"gen_contract: {out} is out of date with the Python constants "
                f"(run: python3 tools/gen_contract.py)",
                file=sys.stderr,
            )
            return 1
        print(f"gen_contract: {out} is in sync")
        return 0

    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as handle:
        handle.write(text)
    print(f"gen_contract: wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
