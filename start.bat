@echo off
setlocal
set BASE_DIR=%~dp0
set ENHANCER=%BASE_DIR%fps_enhancer.py
set LOCAL_PYTHON=%BASE_DIR%runtime\python.exe

if not exist "%ENHANCER%" (
    echo Error: fps_enhancer.py not found in %BASE_DIR%
    pause
    exit /b 1
)

if exist "%LOCAL_PYTHON%" (
    set "PYTHON=%LOCAL_PYTHON%"
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        where python3 >nul 2>&1
        if errorlevel 1 (
            echo No Python runtime found.
            echo Install Python 3 or extract a portable runtime to: %LOCAL_PYTHON%
            pause
            exit /b 1
        )
        set "PYTHON=python3"
    ) else (
        set "PYTHON=python"
    )
)

if not exist "%BASE_DIR%\deps\ffmpeg" mkdir "%BASE_DIR%\deps\ffmpeg"
if not exist "%BASE_DIR%\deps\rife" mkdir "%BASE_DIR%\deps\rife"
if not exist "%BASE_DIR%\models" mkdir "%BASE_DIR%\models"
if not exist "%BASE_DIR%\cache" mkdir "%BASE_DIR%\cache"
if not exist "%BASE_DIR%\config" mkdir "%BASE_DIR%\config"
if not exist "%BASE_DIR%\videos\original" mkdir "%BASE_DIR%\videos\original"
if not exist "%BASE_DIR%\videos\enhanced" mkdir "%BASE_DIR%\videos\enhanced"

%PYTHON% "%ENHANCER%" %*
