# claude-handoff

**English** · [简体中文](./README.zh-CN.md)

Session handoffs for Claude Code. When the context window is filling up, don't `/compact`. Write a structured handoff instead, `/clear`, say "continue", and pick up exactly where you left off, details intact.

```
context hits 60% / 80%  →  automatic reminder
        ↓
     /handoff           →  writes HANDOFF.md (and archives a copy)
        ↓
     /clear             →  empty conversation
        ↓
     "continue"         →  the new conversation receives the handoff, restates the key points, carries on
                           ("继续" or the same word in any language works too)
```

## Why not /compact

`/compact` has the model rewrite the whole conversation as a narrative, and the rewrite loses exactly what hurts most: what is still not done or not verified, the reasons behind decisions, and which approaches were already proven not to work. The author ran both on the same session cut at the same point and scored them against a 33-item checklist written in advance (max 66): handoff 49 / 48, compact 39 / 38.

What the handoff does instead:
- **Structured**: task, blockers, dead ends, decisions and their reasons, state, files changed, each in a fixed place.
- **Verbatim**: your last 5 messages are copied word for word, never paraphrased.
- **Verifiable**: every state claim comes with a command that checks it.
- **Read-back on resume**: the new conversation restates 5 key points word for word before touching anything (the I-PASS clinical handoff protocol).

## What's inside

| File | Installed to | What it does |
|---|---|---|
| `commands/handoff.md` | `~/.claude/commands/` | The `/handoff` command: how to write the handoff and how to check it |
| `commands/handoff_scan.py` | `~/.claude/commands/` | Before writing, pulls all your messages and every "not done / not verified" sentence out of the transcript so nothing slips |
| `hooks/context_usage_reminder.py` | `~/.claude/hooks/` | After each message and tool call, computes context usage from the transcript; reminds once at 60% and once at 80% |
| `hooks/handoff_after_clear.py` | `~/.claude/hooks/` | When `/handoff` finishes, leaves a pointer and archives the handoff; after `/clear`, injects the handoff's key points into the new conversation |

Both hooks are registered in `~/.claude/settings.json`.

## Install

Send this to Claude Code:

```
Read https://github.com/neogeweb3/claude-handoff/blob/main/INSTALL.md and install it for me.
```

It will clone the repo, run the tests, do a dry run, ask you two questions (how long to keep transcripts, how big your context window is), install, and verify. The hooks take effect in a **new session**.

macOS and Linux only (needs `python3`). INSTALL.md is written for Claude, in English; Claude will talk to you in your own language.

The handoff is written in the language you use with Claude; your own messages are kept exactly as you wrote them. Claude replies in your language too. The one line the hooks show directly in the UI (the context reminder) is in English, or in Chinese if you install with `--lang zh`; the installer picks that automatically when you talk to Claude in Chinese.

## After 200 handoffs, can I still find old details?

Yes. HANDOFF.md itself only keeps recent content (5 verbatim messages; task and state are rewritten each time). Older details live in three places:

| Where | What | When it disappears |
|---|---|---|
| `~/.claude/handoff-history/` | A full snapshot of every handoff; `index.tsv` is the table of contents | Never deleted automatically; append-only |
| git history | Every committed version, when the handoff lives in a git repo | When a branch is deleted without being merged |
| `~/.claude/projects/*/*.jsonl` | Raw transcripts, the most complete record | Claude Code deletes them after 30 days by default; the installer offers to raise this to 3650 days |

To look something up, just ask Claude "how did we decide X back then"; `/handoff` tells it where to search and in what order. By hand:

```bash
grep -rn "keyword" ~/.claude/handoff-history/
```

```bash
column -t -s $'\t' ~/.claude/handoff-history/index.tsv | tail -20
```

## FAQ

**I typed `/clear` in the desktop app and it didn't pick up.** The desktop app reports `startup` to the hook instead of `clear`; the hook accepts both. If it still didn't pick up, check `~/.claude/handoff-pointers/hook.log`. Pointers expire after 24 hours, are used once, and are keyed by directory, so they never leak into another project.

**The reminder comes too early / never comes.** The hook can't see your window size. It assumes 200k, and once a model's usage passes 200k it switches that model to 1M and remembers. To set it explicitly, add this to `~/.claude/settings.json`:

```json
{ "env": { "CLAUDE_CONTEXT_WINDOW": "1000000" } }
```

Check current usage:

```bash
python3 ~/.claude/hooks/context_usage_reminder.py --probe <transcript.jsonl>
```

**Context is already almost full.** Say "context is almost full, write the handoff now". The command has an emergency mode: write the most important sections, commit, leave the pointer, skip everything else.

## Uninstall

1. Remove the entries whose command contains `handoff_after_clear.py` or `context_usage_reminder.py` from `hooks` in `~/.claude/settings.json` (the installer left a backup: `settings.json.bak-<timestamp>`).
2. Delete the files:

```bash
rm ~/.claude/commands/handoff.md ~/.claude/commands/handoff_scan.py ~/.claude/hooks/handoff_after_clear.py ~/.claude/hooks/context_usage_reminder.py
```

`~/.claude/handoff-history/` holds your archived handoffs; delete it or keep it, your call.

## Development

```bash
python3 tests/test_hooks.py
```

Tests run in a temporary directory and never touch the real `~/.claude`.

## Credits

- The context usage reminder borrows from `hooks/gsd-context-monitor.js` in [gsd-build/get-shit-done](https://github.com/gsd-build/get-shit-done).
- Keeping recent user messages verbatim comes from [OpenAI Codex's compact.rs](https://github.com/openai/codex/blob/main/codex-rs/core/src/compact.rs).

## License

MIT
