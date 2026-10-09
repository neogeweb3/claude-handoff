# claude-handoff

[English](./README.md) · **简体中文**

给 Claude Code 用的会话交接工具。context 快满的时候，不用 `/compact` 压缩，而是写一份结构化的交接文件，再从它接着干，细节不丢。

```
context 到 60% / 80%  →  自动提醒
        ↓
     /handoff          →  写 HANDOFF.md、存档一份，然后以交接文件当摘要压缩一次，
                          自动接着干。你什么都不用打。
```

Claude Code 低于 2.1.287 时最后一步要手动：`/clear`，再说一句「继续」（任何语言里同样意思的话都行），新对话会拿到交接内容，先复述要点，再接着干。

## 为什么不用 /compact

`/compact` 让模型把整段对话改写成一篇叙述，丢的恰好是最要命的东西：「还没做 / 还没核实」的事、决定背后的理由、哪些路已经证明走不通。作者在同一个会话的同一个位置上做过对照，按事先写好的 33 条清单打分（满分 66）：交接 49 / 48，压缩 39 / 38。

交接文件的做法：
- **结构化**：任务、卡点、别再走的路、决定和理由、状态、改动清单，各有固定位置。
- **原话保留**：你最近 5 条消息逐字复制，不转述。
- **每条可验证**：状态类的声明都附一条能直接跑的验证命令。
- **接手时强制复述**：新对话先逐字复述 5 个要点，再动手（医疗交班协议 I-PASS 的做法）。

## 它由哪几块组成

一个插件，名字叫 `handoff`：

| 部分 | 做什么 |
|---|---|
| `commands/handoff.md` | `/handoff` 命令：交接文件怎么写、写完怎么自查 |
| `scripts/handoff_scan.py` | 写之前从对话记录里把你说过的话、所有「没做 / 没核实」的句子扒出来，免得漏 |
| `hooks/context_usage_reminder.py` | 每条消息、每次工具调用后，从对话记录算出上下文用量；到 60% 和 80% 各提醒一次 |
| `hooks/handoff_after_clear.py` | 每一版交接都存档；不能原地接续时留一个指针，`/clear` 后把交接要点塞进新对话 |
| `hooks/register.ts` | 原地接续（Claude Code 2.1.287 起）：`/handoff` 写完后压缩一次，摘要换成交接文件全文，再自动发「继续」。你自己的 `/compact` 和自动压缩不受影响 |

## 安装

在终端里跑（桌面 App 也用这个）：

```bash
claude plugin marketplace add neogeweb3/claude-handoff && claude plugin install handoff@claude-handoff
```

或者在 Claude Code 输入框里打：`/plugin install handoff --marketplace neogeweb3/claude-handoff`。

**新开一个对话**后生效。支持 macOS 和 Linux（需要 `python3`）。在 macOS 的 Claude 桌面 App（Code 页）和终端 CLI 上测过。

**打开自动更新**，以后修了什么你不用管：`/plugin` → Marketplaces → claude-handoff → Enable auto-update。第三方 marketplace 默认是关的。不开的话，手动更新：

```bash
claude plugin marketplace update claude-handoff && claude plugin update handoff@claude-handoff
```

**可选设置**，写在 `~/.claude/settings.json` 的 `"env"` 里：
- `"CLAUDE_CONTEXT_WINDOW": "1000000"`：你的模型是 100 万窗口时设上（不设的话第一次提醒可能偏早，之后它会自己学会）。
- `"CLAUDE_HANDOFF_LANG": "zh"`：提醒那一行用中文显示。

想让原始对话记录保留超过 Claude Code 默认的 30 天，在最外层设 `"cleanupPeriodDays": 3650`。

想让 Claude 帮你装？发给它：`Read https://github.com/neogeweb3/claude-handoff/blob/main/INSTALL.md and install it for me.`

交接文件用你跟 Claude 说话的语言写，你自己的原话一字不改。

## 从旧版安装升级

插件出现之前装过（用 `install.py`，或者单独装过 `handoff-compact` 插件）？照上面装插件就行。旧的那几样还登记着的时候，插件里对应的部分会先让开，不会重复触发；每次新开对话会提示一行，说还剩哪些旧的。想彻底换过来，就跑那行提示里给的命令（`python3 "<插件目录>/scripts/migrate.py"`，插件目录是 `claude plugin list --json` 里 `handoff@claude-handoff` 的 `installPath`）。

它先列出会改什么，什么都不动；确认后加 `--apply` 再跑一次才真改。它会备份 `settings.json`，只删本项目的 hook 条目，把旧文件挪进 `~/.claude/handoff-migrated-<时间>/`（你自己写的 `/handoff` 命令不碰），并卸载 `handoff-compact`。存档的交接不动。不换也行，旧的照常能用。

## 你自己加的步骤

每次交接都想多做的事（多记一个地方、你环境里特有的检查），写进 `~/.claude/handoff.local.md`。`/handoff` 会先读它、照着做；跟命令本身冲突时以它为准。它在插件外面，更新永远不会动它。

## 交接了 200 次，以前的细节还找得到吗

找得到。主文件 HANDOFF.md 只留最近的内容（原话只留 5 条，任务和状态每次重写），老细节在这三个地方：

| 在哪 | 有什么 | 什么时候会没 |
|---|---|---|
| `~/.claude/handoff-history/` | 每一版交接的完整快照，`index.tsv` 是目录 | 不会自动删，只增不减 |
| git 历史 | 交接文件在 git 仓库里时，每次提交的那一版 | 分支没合并就删掉时 |
| `~/.claude/projects/*/*.jsonl` | 原始对话全文，最全 | 默认 30 天后被 Claude Code 删除；用 `cleanupPeriodDays` 调长（见「安装」） |

想查以前的事，直接问 Claude「之前那次 X 是怎么定的」，`/handoff` 命令里写了按什么顺序查。自己查：

```bash
grep -rn "关键词" ~/.claude/handoff-history/
```

```bash
column -t -s $'\t' ~/.claude/handoff-history/index.tsv | tail -20
```

## 常见问题

**桌面 App 里打 `/clear` 没接上？** 桌面 App 发给 hook 的事件是 `startup` 而不是 `clear`，hook 两种都认。还是没接上就看 `~/.claude/handoff-pointers/hook.log`。指针 24 小时后失效，只能用一次，按目录区分，不会串到别的项目。

**提醒来得太早 / 一直不来？** 提醒 hook 不知道你的窗口多大：默认按 20 万算，某个模型的用量一旦超过 20 万就自动改按 100 万算并记住。想直接指定，在 `~/.claude/settings.json` 里加：

```json
{ "env": { "CLAUDE_CONTEXT_WINDOW": "1000000" } }
```

看当前用量：

```bash
python3 "<插件目录>/hooks/context_usage_reminder.py" --probe <对话记录.jsonl>
```

（插件目录：`claude plugin list --json` 里 `handoff@claude-handoff` 的 `installPath`）

**`/handoff` 跑的不是插件里那个？** 你自己在 `~/.claude/commands/handoff.md` 放了命令文件时，它优先，插件的命令就变成 `/handoff:handoff`。Claude Code 低于 2.1.287 时，插件的命令一律要写成 `/handoff:handoff`。

**context 已经快满了怎么办？** 直接说「快满了，先写 handoff」。命令里有应急模式：只写最要紧的几节、提交、留指针，其余全跳过。

## 卸载

```bash
claude plugin uninstall handoff@claude-handoff
```

`~/.claude/handoff-history/` 里是存档的交接，删不删你定。

## 开发

```bash
python3 tests/test_hooks.py
```

```bash
claude plugin validate . && claude plugin test .
```

测试都在临时目录里跑，不碰真实的 `~/.claude`。每次发版都要改 `.claude-plugin/plugin.json` 里的 `version`：版本号不变，已经装了的人不会更新。

## 致谢

- 上下文用量提醒借鉴了 [gsd-build/get-shit-done](https://github.com/gsd-build/get-shit-done) 的 `hooks/gsd-context-monitor.js`。
- 原话保留的做法来自 [OpenAI Codex 的 compact.rs](https://github.com/openai/codex/blob/main/codex-rs/core/src/compact.rs)。

## 许可证

MIT
