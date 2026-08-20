# chatgpt_automation

Two question-in-a-file automations:

- **[ask.bat](ask.bat)** / `ask_chatgpt.py` — asks **ChatGPT** (via a real
  Edge browser) → [question.txt](question.txt)
- **[ask_claude.bat](ask_claude.bat)** / `ask_claude_code.py` — asks
  **Claude Code** (via the `claude` CLI, in a terminal) →
  [claude_question.txt](claude_question.txt)

Both follow the same pattern: edit the question file, double-click the
`.bat`, get the answer appended below your question in that same file.

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

### Usage

```
ask_claude.bat                                # double-click, or run from a terminal — uses claude_question.txt
python ask_claude_code.py                     # same thing, directly
python ask_claude_code.py myfile.txt          # use a different question file
python ask_claude_code.py --dir "C:\path\to\project"   # run it against a different project
python ask_claude_code.py --model sonnet      # pin a model
python ask_claude_code.py --timeout 600       # allow longer runs (default 300s)
python ask_claude_code.py --permission-mode plan   # never actually execute, just plan
```

### Notes

- `claude_logs.txt` grows with every run (one timestamped block each) —
  delete old entries if it gets too big.
- If a run times out or crashes, `claude_question.txt` still gets a
  `[No result — ...]` note so you notice, and whatever did happen is in
  `claude_logs.txt`.
