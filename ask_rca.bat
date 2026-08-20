@echo off
REM Double-click this file:
REM   1. Reads the question from rca_question.txt
REM   2. Claude Code investigates it (in this folder) and writes a
REM      structured RCA
REM   3. ChatGPT reviews it (same browser tab for the whole run)
REM   4. If ChatGPT wants changes, its feedback goes back to Claude Code
REM      (same session) and it revises — repeats until both agree it's
REM      done, or a safety cap is hit (5 rounds / $2 by default)
REM   5. Full history goes to runs\<timestamp>-<question>\conversation.md;
REM      the final answer is appended to rca_question.txt
REM
REM Requires: claude CLI installed & logged in, Edge installed.
REM First run: log in to ChatGPT in the Edge window that opens (once).

cd /d "%~dp0"
python rca_loop.py
pause
