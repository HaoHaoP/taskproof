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
语言      Python 单包，纯标准库（sqlite3 / subprocess / json / http.server / argparse）
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

**配置与状态分离**：项目注册表是 YAML 文件（人可编辑，可放进用户自己的 git 仓库）。
只有运行时状态进 SQLite。

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
越限行为      立即退出（不排队），何时重试由调用方决定
进程安全      只杀 taskproof 自己起的进程
```

## 退出码

```
0    成功
2-3  注册表问题
64   用法错误
70   适配器（agent）失败
71   验收或产物自检失败
75   并发受限
```

## CLI 表面

```
taskproof init                          初始化工作区（建库、写示例注册表）
taskproof register <path> [--dry-run]   探测仓库并登记
taskproof projects                      列已登记项目
taskproof run <project|path> "<brief>"  派活（主命令）
          [--adapter X] [--model X] [--reasoning X]
          [--read-only] [--worktree] [--no-verify] [--verify-only]
taskproof tasks [--status S] [--project P] [--limit N]
taskproof show <task-id>                单任务详情
taskproof log <task-id>                 事件流
taskproof verify <task-id>              复跑验收
taskproof board [--open | --serve PORT | --out FILE]
taskproof api --port N                  本地 REST（stage 2 前端消费）
taskproof doctor                        环境自检
taskproof gc                            归档与轮转
```

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

## 仓库与合规

```
雇主资产卫生（硬约束）
  不含内部项目名、内部主机名或 IP、私有仓库的验收命令、凭据片段 —— 示例里也不行。
  每次推送前跑一遍关键词扫描。

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
看板视觉设计 —— stage 2
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
