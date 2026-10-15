#!/usr/bin/env python3
"""Build the throwaway demo environment for the README animation.

Everything lands under /tmp/tp-demo so nothing touches a real ledger:

    /tmp/tp-demo/state/   the ledger (TASKPROOF_HOME)
    /tmp/tp-demo/repo/    a toy repository with one failing check

The two adapters are scripts on purpose: the animation is about the *mechanism*
(dispatch -> the agent's claim -> an independent verdict -> the record), not
about any particular model. One script lies, one actually fixes the file; the
ledger is the only thing that tells them apart.

Re-running is safe: the script rebuilds both directories from scratch.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path("/tmp/tp-demo")
STATE = ROOT / "state"
REPO = ROOT / "repo"

CHECK = """#!/bin/sh
# The acceptance command. It is the only thing believed.
grep -q "^hello, world$" app.txt
"""

LYING_AGENT = """#!/bin/sh
# An agent that reports success without doing the work.
cat <<'EOF'
Analysed app.txt and the failing check.
Updated the greeting. All checks pass.
Task complete.
EOF
"""

HONEST_AGENT = """#!/bin/sh
# An agent that actually does the work.
printf 'hello, world\\n' > app.txt
echo "Rewrote app.txt; the check should pass now."
"""

REGISTRY = """# Demo registry (see docs/REGISTRY.md)

[defaults]
concurrency = 2
timeout = 600

[[project]]
id = "demo-app"
path = "/tmp/tp-demo/repo"

[[taskgroup]]
id = "demo-app"
project = "demo-app"
verify = "sh check.sh"
verify_kind = "check"
forbidden_paths = [".git/"]
"""


def run(cmd, cwd=None, env=None):
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)


def main():
    if ROOT.exists():
        shutil.rmtree(ROOT)
    REPO.mkdir(parents=True)
    STATE.mkdir(parents=True)

    (REPO / "app.txt").write_text("hello\n", encoding="utf-8")
    (REPO / "check.sh").write_text(CHECK, encoding="utf-8")
    (REPO / "check.sh").chmod(0o755)
    for name, body in (("agent-lies", LYING_AGENT), ("agent-fixes", HONEST_AGENT)):
        (REPO / name).write_text(body, encoding="utf-8")
        (REPO / name).chmod(0o755)

    run(["git", "init", "-q"], cwd=REPO)
    run(["git", "add", "-A"], cwd=REPO)
    run(["git", "-c", "user.email=demo@example.com", "-c", "user.name=demo",
         "commit", "-qm", "a toy app with one failing check"], cwd=REPO)

    env = dict(os.environ, TASKPROOF_HOME=str(STATE))
    init = run([sys.executable, "-m", "taskproof", "init"], cwd=ROOT, env=env)
    print(init.stdout.strip() or init.stderr.strip())

    # init writes its own empty projects.toml — the demo registry goes in after it.
    (STATE / "projects.toml").write_text(REGISTRY, encoding="utf-8")

    print(f"demo env ready: {ROOT}")
    print("  ledger: " + str(STATE))
    print("  repo:   " + str(REPO))


if __name__ == "__main__":
    main()
