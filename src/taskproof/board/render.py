"""Static HTML dashboard.

Self-contained by design: every value is inlined into the page at generation
time, so a snapshot opens straight from ``file://`` and can be handed to
someone else without a server or the REST API. Standard library only — this is
the deliberately plain stage 1 board; stage 2 replaces the rendering layer with
Vue 3 while the data model stays the same.

Every interpolation is HTML-escaped, because task briefs (and project ids)
come from user input.
"""

import html
from datetime import datetime
from typing import Optional

from .. import dispatch, storage

#: Stable column order for the header, matching models.py.
_STATUS_ORDER = (
    "queued",
    "running",
    "verifying",
    "done",
    "failed",
    "blocked",
    "timeout",
    "cancelled",
)

_STYLE = """\
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { margin: 0; font: 14px/1.5 -apple-system, Segoe UI, Roboto, sans-serif;
       background: #f4f5f7; color: #1f2328; }
header { padding: 20px 24px; background: #1f2328; color: #f4f5f7; }
header h1 { margin: 0 0 6px; font-size: 18px; letter-spacing: .04em; }
.meta { margin: 0 0 12px; color: #b7bcc3; font-size: 12px; }
.counts { display: flex; flex-wrap: wrap; gap: 8px; }
.count { padding: 2px 10px; border-radius: 999px; background: #343a41;
         font-size: 12px; text-transform: uppercase; letter-spacing: .05em; }
.count b { margin-left: 4px; }
main { display: grid; gap: 12px; padding: 20px 24px;
       grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); }
.card { background: #fff; border: 1px solid #d8dce1; border-radius: 8px;
        padding: 14px 16px; }
.card .row { display: flex; justify-content: space-between; align-items: center; }
.id { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-weight: 600; }
.badge { font-size: 11px; text-transform: uppercase; letter-spacing: .06em;
         padding: 2px 8px; border-radius: 999px; background: #e6e8eb; }
.status-done .badge { background: #d6f5dd; color: #0a6b2d; }
.status-failed .badge, .status-timeout .badge { background: #fbe1e1; color: #a01b1b; }
.status-running .badge, .status-verifying .badge { background: #dce9fb; color: #1a4f9c; }
.project { margin-top: 2px; color: #656d76; font-size: 12px; }
.brief { margin: 10px 0; }
dl { display: grid; grid-template-columns: auto 1fr; gap: 2px 10px; margin: 0; }
dt { color: #656d76; font-size: 12px; }
dd { margin: 0; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
     font-size: 12px; word-break: break-word; }
.ts { color: #8b949e; }
"""


def _escape(value) -> str:
    """HTML-escape any value (None -> empty string). Always quote attrs."""
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def _duration(started, finished, reference) -> str:
    """Human duration between `started` and (`finished` or `reference`)."""
    if not started:
        return "—"
    try:
        start = datetime.fromisoformat(str(started))
    except ValueError:
        return "—"

    end = None
    for candidate in (finished, reference):
        if not candidate:
            continue
        try:
            end = datetime.fromisoformat(str(candidate))
            break
        except ValueError:
            continue
    if end is None:
        return "—"

    seconds = max(0, (end - start).total_seconds())
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes, sec = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m{sec:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


def _last_event(conn, task_id: str):
    row = conn.execute(
        "SELECT event, ts FROM events WHERE task_id = ? ORDER BY id DESC LIMIT 1",
        (task_id,),
    ).fetchone()
    return dict(row) if row is not None else None


def _verify_line(task: dict) -> str:
    command = task.get("verify_cmd")
    if not command:
        return "—"
    line = _escape(command)
    exit_code = task.get("verify_exit")
    if exit_code is not None:
        line += f" (exit {_escape(exit_code)})"
    return line


def _card(task: dict, last_event, reference: str) -> str:
    status = task.get("status") or ""
    duration = _duration(task.get("started_at"), task.get("finished_at"), reference)
    if last_event:
        event_line = (
            f'{_escape(last_event.get("event"))} '
            f'<span class="ts">{_escape(last_event.get("ts"))}</span>'
        )
    else:
        event_line = "—"
    return (
        f'<article class="card status-{_escape(status)}">\n'
        '  <div class="row">\n'
        f'    <span class="id">{_escape(task.get("id"))}</span>\n'
        f'    <span class="badge">{_escape(status)}</span>\n'
        "  </div>\n"
        f'  <div class="project">{_escape(task.get("project"))}</div>\n'
        f'  <p class="brief">{_escape(task.get("brief"))}</p>\n'
        "  <dl>\n"
        f'    <dt>duration</dt><dd>{_escape(duration)}</dd>\n'
        f'    <dt>verify</dt><dd>{_verify_line(task)}</dd>\n'
        f'    <dt>last event</dt><dd>{event_line}</dd>\n'
        "  </dl>\n"
        "</article>"
    )


def render_board(workspace: str, *, limit: int = 200,
                 generated_at: Optional[str] = None) -> str:
    """Render the whole board as a single self-contained HTML document."""
    reference = generated_at or storage.now_iso()

    conn = storage.connect(storage.db_path(workspace))
    try:
        storage.migrate(conn)
        counts = dispatch.summary_counts(workspace, conn)
        rows = storage.list_tasks(conn, limit=limit)
        cards = []
        for row in rows:
            task = dict(row)
            cards.append((task, _last_event(conn, task["id"])))
    finally:
        conn.close()

    total = sum(counts.values())
    ordered = list(_STATUS_ORDER) + [
        status for status in counts if status not in _STATUS_ORDER
    ]

    parts = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>taskproof board</title>",
        f"<style>\n{_STYLE}</style>",
        "</head>",
        "<body>",
        "<header>",
        "<h1>taskproof</h1>",
        f'<p class="meta">total {total} · generated {_escape(reference)}</p>',
        '<div class="counts">',
    ]
    for status in ordered:
        parts.append(
            f'<span class="count {_escape(status)}">{_escape(status)}'
            f' <b>{_escape(int(counts.get(status, 0)))}</b></span>'
        )
    parts += ["</div>", "</header>", '<main class="cards">']
    for task, last_event in cards:
        parts.append(_card(task, last_event, reference))
    parts += ["</main>", "</body>", "</html>", ""]
    return "\n".join(parts)
