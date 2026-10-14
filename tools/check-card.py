#!/usr/bin/env python3
"""发车前给「观感卡」跑四查（铁律 12 的机判部分）。

观感卡 = 卡文头部有 `region:` 与 `口径:` 两个头的卡。四查：

  1. `口径:` 指的文件存在；
  2. 锚点（`#标题`）或行号范围（`:a-b`）在那个文件里解析得出来；
  3. store 在**本区域上一张卡之后被写过**（防停更——停更的 store 比没有 store 更坏，
     因为卡会不再引它、改回去描述现象）；
  4. store 所在目录**在 git 里没有未提交改动**（防并发写入：同一功能可能有第二个会话在写
     同一份 store，mtime 分不清「我忘了回写」与「别人刚写过」。store 不在 git 里时这条跳过并说明）。

第 2 条只判「解析得出来」，**判不了「那里的文字就是卡里说的那些」** —— 那一条仍是主智能体读的活。
第 3 条的「本区域上一张卡」从 taskproof 账本里取（卡文的 `region:` 头就在 `brief` 里，不必改库）。

用法:
    check-card.py <卡文件> [--tasks-json FILE] [--quiet] [--json]

退出码: 0 四查全过（或非观感卡）/ 1 有查不过 / 2 用法错误或卡文件读不到。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import subprocess
import sys

REGION_RE = re.compile(r"^region:[ \t]*(\S+)[ \t]*$", re.M)
HEADER_RE = re.compile(r"^(?:口径|spec):[ \t]*(.+?)[ \t]*$", re.M)
HEADING_RE = re.compile(r"^#{1,6}[ \t]+(.+?)[ \t]*$", re.M)
TASK_REGION_RE = r"^region:[ \t]*%s[ \t]*$"


def _fail(msg: str, code: int = 2) -> "None":
    print(f"check-card: {msg}", file=sys.stderr)
    sys.exit(code)


def parse_card(path: str) -> tuple:
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        _fail(f"读不到卡文件 {path}: {exc}")
    region_m = REGION_RE.search(text)
    header_m = HEADER_RE.search(text)
    region = region_m.group(1) if region_m else None
    header = header_m.group(1) if header_m else None
    # 支持 `口径: <path> # 说明` —— 只取第一个空格前的那个 token
    if header and " " in header:
        header = header.split(" ", 1)[0]
    return region, header, text


def split_pointer(pointer: str) -> tuple:
    """`<path>#<anchor>` 或 `<path>:<a>` / `<path>:<a>-<b>` → (path, kind, payload)."""
    if "#" in pointer:
        path, anchor = pointer.split("#", 1)
        return path, "anchor", anchor
    m = re.match(r"^(.*?):(\d+)(?:-(\d+))?$", pointer)
    if m:
        a = int(m.group(2))
        b = int(m.group(3)) if m.group(3) else a
        return m.group(1), "lines", (a, b)
    return pointer, "none", None


def check_file(store_path: str) -> tuple:
    if not os.path.isfile(store_path):
        return False, f"文件不存在：{store_path}"
    return True, f"文件存在：{store_path} ({os.path.getsize(store_path)} B)"


def check_anchor(store_path: str, kind: str, payload) -> tuple:
    with open(store_path, encoding="utf-8") as fh:
        lines = fh.readlines()
    if kind == "anchor":
        if not payload:
            return False, "`口径:` 的锚点是空的（`#` 后面没写标题）"
        heads = [(i + 1, m.group(1)) for i, ln in enumerate(lines)
                 for m in [HEADING_RE.match(ln)] if m]
        for num, head in heads:
            if head == payload:
                return True, f"锚点精确命中 `#{payload}`（{store_path}:{num}）"
        for num, head in heads:
            if payload in head:
                return True, f"锚点命中 `#{payload}` → 第 {num} 行 `{head}`"
        sample = "; ".join(h[1] for h in heads[:8])
        return False, f"锚点 `#{payload}` 在该文件的标题里找不到。现有标题前几个：{sample}"
    if kind == "lines":
        a, b = payload
        if a < 1 or b > len(lines):
            return False, f"行号范围 {a}-{b} 超出文件边界（共 {len(lines)} 行）"
        snippet = "".join(lines[a - 1:b]).strip().replace("\n", " ⏎ ")[:120]
        return True, f"行号 {a}-{b} 落在文件内（共 {len(lines)} 行）：{snippet}"
    return False, "`口径:` 没带锚点也没带行号范围（写成 `<path>#<标题>` 或 `<path>:<a>-<b>`）"


def load_tasks(tasks_json: str) -> list:
    if tasks_json:
        try:
            with open(tasks_json, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            _fail(f"读不到 --tasks-json {tasks_json}: {exc}")
    else:
        try:
            out = subprocess.run(["taskproof", "--json", "tasks", "--all"],
                                 capture_output=True, text=True, timeout=180)
        except (OSError, subprocess.SubprocessError) as exc:
            _fail(f"跑不动 `taskproof --json tasks --all`: {exc}")
        if out.returncode != 0:
            head = (out.stderr or out.stdout).strip().splitlines()
            _fail(f"`taskproof --json tasks --all` 退出码 {out.returncode}: {head[:1]}")
        try:
            data = json.loads(out.stdout)
        except json.JSONDecodeError as exc:
            _fail(f"taskproof 的 --json 输出不是 JSON: {exc}")
    if isinstance(data, dict):
        return data.get("tasks") or []
    return data or []


def _when(task: dict) -> str:
    return task.get("created_at") or task.get("started_at") or ""


def check_freshness(store_path: str, region: str, tasks: list) -> tuple:
    pat = re.compile(TASK_REGION_RE % re.escape(region), re.M)
    hits = [t for t in tasks if pat.search(t.get("brief") or "")]
    if not hits:
        return True, f"账本里 region=`{region}` 没有上一张卡（无停更可比）"
    latest = max(hits, key=_when)
    stamp = _when(latest)
    try:
        last = _dt.datetime.fromisoformat(stamp)
    except ValueError:
        return True, (f"region=`{region}` 上一张卡 {latest.get('id')} 的时间戳"
                      f"（{stamp}）解析不了，跳过停更检查")
    store_mtime = _dt.datetime.fromtimestamp(os.path.getmtime(store_path)).astimezone(last.tzinfo)
    delta = (store_mtime - last).total_seconds()
    detail = (f"region=`{region}` 上一张卡 {latest.get('id')} @ {stamp}；"
              f"store mtime {store_mtime.isoformat(timespec='seconds')}（差 {delta:+.0f}s）")
    if delta <= 0:
        return False, (detail + " → store 在上一张卡之后没被写过，"
                                "先回写 store 再发车")
    return True, detail


def check_store_clean(store_path: str) -> tuple:
    """store 所在目录在 git 里必须没有未提交改动 —— 挡并发写入方。

    范围取 store 文件所在**目录**（不是单个文件）：同一份 store 里别的文件也可能被引，
    半途被改的状态比单文件更值得停一下。不在 git 仓里就跳过并说明。
    """
    directory = os.path.realpath(os.path.dirname(os.path.abspath(store_path)))
    try:
        root = subprocess.run(["git", "-C", directory, "rev-parse", "--show-toplevel"],
                              capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as exc:
        return True, f"跑不动 git 判断并发写入（{exc}），跳过"
    if root.returncode != 0:
        return True, "store 不在 git 仓里 → 判不了并发写入（建议给 store 建仓）"
    # realpath 两边都要做：/tmp 在 macOS 是 /private/tmp 的软链，不归一的话 relpath 会算出
    # `../../../tmp/...` 这种越界相对路径，git status 收到它什么都不报，看着像「干净」（实测）。
    repo = os.path.realpath(root.stdout.strip())
    rel = os.path.relpath(directory, repo)
    if rel.startswith(".."):
        return True, f"store 目录与仓根算不出包含关系（{directory} vs {repo}），跳过"
    try:
        st = subprocess.run(["git", "-C", repo, "status", "--porcelain", "--", rel],
                            capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        return True, f"跑不动 git status（{exc}），跳过"
    dirty = [line for line in st.stdout.splitlines() if line.strip()]
    if dirty:
        shown = "; ".join(line.strip()[:80] for line in dirty[:5])
        more = "" if len(dirty) <= 5 else f"（共 {len(dirty)} 条）"
        return False, (f"store 目录有未提交改动 {shown}{more} → 先弄清那份改动是谁的、"
                       "要不要留，再写卡")
    return True, f"store 目录在 git 里干净（{repo}/{rel}）"


def main() -> int:
    ap = argparse.ArgumentParser(description="观感卡发车前四查（铁律 12）")
    ap.add_argument("card")
    ap.add_argument("--tasks-json", help="离线用：自定义的 taskproof tasks JSON")
    ap.add_argument("--quiet", action="store_true", help="只打印结论行")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    region, header, _ = parse_card(args.card)
    results, ok = [], True

    skipped = (not region and not header)
    if skipped:
        results.append(("skip", "卡文没有 `region:` / `口径:` 头 → 非观感卡，四查跳过"))
    else:
        if not region:
            ok = False
            results.append(("fail", "有 `口径:` 但缺 `region:` 头（收敛预算要靠它计数）"))
        elif region.lower() == "none":
            results.append(("skip", "`region: none` → 非观感卡，四查跳过"))
            skipped = True
        if not skipped:
            if not header or header.lower() == "none":
                ok = False
                results.append(("fail", "观感卡必须有 `口径:` 指针（`<绝对路径>#<标题>` 或 `:a-b`）"))
            else:
                store_path, kind, payload = split_pointer(header)
                if not os.path.isabs(store_path):
                    store_path = os.path.normpath(
                        os.path.join(os.path.dirname(os.path.abspath(args.card)), store_path))
                fine, detail = check_file(store_path)
                ok = ok and fine
                results.append(("pass" if fine else "fail", "查1 存在：" + detail))
                if fine:
                    fine2, detail2 = check_anchor(store_path, kind, payload)
                    ok = ok and fine2
                    results.append(("pass" if fine2 else "fail", "查2 锚点：" + detail2))
                    fine3, detail3 = check_freshness(store_path, region, load_tasks(args.tasks_json))
                    ok = ok and fine3
                    results.append(("pass" if fine3 else "fail", "查3 停更：" + detail3))
                    fine4, detail4 = check_store_clean(store_path)
                    ok = ok and fine4
                    results.append(("pass" if fine4 else "fail", "查4 并发写入：" + detail4))

    if args.json:
        print(json.dumps({"card": args.card, "region": region, "口径": header,
                          "ok": ok and not skipped, "skipped": skipped,
                          "checks": [{"result": r, "detail": d} for r, d in results]},
                         ensure_ascii=False, indent=2))
    else:
        if not args.quiet:
            print(f"check-card: {args.card}")
            print(f"  region={region!r}  口径={header!r}")
        for r, d in results:
            print(f"  [{r.upper()}] {d}")
        print("  结论：" + ("非观感卡，四查跳过" if skipped else ("四查全过 → 可以发车" if ok else "有查不过 → 不许发车")))
    return 0 if (ok or skipped) else 1


if __name__ == "__main__":
    sys.exit(main())
