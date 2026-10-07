"""Static HTML dashboard.

Self-contained by design: every value is inlined into the page at generation
time, so a snapshot opens straight from ``file://`` and can be handed to
someone else without a server or the REST API. Standard library only.
"""

import html
import json
import os
from datetime import datetime

from .. import registry, storage

#: The six lanes rendered by the board. Unknown statuses are folded into
#: ``failed`` so a new lifecycle state can never silently hide a task.
_STATUSES = (
    ("queued", "排队", "○"),
    ("running", "进行中", "●"),
    ("verifying", "验收中", "◉"),
    ("done", "完成", "✓"),
    ("failed", "失败", "✗"),
    ("timeout", "超时", "✗"),
)
_STATUS_ORDER = tuple(status for status, _, _ in _STATUSES)
_BAD = ("failed", "timeout")
_LIVE = ("running", "verifying")

_STYLE = '\n:root{\n  --paper:#f4f6f8; --panel:#fff; --sunken:#f0f2f5;\n  --ink:#0f1114; --ink-2:#474e57; --ink-3:#828a94; --ink-4:#a8afb8;\n  --rule:#d9dde3; --rule-2:#e7eaee;\n  --signal:#b8341d; --signal-wash:#fbeee9; --signal-rule:#e2ab9e;\n  --lane:176px; --col:296px; --rail:214px;\n  --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;\n  --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", sans-serif;\n  --pin:0 6px 10px -6px rgba(15,17,20,.10);\n}\n*{box-sizing:border-box}\nhtml,body{margin:0;height:100%}\nbody{background:var(--paper);color:var(--ink);font:13px/1.5 var(--sans);\n     -webkit-font-smoothing:antialiased;overflow:hidden}\n:focus-visible{outline:2px solid var(--ink);outline-offset:2px}\nbutton{font:inherit;color:inherit;background:none;border:0;padding:0;text-align:left}\n\n/* ── 报头 ── */\n.mast{display:flex;align-items:baseline;gap:13px;padding:14px 20px 12px;background:var(--panel);\n      border-bottom:1px solid var(--rule)}\n.mast h1{margin:0;font:600 14px/1 var(--mono);letter-spacing:-.02em}\n.mast h1 span{color:var(--ink-3);font-weight:400}\n.tally{margin-left:auto;display:flex;gap:16px;font:11.5px/1 var(--mono);color:var(--ink-3);white-space:nowrap}\n.tally b{color:var(--ink);font-weight:600;margin-left:4px}\n.tally .alarm b{color:var(--signal)}\n.tally .gen{color:var(--ink-4);border-left:1px solid var(--rule);padding-left:16px}\n\n.shell{display:flex;height:calc(100vh - 47px)}\n\n/* ── 左栏：项目多选 ── */\n.rail{width:var(--rail);flex:none;background:var(--panel);border-right:1px solid var(--rule);\n      display:flex;flex-direction:column}\n.rh{display:flex;justify-content:space-between;align-items:baseline;padding:13px 16px 9px;\n    font:600 10.5px/1 var(--sans);letter-spacing:.06em;color:var(--ink-2)}\n.rh .rn{font:10px/1 var(--mono);color:var(--ink-4);letter-spacing:0}\n.rquick{display:flex;gap:12px;padding:0 16px 10px}\n.rquick button{font:10.5px/1 var(--sans);color:var(--ink-3);cursor:pointer;\n               border-bottom:1px solid var(--rule)}\n.rquick button:hover{color:var(--ink)}\n.plist{list-style:none;margin:0;padding:0 8px;overflow:auto;flex:1}\n.prow{display:flex;align-items:center;gap:8px;padding:6px 8px;border-radius:3px;cursor:pointer}\n.prow:hover{background:var(--sunken)}\n.prow input{position:absolute;opacity:0;width:0;height:0}\n.box{width:13px;height:13px;flex:none;border:1px solid #b9bfc7;border-radius:2px;\n     background:var(--panel);position:relative}\n.prow input:checked+.box{background:var(--ink);border-color:var(--ink)}\n.prow input:checked+.box::after{content:"";position:absolute;left:3.5px;top:.5px;width:4px;height:8px;\n     border:solid #fff;border-width:0 1.5px 1.5px 0;transform:rotate(45deg)}\n.prow input:focus-visible+.box{outline:2px solid var(--ink);outline-offset:1px}\n.pname{font:11.5px/1.2 var(--mono);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}\n.pn{margin-left:auto;font:10px/1 var(--mono);color:var(--ink-4);display:flex;gap:7px;flex:none}\n.pn em{color:var(--signal);font-style:normal;font-weight:600}\n.rfoot{padding:10px 16px;border-top:1px solid var(--rule-2);\n       font:10px/1 var(--mono);color:var(--ink-4)}\n\n/* ── 矩阵 ── */\n.matrix{flex:1;overflow:auto}\n/* 不要加 min-width:max-content —— 它与 minmax(296px,1fr) 组合会让 1fr 轨道按\n   "内容最大宽度"求解，而卡片是 width:100%，在不定宽轨道里百分比无法解析，\n   Chrome 会把列算炸（实测 6374px/列，网格宽 38420px）。\n   minmax 本身已保证最小列宽，容器窄时轨道溢出即触发横向滚动。 */\n.grid{display:grid;grid-template-columns:var(--lane) repeat(6,minmax(var(--col),1fr));\n      align-content:start}\n.hd{position:sticky;top:0;z-index:3;background:var(--paper);border-bottom:1px solid var(--rule);\n    box-shadow:var(--pin);padding:10px 12px 9px;font:600 10.5px/1 var(--sans);\n    letter-spacing:.06em;color:var(--ink-2);display:flex;justify-content:space-between;\n    align-items:baseline;gap:8px}\n.hd .n{font:600 10.5px/1 var(--mono);letter-spacing:0;color:var(--ink-3)}\n.hd.st-h-failed,.hd.st-h-timeout{color:var(--signal)}\n.hd.st-h-failed .n,.hd.st-h-timeout .n{color:var(--signal)}\n.hd.corner{position:sticky;left:0;z-index:5;justify-content:flex-start;padding-left:20px;\n           color:var(--ink-3)}\n.lane{position:sticky;left:0;z-index:2;background:var(--paper);border-right:1px solid var(--rule);\n      border-bottom:1px solid var(--rule-2);box-shadow:var(--pin);padding:12px 13px 12px 20px}\n.lane .name{font:600 12.5px/1.25 var(--sans);letter-spacing:-.01em}\n.lane .pth{font:10px/1.4 var(--mono);color:var(--ink-4);margin-top:3px;\n           display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}\n.lane .tally2{font:10px/1 var(--mono);color:var(--ink-3);margin-top:8px;display:flex;\n              gap:10px;flex-wrap:wrap}\n.lane .tally2 .bad{color:var(--signal);font-weight:600}\n.cell{padding:8px 10px 9px;border-bottom:1px solid var(--rule-2);background:var(--sunken)}\n.cell+.cell{border-left:1px solid var(--rule-2)}\n\n/* ── 卡片（整张是可点的 button）── */\nbutton.card{display:block;width:100%;background:var(--panel);border:1px solid var(--rule);\n            border-radius:3px;box-shadow:0 1px 1px rgba(15,17,20,.03);position:relative;\n            overflow:hidden;cursor:pointer;padding:8px 10px 8px 12px}\nbutton.card+button.card{margin-top:6px}\nbutton.card:hover{background:#fcfcfd;border-color:#c8cdd4}\nbutton.card[aria-expanded="true"]{border-color:#b6bcc5;background:#fcfcfd}\n.l1{display:flex;align-items:center;gap:7px}\n.mark{font:600 11px/1 var(--mono);color:var(--ink-4);flex:none}\n.cid{font:10px/1 var(--mono);color:var(--ink-4);overflow:hidden;text-overflow:ellipsis;\n     white-space:nowrap}\n.tail{margin-left:auto;display:flex;align-items:center;gap:7px;flex:none}\n.stamp{font:600 9.5px/1 var(--mono);color:var(--ink-3);border:1px solid var(--rule);\n       border-radius:2px;padding:2px 4px}\n.chev{font:9px/1 var(--mono);color:var(--ink-4);transition:transform .15s}\nbutton.card[aria-expanded="true"] .chev{transform:rotate(90deg);color:var(--ink-2)}\n.l2{margin-top:5px;font-size:12.5px;line-height:1.45;color:var(--ink);\n    display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}\n.gist{margin-top:6px;font:9.5px/1 var(--mono);color:var(--ink-4);display:flex;gap:12px;flex-wrap:wrap}\n.st-queued .l2{color:var(--ink-3)}\n.st-running{border-color:#c3c9d1}\n.st-running .mark{color:var(--ink)}\n.st-verifying .mark{color:var(--ink-2)}\n.st-failed,.st-timeout{border-color:var(--signal-rule);background:var(--signal-wash);\n                       border-left:3px solid var(--signal)}\n.st-failed .stamp,.st-timeout .stamp{color:var(--signal);border-color:var(--signal-rule);font-weight:600}\n.st-failed .mark,.st-timeout .mark{color:var(--signal)}\n.st-failed .cid,.st-timeout .cid{color:#a2766c}\n.st-running::before,.st-verifying::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;\n  background:linear-gradient(180deg,transparent,var(--ink) 45%,transparent);background-size:100% 220%;\n  animation:flow 1.9s linear infinite}\n.st-verifying::before{background:linear-gradient(180deg,transparent,var(--ink-3) 45%,transparent);\n  background-size:100% 220%;animation-duration:1.1s}\n@keyframes flow{from{background-position:0 -110%}to{background-position:0 110%}}\n@media (prefers-reduced-motion:reduce){\n  .st-running::before,.st-verifying::before{animation:none;background:var(--ink-3)}\n  .chev{transition:none}}\n.empty{color:var(--ink-4);font:10.5px/1 var(--mono);padding:4px 0 0;opacity:.7}\n\n/* ── 右侧抽屉 ── */\n.scrim{position:fixed;inset:0;background:rgba(15,17,20,.16);opacity:0;pointer-events:none;\n       transition:opacity .2s;z-index:40}\nbody.drawer-open .scrim{opacity:1;pointer-events:auto}\n.drawer{position:fixed;top:0;right:0;bottom:0;width:min(492px,94vw);background:var(--panel);\n        border-left:1px solid var(--rule);box-shadow:-18px 0 40px -24px rgba(15,17,20,.45);\n        transform:translateX(101%);transition:transform .22s cubic-bezier(.4,0,.2,1);\n        z-index:50;display:flex;flex-direction:column}\n.drawer.open{transform:none}\n@media (prefers-reduced-motion:reduce){.drawer{transition:none}.scrim{transition:none}}\n.dh{display:flex;align-items:center;gap:9px;padding:14px 16px 12px;border-bottom:1px solid var(--rule);\n    background:var(--paper)}\n.dh .cid{font:600 12px/1 var(--mono);color:var(--ink);overflow:visible}\n.dh .dur{font:10px/1 var(--mono);color:var(--ink-4);margin-left:auto;text-align:right}\n.sc{font:600 10px/1 var(--sans);letter-spacing:.05em;padding:3px 7px;border-radius:2px;\n    background:var(--sunken);color:var(--ink-2);flex:none}\n.sc-running,.sc-verifying{background:#e8ebef;color:var(--ink)}\n.sc-done{background:#e6ebef;color:var(--ink-2)}\n.sc-failed,.sc-timeout{background:var(--signal-wash);color:var(--signal);\n                       box-shadow:inset 0 0 0 1px var(--signal-rule)}\n.dh .x{font:13px/1 var(--mono);color:var(--ink-4);cursor:pointer;padding:2px 4px;margin-left:10px}\n.dh .x:hover{color:var(--ink)}\n.dbody{overflow:auto;padding:0 0 26px}\n.sec{padding:14px 16px;border-bottom:1px solid var(--rule-2)}\n.sec h4{margin:0 0 9px;font:600 9.5px/1 var(--sans);letter-spacing:.06em;color:var(--ink-4);\n        display:flex;align-items:center;gap:9px}\n.live{display:inline-flex;align-items:center;gap:5px;font:9.5px/1 var(--mono);\n      color:var(--ink-2);letter-spacing:0}\n.live i{width:5px;height:5px;border-radius:50%;background:var(--ink);\n        animation:pulse 1.6s ease-in-out infinite}\n@keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}\n@media (prefers-reduced-motion:reduce){.live i{animation:none}}\n.live[data-off] i{background:var(--ink-4);animation:none}\n.full{margin:0;font:10.5px/1.6 var(--mono);color:var(--ink-2);white-space:pre-wrap;\n      word-break:break-word;background:var(--sunken);border:1px solid var(--rule-2);\n      border-radius:3px;padding:10px 11px}\n\n.tl{list-style:none;margin:0;padding:0 0 0 4px}\n.tl .ev{position:relative;display:grid;grid-template-columns:52px 1fr auto;gap:0 11px;\n        padding:0 0 13px 16px;border-left:1px solid var(--rule)}\n.tl .ev:last-child{border-left-color:transparent;padding-bottom:0}\n.tl .dot{position:absolute;left:-4.5px;top:3px;width:8px;height:8px;border-radius:50%;\n         background:var(--panel);border:1.5px solid var(--ink-4)}\n.tl .ev.now .dot{border-color:var(--ink);background:var(--ink);animation:pulse 1.6s ease-in-out infinite}\n.tl .ev.end .dot{border-color:var(--ink-2)}\n.tl .ev.isbad .dot{border-color:var(--signal);background:var(--signal)}\n.tl .t{font:10px/1.5 var(--mono);color:var(--ink-4)}\n.tl .k{font:600 11.5px/1.5 var(--sans);color:var(--ink);grid-column:2}\n.tl .g{font:10px/1.5 var(--mono);color:var(--ink-4);text-align:right}\n.tl .d{grid-column:2/4;font:10px/1.55 var(--mono);color:var(--ink-3);word-break:break-word}\n\n.claim{margin:0;font-size:11.5px;line-height:1.6;color:var(--ink-2)}\ndl{margin:0;display:grid;grid-template-columns:auto 1fr;gap:3px 12px}\ndt{font:10px/1.5 var(--sans);color:var(--ink-4);white-space:nowrap}\ndd{margin:0;font:10.5px/1.5 var(--mono);color:var(--ink);word-break:break-word}\n.verdict{padding:13px 16px;display:flex;flex-direction:column;gap:7px}\n.vmark{align-self:flex-start;font:600 9.5px/1 var(--mono);letter-spacing:.1em;padding:4px 7px;\n       border:1px solid var(--ink);border-radius:2px;color:var(--ink)}\n.verdict.bad .vmark{border-color:var(--signal);color:var(--signal);background:var(--signal-wash)}\n.vcmd{font:9.5px/1.45 var(--mono);color:var(--ink-3);overflow-wrap:break-word;word-break:normal;\n      display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}\n'
_SCRIPT = '<script>\n(function () {\n  var POLL_MS = 2000, timers = {}, current = null;\n\n  function rows() { return document.querySelectorAll(\'.rowrow[data-project]\'); }\n  function boxes() { return document.querySelectorAll(\'.plist input[type=checkbox]\'); }\n\n  function applyFilter() {\n    var on = {}, n = 0;\n    boxes().forEach(function (b) { on[b.value] = b.checked; if (b.checked) n++; });\n    rows().forEach(function (r) {\n      r.style.display = on[r.dataset.project] ? \'contents\' : \'none\';\n    });\n    document.getElementById(\'rail-count\').textContent = n + \' / \' + boxes().length + \' 显示\';\n  }\n  boxes().forEach(function (b) { b.addEventListener(\'change\', applyFilter); });\n  document.querySelector(\'[data-all]\').addEventListener(\'click\', function () {\n    boxes().forEach(function (b) { b.checked = true; }); applyFilter();\n  });\n  document.querySelector(\'[data-none]\').addEventListener(\'click\', function () {\n    boxes().forEach(function (b) { b.checked = false; }); applyFilter();\n  });\n  applyFilter();\n\n  function close() {\n    if (current) {\n      current.classList.remove(\'open\');\n      var card = document.querySelector(\'[data-task="\' + current.id + \'"]\');\n      if (card) card.setAttribute(\'aria-expanded\', \'false\');\n      if (timers[current.id]) { clearInterval(timers[current.id]); delete timers[current.id]; }\n    }\n    current = null;\n    document.body.classList.remove(\'drawer-open\');\n    if (location.hash) history.replaceState(null, \'\', location.pathname + location.search);\n  }\n\n  function poll(d) {\n    var el = d.querySelector(\'[data-live]\');\n    if (!el) return;\n    // 正式实现：服务端提供 /api/tasks/<id>/events，返回该任务的增量事件\n    fetch(\'/api/tasks/\' + d.id.replace(/^task-/, \'\') + \'/events\', {cache: \'no-store\'})\n      .then(function (r) { if (!r.ok) throw 0; return r.json(); })\n      .then(function () { el.innerHTML = \'<i></i>实时 · 每 2 秒\'; })\n      .catch(function () {\n        // 静态快照 / 无该接口 → 明确标注降级，不假装还在实时\n        el.setAttribute(\'data-off\', \'\');\n        el.innerHTML = \'<i></i>静态快照 · 无法实时更新\';\n        if (timers[d.id]) { clearInterval(timers[d.id]); delete timers[d.id]; }\n      });\n  }\n\n  function open(id) {\n    var d = document.getElementById(id);\n    if (!d) return;\n    if (current && current !== d) close();\n    d.classList.add(\'open\');\n    document.body.classList.add(\'drawer-open\');\n    current = d;\n    var card = document.querySelector(\'[data-task="\' + id + \'"]\');\n    if (card) card.setAttribute(\'aria-expanded\', \'true\');\n    if (history.replaceState) history.replaceState(null, \'\', \'#\' + id);\n    var t = d.querySelector(\'[data-live]\');\n    if (t) { t.removeAttribute(\'data-off\'); t.innerHTML = \'<i></i>实时 · 每 2 秒\'; poll(d);\n             timers[id] = setInterval(function () { poll(d); }, POLL_MS); }\n  }\n\n  document.querySelectorAll(\'button.card\').forEach(function (c) {\n    c.addEventListener(\'click\', function () { open(c.dataset.task); });\n  });\n  document.querySelectorAll(\'[data-close]\').forEach(function (el) {\n    el.addEventListener(\'click\', close);\n  });\n  document.addEventListener(\'keydown\', function (e) { if (e.key === \'Escape\') close(); });\n  if (location.hash) {\n    var d = document.getElementById(location.hash.slice(1));\n    if (d) open(location.hash.slice(1));\n  }\n})();\n</script>'


def _escape(value) -> str:
    """HTML-escape any value (None -> empty string). Always quote attrs."""
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _status_bucket(status) -> str:
    text = "" if status is None else str(status)
    return text if text in _STATUS_ORDER else "failed"


def _status_glyph(status) -> str:
    bucket = _status_bucket(status)
    for key, _, glyph in _STATUSES:
        if key == bucket:
            return glyph
    return "?"


def _status_label(status) -> str:
    bucket = _status_bucket(status)
    for key, label, _ in _STATUSES:
        if key == bucket:
            return label
    return bucket


def _status_chip(status) -> str:
    bucket = _status_bucket(status)
    return f'<span class="sc sc-{_escape(bucket)}">{_escape(_status_label(bucket))}</span>'


def _parse_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _format_seconds(seconds) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds} 秒"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} 分 {sec:02d} 秒"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} 小时 {minutes:02d} 分"


def _duration_seconds(started, finished, reference):
    start = _parse_time(started)
    if start is None:
        return None
    end = _parse_time(finished) or _parse_time(reference)
    if end is None:
        return None
    return max(0, int((end - start).total_seconds()))


def _task_duration(task, reference) -> str:
    raw_status = str(task.get("status") or "")
    started = task.get("started_at")
    if not started and raw_status == "queued":
        started = task.get("created_at")
        prefix = "排队 "
    else:
        prefix = "已跑 " if raw_status in _LIVE else ""
    seconds = _duration_seconds(started, task.get("finished_at"), reference)
    if seconds is None:
        return "—"
    return prefix + _format_seconds(seconds)


def _files_text(count) -> str:
    number = _as_int(count)
    if number is None:
        return "—"
    return f"{number} file" if number == 1 else f"{number} files"


def _meta_parts(task, reference):
    adapter = str(task.get("adapter") or "—")
    attempt = _as_int(task.get("attempt"))
    if attempt is None:
        first = adapter
    else:
        first = f"{adapter} · {attempt} attempt" + ("s" if attempt != 1 else "")
    parts = [first]
    duration = _task_duration(task, reference)
    if duration != "—":
        parts.append(duration)
    files = _as_int(task.get("files_changed"))
    if files is not None:
        parts.append(_files_text(files))
    return parts


def _load_registered_projects(workspace):
    """Best-effort registry read: ``[{id, path, group}]`` in file order."""
    try:
        reg = registry.load(registry.workspace_registry_path(workspace))
    except Exception:
        return []
    return [{"id": p.id, "path": p.path, "group": p.group} for p in reg.projects]


def _known_project_ids(workspace):
    """Every project id the board knows about, in navigation order."""
    ids = []
    seen = set()
    conn = storage.connect(storage.db_path(workspace))
    try:
        storage.migrate(conn)
        for row in storage.project_overview(conn):
            pid = row["project"]
            if pid not in seen:
                seen.add(pid)
                ids.append(pid)
    finally:
        conn.close()
    for proj in _load_registered_projects(workspace):
        if proj["id"] not in seen:
            seen.add(proj["id"])
            ids.append(proj["id"])
    return ids


def known_project_ids(workspace):
    """Project ids the ``?project=`` query may select."""
    return _known_project_ids(workspace)


def _load_events(conn, task_id):
    events = []
    for row in storage.list_events(conn, task_id):
        item = dict(row)
        raw = item.get("payload")
        if raw is not None:
            try:
                item["payload"] = json.loads(raw)
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
        events.append(item)
    return events


def _payload_summary(payload):
    if not isinstance(payload, dict):
        return ""
    value = payload.get("summary")
    if value is None:
        return ""
    text = str(value).strip()
    return text


def _summary_from_result(task):
    path = task.get("result_path")
    if not path or not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return ""
    return _payload_summary(payload)


def _task_summary(task, events):
    for event in reversed(events):
        summary = _payload_summary(event.get("payload"))
        if summary:
            return summary
    return _summary_from_result(task)


def _json_text(value) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
    except (TypeError, ValueError):
        return str(value)


def _event_kind(name) -> str:
    return {
        "started": "开始",
        "queued": "入队",
        "result_schema": "结构化契约",
        "adapter": "适配器",
        "verify": "验收",
        "done": "完成",
        "failed": "失败",
        "timeout": "超时",
        "forbidden": "越界",
        "worktree_created": "工作树",
        "worktree_removed": "清理工作树",
        "worktree_cleanup_failed": "清理失败",
    }.get(str(name or ""), str(name or "事件"))


def _event_detail(event) -> str:
    name = str(event.get("event") or "")
    payload = event.get("payload")
    if not isinstance(payload, dict):
        if payload is None:
            return ""
        return _json_text(payload)

    if name == "started":
        parts = []
        if payload.get("project") is not None:
            parts.append("project=" + str(payload.get("project")))
        if payload.get("adapter") is not None:
            parts.append("adapter=" + str(payload.get("adapter")))
        if payload.get("worktree"):
            parts.append("worktree")
        return " · ".join(parts) or _json_text(payload)
    if name == "result_schema":
        if payload.get("path"):
            return str(payload.get("path"))
        return str(payload.get("note") or _json_text(payload))
    if name == "adapter":
        parts = []
        if payload.get("exit_code") is not None:
            parts.append("退出 " + str(payload.get("exit_code")))
        if payload.get("degraded") is True:
            parts.append("已降级")
        elif payload.get("degraded") is False:
            parts.append("未降级")
        return " · ".join(parts) or _json_text(payload)
    if name == "verify":
        parts = []
        if payload.get("status") is not None:
            parts.append(str(payload.get("status")))
        if payload.get("exit_code") is not None:
            parts.append(str(payload.get("exit_code")))
        if payload.get("note"):
            parts.append(str(payload.get("note")))
        return " · ".join(parts) or _json_text(payload)
    if name == "done":
        files = _as_int(payload.get("files_changed"))
        if files is not None:
            return _files_text(files) + " changed"
        return str(payload.get("summary") or _json_text(payload))
    if name == "failed":
        for key in ("reason", "note", "stage"):
            if payload.get(key):
                return str(payload.get(key))
        paths = payload.get("paths")
        if isinstance(paths, list):
            return "paths=" + ",".join(str(path) for path in paths)
        return _json_text(payload)
    if name == "timeout":
        return str(payload.get("detail") or payload.get("reason") or _json_text(payload))
    if name == "forbidden":
        paths = payload.get("paths")
        if isinstance(paths, list):
            return "paths=" + ",".join(str(path) for path in paths)
    return _json_text(payload)


def _event_gap(events, index) -> str:
    if index >= len(events) - 1:
        return ""
    current = _parse_time(events[index].get("ts"))
    following = _parse_time(events[index + 1].get("ts"))
    if current is None or following is None:
        return ""
    seconds = max(0, int((following - current).total_seconds()))
    return f"{seconds}s"


def _timeline_html(events, live) -> str:
    items = []
    for index, event in enumerate(events):
        last = index == len(events) - 1
        classes = ["ev"]
        if last and live:
            classes.append("now")
        if last:
            classes.append("end")
        if str(event.get("event") or "") in ("failed", "timeout", "forbidden"):
            classes.append("isbad")
        gap = _event_gap(events, index)
        gap_html = f'<span class="g">{_escape(gap)}</span>' if gap else ""
        items.append(
            f'<li class="{" ".join(classes)}">'
            f'<span class="t">{_escape(_time_label(event.get("ts")))}</span>'
            f'<span class="dot"></span>'
            f'<span class="k">{_escape(_event_kind(event.get("event")))}</span>'
            f'{gap_html}'
            f'<span class="d">{_escape(_event_detail(event))}</span>'
            "</li>"
        )
    if not items:
        return '<ol class="tl"></ol>'
    return '<ol class="tl">\n' + "\n".join(items) + "\n</ol>"


def _time_label(value) -> str:
    parsed = _parse_time(value)
    if parsed is None:
        return "—"
    return parsed.strftime("%H:%M:%S")


def _card(task, selected_task_id, reference) -> str:
    task_id = str(task.get("id") or "")
    raw_status = str(task.get("status") or "")
    bucket = _status_bucket(raw_status)
    stamp = None
    if raw_status in ("done", "failed"):
        stamp = task.get("verify_exit")
        if stamp is None:
            stamp = "0" if raw_status == "done" else "1"
    meta = "".join(f"<span>{_escape(part)}</span>" for part in _meta_parts(task, reference))
    expanded = "true" if selected_task_id == task_id else "false"
    stamp_html = f'<span class="stamp">{_escape(stamp)}</span>' if stamp is not None else ""
    return "\n".join([
        f'<button type="button" class="card st-{_escape(bucket)}" data-task="{_escape("task-" + task_id)}" aria-expanded="{expanded}">',
        '<div class="l1">',
        f'<span class="mark">{_escape(_status_glyph(bucket))}</span>',
        f'<span class="cid">{_escape(task_id)}</span>',
        '<span class="tail">',
        stamp_html,
        '<span class="chev" aria-hidden="true">▸</span>',
        "</span></div>",
        f'<div class="l2">{_escape(task.get("brief"))}</div>',
        (f'<div class="gist">{meta}</div>' if meta else ""),
        "</button>",
    ])


def _verdict_html(task) -> str:
    raw_status = str(task.get("status") or "")
    if raw_status == "done":
        label = "PASSED"
        code = task.get("verify_exit")
        if code is None:
            code = 0
        bad = False
    elif raw_status in ("failed", "timeout", "blocked", "cancelled"):
        label = "FAILED"
        code = task.get("verify_exit")
        if code is None:
            code = task.get("exit_code")
        if code is None:
            code = 1
        bad = True
    else:
        return ""
    command = task.get("verify_cmd") or "—"
    bad_class = " bad" if bad else ""
    return (
        f'<div class="verdict{bad_class}">'
        f'<span class="vmark">VERIFY {_escape(label)} {_escape(code)}</span>'
        f'<span class="vcmd" title="{_escape(command)}">{_escape(command)}</span>'
        "</div>"
    )


def _evidence_html(task, events, reference) -> str:
    verify_exit = task.get("verify_exit")
    verify_note = ""
    for event in reversed(events):
        if str(event.get("event") or "") != "verify":
            continue
        payload = event.get("payload")
        if isinstance(payload, dict):
            if verify_exit is None:
                verify_exit = payload.get("exit_code")
            verify_note = str(payload.get("note") or "")
        break
    verify_text = "—" if verify_exit is None else str(verify_exit)
    if verify_note:
        verify_text += " · " + verify_note
    files = task.get("files_changed")
    files_text = "—" if files is None else _files_text(files) + " changed"
    adapter = str(task.get("adapter") or "—")
    if task.get("model"):
        adapter += " " + str(task.get("model"))
    window_start = _time_label(task.get("started_at") or task.get("created_at"))
    window_end = _time_label(task.get("finished_at") or reference)
    rows = (
        ("exit", "—" if task.get("exit_code") is None else task.get("exit_code")),
        ("verify", verify_text),
        ("files", files_text),
        ("adapter", adapter),
        ("时间窗口", window_start + " → " + window_end),
    )
    return "".join(
        f"<dt>{_escape(key)}</dt><dd>{_escape(value)}</dd>" for key, value in rows
    )


def _drawer(task, events, selected_task_id, reference) -> str:
    task_id = str(task.get("id") or "")
    raw_status = str(task.get("status") or "")
    bucket = _status_bucket(raw_status)
    drawer_id = "task-" + task_id
    classes = "drawer open" if selected_task_id == task_id else "drawer"
    live = raw_status in _LIVE
    header_meta = " · ".join(_meta_parts(task, reference))
    parts = [
        f'<aside class="{classes}" id="{_escape(drawer_id)}" hidden>',
        '<header class="dh">',
        f'<span class="mark">{_escape(_status_glyph(bucket))}</span>',
        f'<span class="cid">{_escape(task_id)}</span>',
        _status_chip(bucket),
        f'<span class="dur">{_escape(header_meta)}</span>',
        '<button type="button" class="x" data-close aria-label="关闭">✕</button>',
        "</header>",
        '<div class="dbody">',
        '<section class="sec"><h4>任务全文</h4>'
        f'<pre class="full">{_escape(task.get("brief"))}</pre></section>',
    ]
    live_html = '<span class="live" data-live><i></i>实时 · 每 2 秒</span>' if live else ""
    parts.append(
        '<section class="sec"><h4>进度' + live_html + "</h4>"
        + _timeline_html(events, live) + "</section>"
    )
    summary = _task_summary(task, events)
    if summary:
        parts.append(
            '<section class="sec"><h4>worker 声称</h4>'
            f'<p class="claim">{_escape(summary)}</p></section>'
        )
    parts.append(
        '<section class="sec"><h4>系统证据</h4><dl>'
        + _evidence_html(task, events, reference)
        + "</dl></section>"
    )
    verdict = _verdict_html(task)
    if verdict:
        parts.append(verdict)
    parts += ["</div></aside>"]
    return "\n".join(parts)


def _rail_html(lanes, total) -> str:
    parts = [
        '<aside class="rail">',
        '<div class="rh"><span>项目</span><span class="rn" id="rail-count"></span></div>',
        '<div class="rquick"><button type="button" data-all>全选</button>'
        '<button type="button" data-none>清空</button></div>',
        '<ul class="plist">',
    ]
    for pid, tasks in lanes:
        bad = sum(1 for task in tasks if _status_bucket(task.get("status")) in _BAD)
        bad_html = f"<em>{_escape(bad)}</em>" if bad else ""
        parts.append(
            '<li><label class="prow">'
            f'<input type="checkbox" value="{_escape(pid)}" checked>'
            '<span class="box" aria-hidden="true"></span>'
            f'<span class="pname">{_escape(pid)}</span>'
            f'<span class="pn">{_escape(len(tasks))}{bad_html}</span>'
            "</label></li>"
        )
    parts.append("</ul>")
    parts.append(
        f'<div class="rfoot">{_escape(len(lanes))} 个项目 · {_escape(total)} 个任务</div>'
    )
    parts.append("</aside>")
    return "\n".join(parts)


def _grid_html(lanes, status_counts, events_by_task, selected_task_id, reference, paths):
    parts = ['<div class="matrix"><div class="grid">', '<div class="hd corner">项目</div>']
    for status, label, _ in _STATUSES:
        count = status_counts.get(status, 0)
        count_html = f'<span class="n">{_escape(count)}</span>' if count else ""
        parts.append(
            f'<div class="hd st-h-{_escape(status)}">{_escape(label)}{count_html}</div>'
        )
    for pid, tasks in lanes:
        parts.append(
            f'<div class="rowrow" data-project="{_escape(pid)}" style="display:contents">'
        )
        bad = sum(1 for task in tasks if _status_bucket(task.get("status")) in _BAD)
        path = paths.get(pid) or "—"
        parts.append('<div class="lane">')
        parts.append(f'<div class="name">{_escape(pid)}</div>')
        parts.append(f'<div class="pth">{_escape(path)}</div>')
        parts.append('<div class="tally2">')
        parts.append(f"<span>{_escape(len(tasks))} 任务</span>")
        if bad:
            parts.append(f'<span class="bad">{_escape(bad)} 未通过</span>')
        parts.append("</div></div>")
        buckets = {status: [] for status in _STATUS_ORDER}
        for task in tasks:
            buckets[_status_bucket(task.get("status"))].append(task)
        for status, _, _ in _STATUSES:
            parts.append('<div class="cell">')
            if buckets[status]:
                for task in buckets[status]:
                    parts.append(_card(task, selected_task_id, reference))
            else:
                parts.append('<div class="empty">—</div>')
            parts.append("</div>")
        parts.append("</div>")
    parts.append("</div></div>")
    return "\n".join(parts)


def render_board(workspace: str, *, limit: int = 200,
                 projects=None, task=None, serve=False) -> str:
    """Render a self-contained board with optional project/task selection."""
    reference = storage.now_iso()
    if projects is None:
        selected = None
    elif isinstance(projects, str):
        selected = [projects] if projects else None
    else:
        selected = [str(pid) for pid in projects if pid is not None and str(pid) != ""]
        if not selected:
            selected = None
    if selected is not None:
        deduped = []
        seen = set()
        for pid in selected:
            if pid not in seen:
                seen.add(pid)
                deduped.append(pid)
        selected = deduped
    selected_task_id = None if task is None else str(task)

    conn = storage.connect(storage.db_path(workspace))
    try:
        storage.migrate(conn)
        rows = []
        if selected is None:
            rows = [dict(row) for row in storage.list_tasks(conn, limit=limit)]
        else:
            seen = set()
            for pid in selected:
                for row in storage.list_tasks(conn, project=pid, limit=limit):
                    item = dict(row)
                    if item.get("id") in seen:
                        continue
                    seen.add(item.get("id"))
                    rows.append(item)
            rows.sort(key=lambda item: item.get("created_at") or "", reverse=True)
            rows = rows[:limit]
        events_by_task = {str(row.get("id") or ""): _load_events(conn, row.get("id")) for row in rows}
    finally:
        conn.close()

    grouped = dict(storage.group_tasks_by_project(rows))
    if selected is None:
        lanes = storage.group_tasks_by_project(rows)
    else:
        lanes = [(pid, grouped[pid]) for pid in selected if pid in grouped]

    registered = {proj["id"]: proj for proj in _load_registered_projects(workspace)}
    paths = {}
    for pid, tasks in lanes:
        path = (registered.get(pid) or {}).get("path")
        if not path:
            for item in tasks:
                if item.get("workdir"):
                    path = item.get("workdir")
                    break
        paths[pid] = path or "—"
    if selected_task_id is not None and selected_task_id not in events_by_task:
        selected_task_id = None

    status_counts = {status: 0 for status in _STATUS_ORDER}
    for item in rows:
        status_counts[_status_bucket(item.get("status"))] += 1
    total = len(rows)
    alive = sum(1 for item in rows if str(item.get("status") or "") in _LIVE)
    bad = status_counts["failed"] + status_counts["timeout"]
    generated = _parse_time(reference)
    generated_text = generated.strftime("%m-%d %H:%M") if generated is not None else reference

    body_class = ' class="drawer-open"' if selected_task_id is not None else ""
    parts = [
        "<!doctype html>",
        '<html lang="zh-CN">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>taskproof · 调度台账</title>",
        f"<style>\n{_STYLE}</style>",
        "</head>",
        f"<body{body_class}>",
        '<div class="mast">',
        '<h1>taskproof <span>/ 调度台账</span></h1>',
        '<div class="tally">',
        f'<span>任务<b>{_escape(total)}</b></span>',
        f'<span>在飞<b>{_escape(alive)}</b></span>',
        f'<span class="alarm">未通过<b>{_escape(bad)}</b></span>',
        f'<span class="gen">生成于 {_escape(generated_text)}</span>',
        "</div></div>",
        '<div class="shell">',
        _rail_html(lanes, total),
        _grid_html(lanes, status_counts, events_by_task, selected_task_id, reference, paths),
        "</div>",
        '<div class="scrim" data-close></div>',
    ]
    for _, tasks in lanes:
        for item in tasks:
            parts.append(
                _drawer(item, events_by_task.get(str(item.get("id") or ""), []), selected_task_id, reference)
            )
    parts += [_SCRIPT, "</body>", "</html>", ""]
    return "\n".join(parts)
