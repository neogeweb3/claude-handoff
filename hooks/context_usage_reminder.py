#!/usr/bin/env python3
"""Context usage reminder: PostToolUse + UserPromptSubmit hook.

Computes the current context size from the usage of the last main-thread assistant message in the
transcript (transcript_path in the hook input): input_tokens + cache_creation_input_tokens +
cache_read_input_tokens. Fires once at 60% and once at 80% per session: injects one line of
additionalContext for Claude and shows a systemMessage in the UI. After compaction, once usage drops
below 40%, the thresholds re-arm.

Why it exists: a handoff only beats compaction if it actually happens around 60% (the author's
same-state comparison: handoff 49/48 vs compact 39/38), and Claude cannot see its own usage, so someone
had to watch it by hand.
Borrowed from gsd-build/get-shit-done hooks/gsd-context-monitor.js (thresholds, fire once, fail silently,
remind without commanding). Different data source: GSD reads a file written by its status-line script;
the desktop app does not run status lines, so this reads the transcript directly.

The transcript does not record the window size, so it is resolved in this order:
  1. the CLAUDE_CONTEXT_WINDOW environment variable (set it under "env" in settings.json; most accurate);
  2. learned: once a model's context exceeds 200k, it must have a 1M window; recorded in window.json
     and used from then on;
  3. otherwise 200k. A 1M-window user may get an early reminder before the first time a model passes
     200k; the reminder says so.
The one line shown in the UI (systemMessage) is in English, or in Chinese when CLAUDE_HANDOFF_LANG=zh
(set it under "env" in settings.json). The text injected for Claude stays in English and tells it to reply in
the user's language.
Any exception exits 0 silently so tool calls are never blocked.

Check current usage by hand: python3 <plugin folder>/hooks/context_usage_reminder.py --probe <transcript.jsonl>
(the plugin folder: `claude plugin list --json`, installPath of handoff@claude-handoff)
"""
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
try:
    import legacy  # an older install left next to the plugin: see legacy.py
except ImportError:  # this file used on its own, outside the plugin
    legacy = None

ENV_WINDOW = int(os.environ.get("CLAUDE_CONTEXT_WINDOW") or 0)
LANG = (os.environ.get("CLAUDE_HANDOFF_LANG") or "en").lower()
UI_MESSAGE = {
    "en": "Context %d%% used (about %s tokens): time to hand off",
    "zh": "上下文已用 %d%%（约 %s token），该交接了",
}
SMALL, LARGE = 200_000, 1_000_000
THRESHOLDS = (60, 80)
RESET_BELOW = 40              # after compaction, re-arm once usage drops below this
TAIL_BYTES = 4 * 1024 * 1024  # only read this much from the end of the transcript
STATE_DIR = Path.home() / ".claude" / "context-reminder"
USAGE_KEYS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


def last_main_context(path):
    """Walk back from the end of the transcript to the last main-thread assistant message.
    Returns (context tokens, model) or (None, None)."""
    with open(path, "rb") as fh:
        fh.seek(0, os.SEEK_END)
        fh.seek(max(0, fh.tell() - TAIL_BYTES))
        chunk = fh.read()
    for raw in reversed(chunk.splitlines()):
        if b'"assistant"' not in raw or b'"usage"' not in raw:
            continue
        try:
            d = json.loads(raw)
        except ValueError:
            continue  # first line cut mid-way, or a corrupt line
        if d.get("type") != "assistant" or d.get("isSidechain"):
            continue
        msg = d.get("message") or {}
        usage = msg.get("usage") or {}
        ctx = sum(int(usage.get(k) or 0) for k in USAGE_KEYS)
        if ctx > 0:  # error placeholder messages have all-zero usage
            return ctx, msg.get("model")
    return None, None


def window_for(model, ctx):
    """Returns (window size, whether it is a guess). See the module docstring."""
    if ENV_WINDOW:
        return ENV_WINDOW, False
    path = STATE_DIR / "window.json"
    try:
        learned = json.loads(path.read_text())
    except (OSError, ValueError):
        learned = {}
    key = model or "-"
    if ctx > SMALL and learned.get(key) != LARGE:
        learned[key] = LARGE
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(learned))
    if learned.get(key):
        return learned[key], False
    return SMALL, True


def k(n):
    return "%dk" % round(n / 1000)


def main():
    if legacy and legacy.silenced(__file__):
        return  # an old copy of this hook is still registered and does the reminding
    data = json.loads(sys.stdin.read() or "{}")
    event = data.get("hook_event_name") or "PostToolUse"
    sid = str(data.get("session_id") or "")
    tpath = data.get("transcript_path") or ""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", sid) or not os.path.isfile(tpath):
        return
    ctx, model = last_main_context(tpath)
    if not ctx:
        return
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    window, guessed = window_for(model, ctx)
    pct = ctx * 100 // window

    state_path = STATE_DIR / (sid + ".json")
    try:
        fired = json.loads(state_path.read_text()).get("fired", [])
    except (OSError, ValueError):
        fired = []
    if fired and pct < RESET_BELOW:
        fired = []  # compacted; re-arm
        state_path.write_text(json.dumps({"fired": fired}))
    due = [t for t in THRESHOLDS if pct >= t and t not in fired]
    if not due:
        return
    line = max(due)
    fired = sorted(set(fired) | set(due))
    state_path.write_text(json.dumps({"fired": fired, "at": int(time.time()), "ctx": ctx}))

    later = [t for t in THRESHOLDS if t > line]
    note = (" (Window assumed to be 200k. If yours is 1M, set CLAUDE_CONTEXT_WINDOW=1000000 under \"env\" "
            "in settings.json, or wait: it corrects itself the first time this model passes 200k.)" if guessed else "")
    context_msg = (
        "[Context usage reminder · hook] The last request used about %s tokens, %d%% of a %s window, past the %d%% line "
        "(computed from input+cache tokens in the transcript, not estimated; you can quote this number).%s "
        "The convention is to hand off at 60%% and treat compaction only as a fallback: when you finish the step "
        "you are on, suggest in one sentence that the user run /handoff now. If your tool list has "
        "a tool ending in __compact_now, /handoff compacts and carries on by itself, so do not mention /clear; "
        "otherwise add: then /clear and say continue. "
        "If the user says no, keep working. Reply to the user in the language they write in. %s"
        % (k(ctx), pct, k(window), line, note,
           ("There will be one more reminder at %d%%." % later[0]) if later else "No more reminders this session.")
    )
    out = {
        "systemMessage": UI_MESSAGE.get(LANG[:2], UI_MESSAGE["en"]) % (pct, k(ctx)),
        "hookSpecificOutput": {"hookEventName": event, "additionalContext": context_msg},
    }
    with open(STATE_DIR / "hook.log", "a") as fh:
        fh.write("%s fire %d%% ctx=%d line=%d event=%s sid=%s model=%s\n"
                 % (time.strftime("%Y-%m-%d %H:%M:%S"), pct, ctx, line, event, sid, model))
    sys.stdout.write(json.dumps(out, ensure_ascii=False))


def probe(path):
    ctx, model = last_main_context(path)
    if not ctx:
        print("No main-thread assistant usage found in: %s" % path)
        return
    window, guessed = window_for(model, ctx)
    print("Context %d tokens (%s), %.1f%% of a %s window%s, model %s"
          % (ctx, k(ctx), ctx * 100 / window, k(window), " (guessed)" if guessed else "", model))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--probe":
        probe(sys.argv[2])
        sys.exit(0)
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
