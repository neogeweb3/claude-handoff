# claude-handoff

**English** · [简体中文](./README.zh-CN.md)

Session handoffs for Claude Code. When the context window is filling up, don't `/compact`. Write a structured handoff instead and carry on from it, details intact.

```
context hits 60% / 80%  →  automatic reminder
        ↓
     /handoff           →  writes HANDOFF.md, archives a copy, then compacts once with the
                           handoff as the summary and carries on by itself. You type nothing.
```

On Claude Code older than 2.1.287 the last part is manual: `/clear`, then say "continue" (or the same word in any language), and the new conversation receives the handoff, restates the key points and carries on.

## Why not /compact

`/compact` has the model rewrite the whole conversation as a narrative, and the rewrite loses exactly what hurts most: what is still not done or not verified, the reasons behind decisions, and which approaches were already proven not to work. The author ran both on the same session cut at the same point and scored them against a 33-item checklist written in advance (max 66): handoff 49 / 48, compact 39 / 38.

What the handoff does instead:
- **Structured**: task, blockers, dead ends, decisions and their reasons, state, files changed, each in a fixed place.
- **Verbatim**: your last 5 messages are copied word for word, never paraphrased.
- **Verifiable**: every state claim comes with a command that checks it.
- **Read-back on resume**: the new conversation restates 5 key points word for word before touching anything (the I-PASS clinical handoff protocol).

## What's inside

One plugin, `handoff`:

| Part | What it does |
|---|---|
| `commands/handoff.md` | The `/handoff` command: how to write the handoff and how to check it |
| `scripts/handoff_scan.py` | Before writing, pulls all your messages and every "not done / not verified" sentence out of the transcript so nothing slips |
| `hooks/context_usage_reminder.py` | After each message and tool call, computes context usage from the transcript; reminds once at 60% and once at 80% |
| `hooks/handoff_after_clear.py` | Archives every handoff; without in-place resume, leaves a pointer so the next conversation gets the handoff's key points after `/clear` |
| `hooks/register.ts` | The in-place resume (Claude Code 2.1.287+): after `/handoff`, compacts once with the handoff file's full text in place of the usual summary, then sends "continue". Your own `/compact` and auto-compaction are untouched |

## Install

From a shell (works for the desktop app too):

```bash
claude plugin marketplace add neogeweb3/claude-handoff && claude plugin install handoff@claude-handoff
```

Or at the Claude Code prompt: `/plugin install handoff --marketplace neogeweb3/claude-handoff`.

It takes effect in a **new session**. macOS and Linux (needs `python3`). Tested on macOS in the Claude desktop app (Code tab) and the terminal CLI.

**Turn on auto-update** so fixes reach you without doing anything: `/plugin` → Marketplaces → claude-handoff → Enable auto-update. Third-party marketplaces have it off by default. Without it, update by hand:

```bash
claude plugin marketplace update claude-handoff && claude plugin update handoff@claude-handoff
```

**Optional settings**, under `"env"` in `~/.claude/settings.json`:
- `"CLAUDE_CONTEXT_WINDOW": "1000000"` if your model has a 1M window (otherwise the first reminder may come early; it learns after that).
- `"CLAUDE_HANDOFF_LANG": "zh"` to show the reminder line in Chinese.

And to keep raw transcripts longer than Claude Code's default 30 days, set `"cleanupPeriodDays": 3650` at the top level.

Prefer Claude to do it? Send it: `Read https://github.com/neogeweb3/claude-handoff/blob/main/INSTALL.md and install it for me.`

The handoff is written in the language you use with Claude; your own messages are kept exactly as you wrote them.

## Upgrading from the old install

Installed before the plugin existed (with `install.py`, or the separate `handoff-compact` plugin)? Install the plugin as above; if you had added this marketplace before, refresh it first (`claude plugin marketplace update claude-handoff`), or the install says the plugin is not found. While the old copies are still registered, the plugin's matching parts stay silent, so nothing runs twice, and each new conversation shows one line saying what is left. To switch fully, run the command that line shows (`python3 "<plugin folder>/scripts/migrate.py"`; the plugin folder is the `installPath` of `handoff@claude-handoff` in `claude plugin list --json`).

It lists what it would change and changes nothing; run it again with `--apply` to do it. It backs up `settings.json`, removes only this project's hook entries, moves the old files to `~/.claude/handoff-migrated-<time>/` (a `/handoff` command of your own is left alone), and uninstalls `handoff-compact`. Your archived handoffs are not touched. Not switching is fine too: the old install keeps working.

## Your own additions

Put extra steps you want on every handoff (another place to record it, a check specific to your setup) in `~/.claude/handoff.local.md`. `/handoff` reads it first and follows it; it wins where it conflicts. It lives outside the plugin, so updates never touch it.

## After 200 handoffs, can I still find old details?

Yes. HANDOFF.md itself only keeps recent content (5 verbatim messages; task and state are rewritten each time). Older details live in three places:

| Where | What | When it disappears |
|---|---|---|
| `~/.claude/handoff-history/` | A full snapshot of every handoff; `index.tsv` is the table of contents | Never deleted automatically; append-only |
| git history | Every committed version, when the handoff lives in a git repo | When a branch is deleted without being merged |
| `~/.claude/projects/*/*.jsonl` | Raw transcripts, the most complete record | Claude Code deletes them after 30 days by default; raise it with `cleanupPeriodDays` (see Install) |

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
python3 "<plugin folder>/hooks/context_usage_reminder.py" --probe <transcript.jsonl>
```

(the plugin folder: `installPath` of `handoff@claude-handoff` in `claude plugin list --json`)

**`/handoff` runs something else.** A command file of your own at `~/.claude/commands/handoff.md` takes priority over the plugin's; the plugin's is then `/handoff:handoff`. On Claude Code older than 2.1.287 the plugin's command is always `/handoff:handoff`.

**Context is already almost full.** Say "context is almost full, write the handoff now". The command has an emergency mode: write the most important sections, commit, leave the pointer, skip everything else.

## Uninstall

```bash
claude plugin uninstall handoff@claude-handoff
```

`~/.claude/handoff-history/` holds your archived handoffs; delete it or keep it, your call.

## Development

```bash
python3 tests/test_hooks.py
```

```bash
claude plugin validate . && claude plugin test .
```

Tests run in a temporary directory and never touch the real `~/.claude`. Every release bumps `version` in `.claude-plugin/plugin.json`: installed copies only update when it changes.

## Credits

- The context usage reminder borrows from `hooks/gsd-context-monitor.js` in [gsd-build/get-shit-done](https://github.com/gsd-build/get-shit-done).
- Keeping recent user messages verbatim comes from [OpenAI Codex's compact.rs](https://github.com/openai/codex/blob/main/codex-rs/core/src/compact.rs).

## License

MIT
