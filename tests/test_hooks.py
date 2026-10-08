#!/usr/bin/env python3
"""End-to-end tests for the scripts. Each case runs in a temporary HOME and never touches the real ~/.claude.

  python3 tests/test_hooks.py
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AFTER_CLEAR = os.path.join(ROOT, "hooks", "handoff_after_clear.py")
REMINDER = os.path.join(ROOT, "hooks", "context_usage_reminder.py")
SCAN = os.path.join(ROOT, "commands", "handoff_scan.py")
INSTALL = os.path.join(ROOT, "install.py")

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
    env.pop("CLAUDE_CONTEXT_WINDOW", None)
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


class Install(Base):
    def settings(self):
        with open(os.path.join(self.home, ".claude", "settings.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_merges_without_clobbering_and_is_idempotent(self):
        os.makedirs(os.path.join(self.home, ".claude"))
        with open(os.path.join(self.home, ".claude", "settings.json"), "w") as f:
            json.dump({"model": "x", "cleanupPeriodDays": 9999,
                       "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "echo mine"}]}]}}, f)
        for _ in range(2):
            r = run(INSTALL, ["--cleanup-days", "3650"], home=self.home)
            self.assertEqual(r.returncode, 0, r.stderr)
        s = self.settings()
        self.assertEqual(s["model"], "x")
        self.assertEqual(s["cleanupPeriodDays"], 9999, "never lower an existing longer retention")
        cmds = [h["command"] for g in s["hooks"]["SessionStart"] for h in g["hooks"]]
        self.assertEqual(len(cmds), 2, cmds)            # the existing one plus ours
        self.assertIn("echo mine", cmds)
        self.assertEqual(len(s["hooks"]["PostToolUse"]), 1)
        self.assertTrue(os.path.isfile(os.path.join(self.home, ".claude", "commands", "handoff.md")))

    def test_never_lowers_default_retention(self):
        r = run(INSTALL, ["--cleanup-days", "7"], home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("cleanupPeriodDays", self.settings())

    def test_hook_paths_with_spaces_are_quoted(self):
        spaced = os.path.join(self.home, "with space")
        os.makedirs(spaced)
        r = run(INSTALL, home=spaced)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(spaced, ".claude", "settings.json"), encoding="utf-8") as f:
            cmd = json.load(f)["hooks"]["SessionStart"][0]["hooks"][0]["command"]
        import shlex
        self.assertEqual(shlex.split(cmd)[1], os.path.join(spaced, ".claude", "hooks", "handoff_after_clear.py"))

    def test_refuses_foreign_handoff_without_force(self):
        d = os.path.join(self.home, ".claude", "commands")
        os.makedirs(d)
        with open(os.path.join(d, "handoff.md"), "w") as f:
            f.write("my own handoff")
        r = run(INSTALL, home=self.home)
        self.assertNotEqual(r.returncode, 0)
        with open(os.path.join(d, "handoff.md")) as f:
            self.assertEqual(f.read(), "my own handoff")
        self.assertEqual(run(INSTALL, ["--force"], home=self.home).returncode, 0)
        self.assertTrue(any(n.startswith("handoff.md.bak-") for n in os.listdir(d)))

    def test_dry_run_writes_nothing(self):
        run(INSTALL, ["--dry-run", "--cleanup-days", "3650"], home=self.home)
        self.assertFalse(os.path.exists(os.path.join(self.home, ".claude")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
