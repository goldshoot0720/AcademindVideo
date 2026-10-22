@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem ============================================================
rem  Stop the AcademindVideo local server (Windows)
rem
rem  Usage:
rem    stop.bat          -> stop whatever listens on port 8788
rem    stop.bat 9000     -> stop whatever listens on that port
rem
rem  "py -3" spawns a child python.exe, so the whole process TREE
rem  must be killed (/T), otherwise the real server keeps the port.
rem  After killing, the port is re-checked (up to 3 rounds).
rem ============================================================

set "PORT=%~1"
if not defined PORT set "PORT=8788"

echo Checking 127.0.0.1:%PORT% ...
set /a TRIES=0

:killloop
set "FOUND="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /r /c:":%PORT% .*LISTENING"') do (
    if not "%%P"=="0" (
        set "FOUND=1"
        echo   killing PID %%P
        taskkill /PID %%P /T /F >nul 2>nul
    )
)

if not defined FOUND goto verify
set /a TRIES+=1
if %TRIES% GEQ 3 goto verify
ping -n 2 127.0.0.1 >nul
goto killloop

:verify
set "STILL="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /r /c:":%PORT% .*LISTENING"') do (
    if not "%%P"=="0" set "STILL=%%P"
)

if defined STILL (
    echo [X] port %PORT% is still held by PID %STILL%
    echo     try running this file as administrator.
) else (
    echo [OK] port %PORT% released.
)
echo.
pause
endlocal
