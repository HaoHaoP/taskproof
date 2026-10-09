# 设计

> 初次设计会话的产出：11 项决策 + 硬约束。
> 状态：**设计已定，未实现。**

## 一句话

给 AI 编码 agent 用的传送带：不判断该做什么，只保证"派了就验、验了就记"。

## 来源

抽取自一套跑了数周的私有工作流：一个约 330 行的 bash 派发器、一个会探测仓库
并推导验收命令的项目登记器、一份结构化结果契约、一份追加式任务账本，外加一个看板。
期间跑过约 60 个任务，暴露出本项目正是围绕它们构建的那些失败模式。

## 为什么值得存在

同类项目（golutra ★3.8k、CAO ★1.4k 出自 AWS、cezar ★516、agetor ★88）卷的是
编排广度与 UI。它们的 README 里几乎不谈一件事：

**agent 会撒谎。**

实际观察到的：

```
agent 自称"浏览器已验证 / 已截图"      → 事件流里没有任何浏览器活动
agent 越出范围                        → 拿猜来的弱口令尝试 HTTP 登录
agent 的 JSON 结果被 markdown 包裹     → 结构化解析失败，这次运行看起来是空的
agent 报告成功                        → 独立跑验收命令，是红的
```

对应这些的机制 —— **验收独立于自述、禁改路径、结构化结果契约、追加式审计、
有意义的退出码** —— 是本项目的核心资产。它不是又一个编排器，而是一层
**不信任 worker 的派发层**。

## 定位

```
纯机械，无 LLM —— 不判断"该做什么"，只保证"派了就验、验了就记"
可被任何东西调 —— Hermes / Claude Code / 终端前人，共用同一条 CLI
```

与"绑某个 agent"类工具的分水岭：不需要任何编排大脑，也不假装自己是大脑。

## 不做什么

```
不做内置 LLM 编排（不拆解、不诊断失败、不定重试策略）
不做多 agent 对话层
不做代码生成与编辑
不做任何自动化的 git 写操作（commit / push 永不自动化）
```

## 技术选型

```
语言      Python 单包，纯标准库，Python 3.11+
          （sqlite3 / subprocess / json / http.server / argparse / tomllib）
安装      pipx install taskproof
许可证    Apache-2.0（含专利授权，公司可用；刻意不用 AGPL —— 本工具的价值依赖被采用）
仓库      独立仓库，与雇主代码严格隔离
```

## 存储

```
SQLite —— 状态主库
  认领、任务状态、看板查询都读它
  事务取代锁文件（进程崩了不再留下悬空锁）
  保留与归档逻辑写在代码里，而不是靠人的日历

events.jsonl —— 审计流水
  每次操作追加一行，【只写不查】，从不参与逻辑判定
  按月轮转，旧档 gzip
  作用：审计，以及"第二天早上读一遍就知道昨天干到哪"
```

设计要点：JSONL 不承担查询职责，因此"两套事实源"的问题不会出现。
（前身同时维护账本和一份独立的卡片注册表，二者会漂移 —— 看板显示"运行中"
而任务几小时前就结束，就是这么来的。）

**配置与状态分离**：项目注册表是 TOML 文件（人可编辑，可放进用户自己的 git 仓库）。
只有运行时状态进 SQLite。选 TOML 而非 YAML，是因为标准库自带 `tomllib`（Python 3.11+），
而 YAML 会引入外部依赖。

## 数据模型

```sql
tasks
  id            TEXT PK     t-20261007-001
  project       TEXT        注册表 id
  group         TEXT        并发分组
  brief         TEXT        任务描述
  status        TEXT        queued|running|verifying|done|failed|blocked|timeout|cancelled
  adapter       TEXT        codex|claude|gemini|opencode|custom:<cmd>
  model         TEXT
  reasoning     TEXT
  attempt       INTEGER
  exit_code     INTEGER
  pid           INTEGER
  pgid          INTEGER     适配器自成一组，cancel 就定位这个 pgid
  queue_seq     INTEGER     显式队列序号（仅 queued 可写）
  workdir       TEXT
  result_path   TEXT
  verify_cmd    TEXT
  verify_exit   INTEGER
  files_changed INTEGER
  created_at    TEXT
  started_at    TEXT
  finished_at   TEXT

events
  id INTEGER PK, task_id TEXT, ts TEXT, event TEXT, payload TEXT(JSON)  -- 与 JSONL 同源

claims                          -- 并发守卫，带过期回收
  scope      TEXT PK            group:<g> | global
  task_id    TEXT
  pid        INTEGER
  claimed_at TEXT
  expires_at TEXT               -- 死进程会被自动回收
```

## 适配器契约

一个适配器 = 一条命令模板 + 一套结果解析约定。

```
内置    codex / claude / gemini / opencode
兜底    custom:<cmd>          任意命令
契约
  入参  workdir / brief / model / reasoning / 沙箱模式
  出参  ① 结构化 —— CLI 能产出受 schema 约束的结果时
        ② 降级   —— 按成文约定从 stdout 提取
        ③ 失败   —— 退出码 + 最后 N 行
成文记录的坑：markdown 包裹的 JSON、自称"已验证"、越界行为
```

## 并发与超时

沿用前身，默认值可配置：

```
同组串行      每个分组同时只跑一个任务
全局上限      默认 3 个并发任务
硬超时        默认 1800 秒；超时判定卡死，只杀【该任务】的进程
越限行为      被拒的派发退出 75（同组占用 / 全局上限）；
              用 `run --park` 入队，或等一个槽释放后重试
进程安全      只杀 taskproof 自己起的进程
```

## 任务状态

任务的 `status` 记录这次运行**是什么**，终态则说明它为什么停下。

```
queued                    已入队，等待推进
running / verifying       适配器在跑，随后验收在跑
done                      验收通过（或被记成 SKIPPED，绝不记成"通过"）
failed                    适配器失败，或验收跑了且没过
blocked                   动了受保护路径：待人复核
timeout                   适配器撞上硬超时
cancelled                 被人主动停掉
```

`blocked` 是真正的终态，含义是**「待人复核」**，不是「活干砸了」。越界就记成它：
越界是关于这次运行的事实，不是对活好坏的判决，所以和 `failed` 分开（`failed`
只有一个含义 —— 验收没过，或适配器失败）。越界**绝不**提前短路：验收照常跑，两个
事实都进账本 —— `forbidden` 事件带着越界路径，`verify` 事件带着真实结果。越界优先
于验收红：无论验收什么结果，卡都是 `blocked`，由 `verify_exit` 告诉人活本身好不好。

因为 `blocked` 是终态，队列不推进它，`cancel` 拒绝它（没有进程可杀），`rm` 像对待
其它终态一样删掉它。放行一张 `blocked` 卡是人的决定，走层3 的 `accept <id>`；
调度管线绝不自动把它升成 `done`。`accept` 只作用于 `blocked` 一行，而且它判决的是
**越界**、不是活本身：验收绿才判 `done`，验收红或被跳过一律判 `failed`；两种情况都写
一条 `accepted` 事件，记下是谁放行的、验收结论与退出码、以及被确认的那次越界摘要。
重跑是另一件事：`rerun <id>` 从终态卡起一张新卡，复用它的 brief 与 run 旗标，并在账本
里双向关联（新卡记 `rerun_of`、旧卡记 `rerun_as`），`log <id> --json` 两张卡能互相找到。

## 退出码

```
0    成功
2-3  注册表问题
64   用法错误
70   适配器（agent）失败
71   验收或产物自检失败
75   并发受限
```

退出码描述的是**这条命令的结局**，不是任务的终态，两者刻意解耦：越界在账本里记成
`blocked`，但 `run` 命令仍然退出 `71`（和任何验收失败同一条 `VerifyError` 映射）。
关心活能不能接受的调用方读任务状态；只关心命令结局的调用方读退出码。


## 禁改闸门

闸门只回答一个问题：*这次运行有没有动到注册表保护的路径？* 回答它时既不能信
智能体，也不能把环境里的噪声算到智能体头上。由此得出两条设计原则。

**信号是差分，不是快照。** 闸门在适配器启动前记一次受保护状态，退出后再比对一次。
拿「当前全量」当信号从根上就是错的：仓库在发车时本来就可能脏 —— Finder 生成的
`.DS_Store`、遗留的临时目录、做了一半的构建 —— 用当前状态判断会把这些**每次发车**
都算成适配器干的。只有两次快照之间状态发生变化的路径，才属于这次运行。

**每条规则一个信号，按被保护的对象来选。** 规则的 `kind` 决定用哪个探针，审计事件
里也带上这个 `kind`，读的人一眼能看出是哪一路命中：

```
file       git 状态差分 或 size:mtime_ns 指纹差分
           历史信号；抓内容改动、新增、删除
git        HEAD / symbolic-ref / refs / stash 状态（即 `.git/` 探针）
           抓提交、改写历史、分支/标签移动、stash
presence   只比文件集合的增删
           抓文件新增或删除；忽略纯内容改写
```

`presence` 是刻意拿灵敏度换精度。devServer 重写一个已存在的构建产物，内容变了但
文件集合没变，用户也没碰过这棵树 —— 闸门就该保持沉默。代价是真实且写进文档的：
在 `presence` 下，重写一个已存在文件**不算**违规。真需要抓这种情况的仓库，那条路径
用默认的 `file` 规则。

不带类型的规则保留历史含义，所以已有注册表行为不变：裸路径就是 `file` 规则，历史上
那条裸 `.git/` 规则保留 git-state 含义。类型前缀为 `file:` / `git:` / `presence:`。

## CLI 表面

```
taskproof init                          初始化工作区（建库、写示例注册表）
taskproof register <path> [--dry-run]   探测仓库并登记
taskproof projects                      列已登记项目
taskproof run <project|path> "<brief>"  派活（主命令）
          [--adapter X] [--model X] [--reasoning X]
          [--read-only] [--worktree] [--no-verify] [--timeout N]
          [--park[=N]]  只入队、先不发车；不写号=追尾，=N 指定波次
taskproof tasks [--status S] [--project P] [--limit N]
taskproof show <task-id>                单任务详情
taskproof log <task-id>                 事件流
taskproof verify <task-id>              复跑验收（只更新事实，不动终态）
taskproof accept <task-id>              放行 blocked 卡：验收过→done，否则→failed
taskproof rerun <task-id>               从终态卡起一张新卡，并在账本里双向关联
taskproof advance <task-id>             立刻发车：把一张排队卡单独越过波次推出去
taskproof queue                          常驻守护进程：无人值守连推波次（阻塞）
taskproof cancel <task-id>              停任务（对自己那棵进程树 SIGTERM→SIGKILL）
taskproof rm <task-id>                  删除终态任务的记录、事件与保留的 worktree
taskproof board [--open | --serve PORT | --out FILE]
taskproof api --port N [--allow-write]  本地 REST（stage 2 前端消费）
taskproof doctor                        环境自检
taskproof gc                            归档与轮转
```

`--worktree` 在仓库**同级**目录开一份全新检出
（`<仓库父目录>/<仓库名>-wt-<任务id>`）。跑完干净就删除；若仍留有改动则保留，打印
`worktree kept: ... (N files changed)`，追加一条 `worktree` 事件，之后由
`taskproof rm <任务id>` 删除。

`--park[=N]` 是队列的 CLI 入口：它只写一行 `queued` 记录（`status` 为
`queued`，带一个显式 `queue_seq`）后立刻返回 —— 不占并发槽、不起适配器。
`--park` 不带号是**追尾**：波次 = `max(queue_seq) + 1`；`--park=N` 显式钉在
第 `N` 波。`queue_seq` 相同的卡属于**同一波**，只有所有更低编号的波全部排空，
某一波才推进。运行开关（`--worktree`、`--read-only`、`--no-verify`、
`--timeout`、`--model`、`--reasoning`）存进那张排队行，等它被推进时才生效。
不带 `--park` 的 `run` 保持老的同步行为：立即发车。

**谁推进队列 —— 两条路，各有取舍：**

* `taskproof queue` —— 常驻守护进程，无人值守地把当前波次往前推；同组被拒的卡
  （停在 `queued`、绝不丢弃）下一拍重试。省心，但它会在前一张还没提交时就开始
  下一张，两张卡的 diff 会糊在一起。
* `taskproof advance <id>` —— 人工一张一张地发；这样保住**逐卡提交边界**，下一张
  只在操作者说发时才动。

同一波内，同 group 互斥照旧生效：只跑一张，另一张被拒（exit 75）后**落回
`queued` 不丢**，由守护进程或之后的 `advance` 接着推。

人类可读输出跟随 locale；`--json` 给机器读。

## 前端与节奏

```
stage 1  引擎 + CLI + 本地 REST API + 最简静态看板
         最简看板只为验证数据模型；REST 边界在此定死，stage 2 只替换渲染层
stage 2  Vue 3 + Vite 前端 → Electron 薄壳（不内嵌 Python 运行时）
以后     是否把 Python 运行时嵌进 Electron 包，是纯打包决策，不影响架构
```

采用 Electron 之后仓库变为双语言（Python + TypeScript）；CI、发布流程与
贡献者上手路径都按双产物设计。

### stage 2：桌面应用

静态看板**冻结**：它继续作为 `file://` 快照可用，但不再往下开发。stage 2 在
`desktop/` 里另做一款 Electron 应用，消费同一个回环 REST API。该 API 默认
只读；只有显式加上 `--allow-write`，才会在其上开出一个由「仅本次会话」令牌
保护的写面（项目增 / 改 / 删，以及任务控制：派发 / 立刻发车 / 放行 / 停止 / 删除 / 改序号）。放行两处都写 —— `POST /api/tasks/<id>/accept` 与 `taskproof accept <id>`；`rerun` 刻意只给 CLI（v1 的「再跑一次」是预填表单，不是看板需要拥有的写口）。Python 侧只增加下面这几处小改动，其余全是加法。

**技术选型。** TypeScript、Vue 3（`<script setup>`）、electron-vite
（main / preload / renderer）、Pinia、vue-router（hash 模式 —— 生产走
`file://`）、Element Plus、UnoCSS、vue-i18n、electron-builder。v1 只做开发期
运行，暂不出安装包。

**进程模型。** Electron 持有服务：它拉起 `taskproof api --port 0`，从子进程
stdout 读出实际端口，退出时杀掉子进程。Python 侧的改动就这些 —— 目前 `api`
默认 8787、阻塞且不打印端口，也没有写面：

```
taskproof api --port 0     绑定临时端口，刷出一行实际端口，然后开始服务（只读）
taskproof api --port 0 --allow-write
                           再刷出第二行「仅本次会话」的令牌，并开启令牌保护的注册表写入
```

**矩阵列模型。** 列表示*任务走到了流水线的哪一步*；任务没通过的原因属于卡片
自身的属性，不是一个阶段。所以看板是五列 —— 排队、进行中、验收中、完成、
未通过 —— 最后一列收纳全部异常终态（`failed`、`blocked`、`timeout`、
`cancelled`），各自保留自己的颜色与字形。

从 Python 看板继承下来的硬规矩：**未知状态一律渲染，绝不丢弃。** Python 看板
早已把未知状态折叠进 `failed`，理由相同（"新的生命周期状态绝不能悄悄藏掉一个
任务"）；前端保同等的兜底。

**枚举契约。** 状态词、`verify_kind` 取值、退出码语义在仓库里是同一份产物
（`contract/enums.json`，由 Python 常量生成并签入）。TypeScript 直接 import；
CI 重新生成并 diff，两语言因此不可能漂移。

**组件边界。** 路由页面是容器 —— 取数（轮询 REST）与状态归它们；展示组件
props 进、events 出，不碰 store、不发请求。任务抽屉属于路由的一部分
（`/matrix/:taskId`），因此由该页容器持有，而不是在应用级渲染。

**跨进程边界。** preload 只暴露一组具名 API（`window.tp`：settings /
service / projects / shell），不暴露通用的 `invoke(channel, payload)`。
写注册表走主进程，**本地写令牌永不到达渲染层**；保存前的比对（mtime/hash）
也在主进程完成，用于发现外部编辑。

**设置。** Electron `userData` 下单一 `settings.json`，以主进程为事实源，经
IPC 暴露给渲染层。主进程项（端口、taskproof 路径、工作区、启动、托盘、通知、
Dock 角标、开机自启）与渲染层项（主题、语言）同在一个文件里。

**国际化。** zh-CN + en，跟随系统 locale，兜底 **en**。只翻译界面外壳；任务
全文与小结属于用户数据，永不翻译。

## 仓库与合规

```
雇主资产卫生（硬约束）
  不含内部项目名、内部主机名或 IP、私有仓库的验收命令、凭据片段 —— 示例里也不行。

  扫描器是 tools/scan_assets.py。每个克隆启用一次推送闸门：
      git config core.hooksPath .githooks

  机构专属词库放在仓库**外部**（~/.taskproof/asset-patterns.txt，或
  $TASKPROOF_ASSET_PATTERNS）：一个把词库打包进去的扫描器，泄漏的恰好是它要保护
  的东西。仓库里随附的规则只描述形态，所以扫描永远不会变成空转。

自动化 git 写操作：永不。
```

## stage 1 完成线

```
1  pipx 安装后，在一个干净仓库上跑通：init → register → run → 验收
   → 任务出现在看板上
2  适配器：codex 可用、custom:<cmd> 可用、接口稳定（其余可后续补）
3  SQLite 状态库 + JSONL 审计（按月轮转；JSONL 从不参与逻辑判定）
4  并发守卫用事务实现（不用锁文件），带过期回收
5  验收独立于自述；禁改路径生效；退出码语义对齐
6  最简静态看板 + REST API（列任务、任务详情、事件流）
7  覆盖核心路径的测试（并发守卫 / 验收判定 / 结果解析 / 归档轮转）
8  文档：README（中英）、示例注册表、从零跑通的走查
9  雇主资产扫描：零命中
```

## 未决

```
定位（卖点）—— "先落地再想卖点"
是否内嵌 Python 运行时 —— stage 2 之后按需求定
多用户 / 远程鉴权 —— 暂不在范围内
拆成多个仓库（内核 / 适配器 / 桌面端）—— 以后可以，当前单仓
```

## 附录：调研过的同类项目

```
3.8k  golutra/golutra                      Rust   多 agent 平台，UI 最完整
2.1k  catlog22/Claude-Code-Workflow         TS    JSON 驱动的多 agent 框架
1.4k  awslabs/cli-agent-orchestrator (CAO)  Py    AWS 出品，协调多个编码 CLI
1.3k  bradAGI/awesome-cli-coding-agents     Py    这个方向的索引清单
563   catlog22/maestro-flow                 TS    intent-driven 工作流编排
559   aannoo/hcom                          Rust   agent 互相发消息 / 监视 / 孵化
530   mco-org/mco                           Py    CLI-first 并行交叉验证
516   open-mercato/cezar                    TS    编排器 + ADE，可部署 VPS
419   dsifry/metaswarm                     Shell  18 个人格 + 9 阶段工作流
88    alamops/agetor                        TS    local-first kanban + 每任务独立 worktree
0     anthhub/codex-dispatch               Shell   把任务派给并行 Codex worker
```

命名调研：语义最贴的十个英文词（foreman / steward / warden / attest / gauntlet /
verdict / notary / overseer / proven / proofrun）在 PyPI 上全部已被占用。
`taskproof` 可用，GitHub 同名仓库仅 13 个。
