#!/usr/bin/env python3
"""handoff_scan.py: before writing a handoff, pull the things most easily lost out of the transcript.
Called by /handoff in Step 0.

Why it exists (from the author's same-state comparison): handoffs and compaction both lose the
"not done / not verified / only estimated" kind of statement, and both lost the same three items.
Writing a handoff from memory misses them; they have to be pulled out of the transcript mechanically
and reviewed one by one. Replaying with this scan recovered 3 of the 4 missed items; the fourth only
existed in a data file written by a background agent, not in the transcript.

Usage:
  python3 scripts/handoff_scan.py              # find the latest transcript for the current directory
  python3 scripts/handoff_scan.py <file.jsonl>
Read-only; changes nothing.
"""
import glob
import json
import os
import re
import sys

# Statements that something is not done, not verified, uncertain, or waiting on the user.
# English and Chinese, since users write in either.
FLAG = re.compile(
    r"not (?:yet )?(?:done|verified|tested|checked|run|confirmed)|"
    r"haven'?t (?:yet )?(?:verified|tested|checked|run|confirmed|done)|"
    r"didn'?t (?:verify|test|check|run|confirm)|"
    r"\bunverified\b|\buntested\b|\bunconfirmed\b|not sure|\bunsure\b|\buncertain\b|"
    r"\bestimated?\b|\bguess(?:ed)?\b|\bTBD\b|\bTODO\b|\bbacklog\b|\bpending\b|"
    r"waiting (?:on|for) (?:you|your)|your call|needs? your (?:decision|input)|could ?n[o']t verify|"
    r"未核|没核|没查|未查|没跑|没做|没实测|未实测|没验证|未验证|没测|没取到|没逐个|没法判断|没确认|还没|"
    r"推断|推算|估算|不确定|拿不准|不知道|待定|等你|要你拍板|需要你|你定",
    re.I)
SPLIT = re.compile(r"(?<=[。！？!?])|(?<=\.)\s+|\n")
REMINDER = re.compile(r"^\s*(<system-reminder>.*?</system-reminder>\s*)+", re.S)
# Tags Claude Code itself puts in user-role entries (slash commands, ! shell input, tool views, etc.).
# Anything else starting with "<" is the user's own text (e.g. pasted HTML, "<!-- ... -->").
SYSTEM_TAG = re.compile(r"^<(?:command-[a-z]+|bash-[a-z]+|local-command-[a-z]+|artifact-[a-z-]+|"
                        r"cross-session-message|user-prompt-submit-hook)\b")


def flagged(text):
    return [s.strip() for s in SPLIT.split(text) if s and FLAG.search(s)]


def find_transcript():
    cwd = os.getcwd()
    slug = re.sub(r"[/._]", "-", cwd)
    files = glob.glob(os.path.expanduser("~/.claude/projects/%s/*.jsonl" % slug))
    if files:
        return max(files, key=os.path.getmtime)
    # Directory names with non-ASCII characters may not map to the same project folder name:
    # fall back to the most recent transcript whose cwd field matches.
    recent = sorted(glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl")), key=os.path.getmtime)[-200:]
    needle = json.dumps(cwd, ensure_ascii=False)
    for f in reversed(recent):
        try:
            with open(f, encoding="utf-8") as fh:
                head = fh.read(200000)
        except OSError:
            continue
        if '"cwd":%s' % needle in head or '"cwd": %s' % needle in head:
            return f
    return None


def texts(content):
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else find_transcript()
    if not path or not os.path.exists(path):
        sys.exit("No transcript found: %s has no matching .jsonl under ~/.claude/projects/. "
                 "Pass the path as an argument." % os.getcwd())
    user, mine, agents = [], [], []
    for n, line in enumerate(open(path, encoding="utf-8"), 1):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        ts = r.get("timestamp", "")[:16].replace("T", " ")
        c = (r.get("message") or {}).get("content")
        att = r.get("attachment") or {}
        if r.get("type") == "user" and not r.get("isMeta") and not r.get("isCompactSummary"):
            t = REMINDER.sub("", texts(c)).strip()   # the first message is often wrapped in system reminders
            if "<task-notification>" in t:
                agents += [(ts, n, s) for s in flagged(t)]
            elif t and not SYSTEM_TAG.match(t):
                user.append((ts, n, t))
        elif att.get("type") == "queued_command" and att.get("prompt"):
            t = str(att["prompt"]).strip()           # background task notifications also arrive this way
            if "<task-notification>" in t:
                agents += [(ts, n, s) for s in flagged(t)]
            elif t and not SYSTEM_TAG.match(t):
                user.append((ts, n, "(queued) " + t))
        elif r.get("type") == "assistant":
            mine += [(ts, n, s) for s in flagged(texts(c))]

    def dedup(rows):
        seen, out = set(), []
        for ts, n, s in rows:
            if len(s) >= 2 and s not in seen:
                seen.add(s)
                out.append((ts, n, s))
        return out

    print("# Pre-handoff scan\n\nTranscript (the user's exact words and all details are here; put this in §10): `%s`\n" % path)
    print("## 1. User messages (%d, times in UTC; the last 5 go into §9 verbatim)\n" % len(user))
    for ts, n, t in user:
        body = t if len(t) <= 600 else t[:600] + "... (truncated, full text at line %d)" % n
        print("- [%s] %s" % (ts, body.replace("\n", " ")))
    for title, rows in (("2. Things you said are not done / not verified / pending", mine),
                        ("3. The same kind of sentence from background agent results", agents)):
        rows = dedup(rows)
        print("\n## %s (%d; for each one: put it in §2 / §10, or confirm it is stale)\n" % (title, len(rows)))
        for ts, n, s in rows:
            print("- [%s · line %d] %s" % (ts, n, s[:240]))


if __name__ == "__main__":
    main()
