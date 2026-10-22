@echo off
rem ============================================================
rem  Terminal entry point - identical to start.bat, different name.
rem  (Counterpart of serve.sh on macOS.)
rem
rem  Usage: serve.bat [port] [--no-open]
rem ============================================================
call "%~dp0start.bat" %*
