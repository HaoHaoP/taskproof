# 项目注册表

注册表是 taskproof 唯一读取的配置文件。它是 TOML，说明*哪些仓库可以被派活、
每个仓库怎么验收*，放在工作区里：

```
~/.taskproof/projects.toml        默认位置；工作区可配置
```

`examples/projects.example.toml` 是一份可直接用的起点。本文是参考手册，那份
文件是导览。

## 两层：项目与任务组

一条登记项是两种东西之一：

* **项目**（`[[project]]`）—— 仓 / 筛选单位：`id`、默认 `path`、`aliases`。
  它本身**不可派活**。
* **任务组**（`[[taskgroup]]`，"道"）—— 一条可以派活的道：`id`、归属
  `project`、`path`（缺省继承项目）、`aliases`、验收命令与结果契约。

项目把「同一个仓里发生过的所有事」的身份聚在一起；任务组是一次运行真正瞄准
的单位。任务组的 `group` 是它的**并发锁名**；缺省等于任务组 `id`，所以一条道
同时只跑一个任务。两条道也可以显式写同一个 `group` 来互相串行，跨项目、跨
注册表条目共享一把锁同样允许。

## 结构

```toml
[defaults]
concurrency = 3      # 同时运行的任务数上限
timeout     = 1800   # 秒；超过则判定卡死并终止

# 仓：一个身份、一个默认路径。
[[project]]
id      = "my-app"
path    = "/absolute/path/to/my-app"
aliases = ["app"]

# 一条道。路径继承自项目。
[[taskgroup]]
id     = "my-app"
project = "my-app"
# group = "my-app"      # 可省略；这就是默认值
verify = "npm run build"
verify_kind = "build"
```

`[defaults]` 可省略；两个键省略时取上面显示的值。

一个项目可以带**多条道** —— 子目录、另一份克隆、与仓共享的文档构建。每条道
有自己的验收命令；写了 `path` 就覆盖项目默认路径：

```toml
[[project]]
id   = "api-service"
path = "/absolute/path/to/api-service"

[[taskgroup]]
id      = "api-service"
project = "api-service"
verify  = "mvn -q -DskipTests compile"

[[taskgroup]]
id      = "api-service-docs"
project = "api-service"
path    = "/absolute/path/to/api-service/site"   # 子目录
verify  = "npm test"
```

## `[[project]]` 字段

| 字段 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `id` | 是 | — | 唯一。重复 id 是硬错误。 |
| `path` | 是 | — | 必须是**绝对路径**。它名下各条道的默认路径。 |
| `aliases` | 否 | `[]` | 别名，凡是能写 id 的地方都能写它。 |
| `group` | 否 | 块 `id` | 仅在兼容道块（同时带任一道字段的 `[[project]]`）上有意义；旧文件里的锁名会原样保留。 |
| `verify` / `verify_kind` / `forbidden_paths` / `result_schema` | 否 | — | 不是项目字段。`[[project]]` 块上只要出现其中任意一个，就触发下面的兼容规则。 |

## `[[taskgroup]]` 字段

| 字段 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `id` | 是 | — | 唯一。命令可以拿它指代一条道；锁名缺省等于它。 |
| `project` | 否 | 任务组 `id` | 归属项目。省略 ⟺ 这条道自成一个同名项目。 |
| `path` | 否 | 项目的 `path` | 必须是**绝对路径**。写了就覆盖项目默认值。 |
| `aliases` | 否 | `[]` | 别名，凡是能写 id 的地方都能写它。 |
| `group` | 否 | 任务组 `id` | 并发锁名。`group` 相同的两条道互相串行；跨项目、跨注册表条目共享一把锁也允许。 |
| `verify` | 否 | — | 验收命令；由 taskproof 在智能体退出**之后**执行。 |
| `verify_kind` | 否 | `"none"` | `check` / `build` / `none`。其它取值是硬错误。 |
| `forbidden_paths` | 否 | `[]` | 前缀匹配的路径，智能体不得触碰。每一项可带 `file:` / `git:` / `presence:` 类型；不带类型即 `file`。 |
| `result_schema` | 否 | `"default"` | `"default"`、`"none"`，或指向 JSON Schema 的绝对路径。 |
| `auto_registered` | 否 | `false` | 由 `taskproof register` 写入，不打算手改。 |

## 读旧格式：零迁移

一个 `[[project]]` 块只要带**任一**道字段 —— `verify`、`verify_kind`、
`forbidden_paths`、`result_schema` —— 就被读成**两条**声明：

* 项目 `id = <块 id>`，`path` / `aliases` 照搬；
* 任务组 `id = <块 id>`、`project = <块 id>`，路径继承，道字段照搬。

于是拆分之前写的注册表**一个字都不用改**就能继续跑：每个原本可派活的块变成
「项目 + 一条同名道」，`taskproof run <旧 id> "…"` 照旧解析。不带任何道字段的
`[[project]]` 块是纯筛选项目（0 条道），在挂上道之前不可派活。

旧的 `group` 键会原样带给隐式生成的那条道；缺失或为空时，这条道的 `group`
等于它的 id。因此两个共享 `group` 的旧块仍然共享一把锁；若要拆成两条独立的
道，给其中任意一条写一个不同的 `group`。

## 分辨率顺序

`by_id` / `require`（因而 `run`、`accept`、`tasks --project` 等）按下面的顺序匹配：

1. **任务组**的 `id`，然后是任务组 `alias`；
2. **项目**的 `id`，然后是项目 `alias` —— 仅当该项目**只有一条道**时才能解析。
   项目有多条道是硬错误，报文会列出候选，因此裸的项目 id 绝不会被静默派错道；
3. 路径：先按道路径精确匹配，再按项目路径。

按工作目录推断（`resolve_scope`）保持旧行为：cwd 落在某条道的路径**或其子目录**
下即匹配，**路径最深**的那条道胜出，因此嵌套的检出的优先级高于父仓库。两条道在
同一深度命中时视为歧义并拒绝，报文点名候选。

## 需要讲清的语义

**道的锁是它的 `group`，缺省等于 id。** 每把锁同时只跑一个任务；不同锁并行，
上限为 `concurrency`。两条道可以刻意共享一个 `group`，适合它们指向同一份检出
或其它共享资源的场景。旧 `[[project]]` 块上的 `group` 也会被保留下来。

**缺 `verify` 记为「跳过」，绝不是「通过」。** 没有验收命令时 `verify_kind`
被强制为 `none`，验收记为 skipped。这是刻意的：*"没检查"* 与 *"检查了且通过"*
在审计流里绝不能长得一样。

**验收命令不等于智能体的自述。** `verify` 在智能体进程退出之后、于道的路径下
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
某个 [[project]] / [[taskgroup]] 项不是表
某个项目缺 id 或 path
某个任务组缺 id
某个任务组引用了不存在的项目
不含 project、又没有 path 的任务组
path 不是绝对路径
项目 id 重复 / 任务组 id 重复
verify_kind 不是 check / build / none 之一
result_schema 既不是 "default"、"none"，也不是绝对路径
result_schema 指定的文件不存在
裸项目 id 对应多条道
```

## 编辑方式

这个文件是配置：你愿意的话，把它提交进你自己的仓库。`taskproof register <path>`
会追加一个 `[[taskgroup]]`，是添加一条道的正规入口；但手改完全可以 —— 每次运行
都会重新读它。

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
| `GET /api/projects` | `{"projects": [ … ]}` —— **一行一条道**（taskgroup）加上它的任务计数；每行另带归属的 `project` id |
| `GET /api/tasks` | `{"tasks": [ … ], "count"}`；过滤 `?status=`、`?project=`、`?limit=` |
| `GET /api/tasks/<id>` | 单个任务详情连同它的事件 |
| `GET /api/tasks/<id>/events` | `{"task_id", "events"}` |
| `GET /api/tasks/<id>/log` | 一段日志窗口（默认尾部，或用 `?offset=` 向前续读） |

## 注册表写入

`projects.toml` 由 CLI 编辑，绝不经过 API。`taskproof config` 调用
`registry.set_default`；`taskproof register` 追加一个新的 `[[taskgroup]]` 块
（用 `--project` 挂到已存在的项目下；不写就自成一个项目）。底层注册表写入函数
（`append_taskgroup` / `update_project` / `delete_project`）在 `expected_hash`
对不上时抛 `RegistryConflictError`，而不是悄悄覆盖手改过的文件。
`update_project` / `delete_project` 对**两种**块都生效。

### 外科式改写

写入按字节进行，绝不把解析后的 TOML 整体重新序列化 —— 那会把
手写注释、以及 `registry.load` 不认识的键全部冲掉。正确做法是：读整个文件
文本，按行定位 `[[project]]` / `[[taskgroup]]` 块边界，只在目标块的范围内按行
改 / 加 / 删键；其它字节一律原样保留。删除块时，紧贴其上、中间没有空行隔开的
注释一起删；被空行隔开的注释留下，这样邻近块的手写说明不会被误删。改完先
用 `tomllib` 回读，再用 `load` 校验，只有通过才原子落盘（同目录临时文件 +
`os.replace`）。解析或校验不过的候选，绝不会碰到真正的文件。

---


<sub>也可读 [English](REGISTRY.md)。</sub>
