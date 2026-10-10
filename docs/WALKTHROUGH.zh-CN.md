# 从零开始

一次在临时示例上的完整走查。下面的命令都是照原样跑过的，输出是从那次运行里直接抄下来的。

这个示例刻意不依赖 LLM：用一段 shell 脚本充当智能体，所以全程不需要 API key，也不需要任何编码
CLI。这样做的另一个好处是后半段更诚实 —— 它演示的正是"一个自称干完、其实什么都没干的智能体"，
而这恰恰是 taskproof 存在的理由。

## 1. 安装

```bash
pipx install taskproof
```

从源码仓库：

```bash
pip install -e .
```

## 2. 建工作区

```bash
taskproof init
```

```
initialised workspace: /tmp/tp-walkthrough/workspace
  registry: /tmp/tp-walkthrough/workspace/projects.toml  (no projects yet)
next:
  taskproof register <path>         # probe and register a repository
  taskproof run <project> "<task>"  # dispatch, verify, record
  taskproof board --open            # live dashboard (serves + opens a browser)
  taskproof board --out board.html  # static snapshot (does not auto-refresh)
  registry format                   # examples/projects.example.toml
```

工作区默认在 `~/.taskproof`；`--workspace`（或环境变量 `TASKPROOF_HOME`）可以换地方。

注册表建出来只有 `[defaults]` 表、没有项目。这里不留任何指向不存在路径的占位条目 ——
条目由 `register` 写入（见下一节），所以在你添加之前，`taskproof projects` 就是空的。

## 3. 登记一个仓库

```bash
taskproof register /tmp/tp-walkthrough/demo-library
```

```
project:   demo-library  (/tmp/tp-walkthrough/demo-library)
taskgroup: demo-library  (lock: demo-library)
verify:    (none inferred — set one by hand)
hint:      you may add an AGENTS.md to describe the repo to agents
```

`register` 会探测仓库并追加一条记录。它**不会**替你编一条验收命令：猜出来的命令会让验收看着比
实际更严格，所以推不出来时它直接说推不出来，而不是随便挑一个。

## 4. 声明验收命令

这一步决定了"完成"到底指什么。在工作区的 `projects.toml` 里：

```toml
[defaults]
concurrency = 3   # 同时运行的任务数上限
timeout = 1800    # 秒；超过判为卡死

[[taskgroup]]
id = "demo-library"
path = "/tmp/tp-walkthrough/demo-library"
verify = "sh check.sh"
verify_kind = "check"
result_schema = "none"
```

`verify` 由 taskproof 在智能体进程**退出之后**、于项目路径下执行。智能体对自己工作的任何说法
都不算证据。`result_schema = "none"` 关掉结构化输出：任意命令没有 schema 约定，本来也会退化
成纯文本。

字段参考见 [`REGISTRY.zh-CN.md`](REGISTRY.zh-CN.md)。

```bash
taskproof projects
```

```
ID                   TASKGROUPS             PROBE   TASKS ACTV FAIL LAST ACTIVITY             VERIFY
demo-library         demo-library           -           0    0    0 —                         sh check.sh
  path: /tmp/tp-walkthrough/demo-library
  taskgroup: demo-library -> /tmp/tp-walkthrough/demo-library (sh check.sh)
```

## 5. 派一个任务

`custom:<命令>` 可以把任意命令当作智能体。这里用一个脚本充当：

```bash
taskproof run demo-library "add an add() function to src/lib.py" --adapter "custom:sh fix.sh"
```

```
t-20261008-001  done  demo-library
```

退出码 0。注意决定这个结果的是什么：不是脚本对自己的评价，而是 `sh check.sh` —— taskproof
事后自己跑的那条命令。

## 6. 看它撒谎

同一个项目，换一个"报告成功、什么都没改"的智能体：

```bash
taskproof run demo-library "make the acceptance command pass" \
  --adapter "custom:echo All done! Tests pass, verified in browser."
```

```
taskproof: acceptance command failed (exit 1)
  hint: output: FAIL: add() is missing
```

退出码 **71**。它表示"智能体跑完了，但验收没过"，与"智能体自己失败了"（70）是**刻意区分**的
两种结果 —— 调用方不用解析输出就能分辨。

## 7. 查看

```bash
taskproof tasks --all
```

```
作用域: 全部 1 个项目（来自 --all）

# demo-library (2 个任务)
    ID                 STATUS     PROJECT          BRIEF
    t-20261008-001     done       demo-library     add an add() function to src/lib.py
    t-20261008-002     failed     demo-library     make the acceptance command pass
```

```bash
taskproof show t-20261008-001
```

```
id:       t-20261008-001
project:  demo-library
status:   done
adapter:  custom:sh fix.sh
brief:    add an add() function to src/lib.py
verify:   sh check.sh (exit 0)
workdir:  /tmp/tp-walkthrough/demo-library
```

```bash
taskproof log t-20261008-001
```

```
started        {"project": "demo-library", "group": "demo-library", "adapter": "custom:sh fix.sh", ...}
result_schema  {"enabled": false, "path": null, "note": "structured result disabled ..."}
adapter        {"exit_code": 0, "degraded": true, "summary": "wrote src/lib.py"}
verify         {"status": "PASSED", "ran": true, "exit_code": 0, "note": "", "output_tail": "ok"}
done           {"verify": "PASSED", "files_changed": 1, "summary": "wrote src/lib.py"}
```

时间戳为了排版删掉了。事件流是只追加的，最后两行里那句判定是 taskproof 写的，不是智能体报的。

## 8. 重跑验收

```bash
taskproof verify t-20261008-002
```

```
t-20261008-002  verify: FAILED  exit=1
```

## 9. 看板与 API

```bash
taskproof board --open             # 实时看板，阻塞，服务在 8787
taskproof board --out board.html   # 独立快照，不自动刷新
taskproof api --port 8787          # 给客户端用的只读 REST
taskproof api --port 0             # 绑一个空闲端口并把它打印出来
```

`api --port 0` 在开始服务之前会打印恰好一行：

```
taskproof api listening on http://127.0.0.1:61071
```

`desktop/` 里那个桌面应用就是靠这一行知道自己在跟哪个端口说话。

## 让人意外的几点

**`custom:` 从不启动 shell。** 模板按 shell 风格分词、占位符逐 token 替换，之后不会再被重新解释：

```
custom:sh fix.sh                 # 可以：两个 argv 元素
custom:sh -c printf '...' > x    # 那个 > 会当成普通参数传进去
```

想把 shell 逻辑写进模板是徒劳的 —— 把逻辑放进脚本里。

**不说话的命令等于适配器失败。** 任意命令没有结构化输出约定，taskproof 只能解析它打印出来的
东西。什么都没打印就无可解析，于是这一趟以适配器失败收场（70）。让它说句话。

**`--json` 是全局参数**，放在子命令**之前**：`taskproof --json tasks --all`，
而不是 `taskproof tasks --all --json`。

**失败的派发不会回滚。** 一次以失败告终的派发，工作区可能已经被改过了；退出码告诉你的是结果，
不是磁盘上现在的状态。`forbidden_paths` 和 `--worktree` 就是为这件事准备的。

**`--worktree` 会保留这趟运行未提交的成果。** 带 `--worktree` 的运行在仓库**同级**目录里
开一份全新的检出，路径为 `<仓库父目录>/<仓库名>-wt-<任务id>`（绝不放进仓库内部，因此不会污染
项目自己的 `git status`）。跑完即删——**除非检出里还有改动**，那时它会被**保留**：打印一行
`worktree kept: <路径> (N files changed)`，追加一条 `worktree` 事件记录该路径，检出自此留下供你
查看或提交。保留的检出不会被复用，下次运行照常新开。`taskproof rm <任务id>` 会把保留下来的检出
连同任务的记录与事件一起删掉。

**`verify_kind = "none"` 记为「跳过」，绝不是「通过」** —— 见
[`REGISTRY.zh-CN.md`](REGISTRY.zh-CN.md)。

---

<sub>也可读 [English](WALKTHROUGH.md)。</sub>
