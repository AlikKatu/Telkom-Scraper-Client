@echo off
setlocal enabledelayedexpansion
title TELKOM SCRAPER ENTERPRISE V3 - INITIALIZER

:: Cek direktori kerja
cd /d "%~dp0"

:: 1. Jika virtual environment (.venv) sudah ada, langsung jalankan dashboard
if exist ".venv\Scripts\python.exe" (
    cls
    echo ========================================================
    echo  MEMULAI TELKOM SCRAPER ENTERPRISE DASHBOARD...
    echo ========================================================
    .venv\Scripts\python.exe run.py
    pause
    exit /b
)

cls
echo ========================================================
echo  SEDANG MENYIAPKAN SISTEM OTOMATIS (HANYA SEKALI)...
echo  Mohon tunggu 1-2 menit, sistem sedang dirakit...
echo ========================================================

:: 2. Deteksi Python di sistem (Mencari python, py launcher, atau path lokal)
set "PY_CMD="

python --version >nul 2>&1
if !errorlevel! equ 0 (
    set "PY_CMD=python"
) else (
    py --version >nul 2>&1
    if !errorlevel! equ 0 (
        set "PY_CMD=py"
    )
)

:: Jika masih belum ketemu, cari langsung di AppData Programs
if "%PY_CMD%"=="" (
    for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
        if exist "%%D\python.exe" (
            set "PY_CMD=%%D\python.exe"
        )
    )
)

:: Jika tetap tidak ditemukan sama sekali
if "%PY_CMD%"=="" (
    echo.
    echo [ERROR] Python tidak terdeteksi oleh sistem!
    echo.
    echo Coba langkah berikut:
    echo 1. Matikan 'App Execution Aliases' di Windows:
    echo    Buka Settings - Apps - Advanced app settings - App execution aliases
    echo    Matikan toggle untuk 'python.exe' dan 'python3.exe'.
    echo 2. Atau install Python dengan mencentang 'Add python.exe to PATH'.
    echo.
    pause
    exit /b
)

echo [OK] Python terdeteksi via: %PY_CMD%
echo.

:: 3. Buat Virtual Environment .venv
echo [1/3] Membuat Virtual Environment (.venv)...
%PY_CMD% -m venv .venv
if !errorlevel! neq 0 (
    echo [ERROR] Gagal membuat .venv.
    pause
    exit /b
)

:: 4. Install Dependencies
echo [2/3] Memasang modul pustaka...
.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
.venv\Scripts\python.exe -m pip install -r requirements.txt --quiet

:: 5. Install Browser Playwright
echo [3/3] Memasang browser otomatis Playwright...
.venv\Scripts\python.exe -m playwright install chromium

echo.
echo ========================================================
echo  PERAKITAN SELESAI! MEMULAI DASHBOARD...
echo ========================================================
cls
.venv\Scripts\python.exe run.py
pause