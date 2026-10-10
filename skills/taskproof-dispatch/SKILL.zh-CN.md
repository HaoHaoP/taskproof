---
name: taskproof-dispatch
description: Use when a main agent dispatches coding cards to worker agents through taskproof and must follow the dispatch discipline — register projects and their lanes, fire cards in parallel by default, read status and logs, kill by PID, and re-verify results objectively instead of trusting the worker.
---

# 用 taskproof 派活

`taskproof` 不决定*做什么*，只保证派出去的活被**独立验收**、**留痕**。
本 skill 是**主智能体**（派活的那一个）的操作手册：一次一张卡，卡里有根因、有验收，发车后自己复核，不认 worker 的自述。

命令一律是可直接复制的一整行。示例路径统一写 `/absolute/path/to/repo`。

## 0. 铁律

1. 一张卡只做一件事；卡正文必须指名**文件:行号**的根因，不写"你自己找找"。
2. 验收命令写进卡正文，并与注册表里的 `verify` 保持一致。
3. worker 只做实现，**不提交**；`git add` / commit / push 由主智能体做。
4. 同 group 的**道**串行、异 group 并行，判据见第 6 节；除此之外**默认并行**。
5. **按 PID 杀进程**，不要 `pkill -f`（见第 7 节）。
6. UI 验证只用 `/tmp` 下的一次性 profile + 一次性工作区，**绝不写真实注册表**（见第 8 节）。
7. 主智能体**自己重跑验收**（`taskproof verify <id>`）、自己做客观断言，不把 worker 的自述当结论（见第 9 节）。

## 1. 注册项目与它的任务组

```bash
taskproof init
taskproof register /absolute/path/to/repo                     # 自成一条道
taskproof register /absolute/path/to/repo --project my-repo   # 挂到已有项目下
taskproof register /absolute/path/to/repo --id my-lane --project my-repo
taskproof --json register /absolute/path/to/repo --dry-run
```

注册表是**两层**，`register` 写的是下面那层：

- **`[[project]]`** —— 一块*地方*：`id`、`path`（默认路径）、`aliases`。它是看板成行与筛选的单位。可以省略；一条道不写 `project` 时，自成一个同名项目。
- **`[[taskgroup]]`** —— 一条**道**：`id`、`project`、`path`、`aliases`、`verify`、`verify_kind`、`forbidden_paths`、`result_schema`。派活派进的就是它，它的 `group` 是并发锁。

`register` 追加一条 `[[taskgroup]]`（`--project` 把它挂到已声明的项目下；不带就自成一条道）。`--dry-run` 只探测、不落盘；`--json` 是根级开关，必须放在子命令**之前**。注册表默认在 `~/.taskproof/projects.toml`，也可用 `--workspace <dir>` 指向别处。

**旧写法一个字都不用改**：带任一 lane 字段（`verify` / `verify_kind` / `forbidden_paths` / `result_schema`）的 `[[project]]` 块，等价于"同名项目 + 同名一条道"，它原来的 `group` 原样作为锁保留。

字段以 `docs/REGISTRY.md` 为准；派活时真正相关的这些：

| 字段（写在道上） | 必填 | 默认 | 说明 |
|---|---|---|---|
| `id` | 是 | — | 道之间唯一；重复是硬错误 |
| `project` | 否 | 自己的 `id` | 必须指向已声明的项目，或干脆不写 |
| `path` | 否 | 项目的 `path` | 必须绝对路径 |
| `group` | 否 | 自己的 `id` | 并发锁，见第 6 节 |
| `aliases` | 否 | `[]` | 别名，凡接受 id 处都接受 |
| `verify` | 否 | — | 验收命令，agent 退出后由 taskproof 跑 |
| `verify_kind` | 否 | `"none"` | `check` / `build` / `none` |
| `forbidden_paths` | 否 | `[]` | 禁改路径前缀；末尾带 `/` 覆盖整棵目录 |
| `result_schema` | 否 | `"default"` | `default` / `none` / 绝对路径 JSON Schema |
| `workspace` | 否 | `"none"` | `none` / `worktree` —— 见下面「道可以有自己的检出」 |
| `link` | 否 | `[]` | 依赖路径（相对工作区），从主树软链进来 |

要记住的语义：

- `taskproof projects` 列项目与它名下的道；`taskproof taskgroups` 列道与它的归属。**项目 id 只在它名下只有一条道时**才解析得到那条道；多条道就报错让你指名（API 的 `?project=` 两种 id 都吃）。
- `group` 是**串行 key，不是标签**。同一把锁一次只跑一个；不同锁可并行到 `[defaults] concurrency`。它缺省等于道自己的 id，所以**两条道只有写了同一个值才互斥** —— Python 道与桌面道共用一棵工作树时就是靠这个互不相撞。
- 没有 `verify` 不是"通过"，是 **SKIPPED**。
- `forbidden_paths` 在跑完后检查，且不只靠 `git status`——`.git/` 与被 ignore 的构建产物也算，改了就判失败。
- 闸门忽略 Python 字节码（`__pycache__` 目录段、`.pyc` / `.pyo`），因为那是跑工具的副产品、不是人工改动——但这不是随便写文件的许可。**在道的 worktree 里跑 Python 时用 `python3 -B`（或 `export PYTHONDONTWRITEBYTECODE=1`）**，或者干脆用主树 / 已装的包建数据，别从 worktree 里 import。双保险，不是闸门的替代。
- 类型前缀不是例外：`presence:` 只为它自己那条规则加一路**更弱**的观察，绝不会取消另一条同样覆盖该路径的 `file` 或目录规则。特别地，`presence:t/__pycache__/` **不会**把字节码从 `t/` 规则里豁免出去。
- 一个仓库名下有多条道是常态（一条一个技术栈、或一条一个工作副本）—— 项目这一层就是为它准备的。
- **道可以有自己的检出。** `workspace = "worktree"` 让这条道在仓根旁边拥有一棵**长驻**的 git worktree（`<仓名>-ws-<道 id>`）：这条道**第一次真发车**时惰性创建，之后的每张卡**复用同一棵**；运行目录是道在这棵树里的对应位置（道指向子目录就跑在那个子目录里）。`link = ["web/node_modules", …]` 把依赖从主树软链进来（不写就按构建文件探测：`package.json` → `node_modules`、`Cargo.toml` → `target`；**Python 的 venv 刻意不探测** —— 它的配置与控制台脚本写死绝对路径）。默认是 `none`，理由很硬：含主树绝对路径的 verify 命令一旦跑进工作区，会静默地验收**主树**。`taskproof workspaces` 列这些工作区；`taskproof workspace-rm <道>` 先打印证据（未提交改动、未合并提交），脏则拒绝，`--force` 才删。`--worktree` 仍是一次性语义；道声明了工作区时以工作区为准。
- `.git` 规则读的 `refs/heads/*` 已减去「**别的工作树已检出的分支**」：兄弟检出里的提交不算这张卡头上；卡自己那棵树的 HEAD 与分支、新分支与新标签、`refs/remotes/*` 与 `stash` 照样抓。

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

`tasks --all` 忽略 cwd 作用域、列出所有道；`--json` 给机器读。发车前先看现在几个在跑，在并发上限内就把独立工作一起发出去。

## 4. 发车

```bash
taskproof run my-lane --adapter codex --timeout 1800 "$(cat /tmp/cards/tp-card19.md)"
```

- `--adapter`：`codex` / `claude` / `gemini` / `opencode` / `custom:<cmd>`。
- `--timeout`：秒；覆盖注册表 `[defaults] timeout`。
- `--cap N`：只为这一次发车抬高全局上限。
- `--worktree`：仓边上一棵一次性检出，有改动就保留。**一次性手段**：声明了 `workspace = "worktree"` 的道有长驻工作区，两者同时出现时以道的工作区为准。
- 卡放文件、`$(cat ...)` 传入：省去转义，也方便备份与重跑。

**没有"入队"这个状态。** `run` 当场发车。上限满了就是退出 **75**、账本不留痕：等一会儿重发、给这次发车抬高上限（`--cap N`）、或改持久配置（`config --concurrency N`）。

## 5. 查状态与读日志

```bash
taskproof tasks --all
taskproof --json tasks --all
taskproof show <task-id>
taskproof log <task-id>
taskproof log <task-id> --follow
taskproof verify <task-id>
taskproof workspaces
taskproof workspace-rm my-lane            # 先打印证据，不干净就拒绝
taskproof workspace-rm my-lane --force
```

`log` 打印该任务的完整事件流；`--follow` 会一直跟到终态。

`verifying` 是**真会落库的状态**：验收命令在跑的那段时间，卡就记为 `verifying`，所以一次长编译或整套测试在板上看得见，而不是藏在 `running` 里。停在这个状态不是卡住了，是在验收。

`verify <id>` 会对一张已有任务**重跑**注册表里那条验收命令，并追加一条 `verify` 事件。这就是主智能体的复核动作（见第 9 节）：它把"我又跑了一遍"记成事实，而不是嘴上说。

`workspaces` 列出声明了工作区的道，及其路径与里面还剩什么。`workspace-rm` 先把证据打印出来（未提交改动、未合并提交、以及会解除 git worktree 注册），只删没有留下成果的工作区 —— `--force` 才覆盖，并在输出里说明。删道的工作区**永远不是**别的东西的副作用：`rm <id>` 删的是任务（以及那张任务自己留下的一次性检出），绝不碰道的工作区。

## 5.1 人工收尾：`accept`

`accept <id>` 是人收掉一张管线自己停下的卡的方式。它是**登记、不是判据**。

- 它绝不重跑验收，也绝不改写 `verify_*`：验收结果永远权威，人工登记只是与它并列。
- `blocked`（越界）：`accept <id>` 放行，note 可选——验收绿→`done`，验收红或被跳过→`failed`。
- `failed`（验收红，或适配器失败）：`accept <id> --note "…"` 收成 `done`，但 note **必填**——空或缺一律拒绝（CLI `rc != 0`、HTTP `400`）。note 记的是"这次为什么判为假红"，它不是运行自身 `verify_*` 的替代。
- `done` / `timeout` / `cancelled` 与所有非终态一律拒绝。

## 6. 并行调度：默认并行

**默认就该并行，不要习惯性串行。** 发车前：

1. 先看 `group`：**锁不同的道应当同时发**。给一个项目开多条道本来就是为了这件事——只要文件范围不重叠，同时派发安全，也是压缩整体时间的主要手段。
2. **全局上限**是工作区级的，永远连同**生效值与来源**一起显示——`auto`（机器自动探测）、`toml`（`[defaults] concurrency`）、或 `cli`（一次性 `run --cap N`）。用 `taskproof config --show`（或 `taskproof doctor`）问它，别自己假设数字：全新工作区不带这个键，会自动探测 `clamp(2, cores // 4, 6)`，内存 < 8 GB 时为 2。先 `taskproof tasks --all` 数一下在跑几个，在 cap 之内就把独立工作一起发，别盲目发到槽满。改持久值用 `taskproof config --concurrency N`（保注释、不追溯）；只想抬高一次发车用 `run --cap N`。
3. **当场发车，顺序由你定。** 没有任何东西会把卡"停"起来，也没有守护进程替你推进度 —— 卡与卡之间的次序是主智能体的决定，这也正是**逐卡提交边界**得以保住的原因。被拒的派发（exit 75，同一把锁占用或 cap 满）**在账本里不留痕**：等这条道排空再发。
4. 同一条道里要并行的唯一正路：再开一条**道**（自己的 `path`），给它**不同的 `group`**，并让它声明 `workspace = "worktree"` 拥有自己的检出（一次性场景仍可用 `--worktree`）；**只对文件范围零重叠的卡**这么做 —— 之后主智能体把两份 diff 一次性合回主树。
5. 因此**串行的判据只有一条：同一把锁且文件范围重叠**。其余情况都该并行。
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
taskproof --workspace /tmp/tp-verify-$$ register /absolute/path/to/repo --id verify-repo --project verify-repo
```

**绝不写 `~/.taskproof/projects.toml`。** 真删/真改测试会毁掉用户的注册项——本次开发里就有一次 worker 在真注册表上做删除测试，删掉了用户的一个项目。（注册表是操作者自己的文件；当改它**就是**任务本身时，先备份、再把 diff 给人看。）

**本地 REST 只读，桌面控制台是看板。** `taskproof api` 只提供读接口 —— 没有 `--allow-write`、没有会话令牌、没有任何写端点（写形状的请求一律 404）。派活、停止、放行、删除都在 CLI 里，所以动控制台的卡靠**读它渲染出什么**来验收，而不是靠它去写。

## 9. 主智能体复核清单

worker 报 done、验收显示 PASSED，都不算数。主智能体逐条自己走：

- [ ] **用 `taskproof verify <id>` 重跑验收**并贴真实输出——它会重跑注册表里那条命令并追加一条 `verify` 事件，于是复核是**记在账本里的事实**，不是一句自述。
- [ ] **自己做客观断言**：真窗口就读 DOM（开调试端口 + CDP 比截图可靠）；真文件用 `ls -l`、`python -c "from PIL import Image; ..."`；不要采信 worker 的文字结论。
- [ ] 只 `git add` **本卡点名的文件**，不要把无关改动裹进来。
- [ ] 确认 worker 没有提交（提交由主智能体做）。
- [ ] 复核与提交批量做，别做成每个任务的同步点。
- [ ] 如果这张卡改了**操作者每天要看的东西**（注册表布局、CLI 表面、这份 skill），提交前把那个面重新读一遍。

## 10. 参考

- 注册表字段与硬错误：[`docs/REGISTRY.md`](../../docs/REGISTRY.md)
- 设计决策：[`docs/DESIGN.md`](../../docs/DESIGN.md)
- 从零到一次派发的完整走查：[`docs/WALKTHROUGH.md`](../../docs/WALKTHROUGH.md)
- 退出码：0 成功 / 2 注册表问题 / 64 用法错误 / 70 适配器失败 / 71 验收失败 / 75 并发受限
