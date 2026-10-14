#!/usr/bin/env python3
"""taskproof 整体设计文档的配图生成器（纯 stdlib，确定性输出）。

用法：python3 make_figs.py        # 在脚本所在目录写出 fig1..fig6 的 .svg

约定：
  * 白底、细描边、无渐变 —— 便于打印与在 VS Code Markdown 预览里查看；
  * 颜色只承载语义（蓝=数据流/机制、红=失效或缺陷、绿=改进建议、琥珀=人工动作）；
  * 每张图自带短标题；正文里的题注与编号在 markdown 一侧。
"""

import os

CJK_MIN = 0x2E80

NAVY = "#1f2328"
GREY = "#6e7781"
LINE = "#8c959f"
BLUE = "#0969da"
BLUE_F = "#ddf4ff"
RED = "#cf222e"
RED_F = "#ffebe9"
GREEN = "#1a7f37"
GREEN_F = "#dafbe1"
AMBER = "#9a6700"
AMBER_F = "#fff8c5"
PANEL = "#f6f8fa"

FONT = "'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif"

#: Active language for the rendered labels. `zh-CN` is the source text: every
#: string in this file is written in Chinese and the English set is produced by
#: looking each one up in :data:`TRANS`, so the two sets cannot drift in layout.
LANG = "zh-CN"

#: zh-CN -> en for every label that reaches an SVG `<text>`. A missing key is a
#: bug rather than a graceful fallback: the self-check at the end of a run fails
#: when an English figure still contains CJK characters. Strings that are already
#: language-neutral (paths, status words, code) are deliberately absent.
TRANS = {
    # -- 图 1 ---------------------------------------------------------------
    "图 1  taskproof 的系统上下文与职责边界": "Figure 1  taskproof: context and the boundary of responsibility",
    "主智能体 / 人": "Main agent / human",
    "终端 · 桌面控制台": "Terminal · desktop console",
    "taskproof：纯机械层，无 LLM": "taskproof: purely mechanical, no LLM",
    "配置面": "Config",
    "仓 / 道 / 验收 / 禁改": "repos · lanes · acceptance",
    "调度面": "Dispatch",
    "流水线 ①..⑨": "pipeline ①..⑨",
    "执行面": "Execution",
    "命令模板 + 结果解析": "template + result parsing",
    "判决面": "Verdict",
    "独立验收 + 差分闸门": "acceptance + the diff gate",
    "并发锁 claims": "concurrency claims",
    "事务性占用 + expires_at 过期回收": "transactional claims + expiry reclamation",
    "同 group 串行 · 全局 cap 上限": "one task per group · the global cap",
    "拒绝派发 = 退出码 75，账本不留痕": "a refusal exits 75 and leaves no ledger row",
    "编码 agent CLI": "coding agent CLI",
    "进程组独立、stdin=/dev/null": "own group, stdin=/dev/null",
    "目标仓库": "Target repository",
    "主树 或 长驻 worktree": "main tree / long-lived worktree",
    "验收在仓内跑，产物落 /tmp": "acceptance runs in the repo",
    "存储面": "Storage",
    "写后即忘，不参与判决": "append-only, never read back",
    "只读 REST API → 看板 / 桌面控制台": "read-only REST API → board / desktop console",
    "所有写操作只走 CLI，接口层无写端点": "every mutation is CLI-only; no write endpoints",
    "派发 run + 卡文": "dispatch: run + brief",
    "读写文件": "reads and writes files",
    "写状态与事件": "state + events",
    "读": "read",
    # -- 图 2 ---------------------------------------------------------------
    "图 2  分层结构与模块数据流": "Figure 2  Layers and the module data flow",
    "接口层：CLI 子命令 · 只读 REST API · 浏览器看板 / 桌面控制台":
        "Interface: CLI subcommands · read-only REST API · browser board / desktop console",
    "机械层：无 LLM，判据全部由命令与代码给出":
        "Mechanical layer: no LLM; every verdict comes from a command or from the code",
    "配置解析与校验": "registry parsing and validation",
    "仓 / 道 / 默认值": "repos / lanes / defaults",
    "并发锁": "concurrency locks",
    "claims + 上限求解": "claims + cap resolution",
    "派发流水线": "dispatch pipeline",
    "①..⑨ 与终态落库": "①..⑨ and the terminal row",
    "命令模板": "command templates",
    "结构化结果解析": "structured-result parsing",
    "独立验收 + 探针": "acceptance + probes",
    "审计流": "audit stream",
    "长驻工作区": "long-lived workspace",
    "命令面": "command surface",
    "存储层": "Storage layer",
    "SQLite：tasks（任务行） · events（审计镜像） · claims（锁） · meta":
        "SQLite: tasks (task rows) · events (audit mirror) · claims (locks) · meta",
    "events-YYYY-MM.jsonl：追加式审计流，按月轮转并压缩，永不参与逻辑判断":
        "events-YYYY-MM.jsonl: append-only audit, rotated and compressed monthly, never read for logic",
    "外部输入：卡文（一段自由文本）": "Input: the brief (free text)",
    "素材路径、验收口径、硬约束都写在卡里":
        "paths, acceptance terms and hard constraints all live in it",
    "外部输入：projects.toml（人可编辑、可入自己的仓）":
        "Input: projects.toml (hand-editable, version-controllable)",
    "改它只影响之后的派发；verify 例外，见 §4.7":
        "an edit affects later dispatches only; verify is the exception, see §4.7",
    "命令 / 查询": "commands / queries",
    "状态与事件": "state and events",
    # -- 图 3 ---------------------------------------------------------------
    "图 3  任务生命周期状态机": "Figure 3  The task lifecycle",
    "适配器进程组在跑": "the adapter's group runs",
    "硬超时计时中": "the hard timeout is ticking",
    "验收命令窗口": "the acceptance window",
    "与任务共用同一预算": "shares the task's budget",
    "验收通过（或 SKIPPED）": "acceptance passed (or SKIPPED)",
    "适配器失败 / 验收判红": "adapter failed / acceptance red",
    "动了禁改路径，待人复核": "protected path moved: review",
    "撞硬超时，跳过验收": "hard timeout, no acceptance",
    "人工停止，杀自己的进程组": "stopped by hand, group killed",
    "适配器退出": "the adapter exits",
    "闸门与验收都过": "gate + acceptance pass",
    "验收判红": "acceptance is red",
    "禁改路径被移动": "a protected path moved",
    "硬超时：跳过验收": "hard timeout: acceptance skipped",
    "cancel：只杀本次进程组": "cancel: this run's group only",
    "人工收尾口：accept <id>": "Human sign-off: accept <id>",
    "blocked：无需说明即可收回；failed：必须带 --note":
        "blocked clears with no note; failed needs --note",
    "timeout / cancelled / done 一律拒收": "timeout / cancelled / done are refused",
    "accept 只登记人工判断，绝不重跑验收、不改 verify_*":
        "accept registers a human judgement: never re-runs acceptance, never rewrites verify_*",
    "rerun <id>：从终态开一张新卡，账本互记 rerun_of / rerun_as":
        "rerun <id> opens a fresh card; the ledger links rerun_of / rerun_as",
    "未知状态必须被渲染，不得静默丢弃 —— 新增生命周期状态不能把卡藏起来":
        "an unknown status is always rendered, never dropped: a new state must not hide a card",
    # -- 图 4 ---------------------------------------------------------------
    "图 4  一次派发的流水线": "Figure 4  One dispatch, end to end",
    "解析道": "resolve the lane",
    "id / 别名 / 路径；": "id / alias / path;",
    "未登记即退出 2": "unregistered exits 2",
    "连接与建号": "connect and number",
    "建库、分配任务 id、": "open the db, allocate the id",
    "记录本次派发参数": "record what was dispatched",
    "取锁": "take the locks",
    "同 group 串行 + 全局 cap；": "one per group + global cap;",
    "拒绝即退出 75": "a refusal exits 75",
    "落 running 行": "write the running row",
    "写任务行与 started 事件": "the task row + started event",
    "（含本次 timeout 值）": "(this run's timeout value)",
    "跑适配器": "run the adapter",
    "Popen(new session)、": "Popen(new session),",
    "日志边跑边落盘、记 pgid": "log to disk, pgid recorded",
    "解析结构化结果": "parse the result",
    "契约失败即记 failed，": "contract failure = failed",
    "不靠 stdout 猜结论": "never guessed from stdout",
    "差分 + 禁改闸门": "diff + the gate",
    "跑前/跑后快照比对；": "before/after snapshots",
    "越界记 blocked": "a breach records blocked",
    "独立验收": "independent acceptance",
    "verifying；命令由": "verifying; the command is",
    "注册表现读": "read live from the registry",
    "终态与释放": "terminal row + release",
    "写终态行 + 事件；": "the terminal row and event;",
    "finally 释放锁": "locks released in finally",
    "适配器结束": "the adapter exits",
    "闸门位置：验收之前": "Where the gate sits: before acceptance",
    "闸门判越界时，验收尚未开始 —— 卡落 blocked，":
        "a breach is decided before acceptance starts: the card is blocked,",
    "verify_exit 为 NULL，需要人工补跑 taskproof verify":
        "verify_exit is NULL and a human must run taskproof verify",
    "预算的分工": "How the budget is shared",
    "任务与验收共用同一条 timeout（默认 1800s）；":
        "task and acceptance share one timeout (1800s by default);",
    "验收超时落 failed（exit 记 NULL），不是 timeout 状态":
        "an acceptance timeout is failed with exit NULL, not the timeout status",
    "锁的边界：③ 取锁、⑨ finally 释放；进程崩掉不靠人工解锁 —— claims 带 expires_at，过期由下一个派发回收":
        "Locks: taken in ③, released in ⑨; a crash needs no manual unlock — the next dispatch reclaims the expired claim",
    # -- 图 5 ---------------------------------------------------------------
    "图 5  禁改闸门的判据": "Figure 5  What the gate compares",
    "跑前快照": "Snapshot: before",
    "受保护路径的文件指纹": "fingerprints of protected paths",
    "git 状态（HEAD/refs/stash）": "git state (HEAD/refs/stash)",
    "文件集合": "the file set",
    "跑后快照": "Snapshot: after",
    "同一组探针，同一棵工作树": "same probes, same working tree",
    "（工作区模式下即该 worktree）": "(in workspace mode: that worktree)",
    "差分判决": "The diff decides",
    "只认两次快照之间的变化": "only what changed between them counts",
    "跑前就脏的未跟踪文件、": "a tree that was already dirty,",
    "第三方后台进程写的目录": "directories a dev server rewrites",
    "一律不算在本次派发头上": "is never blamed on this run",
    "三类探针，逐规则选择": "Three probes, chosen per rule",
    "file 规则：指纹 + 差分，抓内容的增删改": "file: fingerprint + diff — content edits",
    "git 规则：HEAD / refs / stash，抓提交、": "git: HEAD / refs / stash — commits,",
    "改历史、切分支与打标签": "rewrites, branch and tag moves",
    "presence 规则：只比文件集合的增删": "presence: file-set membership only",
    "改写已有文件的内容不报警": "rewriting an existing file stays quiet",
    "命中": "hit",
    "两条窄例外": "Two narrow exemptions",
    "__pycache__ 与 .pyc / .pyo：运行 Python 的副产物":
        "__pycache__, .pyc / .pyo: byproducts of running Python",
    "别的工作树已检出的分支：refs 在工作树间共享":
        "branches another worktree has checked out: refs are shared",
    "结构性盲区": "A structural blind spot",
    "树本来就停在错分支、跑前就存在的未跟踪文件：":
        "a tree on the wrong branch, a file that predates the run:",
    "前后无变化，闸门在原理上永远看不见": "nothing changed, so the gate can never see it",
    "判决与事实分离：越界记 blocked（人须复核），验收照跑；最终卡是 blocked 时，verify_exit 仍告诉人代码本身是否可用":
        "A breach records blocked (for review) and acceptance still runs; verify_exit then says whether the work itself was sound",
    # -- 图 6 ---------------------------------------------------------------
    "图 6  超时机制：三段取值链与止损判据":
        "Figure 6  Timeouts: the three-step value chain, and when to stop",
    "A 三段取值链现状（e346213 已落地）":
        "A  The three-step chain as landed (e346213)",
    "单次覆盖 · 来源 cli": "one-off override · source cli",
    "按道预算 · 来源 lane": "the lane's own budget · source lane",
    "注册表默认（本机 1800）· 来源 toml": "the registry default (1800s here) · source toml",
    "内置兜底 1800": "built-in fallback 1800",
    "无人指定时 · 来源 default": "when nothing names one · source default",
    "唯一的取值入口": "the one place the value is read",
    "到点 killpg：SIGTERM → 5s → SIGKILL": "on expiry killpg: SIGTERM → 5s → SIGKILL",
    "只打本次派发自己的进程组": "only this run's own process group",
    "started 事件带 timeout_source，与 cap_source 同形；taskgroups 投影也带 timeout":
        "the started event gains timeout_source (shaped like cap_source); the taskgroups record gains timeout",
    "B 已落地对照": "B  What landed",
    "修复前（e346213 之前）": "before e346213",
    "只认 --timeout 与 [defaults]": "only --timeout and [defaults] were read",
    "道级 timeout 无字段，声明不生效": "the lane had no such field, so its word did not count",
    "修复后（e346213）": "after e346213",
    "三段链 + 内置兜底，值随来源落账": "the three-step chain plus the fallback, source recorded with the value",
    "started 事件 / taskgroups 投影都带": "both the started event and the taskgroups record now carry it",
    "C 止损判据（46ad07ad 已落地）": "C  When to stop (46ad07ad, landed)",
    "现行：只看墙钟": "today: wall clock only",
    "1800s：墙钟到点才杀进程树": "1800s: the process tree dies on the clock",
    "已落地：无进展看门狗 + 墙钟兜底": "landed: idle watchdog + the wall clock",
    "480s：日志与工作树都静默": "480s: log and tree both silent",
    "1800s：兜底墙钟": "1800s: backstop",
    "为什么不能只看日志": "Why the log alone will not do",
    "一次冷编译、一次大依赖下载可以几分钟": "a cold build or a large download can run",
    "不输出；判据须并入工作树的文件改动，": "for minutes without output, so the check has to",
    "二者都静默才判停摆": "include the tree: only both silent is a stall",
}


def translate(s):
    """The label for the active language (Chinese passes through)."""
    if LANG == "zh-CN":
        return s
    return TRANS.get(s, s)



def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def tw(s, size):
    """Rough text width: CJK is one em wide, latin about half."""
    return sum(size if ord(c) >= CJK_MIN else size * 0.55 for c in s)


class Fig:
    def __init__(self, w, h, title=None):
        self.w, self.h = w, h
        self.parts = []
        if title:
            self.text(24, 34, title, 16, NAVY, "start", "600")

    # -- primitives ------------------------------------------------------
    def rect(self, x, y, w, h, fill="none", stroke=LINE, rx=6, sw=1.2, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>'
        )

    def text(self, x, y, s, size=12.5, color=NAVY, anchor="start", weight="400"):
        s = translate(s)
        self.parts.append(
            f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" '
            f'fill="{color}" text-anchor="{anchor}" font-weight="{weight}">{esc(s)}</text>'
        )

    def line(self, x1, y1, x2, y2, color=LINE, sw=1.2, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" '
            f'stroke-width="{sw}"{d}/>'
        )

    def arrow(self, x1, y1, x2, y2, color=BLUE, dash=None, label=None,
              label_side="top", size=11.5, weight="400"):
        self.line(x1, y1, x2, y2, color, 1.3, dash)
        # arrow head, drawn as a small solid triangle so no marker defs are needed
        import math
        ang = math.atan2(y2 - y1, x2 - x1)
        L, W = 9, 4.2
        bx, by = x2 - L * math.cos(ang), y2 - L * math.sin(ang)
        nx, ny = -math.sin(ang), math.cos(ang)
        self.parts.append(
            f'<polygon points="{x2},{y2} {bx + W * nx},{by + W * ny} '
            f'{bx - W * nx},{by - W * ny}" fill="{color}"/>'
        )
        if label:
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            dy = -8 if label_side == "top" else 16
            lw = tw(label, size)
            self.rect(mx - lw / 2 - 4, my + dy - size, lw + 8, size + 6,
                      fill="white", stroke="none", rx=2)
            self.text(mx, my + dy, label, size, color, "middle", weight)

    def box(self, x, y, w, h, lines, fill=PANEL, stroke=LINE, dash=None, pad=7):
        """A box with vertically centred lines.

        lines: list of (text, size, color, weight, gap_before)

        A line wider than the box is reported on stdout rather than silently
        overflowing: the English labels are translated from the Chinese ones and
        a long word would otherwise spill over the border unnoticed.
        """
        self.rect(x, y, w, h, fill, stroke, dash=dash)
        norm = []
        for item in lines:
            t, s, c, wgt, gap = (list(item) + [0, 0, NAVY, "400", 0])[:5]
            norm.append((t, s, c, wgt, gap))
        total = sum(s + gap for _, s, _, _, gap in norm)
        cy = y + (h - total) / 2
        for t, s, c, wgt, gap in norm:
            cy += gap + s
            need = tw(translate(t), s) + pad
            if need > w:
                print(f"  ! OVERFLOW box w={w} needs {need:.0f}: {translate(t)!r}")
            self.text(x + w / 2, cy - s * 0.22, t, s, c, "middle", wgt)

    def wide(self, lines, pad=26):
        """Natural width for a box holding `lines`."""
        return max(tw(t, s) for t, s, *_ in lines) + pad * 2

    def note(self, x, y, w, lines, fill=RED_F, stroke=RED, dash=None):
        self.box(x, y, w, len(lines) * 20 + 16, lines, fill, stroke, dash=dash)

    def save(self, path):
        body = "\n  ".join(self.parts)
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" '
            f'height="{self.h}" viewBox="0 0 {self.w} {self.h}">\n'
            f'  <rect width="{self.w}" height="{self.h}" fill="white"/>\n'
            f"  {body}\n</svg>\n"
        )
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(svg)
        print("wrote", path)


# ---------------------------------------------------------------------------
# 图 1 · 系统上下文与职责边界
# ---------------------------------------------------------------------------
def fig1(path):
    f = Fig(1010, 600, "图 1  taskproof 的系统上下文与职责边界")

    f.box(30, 220, 200, 130, [
        ("主智能体 / 人", 14, NAVY, "600", 0),
        ("Hermes · Claude Code", 11.5, GREY, "400", 8),
        ("终端 · 桌面控制台", 11.5, GREY, "400", 4),
    ], fill=PANEL, stroke=LINE)

    f.rect(290, 78, 430, 400, "#ffffff", LINE, rx=10, sw=1.4, dash="6 4")
    f.text(505, 106, "taskproof：纯机械层，无 LLM", 14, NAVY, "middle", "600")

    inner = [
        (310, 130, "配置面", "projects.toml", "仓 / 道 / 验收 / 禁改", BLUE, BLUE_F),
        (505, 130, "调度面", "dispatch.py", "流水线 ①..⑨", BLUE, BLUE_F),
        (310, 240, "执行面", "adapters/*", "命令模板 + 结果解析", BLUE, BLUE_F),
        (505, 240, "判决面", "verify.py", "独立验收 + 差分闸门", BLUE, BLUE_F),
    ]
    for x, y, head, name, sub, c, fill in inner:
        f.box(x, y, 180, 92, [
            (head, 11, GREY, "600", 0),
            (name, 13.5, NAVY, "600", 6),
            (sub, 11, c, "400", 5),
        ], fill=fill, stroke=c)

    f.box(310, 352, 375, 96, [
        ("并发锁 claims", 12.5, NAVY, "600", 0),
        ("事务性占用 + expires_at 过期回收", 11, GREY, "400", 7),
        ("同 group 串行 · 全局 cap 上限", 11, GREY, "400", 4),
        ("拒绝派发 = 退出码 75，账本不留痕", 11, AMBER, "400", 4),
    ], fill=PANEL, stroke=LINE)

    f.box(770, 130, 210, 110, [
        ("编码 agent CLI", 13, NAVY, "600", 0),
        ("codex · claude · gemini", 11, GREY, "400", 8),
        ("opencode · custom:<cmd>", 11, GREY, "400", 4),
        ("进程组独立、stdin=/dev/null", 11, GREY, "400", 4),
    ], fill="#ffffff", stroke=NAVY)

    f.box(770, 290, 210, 96, [
        ("目标仓库", 13, NAVY, "600", 0),
        ("主树 或 长驻 worktree", 11, GREY, "400", 8),
        ("验收在仓内跑，产物落 /tmp", 11, GREY, "400", 4),
    ], fill="#ffffff", stroke=NAVY)

    f.box(30, 440, 200, 130, [
        ("存储面", 11, GREY, "600", 0),
        ("SQLite", 13.5, NAVY, "600", 6),
        ("tasks · events · claims", 11, GREY, "400", 5),
        ("events-YYYY-MM.jsonl", 11, GREY, "400", 5),
        ("写后即忘，不参与判决", 11, GREY, "400", 5),
    ], fill=PANEL, stroke=LINE)

    f.box(300, 505, 400, 62, [
        ("只读 REST API → 看板 / 桌面控制台", 12.5, NAVY, "600", 0),
        ("所有写操作只走 CLI，接口层无写端点", 11, GREY, "400", 7),
    ], fill=GREEN_F, stroke=GREEN)

    f.arrow(232, 265, 288, 265, BLUE, label="派发 run + 卡文")
    f.arrow(722, 190, 768, 190, NAVY, label="argv + workdir")
    f.arrow(760, 330, 722, 330, NAVY, label="读写文件")
    f.arrow(330, 452, 240, 492, BLUE, label="写状态与事件", label_side="bottom")
    f.arrow(232, 538, 298, 538, GREEN, label="读")
    f.save(path)


# ---------------------------------------------------------------------------
# 图 2 · 分层与模块
# ---------------------------------------------------------------------------
def fig2(path):
    f = Fig(1010, 640, "图 2  分层结构与模块数据流")

    f.box(30, 70, 950, 40, [
        ("接口层：CLI 子命令 · 只读 REST API · 浏览器看板 / 桌面控制台", 13, NAVY, "600", 0),
    ], fill=PANEL, stroke=LINE)

    f.box(30, 150, 950, 230, [], fill="#ffffff", stroke=LINE, dash="6 4")
    f.text(50, 176, "机械层：无 LLM，判据全部由命令与代码给出", 13, NAVY, "start", "600")
    mods = [
        (48, "registry.py", "配置解析与校验", "仓 / 道 / 默认值"),
        (278, "concurrency.py", "并发锁", "claims + 上限求解"),
        (508, "dispatch.py", "派发流水线", "①..⑨ 与终态落库"),
        (738, "adapters/*", "命令模板", "结构化结果解析"),
        (48, "verify.py", "独立验收 + 探针", "file / git / presence"),
        (278, "ledger.py", "审计流", "append / rotate"),
        (508, "workspace", "长驻工作区", "worktree + link"),
        (738, "cli.py", "命令面", "locale + --json"),
    ]
    for i, (x, name, sub, sub2) in enumerate(mods):
        col, row = i % 4, i // 4
        cx = 48 + col * 230
        cy = 200 + row * 90
        f.box(cx, cy, 214, 74, [
            (name, 12.5, NAVY, "600", 0),
            (sub, 11, BLUE, "400", 6),
            (sub2, 10.5, GREY, "400", 4),
        ], fill=BLUE_F, stroke=BLUE)

    f.box(30, 420, 950, 90, [
        ("存储层", 12, GREY, "600", 0),
        ("SQLite：tasks（任务行） · events（审计镜像） · claims（锁） · meta", 12, NAVY, "400", 8),
        ("events-YYYY-MM.jsonl：追加式审计流，按月轮转并压缩，永不参与逻辑判断", 11, GREY, "400", 5),
    ], fill=PANEL, stroke=LINE)

    f.box(30, 548, 470, 62, [
        ("外部输入：卡文（一段自由文本）", 12, NAVY, "600", 0),
        ("素材路径、验收口径、硬约束都写在卡里", 11, GREY, "400", 7),
    ], fill="#ffffff", stroke=LINE)
    f.box(520, 548, 460, 62, [
        ("外部输入：projects.toml（人可编辑、可入自己的仓）", 12, NAVY, "600", 0),
        ("改它只影响之后的派发；verify 例外，见 §4.7", 11, GREY, "400", 7),
    ], fill="#ffffff", stroke=LINE)

    f.arrow(505, 110, 505, 148, BLUE, label="命令 / 查询")
    f.arrow(505, 380, 505, 418, BLUE, label="状态与事件")
    f.arrow(265, 546, 265, 512, BLUE)
    f.arrow(750, 546, 750, 512, BLUE)
    f.save(path)


# ---------------------------------------------------------------------------
# 图 3 · 任务生命周期状态机
# ---------------------------------------------------------------------------
def fig3(path):
    f = Fig(1010, 740, "图 3  任务生命周期状态机")

    f.box(70, 120, 180, 80, [
        ("running", 15, NAVY, "600", 0),
        ("适配器进程组在跑", 11, GREY, "400", 8),
        ("硬超时计时中", 11, GREY, "400", 4),
    ], fill=BLUE_F, stroke=BLUE)

    f.box(420, 120, 180, 80, [
        ("verifying", 15, NAVY, "600", 0),
        ("验收命令窗口", 11, GREY, "400", 8),
        ("与任务共用同一预算", 11, RED, "400", 4),
    ], fill=BLUE_F, stroke=BLUE)

    term = [
        (770, 70, "done", "验收通过（或 SKIPPED）", GREEN, GREEN_F),
        (770, 160, "failed", "适配器失败 / 验收判红", RED, RED_F),
        (770, 250, "blocked", "动了禁改路径，待人复核", AMBER, AMBER_F),
        (770, 340, "timeout", "撞硬超时，跳过验收", RED, RED_F),
        (770, 430, "cancelled", "人工停止，杀自己的进程组", AMBER, AMBER_F),
    ]
    for x, y, name, sub, c, fill in term:
        f.box(x, y, 200, 70, [
            (name, 14, NAVY, "600", 0),
            (sub, 11, c, "400", 7),
        ], fill=fill, stroke=c)

    f.arrow(252, 150, 418, 150, BLUE, label="适配器退出")
    f.arrow(602, 130, 768, 105, GREEN, label="闸门与验收都过")
    f.arrow(602, 150, 768, 195, RED, label="验收判红")
    f.arrow(602, 178, 768, 285, AMBER, label="禁改路径被移动")

    f.line(160, 202, 160, 375, RED, 1.3, "6 4")
    f.arrow(160, 375, 768, 375, RED, dash="6 4", label="硬超时：跳过验收")
    f.line(510, 202, 510, 470, AMBER, 1.3, "6 4")
    f.arrow(510, 470, 768, 470, AMBER, dash="6 4", label="cancel：只杀本次进程组")

    f.box(70, 545, 560, 110, [
        ("人工收尾口：accept <id>", 13, NAVY, "600", 0),
        ("blocked：无需说明即可收回；failed：必须带 --note", 11.5, NAVY, "400", 8),
        ("timeout / cancelled / done 一律拒收", 11.5, RED, "400", 5),
        ("accept 只登记人工判断，绝不重跑验收、不改 verify_*", 11.5, GREY, "400", 5),
        ("rerun <id>：从终态开一张新卡，账本互记 rerun_of / rerun_as", 11.5, GREY, "400", 5),
    ], fill=PANEL, stroke=LINE)

    f.box(70, 675, 890, 44, [
        ("未知状态必须被渲染，不得静默丢弃 —— 新增生命周期状态不能把卡藏起来", 12, GREY, "400", 0),
    ], fill="#ffffff", stroke=LINE, dash="4 3")
    f.save(path)


# ---------------------------------------------------------------------------
# 图 4 · 派发流水线
# ---------------------------------------------------------------------------
def fig4(path):
    f = Fig(1080, 620, "图 4  一次派发的流水线")

    steps_r1 = [
        ("①", "解析道", "id / 别名 / 路径；\n未登记即退出 2"),
        ("②", "连接与建号", "建库、分配任务 id、\n记录本次派发参数"),
        ("③", "取锁", "同 group 串行 + 全局 cap；\n拒绝即退出 75"),
        ("④", "落 running 行", "写任务行与 started 事件\n（含本次 timeout 值）"),
        ("⑤", "跑适配器", "Popen(new session)、\n日志边跑边落盘、记 pgid"),
    ]
    steps_r2 = [
        ("⑤′", "解析结构化结果", "契约失败即记 failed，\n不靠 stdout 猜结论"),
        ("⑥", "差分 + 禁改闸门", "跑前/跑后快照比对；\n越界记 blocked"),
        ("⑦", "独立验收", "verifying；命令由\n注册表现读"),
        ("⑧", "终态与释放", "写终态行 + 事件；\nfinally 释放锁"),
    ]

    def draw(row, y, start_x, gap, w=170, h=104):
        out = []
        x = start_x
        for num, name, sub in row:
            f.box(x, y, w, h, [
                (num, 11, BLUE, "600", 0),
                (name, 12.5, NAVY, "600", 5),
                *[(ln, 10.5, GREY, "400", 4) for ln in sub.split("\n")],
            ], fill="#ffffff", stroke=BLUE)
            out.append(x)
            x += w + gap
        return out

    xs1 = draw(steps_r1, 80, 40, 20)
    xs2 = draw(steps_r2, 280, 40, 20)
    for i in range(len(xs1) - 1):
        f.arrow(xs1[i] + 170, 132, xs1[i + 1], 132, BLUE)
    for i in range(len(xs2) - 1):
        f.arrow(xs2[i] + 170, 332, xs2[i + 1], 332, BLUE)

    # elbow: ⑤ -> ⑤′ so the two rows read as one sequence
    f.line(xs1[-1] + 85, 184, xs1[-1] + 85, 232, BLUE)
    f.line(xs1[-1] + 85, 232, xs2[0] + 85, 232, BLUE)
    f.arrow(xs2[0] + 85, 232, xs2[0] + 85, 278, BLUE)
    label = "适配器结束"
    lw = tw(label, 11.5)
    f.rect(505 - lw / 2 - 5, 232 - 11.5, lw + 10, 18, fill="white", stroke="none", rx=2)
    f.text(505, 232, label, 11.5, BLUE, "middle")

    f.box(40, 415, 470, 92, [
        ("闸门位置：验收之前", 12.5, NAVY, "600", 0),
        ("闸门判越界时，验收尚未开始 —— 卡落 blocked，", 11, GREY, "400", 7),
        ("verify_exit 为 NULL，需要人工补跑 taskproof verify", 11, GREY, "400", 4),
    ], fill=AMBER_F, stroke=AMBER)

    f.box(530, 415, 510, 92, [
        ("预算的分工", 12.5, NAVY, "600", 0),
        ("任务与验收共用同一条 timeout（默认 1800s）；", 11, GREY, "400", 7),
        ("验收超时落 failed（exit 记 NULL），不是 timeout 状态", 11, GREY, "400", 4),
    ], fill=RED_F, stroke=RED)

    f.box(40, 525, 1000, 62, [
        ("锁的边界：③ 取锁、⑨ finally 释放；进程崩掉不靠人工解锁 —— claims 带 expires_at，过期由下一个派发回收", 12, NAVY, "400", 0),
    ], fill=PANEL, stroke=LINE)
    f.save(path)


# ---------------------------------------------------------------------------
# 图 5 · 差分式禁改闸门
# ---------------------------------------------------------------------------
def fig5(path):
    f = Fig(1010, 620, "图 5  禁改闸门的判据")

    f.box(40, 80, 240, 110, [
        ("跑前快照", 13, NAVY, "600", 0),
        ("受保护路径的文件指纹", 10.5, GREY, "400", 7),
        ("git 状态（HEAD/refs/stash）", 10.5, GREY, "400", 4),
        ("文件集合", 10.5, GREY, "400", 4),
    ], fill=PANEL, stroke=LINE)

    f.box(40, 230, 240, 110, [
        ("跑后快照", 13, NAVY, "600", 0),
        ("同一组探针，同一棵工作树", 10.5, GREY, "400", 7),
        ("（工作区模式下即该 worktree）", 10.5, GREY, "400", 4),
    ], fill=PANEL, stroke=LINE)

    f.box(330, 130, 250, 160, [
        ("差分判决", 14, NAVY, "600", 0),
        ("只认两次快照之间的变化", 11.5, BLUE, "400", 9),
        ("跑前就脏的未跟踪文件、", 11, GREY, "400", 7),
        ("第三方后台进程写的目录", 11, GREY, "400", 3),
        ("一律不算在本次派发头上", 11, GREY, "400", 3),
    ], fill=BLUE_F, stroke=BLUE)

    f.box(660, 80, 320, 210, [
        ("三类探针，逐规则选择", 12.5, NAVY, "600", 0),
        ("file 规则：指纹 + 差分，抓内容的增删改", 11, NAVY, "400", 9),
        ("git 规则：HEAD / refs / stash，抓提交、", 11, NAVY, "400", 6),
        ("改历史、切分支与打标签", 11, GREY, "400", 3),
        ("presence 规则：只比文件集合的增删", 11, NAVY, "400", 6),
        ("改写已有文件的内容不报警", 11, GREY, "400", 3),
    ], fill="#ffffff", stroke=LINE)

    f.arrow(282, 135, 328, 160, BLUE)
    f.arrow(282, 285, 328, 260, BLUE)
    f.arrow(582, 210, 658, 185, BLUE, label="命中")

    f.box(40, 400, 450, 100, [
        ("两条窄例外", 12.5, NAVY, "600", 0),
        ("__pycache__ 与 .pyc / .pyo：运行 Python 的副产物", 11, GREEN, "400", 8),
        ("别的工作树已检出的分支：refs 在工作树间共享", 11, GREEN, "400", 4),
    ], fill=GREEN_F, stroke=GREEN)

    f.box(520, 400, 450, 100, [
        ("结构性盲区", 12.5, NAVY, "600", 0),
        ("树本来就停在错分支、跑前就存在的未跟踪文件：", 11, RED, "400", 8),
        ("前后无变化，闸门在原理上永远看不见", 11, RED, "400", 4),
    ], fill=RED_F, stroke=RED)

    f.box(40, 520, 930, 62, [
        ("判决与事实分离：越界记 blocked（人须复核），验收照跑；最终卡是 blocked 时，verify_exit 仍告诉人代码本身是否可用", 12, NAVY, "400", 0),
    ], fill=PANEL, stroke=LINE)
    f.save(path)


# ---------------------------------------------------------------------------
# 图 6 · 超时机制：取值链与判据
# ---------------------------------------------------------------------------
def fig6(path):
    f = Fig(1080, 800, "图 6  超时机制：三段取值链与止损判据")

    # panel A: the landed three-step chain, in precedence order
    f.text(40, 78, "A 三段取值链现状（e346213 已落地）", 13, NAVY, "start", "600")
    f.box(40, 92, 330, 48, [
        ("run --timeout N", 12, NAVY, "600", 0),
        ("单次覆盖 · 来源 cli", 10.5, GREY, "400", 5),
    ], fill=BLUE_F, stroke=BLUE)
    f.box(40, 148, 330, 48, [
        ("[[taskgroup]] timeout", 12, NAVY, "600", 0),
        ("按道预算 · 来源 lane", 10.5, GREY, "400", 5),
    ], fill=BLUE_F, stroke=BLUE)
    f.box(40, 204, 330, 48, [
        ("[defaults] timeout", 12, NAVY, "600", 0),
        ("注册表默认（本机 1800）· 来源 toml", 10.5, GREY, "400", 5),
    ], fill=BLUE_F, stroke=BLUE)
    f.box(40, 260, 330, 48, [
        ("内置兜底 1800", 12, NAVY, "600", 0),
        ("无人指定时 · 来源 default", 10.5, GREY, "400", 5),
    ], fill=PANEL, stroke=LINE)

    f.box(480, 148, 220, 120, [
        ("registry.resolve_timeout()", 11.5, NAVY, "600", 0),
        ("唯一的取值入口", 11, GREY, "400", 6),
        ("cli > lane", 11, GREY, "400", 4),
        ("> toml > default", 11, GREY, "400", 2),
    ], fill=PANEL, stroke=LINE)
    f.box(770, 148, 270, 120, [
        ("adapter.timeout", 11.5, NAVY, "600", 0),
        ("→ proc.wait(timeout)", 11.5, NAVY, "600", 2),
        ("到点 killpg：SIGTERM → 5s → SIGKILL", 10.5, GREY, "400", 8),
        ("只打本次派发自己的进程组", 10.5, GREY, "400", 4),
    ], fill=PANEL, stroke=LINE)

    f.arrow(372, 116, 478, 175, BLUE)
    f.arrow(372, 172, 478, 195, BLUE)
    f.arrow(372, 228, 478, 220, BLUE)
    f.arrow(372, 284, 478, 240, BLUE, dash="4 3")
    f.arrow(702, 208, 768, 208, BLUE, label="effective_timeout")

    f.box(40, 322, 1000, 40, [
        ("started 事件带 timeout_source，与 cap_source 同形；taskgroups 投影也带 timeout", 11.5, GREY, "400", 0),
    ], fill="#ffffff", stroke=LINE, dash="4 3")

    # panel B: what the fix landed (before -> after)
    f.text(40, 408, "B 已落地对照", 13, NAVY, "start", "600")
    f.box(40, 422, 480, 84, [
        ("修复前（e346213 之前）", 12, RED, "600", 0),
        ("只认 --timeout 与 [defaults]", 11, GREY, "400", 7),
        ("道级 timeout 无字段，声明不生效", 11, GREY, "400", 4),
    ], fill=RED_F, stroke=RED, dash="6 4")
    f.box(560, 422, 480, 84, [
        ("修复后（e346213）", 12, GREEN, "600", 0),
        ("三段链 + 内置兜底，值随来源落账", 11, GREY, "400", 7),
        ("started 事件 / taskgroups 投影都带", 11, GREY, "400", 4),
    ], fill=GREEN_F, stroke=GREEN)
    f.arrow(522, 464, 558, 464, GREEN)

    # panel C: when to stop (still a proposal)
    f.text(40, 550, "C 止损判据（46ad07ad 已落地）", 13, NAVY, "start", "600")

    def axis(y, label, marks):
        x0, x1 = 200, 660
        f.line(x0, y, x1, y, LINE, 1.2)
        # The lane label sits BELOW the axis, and each mark label picks its own
        # side: English labels are wide enough to collide with each other when
        # they all share the line above.
        f.text(x0, y + 34, label, 11.5, NAVY, "start", "600")
        f.text(x0, y + 20, "t=0", 10.5, GREY, "start")
        for frac, txt, color, dash, anchor, side in marks:
            x = x0 + frac * (x1 - x0)
            f.line(x, y - 22, x, y + 22, color, 1.4, dash)
            if not txt:
                continue
            ty = y - 30 if side == "above" else y + 44
            if anchor == "end":
                f.text(x - 6, ty, txt, 11, color, "end", "600")
            else:
                f.text(x + 6, ty, txt, 11, color, "start", "600")

    axis(600, "现行：只看墙钟", [
        (0.5, "900s", GREY, "5 4", "start", "below"),
        (1.0, "1800s：墙钟到点才杀进程树", RED, None, "end", "above"),
    ])
    axis(710, "已落地：无进展看门狗 + 墙钟兜底", [
        (0.27, "480s：日志与工作树都静默", GREEN, None, "start", "above"),
        (1.0, "1800s：兜底墙钟", GREY, "5 4", "end", "above"),
    ])

    f.box(700, 560, 340, 118, [
        ("为什么不能只看日志", 12, NAVY, "600", 0),
        ("一次冷编译、一次大依赖下载可以几分钟", 10.5, GREY, "400", 6),
        ("不输出；判据须并入工作树的文件改动，", 10.5, GREY, "400", 4),
        ("二者都静默才判停摆", 10.5, GREY, "400", 4),
    ], fill=PANEL, stroke=LINE)
    f.save(path)


if __name__ == "__main__":
    import sys

    args = [a for a in sys.argv[1:]]
    lang = "zh-CN"
    if "--lang" in args:
        lang = args[args.index("--lang") + 1]
    if lang not in ("zh-CN", "en"):
        raise SystemExit(f"unknown language: {lang} (expected zh-CN or en)")
    LANG = lang

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = os.path.join(root, "docs", "assets", "figures", lang)
    os.makedirs(out_dir, exist_ok=True)

    fig1(os.path.join(out_dir, "fig1-context.svg"))
    fig2(os.path.join(out_dir, "fig2-layers.svg"))
    fig3(os.path.join(out_dir, "fig3-status.svg"))
    fig4(os.path.join(out_dir, "fig4-pipeline.svg"))
    fig5(os.path.join(out_dir, "fig5-gate.svg"))
    fig6(os.path.join(out_dir, "fig6-timeout.svg"))

    # Self-check: an English figure that still shows CJK means a label is absent
    # from TRANS. Fail loudly instead of shipping a half-translated diagram.
    if lang == "en":
        offenders = []
        for name in sorted(os.listdir(out_dir)):
            if not name.endswith(".svg"):
                continue
            body = open(os.path.join(out_dir, name), encoding="utf-8").read()
            if any("\u4e00" <= ch <= "\u9fff" for ch in body):
                offenders.append(name)
        if offenders:
            raise SystemExit(f"untranslated labels remain in: {', '.join(offenders)}")
        print("self-check: no CJK left in the English set")

