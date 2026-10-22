@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem ============================================================
rem  AcademindVideo local server launcher (Windows)
rem  Counterpart of start.command on macOS.
rem
rem  Usage:
rem    double-click start.bat      -> http://localhost:8788/
rem    start.bat 9000              -> custom port
rem    start.bat 9000 --no-open    -> do not open the browser
rem
rem  Stop: press Ctrl-C in this window (or run stop.bat)
rem
rem  NOTE: keep this file pure ASCII + CRLF. Non-ASCII text or
rem  LF-only line endings make cmd.exe mis-parse the script.
rem ============================================================

set "PORT=%~1"
set "NOOPEN="

if /i "%~1"=="--no-open" (
    set "PORT=8788"
    set "NOOPEN=-NoOpen"
)
if /i "%~2"=="--no-open" set "NOOPEN=-NoOpen"

if not defined PORT set "PORT=8788"

rem port must be numeric, otherwise fall back to the default
echo %PORT%| findstr /r "^[0-9][0-9]*$" >nul
if errorlevel 1 set "PORT=8788"

rem prefer PowerShell 7 when present, else built-in Windows PowerShell
set "PSEXE=powershell"
where pwsh >nul 2>nul
if not errorlevel 1 set "PSEXE=pwsh"

"%PSEXE%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" -Port %PORT% %NOOPEN%
if not errorlevel 1 goto done

rem ---- fallback: call python directly if PowerShell path failed ----
echo.
echo [!] PowerShell launch failed, trying Python directly...
set "PYEXE="
where py >nul 2>nul
if not errorlevel 1 set "PYEXE=py -3"
if not defined PYEXE (
    where python >nul 2>nul
    if not errorlevel 1 set "PYEXE=python"
)
if not defined PYEXE goto nopython

if defined NOOPEN (
    %PYEXE% "%~dp0scripts\serve.py" --port %PORT%
) else (
    %PYEXE% "%~dp0scripts\serve.py" --port %PORT% --open
)
if errorlevel 1 (
    echo.
    echo [X] Server failed to start. See the error above.
    pause
)
goto done

:nopython
echo [X] Python 3 not found.
echo     Install it from https://www.python.org/downloads/
echo     Remember to tick "Add python.exe to PATH" during setup.
pause
exit /b 1

:done
endlocal
