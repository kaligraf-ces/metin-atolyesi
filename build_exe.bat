@echo off
chcp 65001 > nul
echo ================================================================
echo   Metin Atolyesi — EXE Derleme
echo ================================================================
echo.

set ROOT=%~dp0
set PY=C:\Users\ac\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe
if not exist "%PY%" set PY=python

cd /d "%ROOT%"

echo [1/3] PyInstaller kontrol ediliyor...
"%PY%" -m pyinstaller --version
if errorlevel 1 (
    echo PyInstaller bulunamadi, kuruluyor...
    "%PY%" -m pip install pyinstaller
)

echo.
echo [2/3] Eski build temizleniyor...
if exist "dist\MetinAtolyesi" rmdir /s /q "dist\MetinAtolyesi"
if exist "build\MetinAtolyesi" rmdir /s /q "build\MetinAtolyesi"

echo.
echo [3/3] EXE derleniyor (bu birkaç dakika surebilir)...
"%PY%" -m PyInstaller MetinAtolyesi.spec --noconfirm

if errorlevel 1 (
    echo.
    echo [HATA] Derleme basarisiz!
    pause
    exit /b 1
)

echo.
echo ================================================================
echo   Derleme tamamlandi!
echo   Konum: %ROOT%dist\MetinAtolyesi\MetinAtolyesi.exe
echo ================================================================
echo.

:: Klasoru Gezgin'de ac
explorer "%ROOT%dist\MetinAtolyesi"
pause
