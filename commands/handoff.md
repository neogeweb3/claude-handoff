---
description: Condense this conversation into HANDOFF.md so you can /clear and say "continue" without losing details. Structured, keeps the user's own words verbatim, every claim verifiable, read-back enforced on resume. Every version is archived, so it is still searchable after 200 handoffs. (claude-handoff)
---

Condense the current conversation into HANDOFF.md at the root of the current working directory (if the working directory is `/` or `~`, write `~/HANDOFF-<timestamp>.md` instead).

**Language**: write the handoff in the language the user has been using in this conversation. Section headings stay as in the template below (the hooks look for `## §0` and `## §11`). §9 is always copied verbatim in whatever language the user wrote.

## Why this instead of /compact

`/compact` asks the model to rewrite the whole conversation as a narrative. Details get lost in the rewrite, and the ones lost are the ones that hurt most: "not done yet / not verified yet / only estimated", the reasons behind decisions, and which approaches were already proven not to work.
- Liu et al. 2023, "Lost in the Middle": accuracy drops by more than 30% when the relevant information sits in the middle of a long context. [arxiv.org/abs/2307.03172](https://arxiv.org/abs/2307.03172)
- Factory.ai compression benchmark: structured, incrementally merged summaries beat full rewrites. [factory.ai](https://factory.ai/news/evaluating-compression)
- The author's own same-state comparison: one session cut at the same point, one copy ran this command and one ran `/compact`, both scored against a 33-item checklist written in advance (max 66). Handoff 49 / 48, compact 39 / 38. Compaction lost the "not done / not verified" items and the reasons behind decisions, and turned already-answered questions into to-dos.

**What this command does instead**:
- **I-PASS** (NEJM 2014 clinical handoff protocol): the receiver reads the key points back before acting; high-quality handoffs went from 31% to 83%. [PMC9923540](https://pmc.ncbi.nlm.nih.gov/articles/PMC9923540/)
- **Codex hybrid compaction**: model summary plus the most recent user messages kept word for word. [compact.rs](https://github.com/openai/codex/blob/main/codex-rs/core/src/compact.rs)
- **Anchored merge**: each handoff builds on the previous version instead of being regenerated from scratch.
- **Sterile cockpit**: passing thoughts stay out of the handoff; durable rules go into CLAUDE.md or your memory system.

**Five design principles**:
1. Summary plus verbatim user messages, never paraphrase alone
2. Anchored merge across sessions
3. Every state claim carries a copy-pasteable `verify: <command>`
4. Ordered by severity (read-back → dead ends → blockers come first)
5. Passing thoughts stay out

## Step 0: is there a previous handoff?

```bash
ls HANDOFF.md 2>/dev/null && echo "anchored merge" || echo "fresh write"
```

**Anchored merge** (a previous version exists): read its version number → keep old §1 / §5 entries, tagged `(inherited from V<N-1>)` → rewrite §3 / §4 / §6 / §7 / §8 → roll §9 to the last 5 messages → regenerate §0 / §11. Bump V<N-1> → V<N>.

**Fresh write**: start at V1.

**Pruning**: drop §1 / §5 entries that have not mattered for 5+ sessions. No need to save them elsewhere: every full version is already archived under `~/.claude/handoff-history/` (see "Archive and lookup" at the end).

**First check the previous handoff belongs to this line of work**: read its header and `git log -1 --format='%h %s' -- HANDOFF.md`. If the topic or branch does not match, it belongs to another line of work: **do not merge, do not overwrite**. Write to `docs/handoff/<date>-<topic>.md` instead (or `HANDOFF-<topic>.md` if there is no docs/), and put that path in §11. (Origin: a HANDOFF.md at a repo root belonged to a different line of work and was overwritten without being read.)

**Then run the scan** (skip in emergency mode):

```bash
python3 ~/.claude/commands/handoff_scan.py
```

It pulls three things out of the transcript: all of the user's messages, every sentence where you said something is not done / not verified / pending, and the same kind of sentence from background agent results. Go through parts 2 and 3 one by one: what still holds goes into §2 or §10, what is stale is left out. **This is the category both handoffs and compaction most often lose.** Put the transcript path printed on the first line into §10.

## Before writing: 6 internal checks (not written into the file)

1. **Top 3 dead ends**: if the next session only reads CLAUDE.md and the task name, which 3 actions will it naturally reach for? Which of those are proven not to work (evidence: file:line / commit / command output / the user's words)?
2. **Blockers**: what is blocking progress? Whose decision is it waiting on?
3. **Decisions and emotional context**: did the user agree readily or reluctantly? How many times has this topic come up? How many times did the user push back, and what were the key words?
4. **Last 5 user messages ready verbatim**: including pushback, reversals and agreements. No paraphrase.
5. **Build / test status**: last green commit plus the command that verifies it.
6. **Fidelity self-assessment**: high / medium / low, with the basis and what may be missing.

## Timing check

You cannot see your own context percentage. **Do not estimate it**; an estimate is a made-up number. Set fidelity from what you can observe:
- No compaction notice seen in this session: fidelity high, verbatim messages come from the full context
- A compaction notice was seen: fidelity medium or lower; §10 says "earlier conversation was compacted, verbatim messages may be incomplete"
- You are writing because the user said context is running out: also medium; §10 says "triggered late, start earlier next time"

(The context usage hook reminds you at 60% / 80%. The number in that reminder is computed from the transcript, so you can quote it.)

## 🚨 Low-context emergency mode (overrides everything above)

**Trigger**: the user says anything like "context is about to run out / almost full / write the handoff now / stop". Enter emergency mode immediately: do not estimate percentages, do not ask.

**Precondition: long commands run in the background.** Anything expected to take more than 30 seconds (network transfers, remote scans, long test runs) must run in the background, otherwise the user's message and Interrupt cannot reach you until it finishes.

**Do exactly three steps and nothing else** (no git log, no scan, no memory updates, no self-review):
1. **One Write** of the handoff file. Target: `HANDOFF.md` if it does not exist or you already know it belongs to this line of work; otherwise `HANDOFF-<yyyymmdd-hhmm>.md` next to it (never overwrite a handoff you have not confirmed is yours). Order: §9 (copy the last 5 user messages straight from your context; this is the one thing that is gone once context is lost) → §0 → §1 → §2 → §4 → whatever else fits.
2. **One commit command** (inside a git repo): `git add <handoff file> && git commit -m "handoff V<N>"`.
3. **One command to leave the pointer and archive**: `python3 ~/.claude/hooks/handoff_after_clear.py --mark <absolute path to the handoff file>`, then tell the user: "type /clear, then say continue".

**Before writing §10, look at the start of your own context**: if it begins with a summary block like "This session is being continued from a previous conversation…", compaction has already happened. §10 says **fidelity low** and "this file is based on a compaction summary", and the raw transcript path goes into the first line of §2: `~/.claude/projects/<dir>/<sessionId>.jsonl`. **Never write "no compaction notice seen" without having looked.**

**After compaction, do not suggest starting a new session**: the context has already been reset, keep working where you are.

**Recovery afterwards** (context was reset and the user asks you to continue): rebuild §9 from the transcript JSONL. Entries with `type=user` whose `message.content` is a string are the user's messages; **messages queued while a task was running are not in type=user**, they are in the `prompt` of entries with `type=attachment` and `attachment.type=queued_command`; text blocks in `type=assistant` entries are your own replies, use them to recover numbers and loose ends the summary dropped. Tag it V<N+1>, with PRIOR_HANDOFF pointing to the previous version.

## File structure (11 sections, ordered by severity)

```markdown
<!--
HANDOFF_VERSION: V<N>
TIMESTAMP_UTC: <ISO 8601>
PRIOR_HANDOFF: <path or "none">
SESSION_PUSH_BACKS: <count>
SESSION_DECISION_OUTSOURCES: <count>
SESSION_LOOPS: <count>
-->

# HANDOFF — <date> <hh:mm> (V<N>)

> Prior chain: `<path to previous version>` or "First handoff"

---

## §0 🔁 Read-back Protocol (mandatory before any tool call)

The next session's first reply must **restate these 5 items word for word** (no paraphrase). Until it has, **no tool calls, no edits, no commits** (the hook injects this section's text into the new conversation, so this is possible; if the hook did not inject it, reading the handoff file is the only exception).

1. **Task**: "<copy §3 verbatim>"
2. **Most serious dead end**: "<copy the first item of §1 verbatim>"
3. **Current blocker**: "<copy §2 verbatim>"
4. **First resumption command**: `<copy the first item of §4 verbatim>`
5. **HEAD**: `<hash>` | verify: `git rev-parse HEAD`

---

## §1 ⚠️ Dead ends (proven not to work)

Ordered by how likely the next session is to walk into them. Every entry needs evidence.

- **Do not X** | Fails because: <file:line / commit / command / the user's words> | Re-check: `<cmd>`
- (Anchored merge: keep old entries, tagged `(inherited from V<N-1>)`)

---

## §2 🚧 Blockers / loose ends

- **Blocker X**: <description> | Needs: <who / what input>
- Work to hand to another session: **first line names the base branch + commit + "after opening the worktree, reset to it first"**. main is not necessarily the latest code; without this the receiver has to dig through every branch.

Or state explicitly "No blocker, go to §4".

---

## §3 🎯 Task

<one sentence>

**Acceptance**: <measurable criterion> | verify: `<cmd>`

---

## §4 🚀 Resumption commands (first 3–5, run in order)

1. `<cmd>` — expected: `<pattern>`
2. `<cmd>` — expected: `<pattern>`
3. `<cmd>` — expected: `<pattern>`

---

## §5 🎯 Decisions (with emotional context and history)

- **Chosen**: <X>
  - Reason: <evidence-backed reason>
  - History: Nth time this came up; previously chose Y / changed because Z
  - Agreement: readily / reluctantly (alternatives were worse)
  - Emotional: user pushed back N times on this, words: "<quote>"
  - Re-check: `<cmd>`
- **Rejected**: <Y> | <reason> | rejected N times
- (Anchored merge: old entries tagged `(inherited from V<N-1>)`)

---

## §6 📦 State (rewritten each time, every line verifiable)

One `<claim> | verify: <cmd>` per line:

- Working directory: `<path>` | verify: `pwd`
- Branch / HEAD: `<name>` / `<hash>` | verify: `git rev-parse HEAD`
- Uncommitted: <list> | verify: `git status --short`
- Background processes: <pid + log> | verify: `ps -p <pid>`
- Written to memory this session: <files> | verify: `ls <file>`
- Remote / external systems: <claim> | verify: `<check command>`

---

## §6b 🪤 Tool / environment traps (hit this session, will be hit again)

- <symptom> → <workaround> | Source: <exact error / command>
- Durable ones also go into CLAUDE.md or memory; list here only what the next session will run into. If none, write "None".

---

## §7 ✅ Build / test status

- Last green: `<hash>` | verify: `git log <hash>`
- Tests: pass / fail / n/a | verify: `<test cmd>`
- Failing tests: <list> | verify: `<test cmd> | grep FAIL`

---

## §8 📝 Files changed

| Path | What changed | Commit / status |
|------|------|-----------------|
| `<path>` | <one line> | `<hash>` or `uncommitted` |

(Mark uncommitted files explicitly; the git index is unreliable when several sessions run in parallel.)

---

## §9 📜 User messages (verbatim)

⚠️ When this conflicts with the paraphrase in §5, §9 wins.

**Copy the last 5 user messages word for word** (tone, pushback and reversals included). **No paraphrase, no summary, no bullet extraction.**

### Message [<turn N-4>] (<ISO timestamp>):
```
<original text; keep emoji, punctuation and tone>
```

### Message [<turn N-3>] (<ISO timestamp>):
```
<original text>
```

(5 messages, oldest first. Anchored merge: drop the old ones and keep the last 5; older messages are in the archive.)

---

## §10 🩺 Integrity self-check

- **Fidelity**: high / medium / low
- **Basis**: <N events / M verifiable claims / K verbatim messages / compaction notice seen or not>
- **May be missing**: <e.g. "earlier conversation was compacted" / "an output was truncated and cannot be quoted verbatim">
- **When not to trust this handoff**: if the next session finds <kind of information> missing or contradictory, do not trust the handoff; instead <action>
- **Transcript**: `<.jsonl path printed on the scan's first line>` (the user's exact words and all details can be found here)

---

## §11 🚀 Opening instruction for the next session

> "Read <absolute path to the handoff file> (V<N>). **Before any tool call**: restate the 5 items of §0 word for word. Then tell the user in one sentence that you have picked up the handoff, and get to work. Look at the first item of §1, the blockers in §2 and the first command in §4. **§9 is ground truth; when it conflicts with the paraphrase in §5, trust §9**. Anything in §2 marked 'needs the user's decision': ask the user first (one sentence plus your recommendation). Everything else that a verify command can settle, decide yourself instead of handing options to the user."
```

## After writing: 4-step self-audit (internal, not written into the file)

### Step 0 — do not say "done" until this passes

**Verbatim**:
- [ ] Version header complete (VERSION / TIMESTAMP / PRIOR / 3 counts)
- [ ] §9 has ≥ 5 verbatim messages, each with a timestamp and a code block
- [ ] Search §9 for `[paraphrased]` / `[summary]` → **0 hits**

**Structure**:
- [ ] §0 has all 5 items filled in
- [ ] §1 has ≥ 1 entry with evidence
- [ ] §2 has ≥ 1 entry, or says "No blocker"
- [ ] §3 acceptance is measurable and has a verify command
- [ ] §4 has ≥ 3 commands with expected output
- [ ] Every §5 entry has agreement, emotional context and a re-check command
- [ ] Every verify command in §6 / §7 runs as pasted
- [ ] Every §8 row has a commit hash or says `uncommitted`
- [ ] §10 has fidelity, basis, may-be-missing and when-not-to-trust
- [ ] §11 says "restate §0 word for word" and "§9 is ground truth"
- [ ] §11 does not contradict §2: anything §2 marks "needs the user's decision" must not be "decide yourself" in §11

**Coverage** (skip in emergency mode):
- [ ] Ran `handoff_scan.py` and went through parts 2 and 3
- [ ] §6b has entries or says "None"
- [ ] §10 has the transcript path
- [ ] Committed, if inside a git repo
- [ ] Ran `--mark` (pointer + archive) and told the user "type /clear, then say continue"

**Hygiene**:
- [ ] Search for `<placeholder>` / `<TODO>` / lines ending in `...` → **0 hits**
- [ ] Search for secrets (`api_key=` / `token=` / `Bearer` / `sk-` / `password=`) → **0 hits**
- [ ] No "thoughts / observations" section and no "narrative" section (that information is already in §5 + §9)
- [ ] Order: §0 → §1 → §2 first, §9 before §10

### Step 1 — every claim verifiable

Does every claim in §6 + §7 + §8 have a `verify:` command that runs as pasted? If not, add one or drop the claim.

### Step 2 — bypass test

For each §1 entry, write one sentence: "what reasoning would the next session use to get around this?" If that reasoning sounds plausible, add re-check commands until it no longer does.

### Step 3 — read-back test

Do the 5 items in §0 match the first item of §1, the first item of §2, §3 and the first command of §4 word for word? If not, fix §0.

If any step fails, fix the file and rerun all four steps until they pass.

## Last step: commit, archive, leave the pointer

🚨 **Skipping this means the handoff was not delivered.**

1. **Inside a git repo, commit**: `git add <handoff file> && git commit -m "handoff V<N>"`.
2. **Leave the pointer and archive**: `python3 ~/.claude/hooks/handoff_after_clear.py --mark <absolute path to the handoff file>`.
   It does two things:
   - Leaves a one-time pointer for the handoff's directory (valid for 24 hours, keyed by directory, never leaks into another project).
   - Copies this version into `~/.claude/handoff-history/`, append-only, and adds a line to `index.tsv` (time, version, directory, task).
3. Tell the user in one sentence where the handoff was written and which version it is, then: "Type `/clear`, then say continue, and we pick up from here. Nothing to copy."
4. **Do not paste §11**. When the new conversation starts, the SessionStart hook injects the handoff path plus the text of §0 and §11 automatically.
   If it did not pick up, check `~/.claude/handoff-pointers/hook.log` first.
   ⚠️ In the desktop app, `/clear` reaches the hook as source `startup`, not `clear`; the hook accepts both.

**When the user is moving to a different window, or asks for the opening prompt**: paste the whole §11 block into your reply as is. Do not change a word, do not summarize, do not say "see the file". The test of a good §11: after pasting it, the user picks up seamlessly.

## Archive and lookup

HANDOFF.md only keeps recent content (§9 has 5 messages, §3–§8 are rewritten each time). **Older details live in three places**:

| Where | What | How to search |
|---|---|---|
| `~/.claude/handoff-history/` | A full snapshot of every handoff version (saved by `--mark`, append-only) | `grep -rn "keyword" ~/.claude/handoff-history/`; to browse: `column -t -s $'\t' ~/.claude/handoff-history/index.tsv` |
| git history (when the handoff is in a git repo) | Every committed version | `git log -S "keyword" --oneline -- HANDOFF.md`, then `git show <hash>:HANDOFF.md` |
| `~/.claude/projects/*/*.jsonl` | Full raw transcripts (the most complete) | §10 of each handoff names its transcript; retention is set by `cleanupPeriodDays` in settings.json (default 30 days) |

When the user asks "how did we decide X back then / what did I say about Y", search in this order: archive → git history → raw transcripts. **If nothing turns up, say so and list where you searched.** Never fill the gap from impression.
