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
import re
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

    A "month we own" is a file whose name matches ``events-<YYYY>-<MM>.jsonl``
    (optionally ``.gz``). Anything else in the directory — a workspace's other
    ``*.jsonl``, a stray lock file — is invisible to this function.

    Retention is deliberately coarse: files are per-month, but a month file is
    pruned once its calendar year is at least ``keep_months`` years behind the
    current one, so the newest ``keep_months`` years of months are kept.
    """
    touched: list = []
    months = _months_on_disk(audit_dir)
    if not months:
        return touched
    current = month_key()
    current_year = int(current[:4])
    for month in sorted(months):
        if month == current:
            # The live month is never compressed and never deleted.
            continue
        files = months[month]
        plain = files.get("plain")
        gz = files.get("gz")
        if plain is not None and compress:
            if gz is None:
                gz = _gzip_copy(plain)
            os.remove(plain)
            touched.append(plain)
            touched.append(gz)
        if current_year - int(month[:4]) >= keep_months:
            # Beyond the window: drop whatever representation survives.
            for stale in (plain, gz):
                if stale and os.path.exists(stale):
                    os.remove(stale)
                    touched.append(stale)
    return touched


def iter_events(audit_dir: str, *, task_id: Optional[str] = None) -> Iterator[dict]:
    """Read events back, oldest first. Transparently reads `.gz` months.

    This exists for `taskproof log` and for human/audit use. No decision logic
    may depend on it.

    Only files this module created are read (same pattern as :func:`rotate`).
    A torn final line — a process killed mid-append — is skipped, and a
    truncated gzip stream stops that month rather than raising.
    """
    months = _months_on_disk(audit_dir)
    for month in sorted(months):
        files = months[month]
        # Prefer the compressed copy: if a crash left both behind, the `.gz` is
        # the completed rotation and the `.jsonl` is a leftover duplicate.
        path = files.get("gz") or files.get("plain")
        if not path:
            continue
        for event in _iter_jsonl_tolerant(path):
            if task_id is not None and event.get("task_id") != task_id:
                continue
            yield event


_MONTH_PATTERN = re.compile(r"^events-(\d{4})-(\d{2})\.jsonl(\.gz)?$")


def _months_on_disk(audit_dir: str) -> dict:
    """``{month: {"plain": path, "gz": path}}`` for files THIS module owns."""
    found: dict = {}
    try:
        names = os.listdir(audit_dir)
    except OSError:
        return found
    for name in names:
        m = _MONTH_PATTERN.match(name)
        if m is None:
            continue
        path = os.path.join(audit_dir, name)
        if not os.path.isfile(path):
            continue
        kind = "gz" if name.endswith(".gz") else "plain"
        found.setdefault(f"{m.group(1)}-{m.group(2)}", {})[kind] = path
    return found


def _gzip_copy(plain_path: str) -> str:
    """Gzip ``plain_path`` in place to ``<plain_path>.gz``; return the new path."""
    gz_path = plain_path + ".gz"
    tmp = gz_path + ".tmp"
    with open(plain_path, "rb") as src, gzip.open(tmp, "wb") as dst:
        shutil.copyfileobj(src, dst)
    os.replace(tmp, gz_path)  # atomic: readers never see a half-written .gz
    return gz_path


def _iter_jsonl_tolerant(path: str) -> Iterator[dict]:
    """``_read_jsonl`` that also survives a truncated gzip stream."""
    try:
        for event in _read_jsonl(path):
            yield event
    except (OSError, EOFError):
        # gzip.BadGzipFile is an OSError; a torn plain line is already skipped
        # inside `_read_jsonl`. Either way an audit read must not explode.
        return


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
