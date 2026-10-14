#!/usr/bin/env python3
"""发车前给「观感卡」跑适用项检查（铁律 12 的机判部分）。

观感卡 = 卡文头部带**参照物头**的卡。两个头，取其一：

    region:  <区域 slug>          # 收敛预算的计数单位；用 `口径:` 时必填
    口径:    <store 文件>#<锚点>   # 参照物是 store（会变、要回写）
    参照物:  <原型/既有实现>:a-b    # 参照物是不可变来源（不会变、没有回写义务）

四条检查，**按参照物种类决定跑哪几条**：

  1. 存在：参照物那个文件在不在；                       ← 两类都跑
  2. 锚点：`#标题` 或行号范围 `:a-b` 在那个文件里解析得出； ← 两类都跑
  3. 停更：store 在**本区域上一张卡之后被写过**；          ← 只对 `口径:` 有意义
     （原型不会变，也没人欠它一次回写，所以对 `参照物:` 标 n/a，
     不标 pass——不适用 ≠ 通过。）
  4. 并发：参照物所在目录**在 git 里没有未提交改动**。      ← 只对 `口径:` 有意义

第 2 条只判「解析得出来」，**判不了「那里的文字就是卡里说的那些」** —— 那一条仍是主智能体读的活。
第 3 条的「本区域上一张卡」从 taskproof 账本里取（卡文的 `region:` 头就在 `brief` 里，不必改库）。

`region: none` 表示这条卡不纳管收敛预算：查 3 标 n/a，其余照跑。

用法:
    check-card.py <卡文件> [--tasks-json FILE] [--quiet] [--json]

退出码: 0 适用项全过（或非观感卡）/ 1 有查不过 / 2 用法错误或卡文件读不到。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import subprocess
import sys
from typing import NoReturn

REGION_RE = re.compile(r"^region:[ \t]*(\S+)[ \t]*$", re.M)
STORE_RE = re.compile(r"^(?:口径|spec):[ \t]*(.+?)[ \t]*$", re.M)
REF_RE = re.compile(r"^(?:参照物|reference):[ \t]*(.+?)[ \t]*$", re.M)
HEADING_RE = re.compile(r"^#{1,6}[ \t]+(.+?)[ \t]*$", re.M)
TASK_REGION_RE = r"^region:[ \t]*%s[ \t]*$"


def _fail(msg: str, code: int = 2) -> NoReturn:
    print(f"check-card: {msg}", file=sys.stderr)
    sys.exit(code)


def _clean_value(value: str) -> str:
    """把头的值收拾干净：去首尾空白、去行尾 HTML 注释、去包裹的反引号/引号。

    **不按空格切** —— 参照物路径里可能有空格（本项目原型就在 `3.0 原型页面/` 下，
    实测按第一个空格切会把 `/…/c需求分析/3.0` 当成路径，报「文件不存在」）。
    要写说明就另起一行。
    """
    v = re.sub(r"\s*<!--.*?-->\s*$", "", value.strip(), flags=re.S).strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "`\"'":
        v = v[1:-1]
    return v


def parse_card(path: str) -> tuple:
    """→ (region, 参照物指针, 参照物是不是 store, 卡文原文)"""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        _fail(f"读不到卡文件 {path}: {exc}")
    store_m = STORE_RE.search(text)
    ref_m = REF_RE.search(text)
    region_m = REGION_RE.search(text)
    region = region_m.group(1) if region_m else None
    if store_m:
        value = _clean_value(store_m.group(1))
        return region, (None if value.lower() in ("none", "-", "") else value), True, text
    if ref_m:
        value = _clean_value(ref_m.group(1))
        return region, (None if value.lower() in ("none", "-", "") else value), False, text
    return region, None, False, text


def split_pointer(pointer: str) -> tuple:
    """`<path>#<anchor>` / `<path>:<a>` / `<path>:<a>-<b>` / `screenshot:<path>`
    → (path, kind, payload)"""
    if pointer.startswith("screenshot:"):
        return pointer[len("screenshot:"):], "screenshot", None
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
    """→ (True/False/None, 说明)；None 表示这一类不适用。"""
    if kind == "screenshot":
        return None, (f"截图类参照物只查存在性（{os.path.basename(store_path)}）；"
                      "观感请人工目视，并照卡文给的取值表核对")
    with open(store_path, encoding="utf-8") as fh:
        lines = fh.readlines()
    if kind == "anchor":
        if not payload:
            return False, "参照物的锚点是空的（`#` 后面没写标题）"
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
    return False, "参照物没带锚点也没带行号范围（写成 `<path>#<标题>` 或 `<path>:<a>-<b>`）"


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
    """→ (True/False, 说明)。store 在本区域上一张卡之后必须被写过。"""
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
    """参照物所在目录在 git 里必须没有未提交改动 —— 挡并发写入方。

    范围取文件所在**目录**（不是单个文件）：同一份 store 里别的文件也可能被引，
    半途被改的状态比单文件更值得停一下。不在 git 仓里就跳过并说明。
    """
    directory = os.path.realpath(os.path.dirname(os.path.abspath(store_path)))
    try:
        root = subprocess.run(["git", "-C", directory, "rev-parse", "--show-toplevel"],
                              capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as exc:
        return True, f"跑不动 git 判断并发写入（{exc}），跳过"
    if root.returncode != 0:
        return True, "参照物不在 git 仓里 → 判不了并发写入（建议给 store 建仓）"
    # realpath 两边都要做：/tmp 在 macOS 是 /private/tmp 的软链，不归一的话 relpath 会算出
    # `../../../tmp/...` 这种越界相对路径，git status 收到它什么都不报，看着像「干净」（实测）。
    repo = os.path.realpath(root.stdout.strip())
    rel = os.path.relpath(directory, repo)
    if rel.startswith(".."):
        return True, f"参照物目录与仓根算不出包含关系（{directory} vs {repo}），跳过"
    try:
        st = subprocess.run(["git", "-C", repo, "status", "--porcelain", "--", rel],
                            capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        return True, f"跑不动 git status（{exc}），跳过"
    dirty = [line for line in st.stdout.splitlines() if line.strip()]
    if dirty:
        shown = "; ".join(line.strip()[:80] for line in dirty[:5])
        more = "" if len(dirty) <= 5 else f"（共 {len(dirty)} 条）"
        return False, (f"参照物目录有未提交改动 {shown}{more} → 先弄清那份改动是谁的、"
                       "要不要留，再写卡")
    return True, f"参照物目录在 git 里干净（{repo}/{rel}）"


def _judge(ok_flag) -> str:
    """True → PASS、False → FAIL、None → N/A（不适用，不等于通过）。"""
    return "n/a" if ok_flag is None else ("pass" if ok_flag else "fail")


def main() -> int:
    ap = argparse.ArgumentParser(description="观感卡发车前检查（铁律 12）")
    ap.add_argument("card")
    ap.add_argument("--tasks-json", help="离线用：自定义的 taskproof tasks JSON")
    ap.add_argument("--quiet", action="store_true", help="只打印结论行")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    region, pointer, is_store, _ = parse_card(args.card)
    results, ok = [], True
    skipped = (not region and not pointer)

    def add(flag, label, detail):
        nonlocal ok
        if flag is False:
            ok = False
        results.append((_judge(flag), label + detail))

    if skipped:
        add(None, "", "卡文没有 `region:` / `口径:` / `参照物:` 头 → 非观感卡，检查跳过")
    elif not pointer:
        add(False, "", "观感卡至少要有一个参照物头：`口径: <store>#<锚点>`（会变的 store）"
                       "或 `参照物: <原型/既有实现>:a-b`（不可变来源）。"
                       "**不是观感卡就不要写这些头** —— 写了 `none` 也算观感卡而无参照物")
    elif region is None and is_store:
        add(False, "", "用了 `口径:` 就必须有 `region:` 头（收敛预算按区域计数）")
    else:
        unnamed_region = region is None or region.lower() == "none"
        if unnamed_region and not is_store:
            add(None, "", f"`region` 缺席或为 none → 不纳管收敛预算（查 3 不适用）")
        path, kind, payload = split_pointer(pointer)
        if not os.path.isabs(path):
            path = os.path.normpath(
                os.path.join(os.path.dirname(os.path.abspath(args.card)), path))
        exist, detail = check_file(path)
        add(exist, "查1 存在：", detail)
        if exist:
            anchor, detail2 = check_anchor(path, kind, payload)
            add(anchor, "查2 锚点：", detail2)
        if not is_store:
            add(None, "查3 停更：", "参照物是不可变来源（原型/既有实现），没有回写义务 → 不适用")
            add(None, "查4 并发：", "同上：这一条只对会被回写的 store 有意义 → 不适用")
        else:
            if unnamed_region:
                add(None, "查3 停更：", "`region` 为 none，不纳管收敛预算 → 不适用")
            elif exist:
                fresh, detail3 = check_freshness(path, region or "", load_tasks(args.tasks_json))
                add(fresh, "查3 停更：", detail3)
            if exist:
                clean, detail4 = check_store_clean(path)
                add(clean, "查4 并发：", detail4)

    applied = [r for r in results if r[0] in ("pass", "fail")]
    if args.json:
        print(json.dumps({"card": args.card, "region": region, "参照物": pointer,
                          "参照物种类": "store" if is_store else "不可变来源",
                          "ok": bool(ok) and not skipped, "skipped": skipped,
                          "checks": [{"result": r, "detail": d} for r, d in results]},
                         ensure_ascii=False, indent=2))
    else:
        if not args.quiet:
            print(f"check-card: {args.card}")
            print(f"  region={region!r}  "
                  f"{'口径' if is_store else '参照物'}={pointer!r}")
        for r, d in results:
            print(f"  [{r.upper()}] {d}")
        tail = ("非观感卡，检查跳过" if skipped
                else (f"适用项 {len(applied)} 条全过 → 可以发车" if ok else "有查不过 → 不许发车"))
        print("  结论：" + tail)
    return 0 if (ok or skipped) else 1


if __name__ == "__main__":
    sys.exit(main())
