# INSTALL: steps for Claude Code

> The user handed you (Claude Code) this file. Follow the steps below and report each result to the user in one sentence, **in the language the user is speaking to you**.
> Stop and ask only where a step says **Ask the user**; do everything else directly.

## 0. Prerequisites

```bash
python3 --version && git --version
```

Both must be present. If python3 is missing, tell the user (macOS: `xcode-select --install`) and stop.

## 1. Get the code

```bash
git clone https://github.com/neogeweb3/claude-handoff.git ~/.claude/claude-handoff 2>/dev/null \
  || git -C ~/.claude/claude-handoff pull --ff-only
```

## 2. Run the tests (they run in a temporary directory and do not touch the user's ~/.claude)

```bash
python3 ~/.claude/claude-handoff/tests/test_hooks.py
```

The last line must be `OK`. If not, show the user the failing output and stop.

## 3. Dry run

```bash
python3 ~/.claude/claude-handoff/install.py --dry-run
```

- If it says `~/.claude/commands/handoff.md already exists and was not installed by this project`: **Ask the user** whether to replace it (the original will be backed up). If yes, add `--force` in step 5; if no, stop.
- Tell the user in one sentence which hooks will be registered: "Three hooks go into settings.json: one picks up the handoff when a new conversation starts, the other checks context usage after each message and each tool call."

## 4. Ask the user two things (in one message)

1. **How long should transcripts be kept?** By default Claude Code deletes local transcripts (plain-text .jsonl files under `~/.claude/projects/`) after 30 days. A handoff keeps only a summary and the last 5 messages verbatim; the full details live in the transcripts. Recommend 3650 days (about 10 years); the cost is disk space and plain-text transcripts staying on the machine longer.
   - Yes → add `--cleanup-days 3650` in step 5
   - (Sessions started in the desktop app are exempt from the 30-day limit by default; only CLI sessions are affected.)
2. **Is the context window 200k or 1M?** Ask the user to run `/context` in any session and read the total.
   - 1M → add `--window 1000000` in step 5
   - 200k or unsure → add nothing. The reminder hook assumes 200k and switches a model to 1M automatically once its usage passes 200k.

## 5. Install

If the user is talking to you in Chinese, also add `--lang zh` (the context reminder line in the UI will then be in Chinese). Do not ask; decide from the language the user is using.

```bash
python3 ~/.claude/claude-handoff/install.py [--force] [--cleanup-days 3650] [--window 1000000] [--lang zh]
```

## 6. Verify

```bash
ls ~/.claude/commands/handoff.md ~/.claude/commands/handoff_scan.py \
   ~/.claude/hooks/handoff_after_clear.py ~/.claude/hooks/context_usage_reminder.py
python3 -c "import json,os;h=json.load(open(os.path.expanduser('~/.claude/settings.json')))['hooks'];print({k:sum('handoff_after_clear' in x.get('command','') or 'context_usage_reminder' in x.get('command','') for g in v for x in g.get('hooks',[])) for k,v in h.items()})"
```

The second command must print 1 each for `SessionStart`, `UserPromptSubmit` and `PostToolUse`.

## 7. Tell the user

Tell the user the following, in their language:

> Installed. It takes effect in a **new session**. How to use it:
> 1. When context usage reaches 60% and 80%, you'll get a reminder (a line saying "Context xx% used").
> 2. Type `/handoff` and wait for the handoff file to be written.
> 3. Type `/clear`, then say "continue" (in any language). That's it.
>
> Every handoff is archived in `~/.claude/handoff-history/`. To look up an old decision later, just ask me.
> To update: ask me to follow this INSTALL.md again. To uninstall: see "Uninstall" in the README.
