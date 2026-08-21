#!/usr/bin/env python3
"""
dev_loop.py — Plan -> Implement -> Test & Ship loop between Claude Code and
ChatGPT. Everything is recorded as ONE JSON file per question.

Default flow (double-click ask_dev.bat, or run with no args):

  PHASE 1 — Planning (ChatGPT-gated):
    Claude:  "<question>\n\nPlan for this, deep dive, and review if the plan
              is SOTA, optimal, complete, and reliable."
    ChatGPT: reviews the plan, replies ending in "PLAN READY" or
             "PLAN NOT READY" (+ feedback if not ready).
    If NOT READY: ChatGPT's feedback goes back to Claude (same session, via
    --resume) to revise the plan. Repeats until READY or --max-plan-rounds.

  PHASE 2 — Implementing (ChatGPT-gated):
    Claude:  "Do it step by step with checkpoints." (short — the approved
              plan is already in its session context via --resume)
    ChatGPT: reviews progress, replies ending in "IMPLEMENTATION DONE" or
             "IMPLEMENTATION NOT DONE".
    If NOT DONE: feedback goes back to Claude to continue. Repeats until
    DONE or --max-impl-rounds.

  PHASE 3 — Test & Ship (Claude-only, self-verifiable — no ChatGPT gate):
    Claude is told to test its work, fix+retest internally until tests
    pass (or determine a failure is pre-existing/unrelated), then commit,
    push, and open a PR. One long autonomous turn (Claude Code already
    natively loops fix/test within a session) rather than an
    orchestrator-driven loop, since passing tests is self-verifiable and
    doesn't need ChatGPT's judgment.

Everything (every turn's prompt, final output, and Claude's full raw
transcript for that turn) is written to runs/<timestamp>-<slug>.json as it
happens, so nothing is lost if it's interrupted.

Requires: the `claude` CLI installed & logged in, `gh` installed & authed
(for the PR step), and Edge (for ChatGPT review) — same prerequisites as
ask_claude_code.py / ask_chatgpt.py, whose code this reuses directly.

Usage:
    python dev_loop.py                              # uses ./dev_question.txt, --dir here
    python dev_loop.py myquestion.txt --dir "C:\\path\\to\\project"
    python dev_loop.py --max-plan-rounds 3 --max-impl-rounds 3
    python dev_loop.py --max-cost 5.0
    python dev_loop.py --model opus

⚠️ Phase 3 makes REAL, OUTWARD, HARD-TO-REVERSE changes: it commits, pushes
a branch, and opens a live PR, fully unattended, with the same
bypassPermissions full tool access as the rest of this project. Only point
--dir at a repo/branch you are fully comfortable with an AI pushing to and
opening PRs against on its own.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

import ask_claude_code as cc  # noqa: E402
import ask_chatgpt as gpt  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

DEFAULT_QUESTION_FILE = SCRIPT_DIR / "dev_question.txt"
DEFAULT_RUNS_DIR = SCRIPT_DIR / "runs"

PLAN_VERDICT_RE = re.compile(r"PLAN\s+(NOT\s+READY|READY)\b", re.IGNORECASE)
IMPL_VERDICT_RE = re.compile(r"IMPLEMENTATION\s+(NOT\s+DONE|DONE)\b", re.IGNORECASE)

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "plan": {"type": "string", "description": "The full plan / deep-dive, or the revised plan addressing reviewer feedback."},
        "notes_for_reviewer": {"type": "string", "description": "Anything specific you want the reviewer to double-check, or an empty string."},
    },
    "required": ["plan", "notes_for_reviewer"],
}

IMPLEMENTATION_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "What you did this turn and the current state of the implementation."},
        "notes_for_reviewer": {"type": "string", "description": "Anything specific you want the reviewer to double-check, or an empty string."},
    },
    "required": ["summary", "notes_for_reviewer"],
}

TEST_SHIP_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["PR_RAISED", "BLOCKED"], "description": "PR_RAISED if you opened a PR; BLOCKED if you could not (explain why in summary)."},
        "summary": {"type": "string", "description": "What you did: tests run, fixes made, and the outcome."},
        "pr_url": {"type": "string", "description": "The PR URL if PR_RAISED, else an empty string."},
    },
    "required": ["status", "summary", "pr_url"],
}


def slugify(text: str, max_len: int = 50) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len] or "question"


def strip_verdict(text: str, pattern: re.Pattern) -> str:
    return pattern.sub("", text or "").strip()


def parse_verdict(text: str, pattern: re.Pattern) -> str:
    matches = list(pattern.finditer(text or ""))
    if not matches:
        return "UNKNOWN"
    return matches[-1].group(1).upper().replace(" ", "_")  # "NOT READY" -> "NOT_READY"


def parse_json_field(answer_text, is_error: bool, fallback_key: str) -> dict:
    if is_error or answer_text is None:
        return {fallback_key: answer_text or "(no output)", "notes_for_reviewer": ""}
    try:
        obj = json.loads(answer_text)
        obj.setdefault("notes_for_reviewer", "")
        return obj
    except (json.JSONDecodeError, TypeError):
        return {fallback_key: answer_text, "notes_for_reviewer": ""}


# ---------- Phase 1: planning prompts ----------

def build_plan_prompt(question: str) -> str:
    return f"{question}\n\nPlan for this, deep dive, and review if the plan is SOTA, optimal, complete, and reliable."


def build_plan_revision_prompt(chatgpt_feedback: str) -> str:
    feedback = strip_verdict(chatgpt_feedback, PLAN_VERDICT_RE)
    return f"A reviewer (ChatGPT) reviewed your plan and responded:\n\n{feedback}\n\nRevise the plan to address this feedback, then resubmit. Respond in the same structured format."


def build_plan_review_prompt(plan: str, notes: str, first: bool) -> str:
    notes_block = f"NOTES FROM CLAUDE:\n{notes}\n\n" if notes.strip() else ""
    lead = "Here is a plan produced by Claude Code:" if first else "Claude has revised its plan based on your feedback:"
    return (
        f"{lead}\n\n{plan}\n\n{notes_block}"
        "Review the plan and decide PLAN READY or PLAN NOT READY, reviewing for SOTA-ness, "
        "completeness, optimality, and reliability. If not ready, give specific, actionable feedback "
        "on exactly what to change.\n\n"
        "End your reply with exactly one line, verbatim (no other text on that line):\n"
        "PLAN READY\nor\nPLAN NOT READY"
    )


# ---------- Phase 2: implementation prompts ----------

def build_implementation_start_prompt() -> str:
    return "The plan has been approved. Do it step by step with checkpoints."


def build_implementation_continue_prompt(chatgpt_feedback: str) -> str:
    feedback = strip_verdict(chatgpt_feedback, IMPL_VERDICT_RE)
    return f"A reviewer (ChatGPT) checked your progress and responded:\n\n{feedback}\n\nContinue the implementation, addressing this. Respond in the same structured format."


def build_implementation_review_prompt(summary: str, notes: str, first: bool) -> str:
    notes_block = f"NOTES FROM CLAUDE:\n{notes}\n\n" if notes.strip() else ""
    lead = "Claude Code has started implementing the approved plan. Progress so far:" if first else "Claude has continued the implementation. Updated progress:"
    return (
        f"{lead}\n\n{summary}\n\n{notes_block}"
        "Review this and decide IMPLEMENTATION DONE or IMPLEMENTATION NOT DONE (still needs more work). "
        "If not done, say specifically what's missing or needs fixing.\n\n"
        "End your reply with exactly one line, verbatim (no other text on that line):\n"
        "IMPLEMENTATION DONE\nor\nIMPLEMENTATION NOT DONE"
    )


# ---------- Phase 3: test & ship prompt ----------

def build_test_ship_prompt() -> str:
    return (
        "The implementation is approved. Now: run the test suite. If tests fail, fix the issues and "
        "re-test, repeating until they pass (or you determine a failure is pre-existing/unrelated to "
        "your change — note that explicitly if so). Once tests pass, commit your changes, push a "
        "branch, and open a pull request (e.g. via `gh pr create`) with a clear description of what "
        "changed and why. Report back with status PR_RAISED (and the PR URL) or BLOCKED (and explain "
        "exactly why — e.g. tests can't be made to pass, or a PR couldn't be created)."
    )


def run_claude_turn(prompt, cwd, model, permission_mode, timeout, session_id, schema, use_ide=True):
    """Runs one claude turn (fresh or --resume'd) and returns
    (events, answer_text, is_error, timed_out, new_session_id, cost_usd)."""
    events, stdout, stderr, returncode = cc.run_claude(
        prompt, cwd=cwd, model=model, permission_mode=permission_mode, timeout=timeout,
        resume_session_id=session_id, json_schema=schema, use_ide=use_ide,
    )
    timed_out = returncode is None
    answer, is_error, result_event = cc.extract_final_result(events)
    new_session_id = cc.extract_session_id(events) or session_id
    cost = (result_event or {}).get("total_cost_usd", 0) or 0
    return events, answer, is_error, timed_out, new_session_id, cost


def run_gated_phase(
    page, phase_name, first_claude_prompt, schema, output_key,
    build_review_prompt, build_revision_prompt, verdict_pattern, target_verdict,
    max_rounds, args, record, session_id, turn_counter, save,
):
    """Runs a Claude-turn -> ChatGPT-review loop for one phase. Mutates
    record['turns'] and calls save() after each turn. Returns
    (output_text, notes, session_id, total_cost, outcome_or_None) where
    outcome_or_None is set only if the phase failed to converge (error /
    max_cost / max_rounds hit) — None means it converged normally."""
    claude_prompt = first_claude_prompt
    total_cost = 0.0
    output_text, notes = "", ""

    for round_i in range(1, max_rounds + 1):
        events, answer, is_error, timed_out, session_id, cost = run_claude_turn(
            claude_prompt, args.dir, args.model, args.permission_mode, args.claude_timeout,
            session_id, schema, use_ide=not args.no_ide,
        )
        total_cost += cost
        data = parse_json_field(answer, is_error, fallback_key=output_key)
        output_text = data.get(output_key, answer or "")
        notes = data.get("notes_for_reviewer", "")

        record["turns"].append({
            "turn": turn_counter[0], "phase": phase_name, "actor": "claude",
            "prompt": claude_prompt, "final_output": output_text,
            "full_logs": events, "session_id": session_id, "cost_usd": cost,
            "is_error": is_error, "timed_out": timed_out,
        })
        turn_counter[0] += 1
        save()
        print(f"[{phase_name} round {round_i}] claude done (cost ${cost:.4f}, is_error={is_error}, timed_out={timed_out})")

        if is_error or timed_out:
            return output_text, notes, session_id, total_cost, "error"
        record["total_cost_usd"] = record.get("total_cost_usd", 0) + cost
        if record["total_cost_usd"] >= args.max_cost:
            return output_text, notes, session_id, total_cost, "max_cost"

        review_prompt = build_review_prompt(output_text, notes, round_i == 1)
        gpt.send_question(page, review_prompt)
        chatgpt_answer = gpt.wait_for_response(page, timeout_s=args.chatgpt_timeout)
        verdict = parse_verdict(chatgpt_answer, verdict_pattern)

        record["turns"].append({
            "turn": turn_counter[0], "phase": phase_name, "actor": "chatgpt",
            "prompt": review_prompt, "final_output": chatgpt_answer, "verdict": verdict,
        })
        turn_counter[0] += 1
        save()
        print(f"[{phase_name} round {round_i}] chatgpt verdict: {verdict}")

        if verdict == target_verdict:
            return output_text, notes, session_id, total_cost, None
        if round_i == max_rounds:
            return output_text, notes, session_id, total_cost, f"max_{phase_name}_rounds"

        claude_prompt = build_revision_prompt(chatgpt_answer)

    return output_text, notes, session_id, total_cost, f"max_{phase_name}_rounds"


def main():
    parser = argparse.ArgumentParser(description="Plan -> Implement -> Test & Ship loop between Claude Code and ChatGPT.")
    parser.add_argument("question_file", nargs="?", default=str(DEFAULT_QUESTION_FILE),
                         help="Path to a text file containing the question (default: ./dev_question.txt).")
    parser.add_argument("--dir", default=str(SCRIPT_DIR),
                         help="Working directory for Claude Code — the project it works on (default: this folder).")
    parser.add_argument("--runs-dir", default=str(DEFAULT_RUNS_DIR), help="Parent folder for run JSON files (default: ./runs).")
    parser.add_argument("--max-plan-rounds", type=int, default=5, help="Max planning review rounds (default: 5).")
    parser.add_argument("--max-impl-rounds", type=int, default=5, help="Max implementation review rounds (default: 5).")
    parser.add_argument("--max-cost", type=float, default=5.0, help="Max cumulative Claude Code cost in USD before giving up (default: 5.0).")
    parser.add_argument("--model", help="Model for Claude Code, e.g. 'sonnet', 'opus'.")
    parser.add_argument("--permission-mode", default="bypassPermissions",
                         choices=["bypassPermissions", "acceptEdits", "auto", "dontAsk", "plan", "manual"],
                         help="Permission mode for Claude Code (default: bypassPermissions).")
    parser.add_argument("--claude-timeout", type=int, default=600, help="Seconds per planning/implementation round (default: 600).")
    parser.add_argument("--test-ship-timeout", type=int, default=1800, help="Seconds for the test&ship turn — longer since Claude iterates fix/retest internally (default: 1800).")
    parser.add_argument("--chatgpt-timeout", type=int, default=180, help="Seconds to wait for each ChatGPT response (default: 180).")
    parser.add_argument("--attach", action="store_true", help="Attach to your already-open Edge instead of the separate automation profile (see README).")
    parser.add_argument("--headless", action="store_true", help="Run ChatGPT's browser with no visible window.")
    parser.add_argument(
        "--no-ide", action="store_true",
        help="Don't connect Claude Code to an open VS Code extension — force fully headless. "
             "By default it connects automatically if VS Code with the Claude Code extension is open.",
    )
    args = parser.parse_args()

    cc.check_claude_cli()
    question = cc.read_question(args.question_file)

    slug = slugify(question)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    Path(args.runs_dir).mkdir(parents=True, exist_ok=True)
    run_path = Path(args.runs_dir) / f"{stamp}-{slug}.json"

    record = {
        "question": question,
        "target_dir": args.dir,
        "started": datetime.now(timezone.utc).isoformat(),
        "turns": [],
        "total_cost_usd": 0.0,
        "outcome": None,
        "pr_url": None,
    }

    def save():
        run_path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")

    save()
    print(f"Run file: {run_path}")

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
        turn_counter = [1]

        # ---------- Phase 1: planning ----------
        print("\n=== PHASE 1: PLANNING ===")
        plan, plan_notes, session_id, cost1, outcome = run_gated_phase(
            page, "planning", build_plan_prompt(question), PLAN_SCHEMA, "plan",
            build_plan_review_prompt, build_plan_revision_prompt, PLAN_VERDICT_RE, "READY",
            args.max_plan_rounds, args, record, session_id, turn_counter, save,
        )
        if outcome:
            record["outcome"] = outcome
            save()
            print(f"\nStopped during planning: {outcome}")
            (page.close() if args.attach else context.close())
            return

        # ---------- Phase 2: implementing ----------
        print("\n=== PHASE 2: IMPLEMENTING ===")
        impl_summary, impl_notes, session_id, cost2, outcome = run_gated_phase(
            page, "implementing", build_implementation_start_prompt(), IMPLEMENTATION_SCHEMA, "summary",
            build_implementation_review_prompt, build_implementation_continue_prompt, IMPL_VERDICT_RE, "DONE",
            args.max_impl_rounds, args, record, session_id, turn_counter, save,
        )
        if outcome:
            record["outcome"] = outcome
            save()
            print(f"\nStopped during implementation: {outcome}")
            (page.close() if args.attach else context.close())
            return

        # ---------- Phase 3: test & ship (Claude-only, self-verifiable) ----------
        print("\n=== PHASE 3: TEST & SHIP ===")
        events, answer, is_error, timed_out, session_id, cost3 = run_claude_turn(
            build_test_ship_prompt(), args.dir, args.model, args.permission_mode,
            args.test_ship_timeout, session_id, TEST_SHIP_SCHEMA, use_ide=not args.no_ide,
        )
        record["total_cost_usd"] += cost3
        data = parse_json_field(answer, is_error, fallback_key="summary")
        status = data.get("status", "BLOCKED")
        pr_url = data.get("pr_url", "")
        summary_text = data.get("summary", answer or "")

        record["turns"].append({
            "turn": turn_counter[0], "phase": "testing", "actor": "claude",
            "prompt": build_test_ship_prompt(), "final_output": summary_text,
            "full_logs": events, "session_id": session_id, "cost_usd": cost3,
            "is_error": is_error, "timed_out": timed_out, "status": status, "pr_url": pr_url,
        })

        if is_error or timed_out:
            outcome = "error"
        elif status == "PR_RAISED":
            outcome = "pr_raised"
            record["pr_url"] = pr_url
        else:
            outcome = "blocked"

        record["outcome"] = outcome
        save()

        print(f"\n=== DONE: {outcome} ===")
        if outcome == "pr_raised":
            print(f"PR: {pr_url}")
        print(f"Total cost: ${record['total_cost_usd']:.4f}")
        print(f"Full run: {run_path}")

        if args.attach:
            page.close()
        else:
            context.close()


if __name__ == "__main__":
    main()
