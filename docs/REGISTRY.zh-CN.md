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
| `forbidden_paths` | 否 | `[]` | 前缀匹配的路径，智能体不得触碰。 |
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

**保护路径在运行之后检查，而且不只靠 git。** 以 `/` 结尾的规则覆盖该目录及其下
所有内容；不带斜杠的规则只匹配那一个确切路径。命中即判定任务失败，即便智能体自称
成功。

这个检查刻意不只依赖 `git status` 的变更列表。git 不会报告 `.git/` 里的任何东西，
而且会漏掉全部被忽略的路径 —— 而构建产物与依赖目录恰好就是被忽略的那些。这是实测
的：`forbidden_paths = ["dist/"]` 且 `dist/` 写在 `.gitignore` 里时，一个适配器写了
`dist/app.js`，任务却被记为 `done`。所以声明的路径还会在运行前后各取一次指纹，从而
覆盖 `.git/`、被忽略的路径以及其它一切。一个需要知道的边界：受保护目录超过 20000 个
条目时只做抽样，此时审计事件里会记 `snapshot_truncated: true`。

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

---

<sub>也可读 [English](REGISTRY.md)。</sub>
