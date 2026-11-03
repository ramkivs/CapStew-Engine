@echo off
REM =====================================================================
REM  CapitalCompass - stop the local engine and interface
REM  Closes the two windows opened by start.bat. Your stored runs in
REM  data\ are untouched - this only stops the running processes.
REM =====================================================================
setlocal EnableExtensions

echo.
echo   Stopping CapitalCompass ...

REM  Legacy CapitalSteward-* titles are still matched so windows opened by
REM  an older start.bat are stopped too (backward compatibility).
for %%T in (CapitalCompass-API CapitalCompass-UI CapitalSteward-API CapitalSteward-UI) do (
  tasklist /FI "WINDOWTITLE eq %%T*" 2>nul | find /i "cmd.exe" >nul
  if not errorlevel 1 (
    taskkill /FI "WINDOWTITLE eq %%T*" /T /F >nul 2>&1
    echo     [+] stopped %%T
  ) else (
    echo     [.] %%T was not running
  )
)

REM Belt and braces: clear anything still holding the two ports.
for %%P in (8000 5173) do (
  for /f "tokens=5" %%I in ('netstat -ano ^| findstr /r /c:":%%P .*LISTENING"') do (
    taskkill /PID %%I /T /F >nul 2>&1
  )
)

echo.
echo   Done. Runs and policy backups remain in data\.
echo.
endlocal
exit /b 0
