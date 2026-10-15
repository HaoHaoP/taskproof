#!/usr/bin/env python3
"""Figures for the Chinese write-up (知乎). Regenerate with:

    python3 tools/article_figures.py

They land in docs/assets/ so the published site can serve them by absolute URL —
which is what an imported Markdown file needs (a local path cannot be fetched).
Deterministic: same input, same bytes. Each figure self-checks its text boxes and
prints an OVERFLOW line instead of silently clipping.
"""

import pathlib

from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/assets"

BG = (13, 17, 23)
PANEL = (22, 27, 34)
LINE = (48, 54, 61)
FG = (230, 237, 243)
MUTED = (139, 148, 158)
ACCENT = (88, 166, 255)
GREEN = (63, 185, 80)
RED = (248, 81, 73)
AMBER = (210, 153, 34)

CJK = "/System/Library/Fonts/Hiragino Sans GB.ttc"
CJK_BOLD = "/System/Library/Fonts/STHeiti Medium.ttc"

problems = []


def font(size, bold=False):
    return ImageFont.truetype(CJK_BOLD if bold else CJK, size)


def tw(draw, text, f):
    box = draw.textbbox((0, 0), text, font=f)
    return box[2] - box[0], box[3] - box[1]


def text(draw, xy, s, f, fill=FG, limit=None):
    w, _ = tw(draw, s, f)
    if limit and w > limit:
        problems.append(f"OVERFLOW {w}>{limit} :: {s[:40]}")
    draw.text(xy, s, font=f, fill=fill)
    return w


def canvas(w, h, title=None, subtitle=None):
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    if title:
        text(d, (60, 44), title, font(40, True))
    if subtitle:
        text(d, (60, 104), subtitle, font(24), MUTED)
    return img, d


def save(img, name):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    img.save(path, optimize=True)
    print(f"wrote {path.relative_to(ROOT)}  {img.size[0]}x{img.size[1]}")


# ---------------------------------------------------------------- 1. the flow
def fig_flow():
    img, d = canvas(1600, 470, "一张卡的一生", "裁决者是验收命令，不是 agent 的自述")
    boxes = [
        ("卡", "任务 + 验收命令", ACCENT),
        ("agent", "改文件、跑命令\n（它的汇报只是汇报）", MUTED),
        ("验收命令", "退出码 0 才算通过\n“没跑” 不记成 “通过”", GREEN),
        ("账本", "改了哪些文件\n裁决 · 完整事件流", AMBER),
    ]
    x, y, bw, bh, gap = 60, 190, 330, 170, 55
    for i, (head, body, col) in enumerate(boxes):
        bx = x + i * (bw + gap)
        d.rounded_rectangle([bx, y, bx + bw, y + bh], radius=14, fill=PANEL, outline=col, width=3)
        text(d, (bx + 24, y + 24), head, font(32, True), col, limit=bw - 48)
        for j, ln in enumerate(body.split("\n")):
            text(d, (bx + 24, y + 78 + j * 34), ln, font(22), MUTED, limit=bw - 48)
        if i < len(boxes) - 1:
            ax = bx + bw + 12
            d.line([ax, y + bh // 2, ax + gap - 24, y + bh // 2], fill=LINE, width=3)
            d.polygon([(ax + gap - 24, y + bh // 2), (ax + gap - 36, y + bh // 2 - 9),
                       (ax + gap - 36, y + bh // 2 + 9)], fill=LINE)
    text(d, (60, 395), "agent 的 “全部检查通过、任务完成” 落在第二条；能不能算数由第三条说了算。",
         font(22), MUTED, limit=1480)
    save(img, "fig-flow.png")


# ----------------------------------------------------- 2. the two timelines
def fig_watchdog():
    img, d = canvas(1600, 500, "墙钟分不清 “在干活” 和 “在空转”",
                    "同一类卡：没有看门狗烧满整个时限，有看门狗按静默止损")
    x0, x1 = 200, 1520
    span = 1800

    def bar(y, secs, color, label, note):
        w = int((x1 - x0) * secs / span)
        d.rounded_rectangle([x0, y, x0 + w, y + 62], radius=10, fill=color)
        text(d, (x0 + 18, y + 16), label, font(24, True), (255, 255, 255), limit=w - 36)
        if note:
            if w > (x1 - x0) * 0.55:            # 条太长，说明放不下就落到条下方
                text(d, (x0, y + 74), note, font(22), MUTED, limit=x1 - x0)
            else:
                text(d, (x0 + w + 22, y + 18), note, font(22), MUTED, limit=1280 - w)

    text(d, (60, 186), "没有看门狗", font(26, True), RED)
    bar(222, 1800, RED, "空转 1800 秒", "一直在输出日志，一个文件都没改；验收没跑到")
    text(d, (60, 350), "有了看门狗", font(26, True), GREEN)
    bar(386, 480, GREEN, "480 秒止损", "日志与工作树都静默 → 停；判据是 “两者都安静”")

    for secs in (0, 480, 900, 1800):
        gx = x0 + int((x1 - x0) * secs / span)
        d.line([gx, 452, gx, 462], fill=LINE, width=2)
        text(d, (gx - 22, 466), f"{secs}s", font(20), MUTED)
    save(img, "fig-watchdog.png")


# ------------------------------------------------------ 3. the cost compare
def fig_cost():
    img, d = canvas(1600, 520, "同一份用量，换模型差一个数量级",
                    "614M 输入 token / 3.9M 输出 token，按各自的价目表折算")
    rows = [("deepseek-v4-flash", 127, "≈ ¥127", GREEN),
            ("Claude Sonnet 级", 1910, "≈ ¥1,910　15 倍", AMBER),
            ("GPT-5.5 级", 3321, "≈ ¥3,321　26 倍", RED)]
    x0, x1 = 560, 1300
    vmax = 3321
    for i, (name, val, label, col) in enumerate(rows):
        y = 210 + i * 90
        text(d, (60, y + 6), name, font(26), FG, limit=480)
        w = max(8, int((x1 - x0) * val / vmax))
        d.rounded_rectangle([x0, y, x0 + w, y + 52], radius=9, fill=col)
        text(d, (x0 + w + 24, y + 10), label, font(26, True), col, limit=280)
    text(d, (60, 448), "单价差不是 “省着用” 能追回来的；选对便宜档位比少干活有效得多。",
         font(22), MUTED, limit=1480)
    save(img, "fig-cost.png")


# ---------------------------------------------------- 4. the shape of the bill
def fig_shape():
    img, d = canvas(1600, 500, "账单的形状：99% 是“重复发送上下文”",
                    "614M 输入 token 里 604M 命中缓存 —— 计费几乎只跟“上下文长度 × 调用次数”有关")
    x0, x1, y, h = 60, 1540, 220, 96
    total = 614.0
    hits = 604.0
    uncached = 9.7
    out = 3.9

    w_hit = int((x1 - x0) * hits / total)
    w_unc = max(6, int((x1 - x0) * uncached / total))
    w_out = max(6, int((x1 - x0) * out / total))
    d.rounded_rectangle([x0, y, x0 + w_hit, y + h], radius=12, fill=ACCENT)
    text(d, (x0 + 26, y + 30), "缓存命中 604M（98.4%）", font(28, True), (10, 20, 32), limit=w_hit - 52)
    d.rounded_rectangle([x0 + w_hit, y, x0 + w_hit + w_unc, y + h], radius=0, fill=AMBER)
    d.rounded_rectangle([x0 + w_hit + w_unc, y, x0 + w_hit + w_unc + w_out, y + h], radius=0, fill=GREEN)
    # 两条小条太窄，说明放到下面，前面用色块对齐
    leg = [(AMBER, "未命中输入 9.7M"), (GREEN, "输出 3.9M")]
    lx = x0
    for col, lab in leg:
        d.rectangle([lx, y + h + 26, lx + 18, y + h + 44], fill=col)
        lw = text(d, (lx + 30, y + h + 22), lab, font(24), MUTED)
        lx += 30 + lw + 60

    text(d, (60, 372), "折算：¥68.51 ÷ 614M ≈ 每百万 token 一毛一分钱。", font(28, True), FG, limit=1480)
    text(d, (60, 424), "所以省钱的杠杆是“别把同一段长上下文反复重发”，不是“让它少干活”。",
         font(24), MUTED, limit=1480)
    save(img, "fig-bill-shape.png")


# --------------------------------------------------------- 5. the three layers
def fig_layers():
    img, d = canvas(1600, 470, "三层各管一件事", "卡 · 道 · 账本")
    cards = [("卡", "一段任务\n＋ 裁决它的命令", ACCENT),
             ("道", "落在哪跑、用哪个 agent\n可改哪些路径（有闸门）", GREEN),
             ("账本", "真实改动 · 裁决\n完整事件流（本地 SQLite）", AMBER)]
    x, y, bw, bh, gap = 60, 190, 460, 190, 60
    for i, (head, body, col) in enumerate(cards):
        bx = x + i * (bw + gap)
        d.rounded_rectangle([bx, y, bx + bw, y + bh], radius=14, fill=PANEL, outline=LINE, width=2)
        d.rectangle([bx, y, bx + bw, y + 6], fill=col)
        text(d, (bx + 28, y + 32), head, font(34, True), col)
        for j, ln in enumerate(body.split("\n")):
            text(d, (bx + 28, y + 92 + j * 34), ln, font(22), MUTED, limit=bw - 56)
    text(d, (60, 404), "工具内部没有一个 token 的 LLM —— 判官不能是另一个可能被同一个提示带偏的模型。",
         font(22), MUTED, limit=1480)
    save(img, "fig-layers.png")


if __name__ == "__main__":
    fig_flow()
    fig_watchdog()
    fig_cost()
    fig_shape()
    fig_layers()
    if problems:
        print("\n自检发现问题：")
        for p in problems:
            print(" ", p)
        raise SystemExit(1)
    print("\n全部图自检通过（无文字溢出）")
