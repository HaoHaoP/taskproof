# taskproof

<p align="center"><img src="docs/assets/icon.png" width="128" alt="taskproof"></p>

给 AI 编码 agent 用的传送带。

它不决定**该做什么**，只保证派出去的活都被**独立验收**过、**留了痕迹** ——
你不需要相信 agent 自称"我干完了"。

**状态：stage 1 已可用，stage 2 的桌面看板也来了。** 引擎、CLI、静态看板、本地只读
REST API，以及 `desktop/` 里的 Electron 看板均已实现。完整设计与决策记录见
[`docs/DESIGN.zh-CN.md`](docs/DESIGN.zh-CN.md)。

## 安装

两条路：不写代码就装桌面控制台，写代码就用命令行。

### 桌面控制台（推荐给不写代码的人）

到 [GitHub Releases](https://github.com/HaoHaoP/taskproof/releases) 页下载对应平台的安装包：

- macOS arm64（Apple 芯片）—— `.dmg`
- Windows x64 —— `.exe`
- Linux x64 —— `.AppImage` / `.deb`

安装包**未签名、未公证**：

- **macOS 只有 arm64**（没有 Intel 版，也没有 Rosetta 版）：首次打开要右键点应用 → 打开，
  或执行 `xattr -d com.apple.quarantine /Applications/Taskproof.app`。
- **Windows 10+**：首次打开会有 SmartScreen 提示。

最低版本：macOS 11+、Windows 10+，或较新的主流 Linux 发行版。安装包**自带 Python 运行时**，
装完即用，不需要 `pip install`；但需要系统里有 **`git`**，作业树与禁改路径闸门靠它，没装 git
时设置页会明说，其余功能照常。

### 命令行版（开发者）

```bash
pipx install git+https://github.com/HaoHaoP/taskproof
```

或从同一个 Release 下载 wheel，装本地文件：

```bash
pipx install ./taskproof-0.1.0-py3-none-any.whl
```

或从源码可编辑安装：

```bash
pip install -e .
```

**PyPI 上没有这个包。** 别去 PyPI 找；用上面三种方式之一。

## 跑一条任务

```bash
taskproof init
taskproof register /absolute/path/to/your/repo
taskproof run <project> "修掉那个挂掉的测试"
```

`run` 一条命令就是完整生命周期：把卡**派发**给可插拔的适配器（codex / claude / gemini /
opencode，或 `custom:<cmd>`），智能体退出后 taskproof **独立跑注册表里的验收命令**，最后把
每一步**记账**进审计流水。智能体自称的"干完了"永远不算判定。

`taskproof tasks` 列出在跑的卡；`taskproof show <id>` 与 `taskproof log <id>` 回读一张卡。

桌面控制台和命令行共用同一个账本。桌面版首次启动会在 `~/.taskproof` 建一个**空工作区**
—— 一张 `[defaults]` 表和一段注释示例，**不放任何示例项目、不放任何示例任务** —— 看板空态
会把你引到「项目」页（或 `taskproof register <path>`）。因为控制台和 CLI 读的是同一个
`~/.taskproof`，两边互相看得见对方的卡。

[`docs/WALKTHROUGH.zh-CN.md`](docs/WALKTHROUGH.zh-CN.md) 把上面这条链在一个临时示例上从头跑到尾
—— 包括"智能体报告成功、而验收命令不同意"的那种情形。

---

## 派发任务

这套用法的核心，是**给派活的那个智能体的纪律**，现在它作为 skill 随仓库一起走：

```
skills/taskproof-dispatch/SKILL.md
skills/taskproof-dispatch/SKILL.zh-CN.md
```

它是**给 AI 编码 agent 的操作手册**，写给**主智能体**（负责规划、注册仓库、写卡、发车的那一个）。
taskproof 本身不做规划（见"不做什么"），这个 skill 补的正是另一半：怎样驱动这个工具，而不重蹈
踩过的坑。两种语言都随仓库发布：`SKILL.md`（英文）与 `SKILL.zh-CN.md`（简体中文）。

它里面的规矩不是凭空写的，每一条都是踩坑换来的。比如 `pkill -f`：卡是当进程 argv 传进去的，
模式会把调度器自己也一起匹配上、把这次运行直接杀掉 —— 这正是这个 skill 要沉淀的那种实战口径。它把本次
开发沉淀的步骤写成可直接照做的清单：注册项目、把卡写进文件并用 `$(cat …)` 传入、
带上明确的 `--adapter` 与 `--timeout` 发车、再用 `taskproof tasks --all` 和
`taskproof log <id>` 回读状态。尤其钉死四条**踩过才知道**的纪律：

- **串行是 group 的属性，不是习惯。** 不同 group 本来就该并行到全局上限；唯一值得串行的情形是
  "同 group 且文件范围重叠"。
- **绝不拿真实注册表做测试。** UI 验证一律用 `/tmp` 下的一次性 profile + 一次性工作区；
  一个在真实 `~/.taskproof/projects.toml` 上做删除测试的 worker，会连带删掉用户的项目。
- **绝不 `pkill -f`。** 卡正文是作为 argv 传给发车进程的，于是卡里的任何字符串都在发车进程自己的
  命令行里 —— `pkill -f` 会匹配到发车自己并把它杀掉（表现为 exit -15、不建任务、日志空）。按 PID 杀。
- **复核 ≠ 自述。** 主智能体自己重跑验收命令、自己做客观断言；"worker 说 done 了"不是证据。

## 问题

GitHub 上的编排类项目都在卷同一件事：**能同时跑多少 agent、支持多少 CLI、UI 多好看**。
几乎没有人认真谈那个真正天天咬人的问题：

**agent 会撒谎。**

下面这些是这套工作流里真实发生过的：

| agent 的说法 | 实际情况 |
|---|---|
| "浏览器已验证，附截图" | 事件流里零条浏览器操作 |
| （静默地、越出范围） | 拿猜来的弱口令尝试登录本地应用的 HTTP 接口 |
| 任务完成，结果文件已写 | JSON 被 markdown 代码块包住，结构化解析失败，整次运行看起来像什么都没干 |
| 任务完成 | 独立跑验收命令，红的 |

这些都不是罕见情况，而是"把写文件的活交给自主进程"的常态。

## taskproof 是什么

一层很薄的机械派发层，给每次 agent 调用套上纪律：

- **独立验收** —— agent 的自述永远不算成功。注册表里的验收命令由 taskproof 事后自己跑。
- **禁改路径** —— 注册项可以声明 agent 不许碰的路径。
- **结构化结果契约** —— 约定输出形状，并为"做不到结构化的 CLI"写明降级方案。
- **追加式审计** —— 每次派发、验收、失败、重试都留痕，"昨天发生了什么"是查询，不是回忆。
- **有意义的退出码** —— 调用方能区分"agent 失败了"和"agent 成功但验收没过"。
- **内部无 LLM** —— taskproof 不做规划、不做拆解、不做决策。任何 agent（或人、或脚本）都能驱动它。

## 形态

```
taskproof run <项目> "<任务>"     # 派发 → 验收 → 记账
taskproof tasks / show / log     # 查状态
taskproof board                  # 静态看板快照
taskproof api --port 8787        # 给客户端用的本地只读 REST API
```

- Python，纯标准库，`pipx install` 可装
- SQLite 存状态（事务认领，不用锁文件）
- JSONL 审计流水，只写不查，按月轮转
- 可插拔适配器（codex / claude / gemini / opencode + 任意命令）

## 并发上限

全局上限是工作区级的，而且**永远显示"生效值 + 来源"**，不给一个光秃秃的数字。来源按优先级三个：

1. `run --cap N` —— 仅本次派发生效，不落盘；
2. 注册表里的 `[defaults] concurrency`；
3. 按机器自动探测。

自动探测刻意保守 —— 一个槽就是多一个完整的编码智能体：

```
cap = clamp(2, 核数 // 4, 6)      # 每四核最多一个槽
if RAM < 8 GiB: cap = 2           # 小内存机器扛不住 核数 // 4
if 核数不可用: cap = 3            # 历史默认值
```

查生效值与来源：

```bash
taskproof config --show
```

改写落盘的值（保留注释）：

```bash
taskproof config --concurrency N
```

`run --cap N` 只对本次派发生效。**改小不追溯**：绝不动正在跑的卡 —— CLI 会把超出新上限的卡
逐张打印出来，取消谁由你决定。

## 终态与两把闸门

两个终态刻意分开：

- **`blocked`** —— 越界：动了注册表声明禁改的路径。验收可能都过了，是闸门把它拦下的。
- **`failed`** —— 验收跑了且红了，或适配器本身失败；是活干砸了。

两者都用 `accept` 清掉，而 accept 是**人工登记，不是重判**：

```bash
taskproof accept <id>                  # blocked：说明可选
taskproof accept <id> --note "原因"     # failed：必须带 --note
```

`accept` **绝不重跑验收、绝不改写已记录的判定** —— 这次运行自己的事实保持权威。收尾一张
`failed` 卡必须留说明，因为那是人工签字，理由得留在账里。`taskproof rerun <id>` 从一张终态卡
起一张新卡，并双向关联（`rerun_of` / `rerun_as`）。

看板上 `blocked` 独立成**「待复核」**列，不混进失败列。

## 桌面看板

`desktop/` 是 stage 2 的看板：一个 **Electron + Vue 3** 应用（Element Plus、UnoCSS、
Pinia、vue-i18n），渲染的数据和静态看板同源，但是活的。中英双语（跟随系统 locale，回退英文）。

有意思的是它的进程模型：应用自己拉起本地服务 —— `taskproof api --port 0` —— 从子进程 stdout
读回绑定的端口，退出时再关掉它。数据全部来自那个回环、**只读**的 REST API，不出 `127.0.0.1`。

写操作是唯一的可选项。`taskproof api --port 0 --allow-write` 会生成一个**会话内令牌**，
只打印一次到 stdout、只存在于进程内存 —— 不写文件、不进 argv、不进环境变量、不进响应，
也绝不交给渲染进程（写路径留在 Electron 主进程）。每次写入都带上读到的 `expected_hash`；
文件在磁盘上变了就拒绝写入并返回 **409** 与当前内容，于是手改过的 `projects.toml` 永远不会被悄悄覆盖。

控制台现在能干什么：

- **列** —— 运行中 / 验收中 / 完成 / 已取消 / 待复核 / 未通过。控制台目前仍留着那列永远
  为空的「排队」，下一张桌面卡把它删掉。列头可用 `?hide=` 查询参数显隐。
- **完成列默认折叠**到最近的几张，折叠条展开其余。
- 验收已过的 blocked 卡上挂**「验收已过」徽标**。
- **「放行」按钮**用于清掉 blocked 卡；写操作走 Electron 主进程持有的会话令牌，遇到
  **409**（"已不是待复核"）就刷新看板而不是报错。
- 设置页显示**生效值 + 来源**，以及解析出来的启动命令（随包运行时 / PATH 上的 `taskproof` /
  自定义命令）。
- **托盘**、**Dock 角标**（未通过计数）与**开机自启**开关。

## 注册表

taskproof 能派活的东西全写在工作区的一个 TOML 文件里
（`~/.taskproof/projects.toml`）：路径、并发组、以及事后必须通过的验收命令。

```toml
[[project]]
id   = "my-app"
path = "/absolute/path/to/my-app"
group = "my-app"
verify = "npm run build"    # 由 taskproof 在智能体退出后执行
verify_kind = "build"       # check | build | none
```

`taskproof register <路径>` 会追加一条。带注释的起点见
[`examples/projects.example.toml`](examples/projects.example.toml)，字段参考与
硬错误清单见 [`docs/REGISTRY.zh-CN.md`](docs/REGISTRY.zh-CN.md)。

## 安全与卫生

- **保护路径是"快照比对"，不只是 diff。** 禁改路径在跑前跑后各做一次指纹，因此 `.git/`
  或被 ignore 的构建/依赖目录里的改动同样会被抓到，不止 `git status` 报出来的那些。
  超过 20000 项的目录树会被抽样，审计事件里记下 `snapshot_truncated: true`。
- **每次 push 前跑资产扫描**（`tools/scan_assets.py`，通过 `core.hooksPath` 挂上）。
  它只带通用的**形状**规则，所以扫描永远不是空转。
- **机构专属词库放在仓库外**（`~/.taskproof/asset-patterns.txt`，或
  `$TASKPROOF_ASSET_PATTERNS`）。把要保护的词本身写进扫描器的做法，恰恰就是泄漏。

## 枚举契约

状态词、`verify_kind` 取值、退出码含义是**同一份**生成物 ——
[`contract/enums.json`](contract/enums.json) —— 由 `tools/gen_contract.py` 从 Python 常量生成。
TypeScript 侧直接 import，不手抄；Python 里有、前端里没有的状态，就是一张会从看板上
凭空消失的任务卡。CI 跑一致性检查，两种语言无法漂移：

```bash
PYTHONPATH=src python3 tools/gen_contract.py --check
```

## 开发

从源码跑：

```bash
pip install -e .
taskproof --version
```

或免安装：

```bash
PYTHONPATH=src python3 -m taskproof doctor
```

两套测试，写这份文档时都全绿：

- **Python** —— `PYTHONPATH=src python3 -m unittest discover -s tests`（448 个）。
- **桌面** —— `cd desktop && npm install && npm test`（258 个）。`npm run build` 会跑类型检查，
  并把三个目标都做一次生产构建。

CI 跑三个检查：资产扫描（`tools/scan_assets.py`）、枚举契约一致性检查
（`PYTHONPATH=src python3 tools/gen_contract.py --check`），以及桌面构建 + 测试。

## 已知限制

- **未签名、未公证。** macOS 首次打开会有 Gatekeeper 提示（右键 → 打开，或清掉 quarantine
  标记）；Windows 会有 SmartScreen 提示。
- **macOS 只有 arm64。** 没有 Intel 版，也没有 Rosetta 路径。
- **闸门需要 `git`。** 没有系统 `git` 时，作业树与禁改路径闸门不可用；设置页会明说，其余功能照常。
- **看板一次最多取回 2000 行。** 到顶时会显示**「已到取回上限」**，而不是假装自己拿全了。
- **Windows / Linux 安装包由 CI 原生 runner 构建。** 本机只能打 macOS 包。

## 文档

文档成对发布，英文与简体中文各一份：

| English | 中文 |
|---|---|
| [`README.md`](README.md) | [`README.zh-CN.md`](README.zh-CN.md) |
| [`docs/DESIGN.md`](docs/DESIGN.md) | [`docs/DESIGN.zh-CN.md`](docs/DESIGN.zh-CN.md) |
| [`docs/REGISTRY.md`](docs/REGISTRY.md) | [`docs/REGISTRY.zh-CN.md`](docs/REGISTRY.zh-CN.md) |
| [`docs/WALKTHROUGH.md`](docs/WALKTHROUGH.md) | [`docs/WALKTHROUGH.zh-CN.md`](docs/WALKTHROUGH.zh-CN.md) |

派活纪律是一个 skill：[`skills/taskproof-dispatch/SKILL.md`](skills/taskproof-dispatch/SKILL.md)（英文）与 [`skills/taskproof-dispatch/SKILL.zh-CN.md`](skills/taskproof-dispatch/SKILL.zh-CN.md)（简体中文）。

## 图标

`docs/assets/icon.png` 是应用图标的 256 px 副本，小到可以放进仓库。来源是一张 AI 生成的
图形；把烧进 PNG 里的棋盘格抠掉后，按苹果的 824/1024 网格摆放（图形占 1024 px 画布里的
824 px，留出正确的圆角边距），再用 `sips` 缩成这个 256 px 副本，放在本页最上面。

## 不做什么

- 不做内置 LLM 编排
- 不做 agent 之间的对话层
- 不生成、不编辑代码
- 不做任何自动化的 `git` 写操作

## 退出码

退出码是给调用方（脚本、agent、CI）的契约：不用解析 stdout，
就能知道这次运行**为什么**结束。

| 码 | 含义 |
|---|---|
| 0  | 成功 |
| 2  | 注册表问题（项目未注册、注册表缺失/损坏、id 重复） |
| 64 | 用法错误（参数不对、路径不存在、任务或适配器不存在） |
| 70 | 适配器（agent）失败 —— CLI 没跑起来，或结果无法解析 |
| 71 | 验收/产物自检失败（验收命令没通过） |
| 75 | 并发受限（同组占用，或全局配额已满） |

## 许可证

Apache-2.0，见 [`LICENSE`](LICENSE)。

---

<sub>English: [README.md](README.md)</sub>
