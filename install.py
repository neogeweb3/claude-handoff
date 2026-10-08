#!/usr/bin/env python3
"""Install or update claude-handoff. Safe to run repeatedly; hooks are never registered twice.

  python3 install.py --dry-run                    # print what would happen, change nothing
  python3 install.py                              # install
  python3 install.py --cleanup-days 3650          # also keep transcripts for 3650 days
  python3 install.py --window 1000000             # also tell the reminder hook your window is 1M
  python3 install.py --force                      # replace an existing handoff.md that is not ours (backed up first)

What it does:
  1. Copies files: commands/handoff.md, commands/handoff_scan.py -> ~/.claude/commands/
                   hooks/*.py -> ~/.claude/hooks/
     If a target exists with different content, it is backed up as <name>.bak-<timestamp> first.
     If ~/.claude/commands/handoff.md exists and was not installed by this project, nothing is copied
     and the script exits (use --force to replace it).
  2. Registers three hooks in ~/.claude/settings.json (backed up before writing):
       SessionStart      -> handoff_after_clear.py (no matcher)
       UserPromptSubmit  -> context_usage_reminder.py
       PostToolUse       -> context_usage_reminder.py
  3. Optional: cleanupPeriodDays and env.CLAUDE_CONTEXT_WINDOW. Retention is only ever raised,
     never lowered below what you already have.
"""
import argparse
import filecmp
import json
import os
import shutil
import sys
import time

SRC = os.path.dirname(os.path.abspath(__file__))
CLAUDE = os.path.expanduser("~/.claude")
STAMP = time.strftime("%Y%m%d-%H%M%S")
MARKER = "claude-handoff"   # present in our handoff.md description; identifies our own install
FILES = [
    ("commands/handoff.md", "commands/handoff.md"),
    ("commands/handoff_scan.py", "commands/handoff_scan.py"),
    ("hooks/handoff_after_clear.py", "hooks/handoff_after_clear.py"),
    ("hooks/context_usage_reminder.py", "hooks/context_usage_reminder.py"),
]


def hook_cmd(name):
    return "python3 %s" % os.path.join(CLAUDE, "hooks", name)


HOOKS = [
    ("SessionStart", hook_cmd("handoff_after_clear.py")),
    ("UserPromptSubmit", hook_cmd("context_usage_reminder.py")),
    ("PostToolUse", hook_cmd("context_usage_reminder.py")),
]


def say(dry, msg):
    print(("[dry-run] " if dry else "") + msg)


def copy_files(dry, force):
    target = os.path.join(CLAUDE, "commands", "handoff.md")
    if os.path.exists(target) and not force:
        with open(target, encoding="utf-8") as f:
            ours = MARKER in f.read()
        if not ours:
            sys.exit("~/.claude/commands/handoff.md already exists and was not installed by this project.\n"
                     "Ask the user whether to replace it; if yes, rerun with --force "
                     "(the original is backed up as .bak-%s)." % STAMP)
    for rel_src, rel_dst in FILES:
        src, dst = os.path.join(SRC, rel_src), os.path.join(CLAUDE, rel_dst)
        if os.path.exists(dst) and filecmp.cmp(src, dst, shallow=False):
            say(dry, "unchanged: %s" % dst)
            continue
        if os.path.exists(dst):
            say(dry, "backup: %s -> %s.bak-%s" % (dst, dst, STAMP))
            if not dry:
                shutil.copy2(dst, "%s.bak-%s" % (dst, STAMP))
        say(dry, "copy: %s -> %s" % (rel_src, dst))
        if not dry:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)


def update_settings(dry, cleanup_days, window):
    path = os.path.join(CLAUDE, "settings.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            settings = json.load(f)   # invalid JSON: fail loudly rather than touch it
    else:
        settings = {}
    before = json.dumps(settings, sort_keys=True)
    hooks = settings.setdefault("hooks", {})
    for event, cmd in HOOKS:
        groups = hooks.setdefault(event, [])
        present = any(h.get("command") == cmd for g in groups for h in g.get("hooks", []))
        if present:
            say(dry, "hook already registered: %s -> %s" % (event, cmd))
        else:
            groups.append({"hooks": [{"type": "command", "command": cmd}]})
            say(dry, "register hook: %s -> %s" % (event, cmd))
    if cleanup_days:
        cur = settings.get("cleanupPeriodDays")
        if isinstance(cur, int) and cur >= cleanup_days:
            say(dry, "cleanupPeriodDays is already %d, unchanged" % cur)
        else:
            settings["cleanupPeriodDays"] = cleanup_days
            say(dry, "cleanupPeriodDays: %s -> %d" % (cur if cur is not None else "unset (default 30)", cleanup_days))
    if window:
        settings.setdefault("env", {})["CLAUDE_CONTEXT_WINDOW"] = str(window)
        say(dry, "env.CLAUDE_CONTEXT_WINDOW = %d" % window)
    if json.dumps(settings, sort_keys=True) == before:
        say(dry, "settings.json needs no changes")
        return
    if dry:
        return
    if os.path.exists(path):
        shutil.copy2(path, "%s.bak-%s" % (path, STAMP))
        print("backup: %s.bak-%s" % (path, STAMP))
    os.makedirs(CLAUDE, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    print("written: %s" % path)


def main():
    ap = argparse.ArgumentParser(description="Install or update claude-handoff")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--cleanup-days", type=int, default=0)
    ap.add_argument("--window", type=int, default=0)
    a = ap.parse_args()
    copy_files(a.dry_run, a.force)
    update_settings(a.dry_run, a.cleanup_days, a.window)
    if not a.dry_run:
        print("\nInstalled. The hooks take effect in a new session; /handoff should then be available.")


if __name__ == "__main__":
    main()
