@echo off
set ROOT=%~dp0
set PY=C:\Users\ac\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe
if not exist "%PY%" set PY=python
cd /d "%ROOT%"
"%PY%" -m metin_atolyesi
