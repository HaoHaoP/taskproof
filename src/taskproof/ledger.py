"""Append-only audit stream.

WRITE-ONLY WITH RESPECT TO LOGIC. Nothing in this package decides anything by
reading these files. The database is the query surface; this is the audit trail
and the "read it once tomorrow morning" surface.

Layout (workspace = ~/.taskproof by default):

    events-2026-10.jsonl        current month
    events-2026-09.jsonl.gz     rotated + compressed

Rotation is driven by `gc` (see `rotate`), not by a background daemon.
"""

import gzip
import json
import os
import shutil
from typing import Iterator, Optional

from .storage import now_iso

EVENT_PREFIX = "events-"


def month_key(iso_ts: Optional[str] = None) -> str:
    """`2026-10` for the given timestamp (or now)."""
    ts = iso_ts or now_iso()
    return ts[:7]


def stream_path(audit_dir: str, month: Optional[str] = None) -> str:
    return os.path.join(audit_dir, f"{EVENT_PREFIX}{month or month_key()}.jsonl")


def append(audit_dir: str, event: dict) -> str:
    """Append one JSON object as a single line. Returns the file written.

    Must be atomic enough that a concurrent reader never sees a partial line:
    one `write()` of a complete line, opened in append mode.
    """
    if audit_dir:
        ensure_dir(audit_dir)
    path = stream_path(audit_dir, month_key(event.get("ts")))
    line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line)  # one write() of a complete line
        fh.flush()
        os.fsync(fh.fileno())
    return path


def rotate(audit_dir: str, *, keep_months: int = 6, compress: bool = True) -> list:
    """Compress rotated months, prune beyond `keep_months`.

    Returns the list of paths touched, so `gc` can report what it did.
    NEVER deletes the current month. Never touches a file it did not create.
    """
    raise NotImplementedError("card: ledger")


def iter_events(audit_dir: str, *, task_id: Optional[str] = None) -> Iterator[dict]:
    """Read events back, oldest first. Transparently reads `.gz` months.

    This exists for `taskproof log` and for human/audit use. No decision logic
    may depend on it.
    """
    raise NotImplementedError("card: ledger")


def _read_jsonl(path: str) -> Iterator[dict]:
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                # A torn line must never break an audit read.
                continue


def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def copy_for_export(audit_dir: str, dest: str) -> str:
    """Bundle the audit dir for sharing (used by `board --out` snapshots)."""
    shutil.make_archive(dest.rstrip("/"), "gztar", audit_dir)
    return dest + ".tar.gz"
