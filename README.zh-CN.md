# claude-handoff

[English](./README.md) · **简体中文**

给 Claude Code 用的会话交接工具。context 快满的时候，不用 `/compact` 压缩，而是写一份结构化的交接文件，`/clear` 之后说一句「继续」就能接着干，细节不丢。

```
context 到 60% / 80%  →  自动提醒
        ↓
     /handoff          →  写 HANDOFF.md（并自动存档一份）
        ↓
     /clear            →  清空对话
        ↓
     「继续」           →  新对话自动拿到交接内容，先复述要点，再接着干
                          （说 continue 或任何语言里同样意思的话都行）
```

## 为什么不用 /compact

`/compact` 让模型把整段对话改写成一篇叙述，丢的恰好是最要命的东西：「还没做 / 还没核实」的事、决定背后的理由、哪些路已经证明走不通。作者在同一个会话的同一个位置上做过对照，按事先写好的 33 条清单打分（满分 66）：交接 49 / 48，压缩 39 / 38。

交接文件的做法：
- **结构化**：任务、卡点、别再走的路、决定和理由、状态、改动清单，各有固定位置。
- **原话保留**：你最近 5 条消息逐字复制，不转述。
- **每条可验证**：状态类的声明都附一条能直接跑的验证命令。
- **接手时强制复述**：新对话先逐字复述 5 个要点，再动手（医疗交班协议 I-PASS 的做法）。

## 它由哪几块组成

| 文件 | 装到哪 | 做什么 |
|---|---|---|
| `commands/handoff.md` | `~/.claude/commands/` | `/handoff` 命令本身：交接文件怎么写、写完怎么自查 |
| `commands/handoff_scan.py` | `~/.claude/commands/` | 写交接前，从对话记录里把你的全部消息和所有「没做 / 没核」的句子拉出来，防漏 |
| `hooks/context_usage_reminder.py` | `~/.claude/hooks/` | 每次发消息、每次工具调用后，从对话记录算 context 用量，到 60% / 80% 各提醒一次 |
| `hooks/handoff_after_clear.py` | `~/.claude/hooks/` | `/handoff` 写完时留一个指针并存档；`/clear` 后新对话开始时，把交接的要点自动塞进新对话 |

两个 hook 登记在 `~/.claude/settings.json`。

## 安装

把下面这句话发给 Claude Code：

```
读 https://github.com/neogeweb3/claude-handoff/blob/main/INSTALL.md ，照着帮我装上。
```

它会：拉代码 → 跑测试 → 预演 → 问你两个问题（对话记录保留多久、context 窗口多大）→ 安装 → 自检。装完**新开一个会话**生效。

只支持 macOS / Linux（需要 `python3`）。INSTALL.md 是写给 Claude 看的，用英文写；Claude 会用你的语言跟你说话。

交接文件用你跟 Claude 对话的语言写；你的原话原样保留。Claude 也会用你的语言回话。hook 直接显示在界面上的只有一行（context 用量提醒），默认英文，装的时候加 `--lang zh` 就是中文；你用中文跟 Claude 说话时，安装会自动加上。

## 交接了 200 次，以前的细节还找得到吗

找得到。主文件 HANDOFF.md 只留最近的内容（原话只留 5 条，任务和状态每次重写），老细节在这三个地方：

| 在哪 | 有什么 | 什么时候会没 |
|---|---|---|
| `~/.claude/handoff-history/` | 每一版交接的完整快照，`index.tsv` 是目录 | 不会自动删，只增不减 |
| git 历史 | 交接文件在 git 仓库里时，每次提交的那一版 | 分支没合并就删掉时 |
| `~/.claude/projects/*/*.jsonl` | 原始对话全文，最全 | 默认 30 天后被 Claude Code 删除；安装时可以改成 3650 天 |

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
python3 ~/.claude/hooks/context_usage_reminder.py --probe <对话记录.jsonl>
```

**context 已经快满了怎么办？** 直接说「快满了，先写 handoff」。命令里有应急模式：只写最要紧的几节、提交、留指针，其余全跳过。

## 卸载

1. 从 `~/.claude/settings.json` 的 `hooks` 里删掉命令含 `handoff_after_clear.py` 和 `context_usage_reminder.py` 的条目（安装时备份过：`settings.json.bak-<时间>`）。
2. 删文件：

```bash
rm ~/.claude/commands/handoff.md ~/.claude/commands/handoff_scan.py ~/.claude/hooks/handoff_after_clear.py ~/.claude/hooks/context_usage_reminder.py
```

`~/.claude/handoff-history/` 里是你的交接存档，要不要删你自己定。

## 开发

```bash
python3 tests/test_hooks.py
```

测试都在临时目录里跑，不碰真实的 `~/.claude`。

## 致谢

- 上下文用量提醒借鉴了 [gsd-build/get-shit-done](https://github.com/gsd-build/get-shit-done) 的 `hooks/gsd-context-monitor.js`。
- 原话保留的做法来自 [OpenAI Codex 的 compact.rs](https://github.com/openai/codex/blob/main/codex-rs/core/src/compact.rs)。

## 许可证

MIT
