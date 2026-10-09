#!/usr/bin/env python3
"""handoff_after_clear.py: /handoff writes the handoff -> user types /clear -> says "continue". No copy-paste in between.

Two modes:
  python3 <plugin folder>/hooks/handoff_after_clear.py --mark <absolute path to handoff file>
      Called as the last step of /handoff:
      1. leaves a pointer for the directory the handoff belongs to;
      2. copies this version into ~/.claude/handoff-history/ (append-only) and adds a line to index.tsv.
  python3 <plugin folder>/hooks/handoff_after_clear.py --mark <absolute path> --archive-only
      Used when the plugin resumes in place (compact_now): archives only, leaves no pointer,
      and removes any old pointer for that directory. The mod already puts the handoff into the context;
      a pointer left behind would inject this handoff again into an unrelated new conversation within 24h.
  (SessionStart hook, registered in the plugin's hooks.json without a matcher; reads the hook input from stdin)
      Runs when a new conversation starts. If the source is clear or startup and the current directory
      has an unused pointer younger than 24 hours, it injects where the handoff is and how to resume,
      together with the text of §0 and §11, then marks the pointer as used.

Why startup too: in the desktop app, /clear keeps the session and starts a new conversation underneath,
and SessionStart reports source=startup, not clear (only the CLI sends clear). So the hook entry
has no matcher and this script filters by source.
Why include §0: the handoff requires restating §0 before any tool call; with only a path, the model
cannot know what to restate without reading the file first.
Why per directory and single use: a HANDOFF.md at a repo root may belong to another line of work, so only
the file /handoff itself marked is trusted; used or older-than-24h pointers are ignored.
--mark picks the owner directory from the handoff file's location, not the shell's cwd, because one `cd`
in a Bash call is enough to move the latter.
Why archive: each anchored merge drops old content (§9 keeps 5 messages, §3-§8 are rewritten). If the
directory is not a git repo, or a worktree branch is deleted, older versions are gone for good. The
archive keeps every version and makes it greppable.
Any exception exits 0 silently so session start is never blocked. Every unused pointer encountered is
logged to hook.log, for debugging "why didn't it pick up".
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
try:
    import legacy  # an older install left next to the plugin: see legacy.py
except ImportError:  # this file used on its own, outside the plugin
    legacy = None

DIR = os.path.expanduser("~/.claude/handoff-pointers")
LOG = os.path.join(DIR, "hook.log")
HISTORY = os.path.expanduser("~/.claude/handoff-history")
MAX_AGE = 24 * 3600
SOURCES = ("clear", "startup")
LANG = (os.environ.get("CLAUDE_HANDOFF_LANG") or "en").lower()


def pointer_for(cwd):
    return os.path.join(DIR, re.sub(r"[/._]", "-", os.path.realpath(cwd)) + ".json")


def inside(path, d):
    path, d = os.path.realpath(path), os.path.realpath(d)
    return path == d or path.startswith(d.rstrip("/") + "/")


def owner_dir(handoff):
    """Directory the pointer belongs to: usually the session directory; if the shell was cd'd away,
    fall back to the git root of the handoff file."""
    cwd = os.getcwd()
    try:
        top = subprocess.run(["git", "-C", os.path.dirname(handoff), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        top = ""
    if not top or (inside(cwd, top) and inside(handoff, cwd)):
        return cwd
    return top


def section(path, num, limit):
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return ""
    m = re.search(r"^## §%s\b.*?$(.*?)(?=^## |\Z)" % num, text, re.S | re.M)
    if not m:
        return ""
    return re.sub(r"\n-{3,}\s*\Z", "", m.group(1).strip()).strip()[:limit]


def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except OSError:
        pass


def archive(path, owner):
    """Copy this version into ~/.claude/handoff-history/<dir>/ (never overwrites) and add a line to
    index.tsv. Returns the archived path."""
    text = open(path, encoding="utf-8").read()
    m = re.search(r"HANDOFF_VERSION:\s*(V\d+)", text)
    ver = m.group(1) if m else "V?"
    task = section(path, "3", 300).split("\n")[0].strip() or "-"
    d = os.path.join(HISTORY, re.sub(r"[/._]", "-", os.path.realpath(owner)))
    os.makedirs(d, exist_ok=True)
    base = "%s-%s-%s" % (time.strftime("%Y%m%d-%H%M%S"), ver, os.path.basename(path))
    dest, n = os.path.join(d, base), 2
    while os.path.exists(dest):
        dest = os.path.join(d, "%s-%d%s" % (os.path.splitext(base)[0], n, os.path.splitext(base)[1]))
        n += 1
    shutil.copy2(path, dest)
    with open(os.path.join(HISTORY, "index.tsv"), "a", encoding="utf-8") as f:
        f.write("\t".join([time.strftime("%Y-%m-%d %H:%M"), ver, owner, task.replace("\t", " "), dest]) + "\n")
    return dest


def mark(path, pointer=True):
    path = os.path.realpath(path)
    if not os.path.isfile(path):
        sys.exit("Handoff file not found: %s" % path)
    os.makedirs(DIR, exist_ok=True)
    owner = owner_dir(path)
    p = pointer_for(owner)
    if pointer:
        json.dump({"handoff": path, "cwd": owner, "written_at": time.time()}, open(p, "w"), ensure_ascii=False)
        print("Pointer saved: in %s, type /clear and then say continue to resume from %s (pointer: %s)" % (owner, path, p))
    else:
        if os.path.exists(p):
            os.remove(p)
        print("No pointer left (resuming in place); any old pointer for %s was removed" % owner)
    try:
        print("Archived: %s" % archive(path, owner))
    except Exception as e:  # a failed archive must not block the pointer, but it must be visible
        print("WARNING: archiving failed (%s): %r"
              % ("the pointer was saved" if pointer else "the handoff file itself is untouched", e))
    if os.path.realpath(owner) != os.path.realpath(os.getcwd()):
        print("Note: the shell is in %s; the pointer is attached to %s, where the handoff file lives." % (os.getcwd(), owner))


def on_session_start():
    try:
        hook = json.load(sys.stdin)
    except ValueError:
        return
    source = hook.get("source")
    note = ""
    if legacy and source in SOURCES and not legacy.running_as_old_copy(__file__):
        note = legacy.notice(LANG)
    # an old copy of this hook is still registered and injects the handoff itself
    text = "" if legacy and legacy.silenced(__file__) else pointer_text(hook)
    sys.stdout.reconfigure(encoding="utf-8")
    if note:
        out = {"systemMessage": note}
        if text:
            out["hookSpecificOutput"] = {"hookEventName": "SessionStart", "additionalContext": text}
        print(json.dumps(out, ensure_ascii=False))
    elif text:
        print(text)


def pointer_text(hook):
    """The text to inject for an unused pointer of this directory, or "". Marks the pointer used."""
    source, cwd = hook.get("source"), hook.get("cwd") or os.getcwd()
    p = pointer_for(cwd)
    if not os.path.isfile(p):
        return ""
    ptr = json.load(open(p))
    if ptr.get("consumed_at"):
        return ""
    if ptr.get("cwd") and os.path.realpath(ptr["cwd"]) != os.path.realpath(cwd):
        # pointer file names are lossy (/ . _ all become -): never hand one project's handoff to another
        log("skip pointer belongs to %s | cwd=%s" % (ptr["cwd"], cwd))
        return ""
    env = "entrypoint=%s attended=%s" % (os.environ.get("CLAUDE_CODE_ENTRYPOINT", "-"),
                                          os.environ.get("CLAUDE_CODE_SESSION_ATTENDED", "-"))
    if source not in SOURCES:
        log("skip source=%s (only clear / startup are used; pointer kept) | cwd=%s | %s" % (source, cwd, env))
        return ""
    dead = ("older than 24 hours" if time.time() - ptr.get("written_at", 0) > MAX_AGE
            else "handoff file missing" if not os.path.isfile(ptr.get("handoff", "")) else "")
    if dead:
        ptr.update(consumed_at=time.time(), consumed_by={"skipped": dead})
        json.dump(ptr, open(p, "w"), ensure_ascii=False)
        log("skip %s | cwd=%s | %s" % (dead, cwd, env))
        return ""
    s0, s11 = section(ptr["handoff"], "0", 2500), section(ptr["handoff"], "11", 2000)
    when = time.strftime("%m-%d %H:%M", time.localtime(ptr["written_at"]))
    lines = ["[Handoff from the previous conversation] written %s: %s" % (when, ptr["handoff"]),
             "When the user says \"continue\" (or the same thing in any language), do this in order:"]
    if s0:
        lines += ["1. Restate the 5 items of §0 below word for word. The text is right here; no tool call needed for this step.",
                  "2. Tell the user in one sentence that you have picked up the handoff (which file, written when).",
                  "3. Then read the whole file above and follow the opening instruction in §11."]
    else:
        lines += ["1. Read the whole file above and follow the opening instruction in §11.",
                  "2. Tell the user in one sentence that you have picked up the handoff (which file, written when), then get to work."]
    lines.append("If the user is asking about something new instead, ignore this handoff.")
    lines.append("Reply to the user in the language they write in.")
    if s0:
        lines += ["", "§0 text:", s0]
    if s11:
        lines += ["", "Opening instruction (§11 text):", s11]
    ptr.update(consumed_at=time.time(), consumed_by={"source": source, "session_id": hook.get("session_id")})
    try:
        json.dump(ptr, open(p, "w"), ensure_ascii=False)
    except OSError as e:  # failing to mark it used must not cost the handoff itself
        log("could not mark pointer used: %r | %s" % (e, p))
    log("inject source=%s | cwd=%s | %s | %s" % (source, cwd, ptr["handoff"], env))
    return "\n".join(lines)


if __name__ == "__main__":
    try:
        if len(sys.argv) == 3 and sys.argv[1] == "--mark":
            mark(sys.argv[2])
        elif len(sys.argv) == 4 and sys.argv[1] == "--mark" and sys.argv[3] == "--archive-only":
            mark(sys.argv[2], pointer=False)
        else:
            on_session_start()
    except SystemExit:
        raise
    except Exception as e:
        log("error %r" % e)
    sys.exit(0)
