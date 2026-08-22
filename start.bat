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

rem 1) Runtime portable incluido junto al programa
if exist "%LOCAL_PYTHON%" set "PYTHON=%LOCAL_PYTHON%"

rem 2) Launcher oficial de Python (viene con el instalador de python.org)
if not defined PYTHON (
    py -3 -c "import sys" >nul 2>nul
    if !errorlevel! equ 0 set "PYTHON=py -3"
)

rem 3) python.exe / python3.exe del PATH, verificando que funcionen de verdad.
rem    El acceso directo de la Microsoft Store existe aunque no haya Python,
rem    asi que probamos cada candidato antes de usarlo.
for %%N in (python python3) do (
    if not defined PYTHON (
        for /f "delims=" %%P in ('where %%N 2^>nul') do (
            if not defined PYTHON (
                "%%~P" -c "import sys" >nul 2>nul
                if !errorlevel! equ 0 set "PYTHON=%%~P"
            )
        )
    )
)

if not defined PYTHON (
    echo No se encontro una instalacion funcional de Python.
    echo.
    echo Instalalo desde https://www.python.org/downloads/
    echo y marca la casilla "Add python.exe to PATH" durante la instalacion.
    echo.
    echo Si ya lo tenes instalado, desactiva el alias de la Microsoft Store en:
    echo Configuracion ^> Aplicaciones ^> Configuracion avanzada de aplicaciones
    echo ^> Alias de ejecucion de aplicaciones.
    echo.
    echo Alternativa: extrae un runtime portable de Python en:
    echo   %LOCAL_PYTHON%
    pause
    exit /b 1
)

"%PYTHON%" -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)"
if !errorlevel! neq 0 (
    echo Tu version de Python es demasiado vieja. Se requiere 3.9 o superior.
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

if !errorlevel! neq 0 (
    echo.
    echo El programa termino con un error. Revisa los mensajes de arriba.
    pause
)
