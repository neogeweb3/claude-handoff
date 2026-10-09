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


def old_hooks(settings=None, script=None):
    """Hook commands in ~/.claude/settings.json that run an old copy of our scripts."""
    names = SCRIPTS if script is None else (script,)
    hooks = (settings if settings is not None else _settings()).get("hooks")
    found = []
    for groups in (hooks.values() if isinstance(hooks, dict) else []):
        for group in (groups if isinstance(groups, list) else []):
            inner = group.get("hooks") if isinstance(group, dict) else None
            for hook in (inner if isinstance(inner, list) else []):
                cmd = str(hook.get("command") or "") if isinstance(hook, dict) else ""
                if any("/.claude/hooks/" + n in cmd for n in names):
                    found.append(cmd)
    return found


def old_plugin_enabled(settings=None):
    enabled = (settings if settings is not None else _settings()).get("enabledPlugins") or {}
    return isinstance(enabled, dict) and enabled.get(OLD_PLUGIN) is True


def running_as_old_copy(path):
    """True when this script itself is the old copy in ~/.claude/hooks: it must never silence itself."""
    return os.path.dirname(os.path.realpath(path)) == os.path.realpath(OLD_HOOK_DIR)


def silenced(script_path):
    """Should the plugin's copy of this script stay quiet because an old copy is registered?"""
    if running_as_old_copy(script_path):
        return False
    return bool(old_hooks(script=os.path.basename(script_path)))


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
