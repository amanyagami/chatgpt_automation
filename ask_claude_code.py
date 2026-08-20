#!/usr/bin/env python3
"""
ask_claude_code.py — default flow (just double-click ask_claude.bat, or run
with no args):
  1. Reads the question from claude_question.txt.
  2. Runs it through the `claude` CLI (Claude Code) non-interactively, in
     this folder, with full tool access and no permission prompts (there's
     no one there to click "approve" — see "Permissions" below).
  3. Appends ONLY the final answer below the question, in claude_question.txt.
  4. Appends the full step-by-step transcript (thinking, tool calls, tool
     results, everything) to claude_logs.txt, under a timestamped header.

Requires the `claude` CLI already installed and logged in (this just shells
out to it — same as running `claude -p "..."` yourself in a terminal).

Usage:
    python ask_claude_code.py                        # uses ./claude_question.txt
    python ask_claude_code.py myquestion.txt          # use a different file
    python ask_claude_code.py --dir "C:\\path\\to\\project"   # run in a different project
    python ask_claude_code.py --model sonnet          # pin a model
    python ask_claude_code.py --timeout 600           # allow longer runs (default 300s)

Permissions:
    By default this runs with --permission-mode bypassPermissions, so Claude
    Code can freely read/edit files and run shell commands in --dir without
    asking. Only run this against a directory you fully trust. Use
    --permission-mode to tighten this (e.g. "plan" to only ever plan, never
    execute) — see `claude --help` for all choices.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DEFAULT_QUESTION_FILE = SCRIPT_DIR / "claude_question.txt"
DEFAULT_LOG_FILE = SCRIPT_DIR / "claude_logs.txt"


def read_question(path: str) -> str:
    text = Path(path).read_text(encoding="utf-8").strip()
    if not text:
        sys.exit(f"Error: {path} is empty.")
    return text


def check_claude_cli():
    if shutil.which("claude"):
        return
    sys.exit(
        "Error: the 'claude' command wasn't found on your PATH.\n"
        "Install Claude Code first: https://docs.claude.com/en/docs/claude-code/setup\n"
        "(npm install -g @anthropic-ai/claude-code — or the platform installer from that page),\n"
        "then run `claude` once to log in, and try again."
    )


def run_claude(
    question: str, cwd: str, model: str | None, permission_mode: str, timeout: int,
    resume_session_id: str | None = None, json_schema: dict | None = None,
):
    """Runs claude -p in stream-json mode and returns (events, raw_stdout, raw_stderr, returncode_or_None).

    resume_session_id: continue an existing session (same context) instead of starting fresh.
    json_schema: force structured output matching this JSON Schema — the final result's
                 "result" field will be a JSON string (json.loads it) instead of free text.
    """
    cmd = [
        "claude", "-p", question,
        "--permission-mode", permission_mode,
        "--output-format", "stream-json",
        "--verbose",
    ]
    if model:
        cmd += ["--model", model]
    if resume_session_id:
        cmd += ["--resume", resume_session_id]
    if json_schema:
        cmd += ["--json-schema", json.dumps(json_schema)]

    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
        )
        stdout, stderr, returncode = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as e:
        stdout = e.stdout or ""
        stderr = e.stderr or ""
        returncode = None  # timed out — process was killed

    events = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"type": "_unparsed_line", "raw": line})

    return events, stdout, stderr, returncode


def extract_final_result(events):
    """Returns (answer_text, is_error, result_event) from the final 'result' event, or (None, True, None)."""
    for event in reversed(events):
        if event.get("type") == "result":
            return event.get("result", ""), bool(event.get("is_error")), event
    return None, True, None


def extract_session_id(events):
    """Returns the session_id from the 'system'/'init' event, or None if not found."""
    for event in events:
        if event.get("type") == "system" and event.get("subtype") == "init":
            return event.get("session_id")
    return None


def format_transcript(question: str, events, stderr: str, returncode, timed_out: bool) -> str:
    """Builds a human-readable transcript block for the log file."""
    now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    lines = [
        "=" * 80,
        f"[{now}] Question:",
        question,
        "=" * 80,
        "",
    ]

    for event in events:
        etype = event.get("type")

        if etype in ("system", "rate_limit_event", "_unparsed_line"):
            continue  # noisy/uninteresting for a readable log

        if etype in ("assistant", "user"):
            content = (event.get("message") or {}).get("content")
            if isinstance(content, str):
                content = [{"type": "text", "text": content}]
            for block in content or []:
                btype = block.get("type")
                if btype == "text" and block.get("text", "").strip():
                    who = "assistant" if etype == "assistant" else "user"
                    lines.append(f"[{who}]\n{block['text'].strip()}\n")
                elif btype == "thinking" and block.get("thinking", "").strip():
                    lines.append(f"[thinking]\n{block['thinking'].strip()}\n")
                elif btype == "tool_use":
                    name = block.get("name", "?")
                    tool_input = json.dumps(block.get("input", {}), ensure_ascii=False)
                    lines.append(f"[tool call] {name}\n  input: {tool_input}\n")
                elif btype == "tool_result":
                    result_content = block.get("content", "")
                    if isinstance(result_content, list):
                        result_content = "\n".join(
                            b.get("text", "") for b in result_content if isinstance(b, dict)
                        )
                    marker = "ERROR" if block.get("is_error") else "result"
                    lines.append(f"[tool {marker}]\n{str(result_content).strip()}\n")

        elif etype == "result":
            status = event.get("subtype", "?")
            lines.append(
                "--- Summary ---\n"
                f"status: {status} | turns: {event.get('num_turns')} | "
                f"duration: {event.get('duration_ms', 0) / 1000:.1f}s | "
                f"cost: ${event.get('total_cost_usd', 0):.4f}\n"
            )

    if timed_out:
        lines.append(f"*** TIMED OUT — process was killed after no result. ***\n")
    if returncode not in (0, None):
        lines.append(f"*** claude exited with code {returncode} ***\n")
    if stderr.strip():
        lines.append(f"[stderr]\n{stderr.strip()}\n")

    lines.append("")  # trailing blank line before next run's block
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Ask Claude Code a question from a file; log the full run separately.")
    parser.add_argument(
        "question_file", nargs="?", default=str(DEFAULT_QUESTION_FILE),
        help="Path to a text file containing the question (default: ./claude_question.txt).",
    )
    parser.add_argument(
        "--dir", default=str(SCRIPT_DIR),
        help="Working directory for Claude Code — the project it operates on (default: this folder).",
    )
    parser.add_argument(
        "--log-file", default=str(DEFAULT_LOG_FILE),
        help="File to append the full transcript to (default: ./claude_logs.txt).",
    )
    parser.add_argument("--out", help="Write only the final answer to this file instead of appending to question_file.")
    parser.add_argument("--model", help="Model alias or name, e.g. 'sonnet', 'opus' (default: your configured default).")
    parser.add_argument(
        "--permission-mode", default="bypassPermissions",
        choices=["bypassPermissions", "acceptEdits", "auto", "dontAsk", "plan", "manual"],
        help="Permission mode passed to claude (default: bypassPermissions — no prompts, since this runs unattended).",
    )
    parser.add_argument("--timeout", type=int, default=300, help="Seconds to allow the run before killing it (default: 300).")
    args = parser.parse_args()

    check_claude_cli()
    question = read_question(args.question_file)

    print(f"Asking Claude Code (cwd={args.dir})...")
    events, stdout, stderr, returncode = run_claude(
        question, cwd=args.dir, model=args.model,
        permission_mode=args.permission_mode, timeout=args.timeout,
    )
    timed_out = returncode is None

    answer, is_error, result_event = extract_final_result(events)

    transcript = format_transcript(question, events, stderr, returncode, timed_out)
    with open(args.log_file, "a", encoding="utf-8") as f:
        f.write(transcript)
    print(f"Full transcript appended to {args.log_file}")

    if answer is None:
        answer = "[No result — the run may have timed out or crashed. Check the log file for details.]"
        is_error = True

    print("\n--- Final answer ---\n")
    print(answer)

    if is_error:
        print("\nWarning: this run reported an error — check claude_logs.txt for details.", file=sys.stderr)

    if args.out:
        Path(args.out).write_text(answer + "\n", encoding="utf-8")
        print(f"\nAnswer written to {args.out}")
    else:
        with open(args.question_file, "a", encoding="utf-8") as f:
            f.write(f"\n\n--- Response ---\n\n{answer}\n")
        print(f"\nAnswer appended to {args.question_file}")


if __name__ == "__main__":
    main()
