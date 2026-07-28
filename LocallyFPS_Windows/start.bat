@echo off
REM start.bat - LocallyFPS portable launcher for Windows.

setlocal enabledelayedexpansion
cd /d "%~dp0"

set "ENHANCER=%~dp0fps_enhancer.py"
set "LOCAL_PYTHON=%~dp0runtime\python.exe"

if not exist "%ENHANCER%" (
    echo No se encontro fps_enhancer.py en: %~dp0
    echo Asegurate de que start.bat y fps_enhancer.py esten en la misma carpeta.
    pause
    exit /b 1
)

set "PYTHON="
if exist "%LOCAL_PYTHON%" (
    set "PYTHON=%LOCAL_PYTHON%"
) else (
    where python >nul 2>nul
    if !errorlevel! equ 0 (
        set "PYTHON=python"
    )
)
if not defined PYTHON (
    echo No Python runtime found.
    echo Install Python 3 or extract a portable runtime to: %LOCAL_PYTHON%
    pause
    exit /b 1
)

if not exist "%~dp0deps\ffmpeg" mkdir "%~dp0deps\ffmpeg"
if not exist "%~dp0deps\rife" mkdir "%~dp0deps\rife"
if not exist "%~dp0models" mkdir "%~dp0models"
if not exist "%~dp0cache" mkdir "%~dp0cache"
if not exist "%~dp0config" mkdir "%~dp0config"
if not exist "%~dp0videos\original" mkdir "%~dp0videos\original"
if not exist "%~dp0videos\enhanced" mkdir "%~dp0videos\enhanced"

"%PYTHON%" "%ENHANCER%" %*

if %errorlevel% neq 0 (
    echo.
    echo El programa termino con un error. Revisa los mensajes de arriba.
    pause
)
