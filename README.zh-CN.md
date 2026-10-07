# taskproof

给 AI 编码 agent 用的传送带。

它不决定**该做什么**，只保证派出去的活都被**独立验收**过、**留了痕迹** ——
你不需要相信 agent 自称"我干完了"。

**状态：stage 1 已可用。** 引擎、CLI、静态看板与本地只读 REST API 均已实现。
完整设计与决策记录见 [`docs/DESIGN.zh-CN.md`](docs/DESIGN.zh-CN.md)。

### 快速上手

```bash
pipx install taskproof        # 或从源码安装：pip install -e .
taskproof init
taskproof register /path/to/your/repo
taskproof run your-repo "修掉那个挂掉的测试"
taskproof board --open
```

---

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
taskproof board                  # 看板
```

- Python，纯标准库，`pipx install` 可装
- SQLite 存状态（事务认领，不用锁文件）
- JSONL 审计流水，只写不查，按月轮转
- 可插拔适配器（codex / claude / gemini / opencode + 任意命令）

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
