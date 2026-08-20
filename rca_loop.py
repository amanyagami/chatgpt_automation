#!/usr/bin/env python3
"""
rca_loop.py — automated RCA review loop between Claude Code and ChatGPT.

Default flow (double-click ask_rca.bat, or run with no args):
  1. Reads the question from rca_question.txt.
  2. Opens a Claude Code session in --dir (default: this folder) with the
     prompt: "<question>\n\nExplain the issue, DEEP dive and RCA."
     Claude responds in a structured format: {status, rca, notes_for_reviewer}.
  3. Sends Claude's RCA (plus a condensed summary of what tools it used) to
     ChatGPT, in the same browser tab for the whole run, asking it to review
     for correctness/completeness/optimality and end with a verdict line:
     VERDICT: APPROVED or VERDICT: NEEDS_REVISION.
  4. If either side isn't done: ChatGPT's feedback is fed back to Claude
     (same session, via --resume) as the next instruction, and round 2
     starts. Repeats until BOTH Claude says status=DONE and ChatGPT says
     VERDICT: APPROVED in the same round, or a safety cap is hit
     (--max-rounds, default 5; --max-cost, default $2).
  5. Everything goes to runs/<timestamp>-<question-slug>/:
       conversation.md       — readable, round-by-round narrative (read this)
       round{N}_claude.jsonl — raw Claude Code transcript for that round
       round{N}_chatgpt.txt  — raw ChatGPT reply for that round
     The final RCA (whatever it converged to, or the last attempt if it
     didn't) is also appended to rca_question.txt, matching the other
     scripts in this repo.

Requires: the `claude` CLI installed & logged in (see ask_claude_code.py),
and Edge (see ask_chatgpt.py) — this reuses both scripts' code directly.

Usage:
    python rca_loop.py                              # uses ./rca_question.txt, --dir here
    python rca_loop.py myquestion.txt --dir "C:\\path\\to\\project"
    python rca_loop.py --max-rounds 3 --max-cost 1.0
    python rca_loop.py --model opus

Permissions: same as ask_claude_code.py — defaults to
--permission-mode bypassPermissions (no prompts, full tool access in --dir,
since nobody's there to approve anything, for potentially several rounds).
Only point --dir at something you trust.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

import ask_claude_code as cc  # noqa: E402
import ask_chatgpt as gpt  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

DEFAULT_QUESTION_FILE = SCRIPT_DIR / "rca_question.txt"
DEFAULT_RUNS_DIR = SCRIPT_DIR / "runs"

RCA_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["DONE", "NEEDS_REVISION"],
            "description": "DONE if you're confident this RCA/answer is complete and correct as-is; "
                            "NEEDS_REVISION if you know it's incomplete or you're still working on it.",
        },
        "rca": {
            "type": "string",
            "description": "The full explanation / deep-dive / root-cause analysis — or, on a "
                            "revision round, the updated version addressing the reviewer's feedback.",
        },
        "notes_for_reviewer": {
            "type": "string",
            "description": "Anything specific you want the reviewer to double-check, or an empty string.",
        },
    },
    "required": ["status", "rca", "notes_for_reviewer"],
}

VERDICT_RE = re.compile(r"VERDICT:\s*(APPROVED|NEEDS_REVISION)", re.IGNORECASE)


def slugify(text: str, max_len: int = 50) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len] or "question"


def summarize_tool_activity(events, max_items: int = 12) -> str:
    """Condensed, human-readable tool-call list (name + short input) for the
    reviewer — deliberately NOT the raw JSONL/thinking blocks, which are
    noisy and not useful to paste into a review."""
    lines = []
    for event in events:
        if event.get("type") != "assistant":
            continue
        for block in (event.get("message") or {}).get("content") or []:
            if block.get("type") == "tool_use":
                name = block.get("name", "?")
                inp_str = json.dumps(block.get("input", {}), ensure_ascii=False)
                if len(inp_str) > 150:
                    inp_str = inp_str[:150] + "..."
                lines.append(f"- {name}: {inp_str}")
    if not lines:
        return "(no tool calls)"
    if len(lines) > max_items:
        omitted = len(lines) - max_items
        lines = lines[:max_items] + [f"... ({omitted} more tool calls omitted; see the round's .jsonl log for full detail)"]
    return "\n".join(lines)


def parse_claude_structured(answer_text, is_error):
    """Returns (status, rca, notes). Falls back gracefully if the structured output didn't parse."""
    if is_error or answer_text is None:
        return "NEEDS_REVISION", answer_text or "(no output)", ""
    try:
        obj = json.loads(answer_text)
        return (
            obj.get("status", "NEEDS_REVISION"),
            obj.get("rca", answer_text),
            obj.get("notes_for_reviewer", ""),
        )
    except (json.JSONDecodeError, TypeError):
        return "NEEDS_REVISION", answer_text, ""


def parse_chatgpt_verdict(answer_text: str) -> str:
    match = None
    for match in VERDICT_RE.finditer(answer_text or ""):
        pass  # take the LAST match, in case an example is mentioned earlier in the reply
    return match.group(1).upper() if match else "UNKNOWN"


def build_claude_prompt(question: str) -> str:
    return f"{question}\n\nExplain the issue, DEEP dive and RCA."


def build_claude_revision_prompt(chatgpt_feedback: str) -> str:
    feedback_text = VERDICT_RE.sub("", chatgpt_feedback).strip()
    return (
        "A reviewer (ChatGPT) has reviewed your analysis and responded with the following feedback:\n\n"
        f"{feedback_text}\n\n"
        "Please address this feedback and revise your analysis accordingly. "
        "Respond again in the same structured format."
    )


def build_first_review_prompt(question: str, rca: str, notes: str, tool_summary: str) -> str:
    notes_block = f"NOTES FROM CLAUDE FOR YOU:\n{notes}\n\n" if notes.strip() else ""
    return (
        "You are reviewing a root-cause analysis produced by another AI (Claude Code) "
        "that investigated the following:\n\n"
        f"QUESTION:\n{question}\n\n"
        f"CLAUDE'S ANALYSIS / RCA:\n{rca}\n\n"
        f"{notes_block}"
        f"TOOLS IT USED WHILE INVESTIGATING:\n{tool_summary}\n\n"
        "Review this for correctness, completeness, and optimality — is anything wrong, missing, "
        "overcomplicated, or is there a simpler/more likely explanation it missed? If it's solid, "
        "approve it. If not, give specific, actionable feedback on exactly what to fix or investigate further.\n\n"
        "End your reply with exactly one line, verbatim (no other text on that line):\n"
        "VERDICT: APPROVED\n"
        "or\n"
        "VERDICT: NEEDS_REVISION"
    )


def build_followup_review_prompt(rca: str, notes: str) -> str:
    notes_block = f"NOTES FROM CLAUDE FOR YOU:\n{notes}\n\n" if notes.strip() else ""
    return (
        "Claude has revised its analysis based on your feedback:\n\n"
        f"{rca}\n\n"
        f"{notes_block}"
        "Please review the revision. Same rules as before — if it's solid now, approve it; "
        "if not, give specific actionable feedback.\n\n"
        "End your reply with exactly one line, verbatim (no other text on that line):\n"
        "VERDICT: APPROVED\n"
        "or\n"
        "VERDICT: NEEDS_REVISION"
    )


def append_md(path: Path, text: str):
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)


def main():
    parser = argparse.ArgumentParser(
        description="RCA review loop: Claude Code investigates, ChatGPT reviews, repeat until both agree it's done."
    )
    parser.add_argument(
        "question_file", nargs="?", default=str(DEFAULT_QUESTION_FILE),
        help="Path to a text file containing the question (default: ./rca_question.txt).",
    )
    parser.add_argument(
        "--dir", default=str(SCRIPT_DIR),
        help="Working directory for Claude Code — the project it investigates (default: this folder).",
    )
    parser.add_argument(
        "--runs-dir", default=str(DEFAULT_RUNS_DIR),
        help="Parent folder for per-question run folders (default: ./runs).",
    )
    parser.add_argument("--max-rounds", type=int, default=5, help="Max review rounds before giving up (default: 5).")
    parser.add_argument("--max-cost", type=float, default=2.0, help="Max cumulative Claude Code cost in USD before giving up (default: 2.0).")
    parser.add_argument("--model", help="Model for Claude Code, e.g. 'sonnet', 'opus'.")
    parser.add_argument(
        "--permission-mode", default="bypassPermissions",
        choices=["bypassPermissions", "acceptEdits", "auto", "dontAsk", "plan", "manual"],
        help="Permission mode for Claude Code (default: bypassPermissions).",
    )
    parser.add_argument("--claude-timeout", type=int, default=300, help="Seconds to allow each Claude round (default: 300).")
    parser.add_argument("--chatgpt-timeout", type=int, default=180, help="Seconds to wait for each ChatGPT response (default: 180).")
    parser.add_argument("--attach", action="store_true", help="Attach to your already-open Edge instead of the separate automation profile (see README).")
    parser.add_argument("--headless", action="store_true", help="Run ChatGPT's browser with no visible window.")
    args = parser.parse_args()

    cc.check_claude_cli()
    question = cc.read_question(args.question_file)

    slug = slugify(question)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = Path(args.runs_dir) / f"{stamp}-{slug}"
    run_dir.mkdir(parents=True, exist_ok=True)
    conversation_path = run_dir / "conversation.md"

    append_md(
        conversation_path,
        f"# RCA review loop\n\n"
        f"**Question:** {question}\n\n"
        f"**Target dir:** {args.dir}\n\n"
        f"**Started:** {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n---\n\n",
    )
    print(f"Run folder: {run_dir}")

    with sync_playwright() as p:
        if args.attach:
            cdp_url = f"http://localhost:{gpt.DEBUG_PORT}"
            if not gpt.ensure_edge_with_debugging(cdp_url):
                sys.exit("Couldn't connect to Edge for --attach. See README.md.")
            browser = p.chromium.connect_over_cdp(cdp_url)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.new_page()
        else:
            gpt.ISOLATED_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            context = p.chromium.launch_persistent_context(
                str(gpt.ISOLATED_PROFILE_DIR), headless=args.headless, channel="msedge",
                viewport={"width": 1280, "height": 900},
            )
            page = context.pages[0] if context.pages else context.new_page()

        page.goto(gpt.CHAT_URL, wait_until="domcontentloaded")
        page.bring_to_front()
        gpt.wait_for_login(page)

        session_id = None
        total_cost = 0.0
        claude_prompt = build_claude_prompt(question)
        final_rca = None
        outcome = None  # "converged" | "max_rounds" | "max_cost" | "error"

        for round_num in range(1, args.max_rounds + 1):
            print(f"\n=== Round {round_num}: Claude Code ===")
            events, stdout, stderr, returncode = cc.run_claude(
                claude_prompt, cwd=args.dir, model=args.model,
                permission_mode=args.permission_mode, timeout=args.claude_timeout,
                resume_session_id=session_id, json_schema=RCA_SCHEMA,
            )
            timed_out = returncode is None
            answer, is_error, result_event = cc.extract_final_result(events)
            session_id = cc.extract_session_id(events) or session_id
            round_cost = (result_event or {}).get("total_cost_usd", 0) or 0
            total_cost += round_cost

            (run_dir / f"round{round_num}_claude.jsonl").write_text(stdout, encoding="utf-8")

            status, rca, notes = parse_claude_structured(answer, is_error)
            tool_summary = summarize_tool_activity(events)
            final_rca = rca

            append_md(
                conversation_path,
                f"## Round {round_num} — Claude Code (status: {status}, cost: ${round_cost:.4f}, cumulative: ${total_cost:.4f})\n\n"
                f"{rca}\n\n"
                + (f"**Notes for reviewer:** {notes}\n\n" if notes.strip() else "")
                + f"<details><summary>Tools used</summary>\n\n```\n{tool_summary}\n```\n\n</details>\n\n---\n\n",
            )
            print(f"Claude status: {status} | cost this round: ${round_cost:.4f} | cumulative: ${total_cost:.4f}")

            if is_error or timed_out:
                outcome = "error"
                append_md(conversation_path, f"**Stopped: Claude Code run failed or timed out.** See round{round_num}_claude.jsonl.\n\n")
                break
            if total_cost >= args.max_cost:
                outcome = "max_cost"
                append_md(conversation_path, f"**Stopped: hit max cost (${args.max_cost}).**\n\n")
                break

            print(f"=== Round {round_num}: ChatGPT review ===")
            review_prompt = (
                build_first_review_prompt(question, rca, notes, tool_summary)
                if round_num == 1 else
                build_followup_review_prompt(rca, notes)
            )
            gpt.send_question(page, review_prompt)
            chatgpt_answer = gpt.wait_for_response(page, timeout_s=args.chatgpt_timeout)
            (run_dir / f"round{round_num}_chatgpt.txt").write_text(chatgpt_answer, encoding="utf-8")

            verdict = parse_chatgpt_verdict(chatgpt_answer)
            append_md(
                conversation_path,
                f"## Round {round_num} — ChatGPT review (verdict: {verdict})\n\n{chatgpt_answer}\n\n---\n\n",
            )
            print(f"ChatGPT verdict: {verdict}")

            if status == "DONE" and verdict == "APPROVED":
                outcome = "converged"
                break
            if round_num == args.max_rounds:
                outcome = "max_rounds"
                break

            claude_prompt = build_claude_revision_prompt(chatgpt_answer)

        summaries = {
            "converged": "\u2705 Converged \u2014 both Claude Code and ChatGPT agree this is done.",
            "max_rounds": f"\u26a0\ufe0f Stopped after {args.max_rounds} rounds without both sides agreeing.",
            "max_cost": f"\u26a0\ufe0f Stopped \u2014 hit the ${args.max_cost} cost cap.",
            "error": "\u274c Stopped \u2014 Claude Code run failed or timed out.",
        }
        summary = summaries[outcome]
        append_md(conversation_path, f"## Outcome\n\n{summary}\n\nTotal cost: ${total_cost:.4f}\n")

        print(f"\n{summary}")
        print(f"Total cost: ${total_cost:.4f}")
        print(f"Full conversation: {conversation_path}")

        with open(args.question_file, "a", encoding="utf-8") as f:
            f.write(
                f"\n\n--- Response ({outcome}) ---\n\n{final_rca}\n\n"
                f"(Full review history: {conversation_path})\n"
            )

        if args.attach:
            page.close()
        else:
            context.close()


if __name__ == "__main__":
    main()
