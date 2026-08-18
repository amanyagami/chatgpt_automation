@echo off
REM Double-click this file:
REM   1. Reads the question from question.txt
REM   2. Opens Edge (dedicated automation profile) and asks ChatGPT
REM   3. Appends the response below the question in question.txt
REM
REM First run: log in to ChatGPT in the Edge window that opens (once).
REM It's remembered after that via the edge_profile\ folder.

cd /d "%~dp0"
python ask_chatgpt.py
pause
