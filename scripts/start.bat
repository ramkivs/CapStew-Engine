@echo off
REM =====================================================================
REM  Capital Steward Engine - local startup (single user, this machine)
REM
REM  Double-click this file. On first run it creates the Python virtual
REM  environment and installs the frontend dependencies; after that it
REM  just starts both services and opens your browser.
REM
REM  Two minimised console windows open:
REM      CapitalSteward-API   the engine  (http://127.0.0.1:8000)
REM      CapitalSteward-UI    the interface (http://127.0.0.1:5173)
REM
REM  Both bind to 127.0.0.1 only - nothing is exposed to your network.
REM  To stop: run scripts\stop.bat, or close the two windows.
REM =====================================================================
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0.."
set "REPO=%CD%"
set "VENV=%REPO%\.venv"
set "PY=%VENV%\Scripts\python.exe"
set "PORT=8000"
set "UIPORT=5173"

echo.
echo   Capital Steward Engine
echo   %REPO%
echo.

REM ---- 1. Python present? ------------------------------------------------
where python >nul 2>nul
if errorlevel 1 (
  echo   [x] Python was not found on PATH.
  echo       Install Python 3.11+ from https://www.python.org/downloads/
  echo       and tick "Add python.exe to PATH" during setup.
  goto :fail
)

REM ---- 2. Virtual environment + backend deps -----------------------------
if not exist "%PY%" (
  echo   [.] First run - creating .venv ...
  python -m venv "%VENV%" || goto :fail
)
"%PY%" -c "import fastapi, uvicorn, yaml, httpx, multipart, pydantic" >nul 2>nul
if errorlevel 1 (
  echo   [.] Installing backend dependencies ...
  "%PY%" -m pip install --disable-pip-version-check -q -r requirements.txt || goto :fail
)

REM ---- 3. Node present? --------------------------------------------------
where node >nul 2>nul
if errorlevel 1 (
  echo   [x] Node.js was not found on PATH.
  echo       Install Node 18+ from https://nodejs.org/ then re-run.
  goto :fail
)

REM ---- 4. Frontend dependencies ------------------------------------------
if not exist "%REPO%\frontend\node_modules" (
  echo   [.] Installing frontend dependencies ...
  pushd "%REPO%\frontend"
  call npm install --no-audit --no-fund || (popd & goto :fail)
  popd
)

REM ---- 5. Port already in use? -------------------------------------------
netstat -ano | findstr /r /c:":%PORT% .*LISTENING" >nul 2>nul
if not errorlevel 1 (
  echo   [!] Port %PORT% is already in use - the engine may already be running.
  echo       Run scripts\stop.bat first, or open http://127.0.0.1:%UIPORT%
  goto :fail
)

REM ---- 6. Start the engine ------------------------------------------------
echo   [.] Starting the engine on http://127.0.0.1:%PORT% ...
start "CapitalSteward-API" /MIN cmd /k ""%PY%" -m uvicorn app.main:app --host 127.0.0.1 --port %PORT%"

REM ---- 7. Wait for it to answer /health -----------------------------------
where curl >nul 2>nul
if errorlevel 1 goto :skipwait
set /a TRIES=0
:wait
"%PY%" -c "import time; time.sleep(1)"
curl -s -o nul "http://127.0.0.1:%PORT%/api/v1/health" && goto :up
set /a TRIES+=1
if %TRIES% lss 40 goto :wait
echo   [x] The engine did not answer within 40s - check the CapitalSteward-API window.
goto :fail
:up
echo   [+] Engine is answering /health
:skipwait

REM ---- 8. Start the interface ---------------------------------------------
echo   [.] Starting the interface on http://127.0.0.1:%UIPORT% ...
start "CapitalSteward-UI" /MIN cmd /k "cd /d "%REPO%\frontend" && npm run dev"

REM ---- 9. Open the browser once the dev server is up ----------------------
set /a TRIES=0
:waitui
"%PY%" -c "import time; time.sleep(1)"
curl -s -o nul "http://127.0.0.1:%UIPORT%" && goto :uiup
set /a TRIES+=1
if %TRIES% lss 40 goto :waitui
:uiup
start "" "http://127.0.0.1:%UIPORT%"

echo.
echo   [+] Ready.  http://127.0.0.1:%UIPORT%
echo.
echo   Your decisions are stored in:  %REPO%\data\
echo   Backups of committed policies: %REPO%\data\backups\
echo.
echo   To stop, run:  scripts\stop.bat
echo.
endlocal
exit /b 0

:fail
echo.
echo   Startup did not complete. See the message above.
echo.
endlocal
pause
exit /b 1
