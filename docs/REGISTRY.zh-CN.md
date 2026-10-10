# 项目注册表

注册表是 taskproof 唯一读取的配置文件。它是 TOML，说明*哪些仓库可以被派活、
每个仓库怎么验收*，放在工作区里：

```
~/.taskproof/projects.toml        默认位置；工作区可配置
```

`examples/projects.example.toml` 是一份可直接用的起点。本文是参考手册，那份
文件是导览。

## 结构

```toml
[defaults]
concurrency = 3      # 同时运行的任务数上限
timeout     = 1800   # 秒；超过则判定卡死并终止

[[project]]
id   = "my-app"
path = "/absolute/path/to/my-app"
group = "my-app"
verify = "npm run build"
verify_kind = "build"
```

`[defaults]` 可省略；两个键省略时取上面显示的值。

## 项目字段

| 字段 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `id` | 是 | — | 唯一。所有命令都靠它指代项目。重复 id 是硬错误。 |
| `path` | 是 | — | 必须是**绝对路径**。 |
| `group` | 否 | `"default"` | 并发组。见下。 |
| `aliases` | 否 | `[]` | 别名，凡是能写 id 的地方都能写它。 |
| `verify` | 否 | — | 验收命令；由 taskproof 在智能体退出**之后**执行。 |
| `verify_kind` | 否 | `"none"` | `check` / `build` / `none`。其它取值是硬错误。 |
| `forbidden_paths` | 否 | `[]` | 前缀匹配的路径，智能体不得触碰。每一项可带 `file:` / `git:` / `presence:` 类型；不带类型即 `file`。 |
| `result_schema` | 否 | `"default"` | `"default"`、`"none"`，或指向 JSON Schema 的绝对路径。 |
| `auto_registered` | 否 | `false` | 由 `taskproof register` 写入，不打算手改。 |

## 需要讲清的语义

**`group` 是串行键，不是标签。** 同一组同时只跑一个任务；不同组并行，上限为
`concurrency`。不写 `group` 的项目落进 `default`，于是*所有*省略它的项目共用
一条道、全部串行。两个仓库可以同时构建就给不同组；不能同时构建（共享构建产物、
同一个 monorepo、同一台设备）就给同一组。

**缺 `verify` 记为「跳过」，绝不是「通过」。** 没有验收命令时 `verify_kind`
被强制为 `none`，验收记为 skipped。这是刻意的：*"没检查"* 与 *"检查了且通过"*
在审计流里绝不能长得一样。

**验收命令不等于智能体的自述。** `verify` 在智能体进程退出之后、于项目路径下
执行。"我干完了"从来不算证据。

**自定义 schema 文件不存在是硬错误。** `result_schema` 指向一个不存在的路径会
直接终止，而不是静默退回默认值 —— 静默退回会在你背后改变结果契约。

**保护路径按「运行前 / 运行后」的差分判定，每条规则各自选信号。** 以 `/` 结尾的
规则覆盖该目录及其下所有内容；不带斜杠的规则只匹配那一个确切路径。命中即判定任务
失败，即便智能体自称成功。

闸门在适配器启动前取一次快照、退出后再取一次，只有**两次之间的差异**才算数。跑前
就已经是脏的、或本来就未跟踪的路径（Finder 生成的 `.DS_Store`、遗留的构建产物、
人手动留下的目录）在两次快照里都在，绝不会被算到适配器头上。错误载荷里的 `kind`
标明是哪一路信号命中。

**语法。** 一条规则要么是裸路径（老写法），要么是 `<类型>:<路径>`。支持的类型：

| 类型 | 含义 | 触发条件 |
|---|---|---|
| `file`（默认） | 指纹 + git 差分 | 该规则下有路径新增、删除或内容改动 —— 历史行为，逐字不变 |
| `git` | 仓库状态（HEAD / refs / stash） | 提交、改写历史、切换分支、打标签、stash |
| `presence` | 只比文件集合 | 该规则下有文件新增或删除 |

```toml
forbidden_paths = [
  ".git/",             # 不带类型：保留历史上的 git-state 含义
  "protected/",        # 不带类型：历史上的文件指纹信号
  "file:protected/",   # 上一行的显式写法
  "git:.git/",         # .git 那一行的显式写法
  "presence:web/dist/",# devServer / HMR 产物：内容被改写不再报警
]
```

不带类型的规则与上一版**逐字兼容**：行为与 `file:` 完全一致（且不带类型的 `.git/`
规则仍保留 git-state 含义，见下）。因为前缀用冒号，若要保护一个本身以
`file:`/`git:`/`presence:` 开头的字面路径，就再套一层显式前缀，例如
`file:presence:notes.txt`。

**怎么选信号。** `presence:` 是给「会被后台进程写入、跟智能体无关」的目录用的 ——
Vite/Webpack 的 HMR 会重写 `dist/**`、`node_modules/.cache/**` —— 也适合「只禁止
智能体在这个目录里增删文件」的场景。它的取舍：对一个**已存在**文件的纯内容改写
**不算违规**。若还要抓内容改动，那条路径就用默认的 `file:` 信号。

默认的 `file` 信号刻意不只依赖 `git status` 的变更列表。git 不会报告 `.git/` 里的
任何东西，而且会漏掉全部被忽略的路径 —— 而构建产物与依赖目录恰好就是被忽略的那些。
这是实测的：`forbidden_paths = ["dist/"]` 且 `dist/` 写在 `.gitignore` 里时，一个适配
器写了 `dist/app.js`，任务却被记为 `done`。所以声明的 `file` 路径还会在运行前后各取
一次指纹，从而覆盖被忽略的路径以及其它一切；git 差分与指纹差分取「或」。

若规则指向仓库的 `.git` 目录，则特殊处理：比较 HEAD、refs 与 stash 状态，而不是
git 的记账文件；因此只读的 `git status` 刷新 index 不算违规，而提交、reset、
切换/建立分支、打标签和 stash 仍会被抓住 —— 探针读的是 HEAD、符号分支、
`refs/heads`、`refs/remotes`、`refs/tags` 的每一项，以及 stash 列表。一个需要知道的
边界：受保护目录超过 20000 个条目时只做抽样，此时审计事件里会记
`snapshot_truncated: true`。

## 硬错误

以下情况终止运行，退出码 2：

```
注册表文件不存在
TOML 非法
[defaults] 不是表
某个 [[project]] 项不是表
某个项目缺 id 或 path
path 不是绝对路径
项目 id 重复
verify_kind 不是 check / build / none 之一
result_schema 既不是 "default"、"none"，也不是绝对路径
result_schema 指定的文件不存在
```

## 编辑方式

这个文件是配置：你愿意的话，把它提交进你自己的仓库。`taskproof register <path>`
会追加一条，是添加项目的正规入口；但手改完全可以 —— 每次运行都会重新读它。

运行期状态从不落在这里。任务、事件与判定在 SQLite 存储里；审计流是 JSONL。

## REST 表面

本地 API 是**只读**的。所有写操作都留在 CLI 里（`taskproof register`、
`taskproof config`、`run`、`accept`、`cancel`、`rm`）；服务端不暴露任何写
端点，也不生成会话令牌。打到旧写路径的写请求就是一个平白的 `404`。

前端读取的端点：

| 端点 | 返回 |
|---|---|
| `GET /api/health` | `{"ok", "version", "concurrency"}` |
| `GET /api/summary` | `{"summary", "concurrency"}` |
| `GET /api/registry` | `{"path", "hash", "mtime"}`；`hash` 是原始字节的 sha256（十六进制小写） |
| `GET /api/projects` | `{"projects": [ … ]}` —— 每条是注册表项目加上它的任务计数 |
| `GET /api/tasks` | `{"tasks": [ … ], "count"}`；过滤 `?status=`、`?project=`、`?limit=` |
| `GET /api/tasks/<id>` | 单个任务详情连同它的事件 |
| `GET /api/tasks/<id>/events` | `{"task_id", "events"}` |
| `GET /api/tasks/<id>/log` | 一段日志窗口（默认尾部，或用 `?offset=` 向前续读） |

## 注册表写入

`projects.toml` 由 CLI 编辑，绝不经过 API。`taskproof config` 调用
`registry.set_default`；`taskproof register` 追加一个块。底层注册表写入函数
（`append_project` / `update_project` / `delete_project`）在 `expected_hash`
对不上时抛 `RegistryConflictError`，而不是悄悄覆盖手改过的文件。

### 外科式改写

写入按字节进行，绝不把解析后的 TOML 整体重新序列化 —— 那会把
手写注释、以及 `registry.load` 不认识的键全部冲掉。正确做法是：读整个文件
文本，按行定位 `[[project]]` 块边界，只在目标块的范围内按行改 / 加 / 删键；
其它字节一律原样保留。删除块时，紧贴其上、中间没有空行隔开的注释一起删；
被空行隔开的注释留下，这样邻近项目的手写说明不会被误删。改完先
用 `tomllib` 回读，再用 `load` 校验，只有通过才原子落盘（同目录临时文件 +
`os.replace`）。解析或校验不过的候选，绝不会碰到真正的文件。

---


<sub>也可读 [English](REGISTRY.md)。</sub>
