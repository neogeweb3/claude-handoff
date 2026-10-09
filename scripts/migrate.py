#!/usr/bin/env python3
"""migrate.py: switch from the old manual install of claude-handoff to the plugin.

  python3 migrate.py            lists what would change; changes nothing
  python3 migrate.py --apply    makes the changes

The old install (install.py, before the plugin) left:
  - hooks in ~/.claude/settings.json that run ~/.claude/hooks/handoff_after_clear.py and
    ~/.claude/hooks/context_usage_reminder.py;
  - files: ~/.claude/commands/handoff.md, ~/.claude/commands/handoff_scan.py and the two hook scripts;
  - optionally the separate plugin handoff-compact@claude-handoff (the in-place resume, now inside this plugin).
While any of those is active the plugin's matching part stands aside (hooks/legacy.py), so nothing
runs twice; this script removes them so the plugin takes over.

What --apply does:
  1. settings.json: copied to settings.json.bak-handoff-<time> first; then only the hook entries that run
     those two old scripts are removed (an entry left with no hooks, and an event left with no entries,
     are dropped). Everything else is written back unchanged.
  2. The old files are moved (not deleted) into ~/.claude/handoff-migrated-<time>/, keeping their paths.
     A file is only moved when it carries one of this project's marks (OLD_FILES below); a file of the same
     name that is your own, such as your own /handoff command, is left where it is.
  3. handoff-compact@claude-handoff is uninstalled with `claude plugin uninstall --scope <its scope>`, for
     each scope it is installed in; if that fails, the command is printed for you to run.
Handoff archives (~/.claude/handoff-history), pointers and settings such as env.CLAUDE_CONTEXT_WINDOW are
not touched. Running it again after a successful run finds nothing to do.

Undo: copy the settings.json backup back over ~/.claude/settings.json, move the files back from the
handoff-migrated folder, and reinstall handoff-compact if you want it.
"""
import json
import os
import shlex
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "hooks"))
from legacy import script_of  # noqa: E402  (the same test the hooks use to recognise an old registration)

CLAUDE = os.path.join(os.path.expanduser("~"), ".claude")
SETTINGS = os.path.join(CLAUDE, "settings.json")
# Each old file and strings only this project's versions contain (every released version and the
# author's own copies were checked); a file without them is someone else's and is left alone.
OLD_FILES = {
    "commands/handoff.md": ("claude-handoff", "HANDOFF_VERSION"),
    "commands/handoff_scan.py": ("queued_command",),
    "hooks/handoff_after_clear.py": ("handoff-pointers",),
    "hooks/context_usage_reminder.py": ("context-reminder",),
}
OLD_PLUGIN = "handoff-compact@claude-handoff"
STAMP = time.strftime("%Y%m%d-%H%M%S")


def is_old_hook(hook):
    return isinstance(hook, dict) and script_of(hook.get("command")) is not None


def strip_hooks(settings):
    """Returns (settings without the old hook entries, list of removed commands)."""
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return settings, []
    removed, new_hooks = [], {}
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            new_hooks[event] = groups
            continue
        kept_groups = []
        for group in groups:
            inner = group.get("hooks") if isinstance(group, dict) else None
            if not isinstance(inner, list):
                kept_groups.append(group)
                continue
            kept = [h for h in inner if not is_old_hook(h)]
            removed += ["%s: %s" % (event, h.get("command")) for h in inner if is_old_hook(h)]
            if kept:
                kept_groups.append(dict(group, hooks=kept))
            elif len(kept) == len(inner):
                kept_groups.append(group)  # an empty entry that was never ours stays as it was
        if kept_groups or not groups:
            new_hooks[event] = kept_groups
    out = dict(settings)
    if new_hooks:
        out["hooks"] = new_hooks
    else:
        out.pop("hooks", None)
    return out, removed


def ours(path):
    """Is this old file from this project? Only when it carries one of its marks (OLD_FILES)."""
    marks = OLD_FILES[os.path.relpath(path, CLAUDE)]
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return False
    return any(m in text for m in marks)


def old_plugin_installs():
    """[(scope, projectPath or None)] of the old plugin; [("user", None)] when only settings name it."""
    try:
        data = json.load(open(os.path.join(CLAUDE, "plugins", "installed_plugins.json"), encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    records = (data.get("plugins") or {}).get(OLD_PLUGIN) if isinstance(data, dict) else None
    found = [(r.get("scope") or "user", r.get("projectPath")) for r in records or [] if isinstance(r, dict)]
    if not found:
        try:
            settings = json.load(open(SETTINGS, encoding="utf-8"))
        except (OSError, ValueError):
            settings = {}
        enabled = settings.get("enabledPlugins") if isinstance(settings, dict) else None
        if isinstance(enabled, dict) and OLD_PLUGIN in enabled:
            found = [("user", None)]
    return found


def uninstall_command(scope, project):
    cmd = "claude plugin uninstall %s --scope %s" % (OLD_PLUGIN, scope)
    return ("cd %s && %s" % (shlex.quote(project), cmd)) if project else cmd


def main():
    apply = "--apply" in sys.argv[1:]
    unknown = [a for a in sys.argv[1:] if a != "--apply"]
    if unknown:
        sys.exit("usage: migrate.py [--apply]")
    plan = []

    settings_text = None
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            settings_text = f.read()
        settings = json.loads(settings_text)
    except FileNotFoundError:
        settings = None
    except ValueError:
        sys.exit("~/.claude/settings.json is not valid JSON; fix it first. Nothing was changed.")
    removed = []
    if isinstance(settings, dict):
        new_settings, removed = strip_hooks(settings)
        plan += ["remove hook  " + r for r in removed]

    files = [os.path.join(CLAUDE, rel) for rel in OLD_FILES if os.path.isfile(os.path.join(CLAUDE, rel))]
    skipped = [f for f in files if not ours(f)]
    files = [f for f in files if ours(f)]
    plan += ["move file    " + f for f in files]
    installs = old_plugin_installs()
    plan += ["uninstall    %s (%s scope%s)" % (OLD_PLUGIN, sc, ", " + pp if pp else "") for sc, pp in installs]

    for f in skipped:
        note = ("; your own /handoff keeps priority over the plugin's, which is then /handoff:handoff"
                if f.endswith("handoff.md") else "")
        print("left alone   %s (does not look like this project's%s)" % (f, note))
    if not plan:
        print("Nothing to migrate: no old install of claude-handoff found.")
        return
    print(("Changing:" if apply else "Would change (run again with --apply to do it):"))
    for line in plan:
        print("  " + line)
    if not apply:
        return

    if removed:
        backup = "%s.bak-handoff-%s" % (SETTINGS, STAMP)
        with open(backup, "w", encoding="utf-8") as f:
            f.write(settings_text)
        tmp = SETTINGS + ".tmp-handoff"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(new_settings, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, SETTINGS)
        print("settings.json backed up to %s" % backup)
    if files:
        dest_root = os.path.join(CLAUDE, "handoff-migrated-" + STAMP)
        for f in files:
            dest = os.path.join(dest_root, os.path.relpath(f, CLAUDE))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.move(f, dest)
        print("old files moved to %s" % dest_root)
    for scope, project in installs:
        if project and not os.path.isdir(project):
            print("skipped %s in %s (that folder is gone)" % (OLD_PLUGIN, project))
            continue
        try:
            r = subprocess.run(["claude", "plugin", "uninstall", OLD_PLUGIN, "--scope", scope], cwd=project,
                               capture_output=True, text=True, timeout=120)
            ok = r.returncode == 0
        except (OSError, subprocess.SubprocessError):
            ok = False
        print(("uninstalled %s (%s scope)" % (OLD_PLUGIN, scope)) if ok else
              ("could not uninstall %s; run: %s" % (OLD_PLUGIN, uninstall_command(scope, project))))
    print("Done. Start a new conversation (or restart Claude Code) for the plugin to take over.")


if __name__ == "__main__":
    main()
