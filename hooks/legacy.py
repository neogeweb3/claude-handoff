"""Is an older install of claude-handoff still active next to this plugin?

Before the plugin, install.py copied the scripts to ~/.claude/hooks/ and ~/.claude/commands/ and
registered the hooks in ~/.claude/settings.json; the in-place resume was a separate plugin,
handoff-compact@claude-handoff. A user who installs the plugin without removing those would get every
reminder twice and two handoffs injected after /clear. So while an old copy is registered, the plugin's
copy of that hook stays silent, and at session start the plugin says once what is still there and how
to switch (scripts/migrate.py).

Cost: reading settings.json once per hook run, well under a millisecond; nothing reaches the context
when the plugin stays silent.
"""
import json
import os
import shlex

CLAUDE = os.path.join(os.path.expanduser("~"), ".claude")
SETTINGS = os.path.join(CLAUDE, "settings.json")
OLD_HOOK_DIR = os.path.join(CLAUDE, "hooks")
OLD_COMMAND = os.path.join(CLAUDE, "commands", "handoff.md")
OLD_PLUGIN = "handoff-compact@claude-handoff"
SCRIPTS = ("handoff_after_clear.py", "context_usage_reminder.py")
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
MIGRATE = os.path.join(PLUGIN_ROOT, "scripts", "migrate.py")


def _settings():
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def script_of(cmd, names=SCRIPTS):
    """If this hook command is `python3 <...>/.claude/hooks/<one of names>` (how install.py registered it,
    the path shlex-quoted when it has spaces), the script path it runs; otherwise None."""
    try:
        argv = shlex.split(str(cmd or ""))
    except ValueError:
        return None
    if len(argv) < 2 or not os.path.basename(argv[0]).startswith("python"):
        return None
    path = os.path.expanduser(argv[1])
    parent = os.path.dirname(path)
    if (os.path.basename(path) in names and os.path.basename(parent) == "hooks"
            and os.path.basename(os.path.dirname(parent)) == ".claude"):
        return path
    return None


def old_hooks(settings=None, script=None):
    """Old registrations in ~/.claude/settings.json: [(command, script path, matcher)]."""
    names = SCRIPTS if script is None else (script,)
    hooks = (settings if settings is not None else _settings()).get("hooks")
    found = []
    for groups in (hooks.values() if isinstance(hooks, dict) else []):
        for group in (groups if isinstance(groups, list) else []):
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                continue
            for hook in group["hooks"]:
                path = script_of(hook.get("command"), names) if isinstance(hook, dict) else None
                if path:
                    found.append((hook["command"], path, group.get("matcher")))
    return found


def old_plugin_enabled(settings=None):
    enabled = (settings if settings is not None else _settings()).get("enabledPlugins") or {}
    return isinstance(enabled, dict) and enabled.get(OLD_PLUGIN) is True


def running_as_old_copy(path):
    """True when this script itself is the old copy in ~/.claude/hooks: it must never silence itself."""
    return os.path.dirname(os.path.realpath(path)) == os.path.realpath(OLD_HOOK_DIR)


def silenced(script_path):
    """Should the plugin's copy of this script stay quiet because an old copy will do the job?
    Only when that copy can actually run (its file is there) on every occasion (no matcher): a twice-shown
    reminder is a nuisance, a missing one defeats the point."""
    if running_as_old_copy(script_path):
        return False
    return any(os.path.isfile(path) and matcher in (None, "", "*")
               for _, path, matcher in old_hooks(script=os.path.basename(script_path)))


def leftovers():
    """What of the old install is still active, as short labels."""
    s = _settings()
    out = []
    if old_hooks(s):
        out.append("hooks in ~/.claude/settings.json")
    if os.path.isfile(OLD_COMMAND):
        out.append("~/.claude/commands/handoff.md")
    if old_plugin_enabled(s):
        out.append("the " + OLD_PLUGIN + " plugin")
    return out


def notice(lang="en"):
    """One line for the user at session start, or "" when nothing old is left."""
    left = leftovers()
    if not left:
        return ""
    if lang[:2] == "zh":
        return ("claude-handoff：旧的安装还在生效（%s），插件里对应的部分先让开了。"
                "要换成插件：python3 \"%s\"（先列出会改什么），确认后加 --apply。不换也能照常用。"
                % ("、".join(left), MIGRATE))
    return ("claude-handoff: an older install is still active (%s), so the plugin's matching parts are standing aside. "
            "To switch to the plugin: python3 \"%s\" (lists what it would change), then again with --apply. "
            "Not switching is fine too." % (", ".join(left), MIGRATE))
