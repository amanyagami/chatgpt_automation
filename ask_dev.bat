@echo off
REM Double-click this file:
REM   1. Reads the question from dev_question.txt
REM   2. PLAN phase: Claude Code plans it, ChatGPT reviews (PLAN READY /
REM      PLAN NOT READY) until approved
REM   3. IMPLEMENT phase: Claude Code implements it step by step, ChatGPT
REM      reviews (IMPLEMENTATION DONE / NOT DONE) until approved
REM   4. TEST & SHIP phase: Claude Code tests, fixes until green, commits,
REM      pushes, and opens a PR — fully unattended
REM   5. Everything is saved to runs\<timestamp>-<question>.json
REM
REM ⚠️ This makes REAL commits/pushes/PRs unattended. Only run it against a
REM repo/branch you're fully comfortable with an AI pushing to on its own.
REM See README.md before first use.
REM
REM Requires: claude CLI (logged in), gh CLI (authenticated), Edge.

cd /d "%~dp0"
python dev_loop.py
pause
