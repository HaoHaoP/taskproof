# <卡号> · <一句话说明这张卡做什么>

<!-- 复制本文件（cp <skill 目录>/templates/card.zh-CN.md /tmp/cards/<卡号>.md），逐节填满，删掉注释。
     空着一节是卡的缺陷，不是风格问题：素材那节空着 = 让 worker 猜；硬约束空着 = 邀请它乱逛。
     一张卡守住：一个根因、一段文件范围、一条验收命令。
     结果要人用眼睛看的卡是「观感卡」—— 见 ../references/visual-cards.zh-CN.md：
     填 region + **一个**参照物头 + 状态真值表 + 红绿探针，没有合格参照物不许发车。
     不是观感卡的卡，这些头一个都不写。 -->

region:   <区域 slug，如 header-buttons；参照物是不可变来源时可省；none = 不纳管收敛预算>
口径:     <参照物是 store（会变、你欠它一次回写）：/绝对路径.md#锚点>
参照物:   <参照物是不可变来源：/绝对路径/原型.html:1028-1066，或 screenshot:/绝对路径/截图.png>
<!-- `口径:` 与 `参照物:` 二选一，只填一个，另一个删掉。 -->

## 根因
- `path/to/file.py:88` —— 这张卡要闭掉的那一处，写成事实。
- <!-- 观感卡：根因是「当前渲染 vs 参照物」的差值。操作者的原话进 store，绝不进卡。 -->

## 素材
<!-- 绝对路径 + 行号范围，并明写「自己读」。绝不把操作者的原型/口径/设计稿用自己的话复述。 -->
- 原型：`/absolute/path/to/prototype/viewer.html:1710-1735`
- 设计口径：`/absolute/path/to/design/notes.md` 第 3 节
- 自己读，不要我复述。
- <!-- 观感卡，只许一个：--> 参照物：`…`（原型行号 | 既有实现行号 | 已圈定的对拍页 | 圈过的截图+量出的取值）

## 状态真值表
<!-- 观感卡必填；否则写「不适用」。
     行 = 所有可能出现的状态（页签 × 编辑/查看 × 选中/未选 × 有数据/无数据）；
     列 = 元素；格 = 有/无/位置 + 决定它的那处 file:line。
     空格就是没定过的状态，一定作为返工回来。 -->

| 状态 | 元素A | 元素B | 元素C |
|---|---|---|---|
| | | | |

## 红绿探针
<!-- 观感卡必填。一条断言、真浏览器、修之前必须红、修完绿。
     量的是数不是观感：元素数、getComputedStyle 取值、offsetWidth、elementFromPoint、
     类名、aria-expanded、location.hash。 -->
- 修之前必须红：`<命令/探针>`
- 人工目视（搬不到机器那侧的）：<一行，诚实写>

## 要做的事
- 只改 `path/to/file.py` 与 `tests/test_....py`，闭掉上面那个根因，别的都不动。

## 测试
<!-- 改行为 / 修 bug：每个根因一条测试，并在下面的验收命令里点名。
     不改行为：写明，标注这是只写测试的卡，并把「不许改任何生产文件」写成硬约束。 -->
- 新增测试：`tests.test_cli.TestDispatch.test_refuses_full_cap`

## 验收
```bash
cd /absolute/path/to/repo && python -m unittest tests.test_cli.TestDispatch.test_refuses_full_cap -v && python -m unittest discover -s tests
```
<!-- 一条命令；exit 0 即卡里的要求都满足。与注册表里的 verify 逐字一致。
     发车前它必须在干净树上是绿的，并且它必须真能红。
     必须落盘的卡再加一条「真落盘」检查，挡住「什么都没改、verify 却绿」：
     git diff --quiet -- <file> && exit 1 -->

## 硬约束
- 只改上面点名的文件；不 `git add` / commit / push。
- 不装依赖、不动构建配置。
- <项目特有：不 `npm install`、不碰 `~/.taskproof/` ……>

## 交付
- 改动文件清单。
- 修之前你看到的失败输出。
- 验收命令的真实输出。
- <!-- 观感卡：--> 每一处配色/尺寸，给出它来自参照物的哪一行。
- <下一张卡或操作者需要知道的，一条一行>
