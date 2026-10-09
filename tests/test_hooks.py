#!/usr/bin/env python3
"""End-to-end tests for the scripts. Each case runs in a temporary HOME and never touches the real ~/.claude.

  python3 tests/test_hooks.py
"""
import json
import shutil
import os
import shlex
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AFTER_CLEAR = os.path.join(ROOT, "hooks", "handoff_after_clear.py")
REMINDER = os.path.join(ROOT, "hooks", "context_usage_reminder.py")
SCAN = os.path.join(ROOT, "scripts", "handoff_scan.py")
MIGRATE = os.path.join(ROOT, "scripts", "migrate.py")

HANDOFF = """<!--
HANDOFF_VERSION: V{v}
-->
# HANDOFF (V{v})

## §0 🔁 Read-back Protocol

1. **Task**: "Fix the login page"

---

## §3 🎯 Task

Fix the login page, version {v}

---

## §9 📜 User messages

### Message [1]:
```
codeword-{v}
```

## §11 🚀 First message to next session

> "Read handoff V{v}"
"""


def run(script, args=(), stdin="", home=None, cwd=None, env_extra=None):
    env = dict(os.environ, HOME=home)
    for name in ("CLAUDE_CONTEXT_WINDOW", "CLAUDE_HANDOFF_LANG"):  # the tester's own settings must not leak in
        env.pop(name, None)
    env.update(env_extra or {})
    return subprocess.run([sys.executable, script, *args], input=stdin, capture_output=True,
                          text=True, env=env, cwd=cwd, timeout=30)


def assistant_line(ctx, model="claude-test"):
    return json.dumps({"type": "assistant", "message": {"model": model, "usage": {
        "input_tokens": ctx, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}}})


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.realpath(self.tmp.name)
        self.work = os.path.join(self.home, "proj")
        os.makedirs(self.work)

    def tearDown(self):
        self.tmp.cleanup()

    def write_handoff(self, v):
        p = os.path.join(self.work, "HANDOFF.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(HANDOFF.format(v=v))
        return p


class AfterClear(Base):
    def session_start(self, source="startup"):
        return run(AFTER_CLEAR, stdin=json.dumps({"source": source, "cwd": self.work, "session_id": "s1"}),
                   home=self.home, cwd=self.work)

    def test_mark_then_inject_once(self):
        p = self.write_handoff(1)
        r = run(AFTER_CLEAR, ["--mark", p], home=self.home, cwd=self.work)
        self.assertIn("Pointer saved", r.stdout)
        first = self.session_start("startup").stdout
        self.assertIn("§0 text", first)
        self.assertIn("Fix the login page", first)
        self.assertIn("Read handoff V1", first)
        self.assertEqual(self.session_start("clear").stdout, "", "a pointer is used once")

    def test_injection_tells_claude_to_reply_in_user_language(self):
        p = self.write_handoff(1)
        run(AFTER_CLEAR, ["--mark", p], home=self.home, cwd=self.work)
        self.assertIn("Reply to the user in the language they write in", self.session_start().stdout)

    def test_archive_only_leaves_no_pointer_and_clears_old_one(self):
        old = self.write_handoff(1)
        run(AFTER_CLEAR, ["--mark", old], home=self.home, cwd=self.work)
        p = self.write_handoff(2)
        r = run(AFTER_CLEAR, ["--mark", p, "--archive-only"], home=self.home, cwd=self.work)
        self.assertNotIn("Pointer saved", r.stdout)
        archived = r.stdout.split("Archived: ", 1)[1].splitlines()[0]
        with open(archived, encoding="utf-8") as f:
            self.assertEqual(f.read(), HANDOFF.format(v=2), "the archive holds this version in full")
        self.assertEqual(self.session_start("startup").stdout, "", "resumed in place: nothing to inject later")

    def test_archive_only_failure_does_not_claim_a_pointer(self):
        p = self.write_handoff(1)
        os.makedirs(os.path.join(self.home, ".claude"))
        open(os.path.join(self.home, ".claude", "handoff-history"), "w").close()  # a file where the dir goes
        r = run(AFTER_CLEAR, ["--mark", p, "--archive-only"], home=self.home, cwd=self.work)
        self.assertIn("WARNING: archiving failed", r.stdout)
        self.assertNotIn("pointer was saved", r.stdout)

    def test_other_source_keeps_pointer(self):
        p = self.write_handoff(1)
        run(AFTER_CLEAR, ["--mark", p], home=self.home, cwd=self.work)
        self.assertEqual(self.session_start("resume").stdout, "")
        self.assertIn("§0 text", self.session_start("clear").stdout)

    def test_pointer_never_crosses_to_lookalike_directory(self):
        """project-one and project_one map to the same pointer file name; the handoff must not cross over."""
        other = os.path.join(self.home, "proj_x")
        mine = os.path.join(self.home, "proj-x")
        os.makedirs(other)
        os.makedirs(mine)
        p = os.path.join(mine, "HANDOFF.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(HANDOFF.format(v=1))
        run(AFTER_CLEAR, ["--mark", p], home=self.home, cwd=mine)
        stdin = json.dumps({"source": "startup", "cwd": other, "session_id": "s1"})
        self.assertEqual(run(AFTER_CLEAR, stdin=stdin, home=self.home, cwd=other).stdout, "")
        stdin = json.dumps({"source": "startup", "cwd": mine, "session_id": "s2"})
        self.assertIn("§0 text", run(AFTER_CLEAR, stdin=stdin, home=self.home, cwd=mine).stdout)

    def test_every_version_archived_and_greppable(self):
        """The 200-handoffs question: the main file is overwritten, old versions must stay archived and greppable."""
        for v in range(1, 6):
            p = self.write_handoff(v)
            r = run(AFTER_CLEAR, ["--mark", p], home=self.home, cwd=self.work)
            self.assertIn("Archived", r.stdout, r.stdout + r.stderr)
        with open(os.path.join(self.work, "HANDOFF.md"), encoding="utf-8") as f:
            self.assertNotIn("codeword-1", f.read())       # version 1 is gone from the main file
        hist = os.path.join(self.home, ".claude", "handoff-history")
        found = subprocess.run(["grep", "-rl", "codeword-1", hist], capture_output=True, text=True).stdout
        self.assertEqual(len(found.strip().splitlines()), 1, "version 1 should be archived exactly once")
        with open(os.path.join(hist, "index.tsv"), encoding="utf-8") as f:
            rows = [l.split("\t") for l in f.read().splitlines()]
        self.assertEqual([r[1] for r in rows], ["V1", "V2", "V3", "V4", "V5"])
        self.assertTrue(rows[0][3].startswith("Fix the login page, version 1"))

    def test_same_second_never_overwrites(self):
        p = self.write_handoff(7)
        for _ in range(3):
            run(AFTER_CLEAR, ["--mark", p], home=self.home, cwd=self.work)
        hist = os.path.join(self.home, ".claude", "handoff-history")
        files = [f for _, _, fs in os.walk(hist) for f in fs if f.endswith(".md")]
        self.assertEqual(len(files), 3)

    def test_bad_stdin_is_silent(self):
        r = run(AFTER_CLEAR, stdin="not json", home=self.home, cwd=self.work)
        self.assertEqual((r.returncode, r.stdout), (0, ""))


class Reminder(Base):
    def fire(self, ctx, model="claude-test", sid="s1", env=None):
        t = os.path.join(self.home, "t.jsonl")
        with open(t, "w") as f:
            f.write(assistant_line(ctx, model) + "\n")
        r = run(REMINDER, stdin=json.dumps({"hook_event_name": "PostToolUse", "session_id": sid,
                                            "transcript_path": t}), home=self.home, env_extra=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout else None

    def test_200k_default_fires_at_60_and_80_once_each(self):
        self.assertIsNone(self.fire(110_000))
        out = self.fire(125_000)
        self.assertIn("past the 60% line", out["hookSpecificOutput"]["additionalContext"])
        self.assertIn("Window assumed to be 200k", out["hookSpecificOutput"]["additionalContext"])
        self.assertIsNone(self.fire(130_000), "60% fires only once")
        self.assertIn("past the 80% line", self.fire(165_000)["hookSpecificOutput"]["additionalContext"])

    def test_ui_line_follows_lang_and_claude_is_told_to_match_user(self):
        en = self.fire(125_000, sid="en")
        self.assertIn("Context 62% used", en["systemMessage"])
        self.assertIn("Reply to the user in the language they write in", en["hookSpecificOutput"]["additionalContext"])
        self.assertIn("compact_now", en["hookSpecificOutput"]["additionalContext"], "with the mod, no /clear")
        zh = self.fire(125_000, sid="zh", env={"CLAUDE_HANDOFF_LANG": "zh"})
        self.assertIn("62%", zh["systemMessage"])
        self.assertNotIn("Context", zh["systemMessage"])

    def test_learns_1m_window_per_model(self):
        self.fire(250_000, model="big")                     # over 200k -> this model has a 1M window
        self.assertIsNone(self.fire(300_000, model="big", sid="s2"))   # 30%: no reminder
        out = self.fire(620_000, model="big", sid="s3")
        self.assertIn("62%", out["systemMessage"])
        self.assertNotIn("Window assumed", out["hookSpecificOutput"]["additionalContext"])
        self.assertIn("past the 60% line", self.fire(125_000, model="small", sid="s4")["hookSpecificOutput"]["additionalContext"])

    def test_env_overrides(self):
        self.assertIsNone(self.fire(125_000, env={"CLAUDE_CONTEXT_WINDOW": "1000000"}))

    def test_reset_after_compaction(self):
        self.fire(125_000)
        self.fire(40_000)                                   # dropped to 20% after compaction
        self.assertIsNotNone(self.fire(125_000), "re-armed after compaction")


class Scan(Base):
    def test_finds_transcript_by_cwd_field_when_slug_mismatch(self):
        d = os.path.join(self.home, ".claude", "projects", "name-does-not-match")
        os.makedirs(d)
        lines = [
            {"type": "user", "cwd": self.work, "timestamp": "2026-01-01T00:00:00Z", "message": {"content": "please fix the login page"}},
            {"type": "assistant", "cwd": self.work, "message": {"content": [{"type": "text", "text": "Fixed it. I haven't run the tests yet. Next I will deploy."}]}},
        ]
        with open(os.path.join(d, "x.jsonl"), "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(l, ensure_ascii=False, separators=(",", ":")) for l in lines))
        r = run(SCAN, home=self.home, cwd=self.work)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("please fix the login page", r.stdout)
        self.assertIn("I haven't run the tests yet", r.stdout)
        self.assertNotIn("Next I will deploy", r.stdout, "only the flagged sentence, not the whole message")


class ScanCompleteness(Base):
    def scan(self, lines):
        d = os.path.join(self.home, ".claude", "projects", "x")
        os.makedirs(d)
        with open(os.path.join(d, "x.jsonl"), "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(dict(l, cwd=self.work), ensure_ascii=False, separators=(",", ":")) for l in lines))
        r = run(SCAN, home=self.home, cwd=self.work)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_short_and_same_prefix_sentences_are_kept(self):
        prefix = "The migration script is written and it handles every table we listed except "
        out = self.scan([{"type": "assistant", "message": {"content": [{"type": "text", "text":
              "Untested. " + prefix + "orders, not verified. " + prefix + "users, not verified."}]}}])
        part2 = out.split("## 2.")[1]
        self.assertIn("Untested.", part2)
        self.assertIn("orders, not verified", part2)
        self.assertIn("users, not verified", part2)

    def test_user_text_starting_with_angle_bracket_is_kept(self):
        out = self.scan([
            {"type": "user", "message": {"content": "<!-- reply --> ship it"}},
            {"type": "user", "message": {"content": "<command-name>/handoff</command-name>"}},
        ])
        part1 = out.split("## 2.")[0]
        self.assertIn("ship it", part1)
        self.assertNotIn("command-name", part1)


class ScanChinese(Base):
    def test_flags_chinese_sentences_too(self):
        d = os.path.join(self.home, ".claude", "projects", "x")
        os.makedirs(d)
        with open(os.path.join(d, "x.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "assistant", "cwd": self.work, "message": {"content": [
                {"type": "text", "text": "\u6539\u597d\u4e86\u3002\u8fd8\u6ca1\u8dd1\u6d4b\u8bd5\u3002"}]}},
                ensure_ascii=False, separators=(",", ":")))
        r = run(SCAN, home=self.home, cwd=self.work)
        self.assertIn("\u8fd8\u6ca1\u8dd1\u6d4b\u8bd5", r.stdout)
        self.assertNotIn("\u6539\u597d\u4e86", r.stdout.split("## 2.")[1])


def old_hooks(home):
    """Hooks as install.py registered them, plus two that are not ours."""
    d = os.path.join(home, ".claude", "hooks")
    return {
        "SessionStart": [{"hooks": [{"type": "command", "command": "python3 %s/handoff_after_clear.py" % d}]}],
        "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "python3 %s/context_usage_reminder.py" % d},
                                        {"type": "command", "command": "python3 %s/mine.py" % d}]}],
        "PostToolUse": [{"hooks": [{"type": "command", "command": "python3 %s/context_usage_reminder.py" % d}],
                         "timeout": 5}],
        "Stop": [{"matcher": "", "hooks": [{"type": "command", "command": "echo %s/context_usage_reminder.py" % d}]}],
    }


def put_old_files(home, files=("hooks/handoff_after_clear.py", "hooks/context_usage_reminder.py")):
    marks = {"handoff_after_clear.py": "handoff-pointers", "context_usage_reminder.py": "context-reminder",
             "handoff_scan.py": "queued_command", "handoff.md": "HANDOFF_VERSION"}
    for rel in files:
        path = os.path.join(home, ".claude", rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write("# old copy: %s\n" % marks.get(os.path.basename(rel), ""))


class Legacy(Base):
    """An old install.py setup still registered next to the plugin: the plugin's copies stay silent."""

    def write_settings(self, data):
        os.makedirs(os.path.join(self.home, ".claude"), exist_ok=True)
        with open(os.path.join(self.home, ".claude", "settings.json"), "w", encoding="utf-8") as f:
            json.dump(data, f)

    def remind(self, script=REMINDER):
        t = os.path.join(self.home, "t.jsonl")
        with open(t, "w") as f:
            f.write(assistant_line(125_000) + "\n")
        return run(script, stdin=json.dumps({"hook_event_name": "PostToolUse", "session_id": "s1",
                                             "transcript_path": t}), home=self.home)

    def start(self, source="startup", env=None):
        return run(AFTER_CLEAR, stdin=json.dumps({"source": source, "cwd": self.work, "session_id": "s1"}),
                   home=self.home, cwd=self.work, env_extra=env)

    def test_reminder_is_silent_while_the_old_one_is_registered(self):
        put_old_files(self.home)
        self.write_settings({"hooks": old_hooks(self.home)})
        self.assertEqual(self.remind().stdout, "")

    def test_reminder_fires_when_only_unrelated_hooks_exist(self):
        put_old_files(self.home)
        self.write_settings({"hooks": {"Stop": old_hooks(self.home)["Stop"]}})   # `echo <our path>` is not ours
        self.assertIn("past the 60% line", self.remind().stdout)

    def test_registered_but_old_file_gone_the_plugin_reminds(self):
        self.write_settings({"hooks": old_hooks(self.home)})                      # no files on disk
        self.assertIn("past the 60% line", self.remind().stdout)

    def test_old_entry_with_a_matcher_does_not_count(self):
        put_old_files(self.home)
        h = old_hooks(self.home)
        for event in ("UserPromptSubmit", "PostToolUse"):
            h[event][0]["matcher"] = "Bash"
        self.write_settings({"hooks": h})
        self.assertIn("past the 60% line", self.remind().stdout)

    def test_the_old_copy_never_silences_itself(self):
        self.write_settings({"hooks": old_hooks(self.home)})
        old = os.path.join(self.home, ".claude", "hooks")
        os.makedirs(old)
        for name in ("context_usage_reminder.py", "legacy.py"):
            shutil.copy(os.path.join(ROOT, "hooks", name), old)
        self.assertIn("past the 60% line", self.remind(os.path.join(old, "context_usage_reminder.py")).stdout)

    def test_session_start_notice_and_no_double_injection(self):
        p = self.write_handoff(1)
        run(AFTER_CLEAR, ["--mark", p], home=self.home, cwd=self.work)
        put_old_files(self.home)
        self.write_settings({"hooks": old_hooks(self.home)})
        out = json.loads(self.start().stdout)
        self.assertIn("older install is still active", out["systemMessage"])
        self.assertIn("scripts/migrate.py", out["systemMessage"])
        self.assertNotIn("hookSpecificOutput", out, "the old SessionStart hook injects; the plugin must not")
        with open(os.path.join(self.home, ".claude", "handoff-pointers", os.listdir(
                os.path.join(self.home, ".claude", "handoff-pointers"))[0])) as f:
            self.assertNotIn("consumed_at", json.load(f), "the pointer is left for the old hook")
        zh = json.loads(self.start(env={"CLAUDE_HANDOFF_LANG": "zh"}).stdout)
        self.assertIn("旧的安装还在生效", zh["systemMessage"])

    def test_old_command_file_only_notice_plus_injection(self):
        p = self.write_handoff(1)
        run(AFTER_CLEAR, ["--mark", p], home=self.home, cwd=self.work)
        os.makedirs(os.path.join(self.home, ".claude", "commands"), exist_ok=True)
        open(os.path.join(self.home, ".claude", "commands", "handoff.md"), "w").write("HANDOFF_VERSION")
        out = json.loads(self.start().stdout)
        self.assertIn("commands/handoff.md", out["systemMessage"])
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertIn("Fix the login page", out["hookSpecificOutput"]["additionalContext"])
        self.assertNotIn("hookSpecificOutput", json.loads(self.start().stdout), "a pointer is used once")

    def test_old_plugin_enabled_is_reported(self):
        self.write_settings({"enabledPlugins": {"handoff-compact@claude-handoff": True}})
        self.assertIn("handoff-compact@claude-handoff", json.loads(self.start().stdout)["systemMessage"])

    def test_unwritable_pointer_still_injects(self):
        p = self.write_handoff(1)
        run(AFTER_CLEAR, ["--mark", p], home=self.home, cwd=self.work)
        d = os.path.join(self.home, ".claude", "handoff-pointers")
        ptr = os.path.join(d, [f for f in os.listdir(d) if f.endswith(".json")][0])
        os.chmod(ptr, 0o444)
        try:
            self.assertIn("Fix the login page", self.start().stdout)
        finally:
            os.chmod(ptr, 0o644)

    def test_no_notice_on_resume_and_nothing_without_leftovers(self):
        put_old_files(self.home)
        self.write_settings({"hooks": old_hooks(self.home)})
        self.assertEqual(self.start("resume").stdout, "")
        self.write_settings({})
        self.assertEqual(self.start().stdout, "")


class Migrate(Base):
    def setUp(self):
        super().setUp()
        self.claude = os.path.join(self.home, ".claude")
        put_old_files(self.home, ("commands/handoff.md", "commands/handoff_scan.py", "hooks/handoff_after_clear.py",
                                  "hooks/context_usage_reminder.py", "hooks/mine.py"))
        self.original = {"hooks": old_hooks(self.home), "env": {"CLAUDE_CONTEXT_WINDOW": "1000000"}, "model": "opus"}
        self.settings_path = os.path.join(self.claude, "settings.json")
        with open(self.settings_path, "w") as f:
            json.dump(self.original, f)

    def migrate(self, *args):
        # no `claude` on PATH: the uninstall step must fall back to printing the command
        return run(MIGRATE, list(args), home=self.home, env_extra={"PATH": "/usr/bin:/bin"})

    def settings(self):
        with open(self.settings_path, encoding="utf-8") as f:
            return json.load(f)

    def test_dry_run_lists_and_changes_nothing(self):
        before = open(self.settings_path).read()
        r = self.migrate()
        self.assertIn("Would change", r.stdout)
        self.assertIn("context_usage_reminder.py", r.stdout)
        self.assertEqual(open(self.settings_path).read(), before)
        self.assertTrue(os.path.isfile(os.path.join(self.claude, "commands", "handoff.md")))

    def test_apply_removes_only_ours_and_keeps_backups(self):
        r = self.migrate("--apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.settings()
        d = os.path.join(self.claude, "hooks")
        expected = old_hooks(self.home)
        del expected["SessionStart"]                       # an event left empty is dropped
        del expected["PostToolUse"]
        expected["UserPromptSubmit"][0]["hooks"] = [{"type": "command", "command": "python3 %s/mine.py" % d}]
        self.assertEqual(s["hooks"], expected, "only our entries go; everything else is unchanged")
        self.assertEqual((s["env"], s["model"]), (self.original["env"], self.original["model"]))
        backups = [f for f in os.listdir(self.claude) if f.startswith("settings.json.bak-handoff-")]
        self.assertEqual(len(backups), 1)
        with open(os.path.join(self.claude, backups[0])) as f:
            self.assertEqual(json.load(f), self.original)
        moved = [d for d in os.listdir(self.claude) if d.startswith("handoff-migrated-")]
        self.assertEqual(len(moved), 1)
        for rel in ("commands/handoff.md", "commands/handoff_scan.py", "hooks/handoff_after_clear.py",
                    "hooks/context_usage_reminder.py"):
            self.assertTrue(os.path.isfile(os.path.join(self.claude, moved[0], rel)), rel)
            self.assertFalse(os.path.exists(os.path.join(self.claude, rel)), rel)
        self.assertTrue(os.path.isfile(os.path.join(self.claude, "hooks", "mine.py")), "not ours, not moved")

    def test_second_run_finds_nothing(self):
        self.migrate("--apply")
        self.assertIn("Nothing to migrate", self.migrate("--apply").stdout)

    def test_foreign_files_with_our_names_are_left_alone(self):
        for rel in ("commands/handoff.md", "commands/handoff_scan.py"):
            with open(os.path.join(self.claude, rel), "w") as f:
                f.write("my own file")
        r = self.migrate("--apply")
        self.assertEqual(r.stdout.count("left alone"), 2)
        for rel in ("commands/handoff.md", "commands/handoff_scan.py"):
            self.assertTrue(os.path.isfile(os.path.join(self.claude, rel)), rel)

    def test_old_plugin_uninstall_falls_back_to_printing_the_command(self):
        s = dict(self.original, enabledPlugins={"handoff-compact@claude-handoff": True})
        with open(self.settings_path, "w") as f:
            json.dump(s, f)
        r = self.migrate("--apply")
        self.assertIn("claude plugin uninstall handoff-compact@claude-handoff --scope user", r.stdout)

    def test_invalid_settings_changes_nothing(self):
        with open(self.settings_path, "w") as f:
            f.write("{ not json")
        r = self.migrate("--apply")
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(os.path.isfile(os.path.join(self.claude, "commands", "handoff.md")))


class Manifest(unittest.TestCase):
    def load(self, *rel):
        with open(os.path.join(ROOT, *rel), encoding="utf-8") as f:
            return json.load(f)

    def test_one_version_and_the_marketplace_points_at_the_plugin(self):
        plugin = self.load(".claude-plugin", "plugin.json")
        entry = self.load(".claude-plugin", "marketplace.json")["plugins"]
        self.assertEqual([e["name"] for e in entry], [plugin["name"]])
        self.assertEqual(plugin["name"], "handoff", "the tool id mcp__handoff__compact_now depends on it")
        self.assertEqual(entry[0]["source"], "./")
        self.assertRegex(plugin["version"], r"^\d+\.\d+\.\d+$")
        # a version in the marketplace entry would win over plugin.json: keep exactly one
        self.assertNotIn("version", entry[0])

    def test_hooks_json_registers_exactly_the_three_hooks_and_the_module(self):
        hooks = self.load("hooks", "hooks.json")
        got = {event: [shlex.split(h["command"]) for g in groups for h in g["hooks"]]
               for event, groups in hooks["hooks"].items()}
        script = lambda name: [["python3", "${CLAUDE_PLUGIN_ROOT}/hooks/" + name]]
        self.assertEqual(got, {"SessionStart": script("handoff_after_clear.py"),
                               "UserPromptSubmit": script("context_usage_reminder.py"),
                               "PostToolUse": script("context_usage_reminder.py")})
        for argv in sum(got.values(), []):
            self.assertTrue(os.path.isfile(os.path.join(ROOT, argv[1].split("}/")[1])), argv)
        self.assertEqual(hooks["modules"], ["./register.ts"])
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "hooks", "register.ts")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
