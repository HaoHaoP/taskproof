---
name: taskproof-dispatch
description: Use when a main agent dispatches coding cards to worker agents through taskproof and must follow the dispatch discipline — register projects, fire cards in parallel by default, read status and logs, kill by PID, and re-verify results objectively instead of trusting the worker.
---

# 用 taskproof 派活

`taskproof` 不决定*做什么*，只保证派出去的活被**独立验收**、**留痕**。
本 skill 是**主智能体**（派活的那一个）的操作手册：一次一张卡，卡里有根因、有验收，发车后自己复核，不认 worker 的自述。

命令一律是可直接复制的一整行。示例路径统一写 `/absolute/path/to/repo`。

## 0. 铁律

1. 一张卡只做一件事；卡正文必须指名**文件:行号**的根因，不写"你自己找找"。
2. 验收命令写进卡正文，并与注册表里的 `verify` 保持一致。
3. worker 只做实现，**不提交**；`git add` / commit / push 由主智能体做。
4. 同 group 串行、异 group 并行的判据见第 6 节；除此之外**默认并行**。
5. **按 PID 杀进程**，不要 `pkill -f`（见第 7 节）。
6. UI 验证只用 `/tmp` 下的一次性 profile + 一次性工作区，**绝不写真实注册表**（见第 8 节）。
7. 主智能体**自己重跑验收**、自己做客观断言，不把 worker 的自述当结论（见第 9 节）。

## 1. 注册项目

```bash
taskproof init
taskproof register /absolute/path/to/repo
taskproof register /absolute/path/to/repo --id my-repo --group my-repo
taskproof --json register /absolute/path/to/repo --dry-run
```

`register` 会探测仓库并追加一条 `[[project]]`（`--dry-run` 只探测、不落盘；`--json` 是根级开关，必须放在子命令**之前**）。注册表默认在 `~/.taskproof/projects.toml`，也可用 `--workspace <dir>` 指向别处。

字段以 `docs/REGISTRY.md` 为准：

| 字段 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `id` | 是 | — | 唯一；重复是硬错误 |
| `path` | 是 | — | 必须绝对路径 |
| `group` | 否 | `"default"` | 并发组，见第 6 节 |
| `aliases` | 否 | `[]` | 别名，凡接受 id 处都接受 |
| `verify` | 否 | — | 验收命令，agent 退出后由 taskproof 跑 |
| `verify_kind` | 否 | `"none"` | `check` / `build` / `none` |
| `forbidden_paths` | 否 | `[]` | 禁改路径前缀；末尾带 `/` 覆盖整棵目录 |
| `result_schema` | 否 | `"default"` | `default` / `none` / 绝对路径 JSON Schema |

要记住的语义：

- `group` 是**串行 key，不是标签**。同 group 一次只跑一个；不同 group 可并行到 `[defaults] concurrency`。省略 `group` 会落到 `default`，于是所有省略者挤在同一条道。
- 没有 `verify` 不是"通过"，是 **SKIPPED**。
- `forbidden_paths` 在跑完后检查，且不只靠 `git status`——`.git/` 与被 ignore 的构建产物也算，改了就判失败。
- 一个仓库可以注册多条：例如 `taskproof` 指向仓库根、`taskproof-desktop` 指向 `desktop/` 子目录，就是为了让不同目录的卡同时发车。

## 2. 把卡写进文件

卡正文放在文件里，发车时用 `$(cat ...)` 传入——避免 shell 转义，也让卡可复用、可归档。

````bash
mkdir -p /tmp/cards
cat > /tmp/cards/tp-card19.md <<'CARD'
# TP-card19 · 一句话说明这张卡做什么

## 根因
- `src/taskproof/cli.py:88` 在 X 情况下返回了错误的退出码。

## 要做的事
- 只改 `src/taskproof/cli.py`，修掉上面这一处。

## 验收
```bash
cd /absolute/path/to/repo && python -m pytest -q
```

## 硬约束
- 只改上面点名的文件；不 `git add` / commit / push。

## 交付
- 改动文件清单 + 验收命令的真实输出。
CARD
````

## 3. 发车前先看并发现状

```bash
taskproof tasks --all
taskproof --json tasks --all
```

`tasks --all` 忽略 cwd 作用域、列出所有项目；`--json` 给机器读。发车前先看现在几个在跑，在并发上限内就把独立工作一起发出去。

## 4. 发车

```bash
taskproof run my-repo --adapter codex --timeout 1800 "$(cat /tmp/cards/tp-card19.md)"
```

- `--adapter`：`codex` / `claude` / `gemini` / `opencode` / `custom:<cmd>`。
- `--timeout`：秒；覆盖注册表 `[defaults] timeout`。
- 卡放文件、`$(cat ...)` 传入：省去转义，也方便备份与重跑。

## 5. 查状态与读日志

```bash
taskproof tasks --all
taskproof --json tasks --all
taskproof show <task-id>
taskproof log <task-id>
taskproof log <task-id> --follow
```

`log` 打印该任务的完整事件流；`--follow` 会一直跟到终态。

## 6. 并行调度：默认并行

**默认就该并行，不要习惯性串行。** 发车前：

1. 先看 `group`：**不同 group 的任务应当同时发**。同一仓库注册多个条目本来就是为了这件事——只要文件范围不重叠，同时派发安全，也是压缩整体时间的主要手段。
2. `[defaults] concurrency` 是**全局上限**（本机为 3）。先 `taskproof tasks --all` 数一下在跑几个，在 cap 之内就把独立工作一起发，别盲目发到槽满。
3. **新卡默认入队：`taskproof run --park`**（不带号 = 追尾，波次 = 当前最大 `queue_seq` + 1；`--park=N` 指定第 `N` 波）。`queue_seq` 相同的卡属于**同一波**，某一波只在所有更低编号的波排空后才推进。**同一 group 依旧同一时刻只允许一个任务**：被拒（exit 75）的同组卡**落回 `queued` 绝不丢**，下一拍重试。**谁推进由你定**：常驻的 `taskproof queue` 守护进程（无人值守连推），或人工 `taskproof advance <id>`。需要保住**逐卡提交边界**时选 `advance` —— 守护进程会在前一张还没提交时就开始下一张，两张卡的 diff 会糊在一起。
4. 同 group 内确实要并行的唯一合法做法：另注册一个指向 **worktree** 的项目条目、给它不同的 group 名，运行时加 `--worktree`；且**只对文件范围不重叠的卡**这么做——两边 diff 事后由主智能体批量合并回主树。
5. 因此**串行的判据只有一条：同一 group 且文件范围重叠**。其余情况都该并行。
6. 主智能体自己的节拍也要批量：复核与提交攒起来一起做，别让"等我提交"变成整条链的节拍器。

## 7. 杀进程：按 PID

```bash
taskproof --json tasks --all      # 找到任务的 pid
kill <pid>
```

**不要 `pkill -f`。** 卡正文是作为 argv 传给 `taskproof run` 的，卡里出现的任何字符串（比如 `--remote-debugging-port=9333`）都在发车进程自己的命令行里，`pkill -f` 会连发车一起杀掉——表现为 exit -15、不建任务、日志空。

## 8. UI 验证：一次性 profile + 一次性工作区

派出去的 UI 卡，验证时必须开一次性环境，把状态写到 `/tmp`，别落到真实注册表：

```bash
taskproof --workspace /tmp/tp-verify-$$ init
taskproof --workspace /tmp/tp-verify-$$ register /absolute/path/to/repo --id verify-repo --group verify-repo
```

**绝不写 `~/.taskproof/projects.toml`。** 真删/真改测试会毁掉用户的注册项——本次开发里就有一次 worker 在真注册表上做删除测试，删掉了用户的一个项目。

## 9. 主智能体复核清单

worker 报 done、验收显示 PASSED，都不算数。主智能体逐条自己走：

- [ ] **自己重跑验收命令**，贴真实输出（与卡正文里那条对齐）。
- [ ] **自己做客观断言**：真窗口用 `document.elementFromPoint(...)` 之类；真文件用 `ls -l`、`python -c "from PIL import Image; ..."`；不要采信 worker 的文字结论。
- [ ] 只 `git add` **本卡点名的文件**，不要把无关改动裹进来。
- [ ] 确认 worker 没有提交（提交由主智能体做）。
- [ ] 复核与提交批量做，别做成每个任务的同步点。

## 10. 参考

- 注册表字段与硬错误：[`docs/REGISTRY.md`](../../docs/REGISTRY.md)
- 设计决策：[`docs/DESIGN.md`](../../docs/DESIGN.md)
- 从零到一次派发的完整走查：[`docs/WALKTHROUGH.md`](../../docs/WALKTHROUGH.md)
- 退出码：0 成功 / 2 注册表问题 / 64 用法错误 / 70 适配器失败 / 71 验收失败 / 75 并发受限
