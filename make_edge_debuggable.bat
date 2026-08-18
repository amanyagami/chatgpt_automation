@echo off
REM One-time setup: makes Edge always start with remote debugging enabled,
REM so ask_chatgpt.py can find your normal, already-open Edge and add a tab
REM to it (or launch Edge normally if it isn't running). Edge looks and
REM behaves completely normally either way — this only adds a hidden flag.
REM
REM What this does: edits the target of your Edge Start Menu / Taskbar
REM shortcuts to append " --remote-debugging-port=9222", so however you
REM normally open Edge, debugging is already on.
REM
REM Safe to re-run. Requires closing Edge once for the change to take effect
REM on windows already open.

setlocal enabledelayedexpansion
set "PORT=9222"

set "TARGETS=%APPDATA%\Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar\Microsoft Edge.lnk"
set "TARGETS2=%USERPROFILE%\Desktop\Microsoft Edge.lnk"

echo This will update your Edge shortcuts to always enable remote debugging
echo (port %PORT%) so ask_chatgpt.py can attach to your normal Edge window.
echo.
echo Close all Edge windows now, then press any key to continue...
pause >nul

powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$paths = @('%APPDATA%\Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar\Microsoft Edge.lnk', '%USERPROFILE%\Desktop\Microsoft Edge.lnk');" ^
  "foreach ($p in $paths) {" ^
  "  if (Test-Path $p) {" ^
  "    $sc = $ws.CreateShortcut($p);" ^
  "    if ($sc.Arguments -notmatch 'remote-debugging-port') {" ^
  "      $sc.Arguments = ($sc.Arguments + ' --remote-debugging-port=%PORT%').Trim();" ^
  "      $sc.Save();" ^
  "      Write-Host ('Updated: ' + $p)" ^
  "    } else {" ^
  "      Write-Host ('Already set: ' + $p)" ^
  "    }" ^
  "  }" ^
  "}"

echo.
echo Done. Open Edge normally from now on (Start Menu / Taskbar / Desktop
echo icon) and ask.bat will be able to find it and add a tab to it.
echo.
echo Note: if you usually launch Edge some other way (e.g. a different
echo pinned icon), right-click it -^> Properties -^> Target, and add
echo  --remote-debugging-port=%PORT%  to the end yourself.
pause
