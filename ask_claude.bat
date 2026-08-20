@echo off
REM Double-click this file:
REM   1. Reads the question from claude_question.txt
REM   2. Runs it through the Claude Code CLI in this folder (full tool
REM      access, no permission prompts — see ask_claude_code.py docstring)
REM   3. Appends the final answer below the question in claude_question.txt
REM   4. Appends the full transcript (thinking/tool calls/tool results) to
REM      claude_logs.txt
REM
REM Requires the `claude` CLI already installed and logged in.

cd /d "%~dp0"
python ask_claude_code.py
pause
