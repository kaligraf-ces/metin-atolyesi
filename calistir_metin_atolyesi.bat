@echo off
chcp 65001 > nul
set ROOT=%~dp0
set PY=C:\Users\ac\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe
if not exist "%PY%" set PY=python
cd /d "%ROOT%"

:: Kritik paketleri sessizce kontrol et / kur
"%PY%" -c "import anthropic" 2>nul || "%PY%" -m pip install anthropic -q
"%PY%" -c "import PIL" 2>nul || "%PY%" -m pip install pillow -q
"%PY%" -c "import fitz" 2>nul || "%PY%" -m pip install PyMuPDF -q

"%PY%" -m metin_atolyesi
