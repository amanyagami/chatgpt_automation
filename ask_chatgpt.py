#!/usr/bin/env python3
"""
ask_chatgpt.py — default flow (just double-click ask.bat, or run with no args):
  1. Reads the question from question.txt (everything in the file).
  2. Opens Edge under a dedicated automation profile (edge_profile/,
     separate from your everyday Edge — log in there once, remembered after
     that).
  3. Submits the question to chatgpt.com and waits for the full response.
  4. Appends the response below the question, in the SAME file.

This is the reliable default: it doesn't depend on Edge already being open
in a particular way, doesn't touch your everyday browser shortcuts, and
isn't affected by corporate policies that block remote debugging.

Usage:
    python ask_chatgpt.py                       # uses ./question.txt, appends answer to it
    python ask_chatgpt.py myquestion.txt         # use a different file
    python ask_chatgpt.py question.txt --out answer.txt   # write answer elsewhere instead
    python ask_chatgpt.py --headless             # once logged in, no visible window

Advanced — reuse your actual everyday Edge (new tab if it's open, launch it
normally if not) instead of the separate profile above. Requires one-time
setup (see README.md "Advanced: attach to your everyday Edge") since
Chromium browsers can only be remote-controlled if started with a debugging
flag from the start:
    python ask_chatgpt.py --attach
"""

import argparse
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def _ensure_playwright_installed():
    """Auto-install the playwright package (one-time) if it's missing, so
    double-clicking ask.bat works on a fresh machine with no manual setup."""
    try:
        import playwright  # noqa: F401
        return
    except ImportError:
        pass
    print("First-time setup: installing the 'playwright' package (one-time, ~30s)...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "playwright"],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        sys.exit(
            "Failed to auto-install playwright.\n"
            f"Try running manually: {sys.executable} -m pip install playwright\n"
            f"({e})"
        )
    print("playwright installed.\n")


_ensure_playwright_installed()

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout  # noqa: E402

ISOLATED_PROFILE_DIR = Path(__file__).parent / "edge_profile"
DEFAULT_QUESTION_FILE = Path(__file__).parent / "question.txt"
CHAT_URL = "https://chatgpt.com/"
DEBUG_PORT = 9222

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def read_question(path: str) -> str:
    text = Path(path).read_text(encoding="utf-8").strip()
    if not text:
        sys.exit(f"Error: {path} is empty.")
    return text


def find_edge_exe() -> str:
    for candidate in EDGE_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return "msedge"  # fall back to whatever's on PATH


def cdp_is_up(cdp_url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{cdp_url}/json/version", timeout=1) as resp:
            return resp.status == 200
    except (urllib.error.URLError, ConnectionError, OSError):
        return False


def ensure_edge_with_debugging(cdp_url: str, wait_s: int = 25) -> bool:
    """If a debuggable Edge is already running, use it. Otherwise launch Edge
    normally (your real profile) with debugging enabled. Returns True once
    the CDP endpoint is reachable."""
    if cdp_is_up(cdp_url):
        print("Found your already-running Edge — opening a new tab in it.")
        return True

    print("Edge isn't running in debuggable mode — launching it normally...")
    edge_exe = find_edge_exe()
    try:
        subprocess.Popen([edge_exe, f"--remote-debugging-port={DEBUG_PORT}"])
    except OSError as e:
        print(f"Could not launch Edge ({edge_exe}): {e}", file=sys.stderr)
        return False

    deadline = time.time() + wait_s
    while time.time() < deadline:
        if cdp_is_up(cdp_url):
            return True
        time.sleep(0.5)
    return False


def wait_for_login(page):
    """Block until the composer (prompt textbox) is visible, i.e. user is logged in."""
    composer = page.locator('div#prompt-textarea, textarea#prompt-textarea')
    try:
        composer.first.wait_for(state="visible", timeout=5000)
        return
    except PWTimeout:
        pass
    print(
        "\nNot logged in yet (or page still loading).\n"
        "A browser tab is open — please log in to ChatGPT there.\n"
        "Waiting up to 5 minutes for the chat box to appear...\n"
    )
    composer.first.wait_for(state="visible", timeout=5 * 60 * 1000)


def send_question(page, question: str):
    composer = page.locator('div#prompt-textarea, textarea#prompt-textarea').first
    composer.click()
    composer.fill(question)
    page.keyboard.press("Enter")


def wait_for_response(page, timeout_s: int = 180) -> str:
    """Wait for the assistant to finish streaming, then return the last message text."""
    assistant_msgs = page.locator('[data-message-author-role="assistant"]')

    # Wait for at least one assistant message to appear.
    assistant_msgs.last.wait_for(state="visible", timeout=30_000)

    # Wait until the "stop generating" button disappears (streaming done),
    # by polling the message text until it stops changing.
    deadline = time.time() + timeout_s
    last_text = ""
    stable_count = 0
    while time.time() < deadline:
        current_text = assistant_msgs.last.inner_text()
        if current_text == last_text and current_text.strip():
            stable_count += 1
            if stable_count >= 3:  # unchanged for ~1.5s -> done streaming
                break
        else:
            stable_count = 0
        last_text = current_text
        time.sleep(0.5)

    return last_text.strip()


def main():
    parser = argparse.ArgumentParser(description="Ask ChatGPT a question from a file via browser automation.")
    parser.add_argument(
        "question_file",
        nargs="?",
        default=str(DEFAULT_QUESTION_FILE),
        help="Path to a text file containing the question (default: ./question.txt).",
    )
    parser.add_argument(
        "--out",
        help="Write the response to this file instead of appending it below the "
             "question in question_file.",
    )
    parser.add_argument("--timeout", type=int, default=180, help="Seconds to wait for a response (default: 180).")
    parser.add_argument(
        "--attach",
        action="store_true",
        help="Advanced: reuse your actual everyday Edge (new tab if it's already open, "
             "launch it normally if not) instead of the separate automation profile. "
             "Requires one-time setup — see README.md.",
    )
    parser.add_argument("--headless", action="store_true", help="Run with no visible window (only once already logged in).")
    parser.add_argument(
        "--cdp-url",
        default=f"http://localhost:{DEBUG_PORT}",
        help=f"CDP endpoint for your real Edge, only used with --attach (default: http://localhost:{DEBUG_PORT}).",
    )
    args = parser.parse_args()

    question = read_question(args.question_file)

    # Check Edge reachability BEFORE starting the Playwright driver, so a
    # failure here exits cleanly instead of leaving a half-started driver
    # connection behind (which prints noisy but harmless asyncio warnings).
    if args.attach and not ensure_edge_with_debugging(args.cdp_url):
        sys.exit(
            "\nCouldn't connect to your Edge.\n"
            "This usually means Edge is already running WITHOUT debugging enabled.\n"
            "Fix: close all Edge windows and try again, or run "
            "make_edge_debuggable.bat once so Edge always starts this way "
            "(see README.md).\n"
            "(Or drop --attach to use the separate automation profile instead — "
            "more reliable, no setup needed.)"
        )

    with sync_playwright() as p:
        if args.attach:
            browser = p.chromium.connect_over_cdp(args.cdp_url)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.new_page()
        else:
            ISOLATED_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            context = p.chromium.launch_persistent_context(
                str(ISOLATED_PROFILE_DIR),
                headless=args.headless,
                channel="msedge",
                viewport={"width": 1280, "height": 900},
            )
            page = context.pages[0] if context.pages else context.new_page()

        page.goto(CHAT_URL, wait_until="domcontentloaded")
        page.bring_to_front()

        wait_for_login(page)

        print("Sending question...")
        send_question(page, question)

        print("Waiting for response...")
        answer = wait_for_response(page, timeout_s=args.timeout)

        if not answer:
            print("Warning: got an empty response — the page structure may have changed.", file=sys.stderr)

        print("\n--- Response ---\n")
        print(answer)

        if args.out:
            Path(args.out).write_text(answer + "\n", encoding="utf-8")
            print(f"\nResponse written to {args.out}")
        else:
            with open(args.question_file, "a", encoding="utf-8") as f:
                f.write(f"\n\n--- Response ---\n\n{answer}\n")
            print(f"\nResponse appended to {args.question_file}")

        if args.attach:
            page.close()  # only close our tab — leave the rest of your browser alone
        else:
            context.close()


if __name__ == "__main__":
    main()
