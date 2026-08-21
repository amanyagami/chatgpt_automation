# chatgpt_automation

Write a question in a text file, double-click a `.bat` file, get an AI's
answer written back into that same file. Four tools, same idea, different
amount of automation:

| Double-click | Edit this file first | What happens |
|---|---|---|
| [`ask.bat`](ask.bat) | [`question.txt`](question.txt) | ChatGPT answers it (opens Edge) |
| [`ask_claude.bat`](ask_claude.bat) | [`claude_question.txt`](claude_question.txt) | Claude Code answers it (in a terminal) |
| [`ask_rca.bat`](ask_rca.bat) | [`rca_question.txt`](rca_question.txt) | Claude Code investigates, ChatGPT reviews it, back and forth until both agree |
| [`ask_dev.bat`](ask_dev.bat) | [`dev_question.txt`](dev_question.txt) | Claude Code plans → builds → tests → opens a PR, with ChatGPT reviewing each stage |

Start with `ask.bat` or `ask_claude.bat` if you're new here — they're the
simple, one-shot versions. `ask_rca.bat` and `ask_dev.bat` are the same
idea looped multiple times with a second AI checking the work.

Every script below also takes `--help` for its full list of options — this
README only covers what you'd actually need day to day.

## Setup, once

| For | You need |
|---|---|
| `ask.bat` | Nothing — it installs its one Python dependency itself the first time you run it. Just Python 3 and Microsoft Edge. |
| `ask_claude.bat`, `ask_rca.bat` | The [Claude Code CLI](https://docs.claude.com/en/docs/claude-code/setup) installed and logged in (`npm install -g @anthropic-ai/claude-code`, then run `claude` once) |
| `ask_dev.bat` | Everything above, **plus** [`gh`](https://cli.github.com/) (GitHub CLI) installed and logged in — it opens real pull requests |

**First run of `ask.bat`:** a Chrome-like Edge window opens — log in to
ChatGPT there once. It remembers you after that.

That's it — no other config files, no accounts to set up in this repo
itself.

---

## `ask.bat` — ask ChatGPT

1. Reads your question from `question.txt`.
2. Opens Edge (its own separate profile, not your everyday one) and asks
   ChatGPT.
3. Writes the answer back into `question.txt`, under a `--- Response ---`
   line.

```
ask.bat                              # just double-click it
python ask_chatgpt.py myfile.txt     # or run it on a different file
python ask_chatgpt.py --headless     # once logged in, no visible window
```

<details>
<summary>Advanced: reuse your everyday Edge instead of a separate profile</summary>

By default `ask.bat` uses its own dedicated Edge profile so it never
touches your regular browsing. If you'd rather it hop into your actual,
already-open Edge (new tab if open, launches Edge normally if not), that's
possible with `--attach`, but it needs one-time setup and is less
reliable — many work laptops block the browser flag it depends on.

1. Run `make_edge_debuggable.bat` once (edits your Edge shortcuts to add a
   debugging flag — Edge looks and behaves 100% normally either way).
2. Close all Edge windows so the next one you open picks up the change.
3. `python ask_chatgpt.py --attach`

If Edge ever gets reopened through a shortcut that wasn't patched, `--attach`
stops working until you close Edge and reopen it the patched way — if
that's annoying, just go back to plain `ask.bat`.
</details>

---

## `ask_claude.bat` — ask Claude Code

1. Reads your question from `claude_question.txt`.
2. Runs it through the `claude` CLI, right here in this folder, with full
   permission to read/edit files and run commands (see ⚠️ below).
3. Writes **only the final answer** back into `claude_question.txt`.
4. Writes the **full transcript** (every tool call, all the detail) to
   `claude_logs.txt`, so nothing's lost even though the question file stays
   short and readable.

```
ask_claude.bat
python ask_claude_code.py --dir "C:\path\to\a\project"   # ask it about a different folder
python ask_claude_code.py --model opus
```

> **⚠️ Full, unattended tool access.** There's no one there to click
> "approve," so this runs with every permission pre-granted
> (`--permission-mode bypassPermissions`) in whatever folder you point it
> at (`--dir`, default: this one). Only use it on something you trust —
> a scratch folder or a git repo you can diff/revert. Pass
> `--permission-mode plan` to make it look-but-never-touch instead.

If you have **VS Code open with the Claude Code extension**, every run
connects to it automatically — you'll see it work live in your editor.
Nothing to configure; harmless if VS Code isn't open. Add `--no-ide` to
skip this.

---

## `ask_rca.bat` — investigate, then get a second opinion

Like `ask_claude.bat`, but ChatGPT double-checks the answer before you see
it — and if it's not satisfied, they go back and forth until it is.

1. Claude Code investigates your question (`rca_question.txt`) — deep dive,
   root-cause analysis.
2. ChatGPT reviews it (same browser tab the whole run, so it remembers
   earlier rounds) and says `APPROVED` or `NEEDS_REVISION` + why.
3. If revision's needed, that feedback goes straight back to Claude (same
   session — it remembers its own prior work) to fix and resubmit.
4. Repeats until both sides agree it's done, or a safety cap hits:
   **5 rounds** or **$2** of Claude API spend, whichever first.

```
ask_rca.bat
python rca_loop.py --dir "C:\path\to\a\project"
python rca_loop.py --max-rounds 3 --max-cost 1.0   # tighter caps
```

Everything's saved to `runs/<timestamp>-<question>/conversation.md` — the
full round-by-round back-and-forth, readable top to bottom. If it hits a
cap without agreeing, that file shows exactly where it got stuck.

Same ⚠️ full-tool-access note as `ask_claude.bat` above — same default,
same reasoning.

---

## `ask_dev.bat` — plan it, build it, test it, ship it

The most automated of the four: Claude Code doesn't just answer your
question, it **implements** it and **opens a real pull request**.

1. **Plan** — Claude writes a plan; ChatGPT reviews it (`PLAN READY` /
   `PLAN NOT READY` + feedback) until approved.
2. **Build** — Claude implements it step by step; ChatGPT reviews progress
   (`IMPLEMENTATION DONE` / `NOT DONE`) until approved.
3. **Test & ship** — Claude runs the tests, fixes anything broken, commits,
   pushes a branch, and opens the PR itself. No review gate here — passing
   tests is something Claude can verify on its own.

```
ask_dev.bat
python dev_loop.py --dir "C:\path\to\a\project"
python dev_loop.py --max-cost 2.0
```

> **⚠️ This one pushes real commits and opens a real PR, fully
> unattended, with no pause to confirm first.** Only point `--dir` at a
> repo/branch you're genuinely fine with an AI committing to and opening a
> PR against on its own.

Everything (every prompt, every answer, Claude's full transcript per turn)
is saved to one file: `runs/<timestamp>-<question>.json`.

<details>
<summary>What's in the JSON file, and why this design</summary>

```json
{
  "question": "...",
  "turns": [
    {"turn": 1, "phase": "planning", "actor": "claude", "final_output": "<the plan>",
     "full_logs": [ /* Claude's real transcript for this turn, as actual JSON */ ], "cost_usd": 0.21},
    {"turn": 2, "phase": "planning", "actor": "chatgpt", "final_output": "...", "verdict": "NOT_READY"},
    { "...": "and so on, alternating claude/chatgpt through implementing, then one final testing turn" }
  ],
  "outcome": "pr_raised",
  "pr_url": "https://github.com/.../pull/42"
}
```

`outcome` is one of: `pr_raised`, `blocked` (couldn't get tests green or
open the PR — see the last turn), `error`, `max_cost`,
`max_planning_rounds`, `max_implementing_rounds`.

Each phase is driven turn-by-turn by this script (not one giant prompt
covering the whole pipeline) — every message is short and specific to
exactly what's needed right now, and Claude's own session memory
(`--resume`) carries the context forward instead of re-explaining it each
time. The one phase that *isn't* turn-by-turn is testing: Claude runs its
own fix→retest loop in a single long turn, because "do the tests pass" is
something it can check itself — it doesn't need ChatGPT's opinion the way
"is this plan good?" does.
</details>

---

## How the pieces underneath work (only if you're curious)

<details>
<summary>Permission modes</summary>

`ask_claude.bat`, `ask_rca.bat`, and `ask_dev.bat` all default to
`--permission-mode bypassPermissions` — Claude Code can read/edit files and
run shell commands without asking, because these run unattended and
there's no terminal for it to prompt in. Tighten this any time with
`--permission-mode plan` (look, never touch) or see `claude --help` for the
full list.
</details>

<details>
<summary>VS Code / --ide</summary>

Every Claude Code call in this repo passes `--ide` by default. If VS Code
is open with the Claude Code extension logged in, the session connects to
it automatically and you'll see the work happen live in your editor. If
VS Code isn't open, it's a no-op — confirmed by testing. Pass `--no-ide`
anywhere to force a fully headless run regardless.
</details>

<details>
<summary>Cost caps</summary>

`ask_rca.bat` and `ask_dev.bat` make real, repeated calls to Claude — each
tracks actual spend (from Claude Code's own reported cost) and stops once
it crosses `--max-cost` ($2 and $5 by default), rather than looping
forever if the two AIs never agree.
</details>

---

## Troubleshooting

- **"the 'claude' command wasn't found"** — install the Claude Code CLI
  (see Setup table above) and run `claude` once to log in.
- **A ChatGPT-involving script can't reach Edge** — close all Edge windows
  and try again; see the "Advanced" section under `ask.bat` above.
- **`claude_logs.txt` / `runs/` getting big** — safe to delete old entries;
  they're just history, nothing reads them back in.
- **OpenAI changed chatgpt.com and answers stopped coming through** — the
  page-reading logic in `ask_chatgpt.py` (`send_question` /
  `wait_for_response`) may need updating for the new page structure.
