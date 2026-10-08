#!/usr/bin/env python3
"""Employer-asset scan: the one check that must not live in the repository.

DESIGN.md promises "a keyword scan runs before every push". That promise has a
trap in it: the list of forbidden words is a list of *internal* names, so a
scanner that hardcodes them would leak exactly what it is meant to protect.

So this script ships with generic rules only, and reads the organisation-specific
words from outside the repository:

    $TASKPROOF_ASSET_PATTERNS          path to a pattern file, or
    ~/.taskproof/asset-patterns.txt    the default location

One pattern per line, `#` for comments, matched case-insensitively. With no
pattern file it still checks the generic rules, so it is never a no-op.

    python3 tools/scan_assets.py            # scan the repository
    python3 tools/scan_assets.py --staged   # scan only git-staged content
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PATTERN_FILE = os.path.join(
    os.path.expanduser("~"), ".taskproof", "asset-patterns.txt"
)

#: Generic rules that are safe to ship: they describe shapes, not names.
#:
#: The hostname rule is deliberately anchored to a URL or a host assignment.
#: A bare `\w+\.(?:corp|internal|lan|local)` also matches an i18n key like
#: `service.local`, which is a false positive that would block every push --
#: measured, on this repository, on the first run.
GENERIC_PATTERNS = {
    "private IPv4 address": r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b",
    "internal URL": r"(?i)(?:https?://|//)[\w.-]+\.(?:corp|internal|intranet|lan|local)\b",
    "internal host assignment": r"(?i)\b(?:host|hostname|server|endpoint)\s*[:=]\s*['\"]?[\w-]+\.(?:corp|internal|intranet|lan)\b",
    "credential assignment": r"(?i)\b(?:password|passwd|secret|api[_-]?key|access[_-]?token)\s*[:=]\s*['\"][^'\"\s]{8,}",
    "private key block": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
}

SKIP_DIRS = {
    ".git", "node_modules", "out", "dist", "build", "__pycache__",
    ".venv", "venv", ".mypy_cache", ".pytest_cache", ".ruff_cache",
}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".gz", ".woff", ".woff2", ".ico"}
SCAN_SUFFIXES = {
    ".py", ".md", ".toml", ".txt", ".yml", ".yaml", ".json", ".ts", ".vue",
    ".js", ".css", ".html", ".sh", ".cfg", ".ini", ".env", "",
}
#: This file necessarily talks about scanners and patterns; it is not a leak.
ALLOWLIST = {os.path.join("tools", "scan_assets.py")}


def load_patterns() -> tuple[dict[str, str], str]:
    patterns = dict(GENERIC_PATTERNS)
    source = os.environ.get("TASKPROOF_ASSET_PATTERNS") or (
        DEFAULT_PATTERN_FILE if os.path.exists(DEFAULT_PATTERN_FILE) else ""
    )
    if not source or not os.path.exists(source):
        return patterns, ""
    with open(source, encoding="utf-8") as handle:
        for line in handle:
            word = line.strip()
            if not word or word.startswith("#"):
                continue
            patterns[f"pattern file: {word}"] = "(?i)" + re.escape(word)
    return patterns, source


def iter_files(staged_only: bool):
    if staged_only:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=False,
        ).stdout
        for name in out.splitlines():
            path = os.path.join(REPO_ROOT, name)
            if os.path.isfile(path):
                yield path
        return
    for root, dirs, names in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in names:
            if os.path.splitext(name)[1].lower() in SKIP_SUFFIXES:
                continue
            yield os.path.join(root, name)


def compile_patterns(patterns: dict[str, str]) -> dict[str, "re.Pattern[str]"]:
    return {label: re.compile(rx) for label, rx in patterns.items()}


def scan_text(text: str, compiled) -> list[tuple[int, str, str]]:
    """Hits in one blob of text: `(line_number, label, line)`. Exposed for tests."""
    hits = []
    for number, line in enumerate(text.splitlines(), 1):
        for label, rx in compiled.items():
            if rx.search(line):
                hits.append((number, label, line.strip()[:120]))
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true", help="only git-staged files")
    args = parser.parse_args()

    patterns, source = load_patterns()
    compiled = compile_patterns(patterns)

    hits: list[tuple[str, int, str, str]] = []
    scanned = 0
    for path in iter_files(args.staged):
        rel = os.path.relpath(path, REPO_ROOT)
        if rel in ALLOWLIST:
            continue
        if os.path.splitext(path)[1].lower() not in SCAN_SUFFIXES:
            continue
        try:
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
        except (OSError, UnicodeDecodeError):
            continue
        scanned += 1
        for number, label, line in scan_text(text, compiled):
            hits.append((rel, number, label, line))

    print(f"scan_assets: {scanned} files, {len(compiled)} patterns"
          + (f" ({len(compiled) - len(GENERIC_PATTERNS)} from {source})" if source else
             " (generic rules only — set TASKPROOF_ASSET_PATTERNS for the rest)"))
    for rel, number, label, line in hits:
        print(f"  {rel}:{number}: {label}\n      {line}")
    if hits:
        print(f"scan_assets: FAIL — {len(hits)} hit(s)")
        return 1
    print("scan_assets: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
