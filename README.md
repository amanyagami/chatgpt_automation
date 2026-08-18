# chatgpt_automation

Double-click **`ask.bat`** and it will:
1. Read the question from [question.txt](question.txt).
2. Open Edge under a dedicated automation profile and submit it to
   chatgpt.com.
3. Wait for the full response.
4. Append the response below the question, in that same file.

Just edit `question.txt` with your question, save it, and double-click
`ask.bat`. Next time, edit it again (the old Q&A is still there above —
delete it if you don't want it piling up) and double-click again.

This uses a **separate, dedicated Edge profile** (`edge_profile/`) rather
than your everyday Edge — it's the reliable option: no shortcut editing,
not affected by corporate policies that block remote debugging, and not
dependent on Edge already being open in a particular way. The only cost is
logging in to ChatGPT once in that separate window.

## Setup

Nothing to install manually — `ask_chatgpt.py` auto-installs the
`playwright` Python package the first time it runs if it's missing (needs
Python 3 already installed, and internet access for that one-time
`pip install`). You'll see a short "First-time setup..." message once.

## First run

A visible Edge window opens. Log in to ChatGPT there, once — it's
remembered for every run after that (saved in `edge_profile/`).

## Usage

```
ask.bat                              # double-click, or run from a terminal — uses question.txt
python ask_chatgpt.py                # same thing, directly
python ask_chatgpt.py myfile.txt     # use a different question file
python ask_chatgpt.py question.txt --out answer.txt   # write the answer to a separate file instead
python ask_chatgpt.py --headless     # once logged in, no visible window
```

## Advanced: attach to your everyday Edge instead

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

## Notes

- Login is manual by design — automating ChatGPT's login (and any bot/CAPTCHA
  checks) isn't reliable and can violate OpenAI's terms.
- If OpenAI changes chatgpt.com's page structure, the CSS selectors in
  `ask_chatgpt.py` (`send_question` / `wait_for_response`) may need updating.
- `--timeout` controls how long (seconds) to wait for the response to finish
  streaming before giving up (default 180).
