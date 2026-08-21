# chatgpt_automation

Four question-in-a-file automations:

- **[ask.bat](ask.bat)** / `ask_chatgpt.py` — asks **ChatGPT** (via a real
  Edge browser) → [question.txt](question.txt)
- **[ask_claude.bat](ask_claude.bat)** / `ask_claude_code.py` — asks
  **Claude Code** (via the `claude` CLI, in a terminal) →
  [claude_question.txt](claude_question.txt)
- **[ask_rca.bat](ask_rca.bat)** / `rca_loop.py` — **Claude Code
  investigates, ChatGPT reviews, they go back and forth until both agree
  it's done** → [rca_question.txt](rca_question.txt)
- **[ask_dev.bat](ask_dev.bat)** / `dev_loop.py` — **Plan → Implement →
  Test & Ship**: Claude Code plans it, ChatGPT reviews the plan; Claude
  implements it, ChatGPT reviews the implementation; Claude tests, fixes,
  and opens a PR — all logged to one JSON file →
  [dev_question.txt](dev_question.txt)

The first two follow the same pattern: edit the question file, double-click
the `.bat`, get the answer appended below your question in that same file.
The last two build on them for multi-round loops — see their own sections
below.

---

## ask.bat — ask ChatGPT

1. Reads the question from `question.txt`.
2. Opens Edge under a dedicated automation profile and submits it to
   chatgpt.com.
3. Waits for the full response.
4. Appends the response below the question, in that same file.

This uses a **separate, dedicated Edge profile** (`edge_profile/`) rather
than your everyday Edge — it's the reliable option: no shortcut editing,
not affected by corporate policies that block remote debugging, and not
dependent on Edge already being open in a particular way. The only cost is
logging in to ChatGPT once in that separate window.

### Setup

Nothing to install manually — `ask_chatgpt.py` auto-installs the
`playwright` Python package the first time it runs if it's missing (needs
Python 3 already installed, and internet access for that one-time
`pip install`). You'll see a short "First-time setup..." message once.

### First run

A visible Edge window opens. Log in to ChatGPT there, once — it's
remembered for every run after that (saved in `edge_profile/`).

### Usage

```
ask.bat                              # double-click, or run from a terminal — uses question.txt
python ask_chatgpt.py                # same thing, directly
python ask_chatgpt.py myfile.txt     # use a different question file
python ask_chatgpt.py question.txt --out answer.txt   # write the answer to a separate file instead
python ask_chatgpt.py --headless     # once logged in, no visible window
```

### Advanced: attach to your everyday Edge instead

If you'd rather it reuse your actual, everyday Edge — new tab if it's
already open, launch it normally if not — that's possible with `--attach`,
but it's less reliable than the default above: it depends on a shortcut
hack (see caveats below) and on your machine allowing remote debugging at
all, which many corporate-managed Windows machines block by policy. Try the
default first; only reach for this if you specifically want to avoid a
separate login.

Chromium browsers can only be remote-controlled if they were started with a
debugging flag — that can't be turned on for a window that's already open.
So for "new tab if open / launch normally if not" to work against your
*real* Edge, your everyday Edge shortcut needs that flag baked in (Edge
looks and behaves 100% normally either way).

1. **Run `make_edge_debuggable.bat` once.** It edits your Taskbar/Desktop
   Edge shortcut(s) to always include ` --remote-debugging-port=9222`.
   (If you pin/launch Edge some other way, right-click that icon →
   Properties → Target, and append the same flag yourself.)
2. **Close all existing Edge windows** so the next one you open picks up
   the new shortcut.
3. Open Edge normally (Start Menu / Taskbar / Desktop icon), log in to
   ChatGPT if needed.
4. Run:
   ```
   python ask_chatgpt.py --attach
   ```
   It opens a new tab there, gets the answer, then closes only that tab —
   the rest of your browser is left alone.

**Caveat:** if Edge gets reopened later through a launch path that wasn't
patched (Start tile, "continue where you left off," a link clicked from
another app, etc.), it may come up without the flag again, and `--attach`
will fail until you close Edge and reopen it via a patched shortcut. If
this gets annoying, just drop back to the default (`ask.bat`, no flags).

### Notes

- Login is manual by design — automating ChatGPT's login (and any bot/CAPTCHA
  checks) isn't reliable and can violate OpenAI's terms.
- If OpenAI changes chatgpt.com's page structure, the CSS selectors in
  `ask_chatgpt.py` (`send_question` / `wait_for_response`) may need updating.
- `--timeout` controls how long (seconds) to wait for the response to finish
  streaming before giving up (default 180).

---

## ask_claude.bat — ask Claude Code

1. Reads the question from `claude_question.txt`.
2. Runs it through the `claude` CLI (Claude Code), non-interactively, in
   this folder — with full tool access (Bash, file edits, etc.) and no
   permission prompts, since there's no one there to approve anything.
3. Appends **only the final answer** below the question, in
   `claude_question.txt`.
4. Appends the **full transcript** — thinking, every tool call and its
   result, cost/duration summary — to `claude_logs.txt`, under a
   timestamped header, so nothing is lost even though the question file
   stays clean.

### ⚠️ Permissions — read this before using

By default this runs with `--permission-mode bypassPermissions`: Claude
Code can read/edit any file and run any shell command in the target
directory (`--dir`, default: this folder) **without asking**. That's the
whole point — there's no terminal for it to prompt in — but it means:

- **Only point `--dir` at something you fully trust.** Don't run this
  against a directory with anything you can't afford to have changed or
  deleted.
- Consider a scratch/throwaway project directory, or a git repo you can
  diff/revert, rather than anything important.
- To reduce risk without losing automation, pass a tighter
  `--permission-mode` (e.g. `plan` to only ever plan and never execute) —
  run `claude --help` for the full list of modes.

### Setup

Requires the [Claude Code CLI](https://docs.claude.com/en/docs/claude-code/setup)
already installed (`npm install -g @anthropic-ai/claude-code`, or the
platform installer from that page) and logged in — same as if you were
going to type `claude` in a terminal yourself. The script checks for this
and tells you exactly what's missing if not.

### VS Code integration

By default every run passes `--ide`: if you have **VS Code open with the
Claude Code extension** (logged in), the session automatically connects to
it — you'll see the work happen live in your editor (file edits, etc.),
same as using the extension directly, just driven by this script instead
of you typing. If VS Code isn't open, this is a harmless no-op — confirmed
by testing `--ide` with no IDE present, it just runs normally. Pass
`--no-ide` to force a fully headless run regardless.

This applies to `rca_loop.py` and `dev_loop.py` too — same flag, same
behavior, since they all share this same underlying `run_claude()` call.

### Usage

```
ask_claude.bat                                # double-click, or run from a terminal — uses claude_question.txt
python ask_claude_code.py                     # same thing, directly
python ask_claude_code.py myfile.txt          # use a different question file
python ask_claude_code.py --dir "C:\path\to\project"   # run it against a different project
python ask_claude_code.py --model sonnet      # pin a model
python ask_claude_code.py --timeout 600       # allow longer runs (default 300s)
python ask_claude_code.py --permission-mode plan   # never actually execute, just plan
python ask_claude_code.py --no-ide            # don't connect to VS Code even if it's open
```

### Notes

- `claude_logs.txt` grows with every run (one timestamped block each) —
  delete old entries if it gets too big.
- If a run times out or crashes, `claude_question.txt` still gets a
  `[No result — ...]` note so you notice, and whatever did happen is in
  `claude_logs.txt`.

---

## ask_rca.bat — Claude Code investigates, ChatGPT reviews, repeat until both agree

1. Reads the question from `rca_question.txt`.
2. **Round 1:** Claude Code investigates it in `--dir` (default: this
   folder) with the prompt *"\<question\>\n\nExplain the issue, DEEP dive and
   RCA."* — responding in a structured format (`status`, `rca`,
   `notes_for_reviewer`), so the loop can tell programmatically whether
   Claude itself considers it done.
3. Claude's RCA (plus a condensed, readable summary of which tools it used
   — not the raw noisy transcript) is sent to ChatGPT for review, in the
   **same browser tab for the whole run** (so ChatGPT keeps context of
   earlier rounds without re-pasting everything). ChatGPT is instructed to
   end its reply with `VERDICT: APPROVED` or `VERDICT: NEEDS_REVISION`.
4. **If either side isn't satisfied:** ChatGPT's feedback is fed back to
   Claude Code — same session, via `--resume`, so it keeps full context of
   its own prior investigation — as the next instruction, and another round
   starts.
5. **Stops** when Claude reports `status: DONE` *and* ChatGPT says
   `VERDICT: APPROVED` in the same round, or a safety cap is hit:
   `--max-rounds` (default 5) or `--max-cost` (default $2, tracked from
   Claude Code's real per-round cost).

### Output layout

```
runs/<timestamp>-<question-slug>/
  conversation.md        # readable, round-by-round narrative — read this one
  round1_claude.jsonl     # raw Claude Code transcript, round 1
  round1_chatgpt.txt       # raw ChatGPT reply, round 1
  round2_claude.jsonl, round2_chatgpt.txt, ...
```

The final RCA (converged, or the last attempt if a cap was hit) is also
appended to `rca_question.txt`, same convention as the other two scripts —
plus a pointer to the full `conversation.md` for that run.

### Usage

```
ask_rca.bat                                          # double-click, or run from a terminal
python rca_loop.py                                   # same thing, directly
python rca_loop.py myquestion.txt --dir "C:\path\to\project"
python rca_loop.py --max-rounds 3 --max-cost 1.0      # tighter caps
python rca_loop.py --model opus
```

### Notes

- **Permissions**: same `--permission-mode bypassPermissions` default as
  `ask_claude_code.py` — Claude Code has full, unattended tool access in
  `--dir` for potentially several rounds. Only point it at a folder you
  trust. See that script's section above for the full rationale.
- **This loop makes real, separate API calls to Claude each round** — cost
  is tracked and capped by `--max-cost`, but check the number feels right
  for your use before leaving it unattended on a hard problem.
- Two models reviewing each other can still disagree indefinitely on
  genuinely ambiguous questions — that's exactly what `--max-rounds` is
  for. If it hits the cap, `conversation.md` has the full back-and-forth so
  you can see where it got stuck and take it from there yourself.
- Reuses `ask_chatgpt.py`'s and `ask_claude_code.py`'s code directly (same
  Edge profile, same `claude` CLI invocation) — the `--attach` /
  `make_edge_debuggable.bat` option from the ChatGPT section works here too.

---

## ask_dev.bat — Plan → Implement → Test & Ship

A three-phase loop, everything recorded in **one JSON file** per question.

### ⚠️ Read this before using

Phase 3 makes **real, outward, hard-to-reverse changes**: it commits, pushes
a branch, and **opens a live pull request, fully unattended**, using the
same `bypassPermissions` full tool access as the rest of this project. Only
point `--dir` at a repo/branch you are genuinely comfortable with an AI
pushing to and opening PRs against on its own. There is no pause before
this happens by default.

### How it works

1. **PLAN** (`claude_question.txt` → Claude): *"\<question\>\n\nPlan for
   this, deep dive, and review if the plan is SOTA, optimal, complete, and
   reliable."* → ChatGPT reviews, replying `PLAN READY` or
   `PLAN NOT READY` (+ feedback). If not ready, the feedback goes back to
   Claude (same session, via `--resume`) to revise. Repeats until READY or
   `--max-plan-rounds` (default 5).
2. **IMPLEMENT**: Claude gets a short *"Do it step by step with
   checkpoints"* (the approved plan is already in its session context — no
   need to re-paste it). ChatGPT reviews progress, replying
   `IMPLEMENTATION DONE` or `IMPLEMENTATION NOT DONE`. Same feedback loop
   as planning, until DONE or `--max-impl-rounds` (default 5).
3. **TEST & SHIP**: one long, autonomous Claude turn (not orchestrator-gated
   — passing tests is self-verifiable, it doesn't need ChatGPT's opinion).
   Claude is told to run the tests, fix and re-test until they pass (or
   explain why a failure is pre-existing), then commit, push, and
   `gh pr create`.

Global safety net: `--max-cost` (default $5) stops the loop at any point if
cumulative Claude Code spend crosses it, before starting another round.

### Why turn-by-turn instead of one giant upfront prompt

The orchestrator (this script) tracks which phase it's in — not the model.
Each turn gets a short, explicit, self-contained instruction for exactly
the current step, leaning on `--resume` for memory instead of re-pasting
context. This is both cheaper and more reliable than one big prompt
up-front describing the whole pipeline and trusting the model to correctly
self-navigate phase transitions many turns later. The one exception is
Phase 3, which *is* one long autonomous turn — because Claude Code already
natively loops fix→test→retest within a session, and the "gate" there
(tests passing) doesn't need another model's judgment the way "is this
plan good?" does.

### Output: one JSON file

`runs/<timestamp>-<question-slug>.json`:

```json
{
  "question": "...",
  "target_dir": "...",
  "turns": [
    {"turn": 1, "phase": "planning", "actor": "claude",
     "prompt": "...", "final_output": "<the plan>",
     "full_logs": [ /* real nested JSON — parsed Claude transcript events for this turn */ ],
     "session_id": "...", "cost_usd": 0.21},
    {"turn": 2, "phase": "planning", "actor": "chatgpt",
     "prompt": "...", "final_output": "...", "verdict": "NOT_READY"},
    { "...": "more turns, alternating claude/chatgpt, through implementing" },
    {"turn": 9, "phase": "testing", "actor": "claude",
     "final_output": "...", "status": "PR_RAISED", "pr_url": "https://github.com/.../pull/42"}
  ],
  "total_cost_usd": 1.83,
  "outcome": "pr_raised",
  "pr_url": "https://github.com/.../pull/42"
}
```

`outcome` is one of: `pr_raised`, `blocked` (tests couldn't be made to
pass, or PR creation failed — see the last turn's `final_output`), `error`
(a Claude run crashed/timed out), `max_cost`, `max_planning_rounds`,
`max_implementing_rounds`.

### Usage

```
ask_dev.bat                                          # double-click, or run from a terminal
python dev_loop.py                                   # same thing, directly
python dev_loop.py myquestion.txt --dir "C:\path\to\project"
python dev_loop.py --max-plan-rounds 3 --max-impl-rounds 3
python dev_loop.py --max-cost 2.0
python dev_loop.py --model opus
```

### Notes

- Requires `gh` (GitHub CLI) installed and authenticated, in addition to
  `claude` and Edge — needed for the PR step in Phase 3.
- `runs/*.json` files can get large — full Claude transcripts (including
  every tool call and thinking block) are embedded per turn, by design, so
  the whole history is in one place. Not committed to git (`.gitignore`).
- If a phase never converges, ChatGPT's actual feedback for every round is
  still in the JSON — read the last few turns to see exactly where it got
  stuck.
- This is a different tool from `rca_loop.py`, not a replacement — use
  `ask_rca.bat` when you just want a reviewed explanation/investigation,
  and `ask_dev.bat` when you want actual code changes shipped as a PR.
