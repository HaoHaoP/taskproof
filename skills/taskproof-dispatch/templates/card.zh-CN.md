# <卡号> · <一句话说明这张卡做什么>

<!-- 复制本文件（cp <skill 目录>/templates/card.zh-CN.md /tmp/cards/<卡号>.md），逐节填满，删掉注释。
     空着一节是卡的缺陷，不是风格问题：素材那节空着 = 让 worker 猜；硬约束空着 = 邀请它乱逛。
     一张卡守住：一个根因、一段文件范围、一条验收命令。 -->

## 根因
- `path/to/file.py:88` —— 这张卡要闭掉的那一处，写成事实。

## 素材
<!-- 绝对路径 + 行号范围，并明写「自己读」。绝不把操作者的原型/口径/设计稿用自己的话复述。 -->
- 原型：`/absolute/path/to/prototype/viewer.html:1710-1735`
- 设计口径：`/absolute/path/to/design/notes.md` 第 3 节
- 自己读，不要我复述。

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
     发车前它必须在干净树上是绿的，并且它必须真能红。 -->

## 硬约束
- 只改上面点名的文件；不 `git add` / commit / push。
- 不装依赖、不动构建配置。
- <项目特有：不 `npm install`、不碰 `~/.taskproof/` ……>

## 交付
- 改动文件清单。
- 修之前你看到的失败输出。
- 验收命令的真实输出。
- <下一张卡或操作者需要知道的，一条一行>
