@echo off
title TELKOM SCRAPER ENTERPRISE V3
cd /d "%~dp0"

:: 1. Cek apakah setup otomatis sudah pernah berjalan
if exist ".venv\installed.flag" goto RUN_APP

echo ========================================================
echo  SEDANG MENYIAPKAN SISTEM OTOMATIS (HANYA SEKALI)...
echo  Mohon tunggu 1-2 menit, sistem sedang dirakit...
echo ========================================================
echo.

:: 2. Cek apakah Python ada di laptop
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python belum terpasang di laptop ini!
    echo Silakan install Python 3.10 ke atas dulu.
    echo Pastikan centang "Add Python to PATH" saat install.
    echo.
    pause
    exit /b
)

:: 3. Bikin ruang virtual (.venv) otomatis
if not exist ".venv" (
    echo -> [1/3] Membuat ruang kerja sistem...
    python -m venv .venv
)

:: 4. Pasang library otomatis
echo -> [2/3] Memasang kebutuhan sistem...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt >nul 2>&1

:: 5. Download Chromium Playwright otomatis
echo -> [3/3] Memasang mesin browser otomatis...
playwright install chromium >nul 2>&1

:: 6. Bikin penanda bahwa instalasi sudah tuntas
echo setup_done > .venv\installed.flag
echo.
echo [SUKSES] Sistem selesai dirakit! Membuka Dasbor...
timeout /t 2 >nul

:RUN_APP
cls
call .venv\Scripts\activate.bat
python run.py
pause