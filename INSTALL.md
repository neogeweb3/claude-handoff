# INSTALL: steps for Claude Code

> The user handed you (Claude Code) this file. Follow the steps below and report each result to the user in one sentence, **in the language the user is speaking to you**.
> Stop and ask only where a step says **Ask the user**; do everything else directly.

## 0. Prerequisites

```bash
python3 --version && claude --version
```

python3 must be present; if it is missing, tell the user (macOS: `xcode-select --install`) and stop. Claude Code 2.1.287 or later gets the in-place resume; older versions work too, but `/handoff` then has to be typed as `/handoff:handoff` and resuming takes `/clear` + "continue".

## 1. Is there an old install?

```bash
ls ~/.claude/commands/handoff.md ~/.claude/hooks/handoff_after_clear.py ~/.claude/hooks/context_usage_reminder.py 2>/dev/null; claude plugin list 2>&1 | grep -c "handoff-compact@claude-handoff"
```

Any file listed, or a count above 0, means the user installed claude-handoff before it was a plugin. Remember this for step 3.

## 2. Install the plugin

```bash
claude plugin marketplace add neogeweb3/claude-handoff && claude plugin install handoff@claude-handoff
```

Both are safe to rerun ("already added" / "already installed" is fine).

## 3. Ask the user (in one message)

1. **How long should transcripts be kept?** By default Claude Code deletes local transcripts (plain-text .jsonl files under `~/.claude/projects/`) after 30 days. A handoff keeps only a summary and the last 5 messages verbatim; the full details live in the transcripts. Recommend 3650 days (about 10 years); the cost is disk space and plain-text transcripts staying on the machine longer. (Sessions started in the desktop app are exempt from the 30-day limit by default; only CLI sessions are affected.)
2. **Is the context window 200k or 1M?** Ask the user to run `/context` in any session and read the total. With 200k or unsure, nothing to set: the reminder assumes 200k and switches a model to 1M once its usage passes 200k.
3. **Turn on auto-update?** Third-party marketplaces have it off by default, so fixes only arrive when the user updates by hand. Recommend yes.
4. Only if step 1 found an old install: **switch to the plugin now?** Until they switch, the plugin's matching parts stay silent and each new conversation shows one line about the old install; nothing runs twice either way. Show the preview first:

   ```bash
   python3 "$(claude plugin list --json | python3 -c 'import json,sys;print([p["installPath"] for p in json.load(sys.stdin) if p["id"]=="handoff@claude-handoff"][0])')/scripts/migrate.py"
   ```

## 4. Apply the answers

Settings go into `~/.claude/settings.json`. Back it up, then merge only what the user agreed to; if the user is talking to you in Chinese, also set the reminder line to Chinese (decide from their language, do not ask):

```bash
python3 - <<'EOF'
import json, os, shutil, time
p = os.path.expanduser("~/.claude/settings.json")
s = json.load(open(p)) if os.path.exists(p) else {}
if os.path.exists(p):
    shutil.copy2(p, p + ".bak-" + time.strftime("%Y%m%d-%H%M%S"))
CLEANUP_DAYS = None   # 3650 if the user said yes to question 1
WINDOW = None         # "1000000" if the user has a 1M window
LANG = None           # "zh" if the user talks to you in Chinese
if CLEANUP_DAYS and (s.get("cleanupPeriodDays") or 30) < CLEANUP_DAYS:
    s["cleanupPeriodDays"] = CLEANUP_DAYS   # only ever raised
if WINDOW:
    s.setdefault("env", {})["CLAUDE_CONTEXT_WINDOW"] = WINDOW
if LANG:
    s.setdefault("env", {})["CLAUDE_HANDOFF_LANG"] = LANG
json.dump(s, open(p, "w"), ensure_ascii=False, indent=2)
EOF
```

If they want auto-update, tell them the one place to turn it on (it cannot be set from the marketplace): `/plugin` → Marketplaces → claude-handoff → Enable auto-update.

If they want to switch, run the preview command from step 3 again with `--apply` added after `migrate.py"`.

## 5. Verify

```bash
claude plugin list 2>&1 | grep -A3 "handoff@claude-handoff"
```

Must show `Status: ✔ enabled`. If they switched, running the preview again must print `Nothing to migrate`.

## 6. Tell the user

Tell the user the following, in their language:

> Installed. It takes effect in a **new session**. How to use it:
> 1. When context usage reaches 60% and 80%, you'll get a reminder (a line saying "Context xx% used").
> 2. Type `/handoff`. It writes the handoff file, then compacts the conversation with the handoff as the summary and carries on by itself.
>    (On Claude Code older than 2.1.287: type `/handoff:handoff`, then `/clear`, then say "continue".)
>
> Every handoff is archived in `~/.claude/handoff-history/`. To look up an old decision later, just ask me.
> Extra steps you want on every handoff go in `~/.claude/handoff.local.md`. To uninstall: `claude plugin uninstall handoff@claude-handoff`.
