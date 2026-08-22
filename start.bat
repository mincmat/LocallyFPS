@echo off
REM start.bat - LocallyFPS portable launcher for Windows.

setlocal enabledelayedexpansion
cd /d "%~dp0"

set "ENHANCER=%~dp0fps_enhancer.py"
set "LOCAL_PYTHON=%~dp0runtime\python.exe"
set "PYEXE="
set "PYARG="

echo LocallyFPS launcher
echo -------------------
echo.

if not exist "%ENHANCER%" (
    echo [ERROR] No se encontro fps_enhancer.py en: %~dp0
    echo Asegurate de que start.bat y fps_enhancer.py esten en la misma carpeta.
    pause
    exit /b 1
)

rem 1) Runtime portable incluido junto al programa
if exist "%LOCAL_PYTHON%" call :try_python "%LOCAL_PYTHON%"

rem 2) Launcher oficial de Python (viene con el instalador de python.org)
if not defined PYEXE (
    for /f "delims=" %%I in ('where py 2^>nul') do (
        if not defined PYEXE call :try_python "%%~I" -3
    )
)

rem 3) python.exe / python3.exe del PATH, probando cada candidato de verdad.
rem    El alias de la Microsoft Store existe aunque no haya Python instalado,
rem    por eso se descarta por ruta y se verifica que ejecute.
for %%N in (python python3) do (
    if not defined PYEXE (
        for /f "delims=" %%P in ('where %%N 2^>nul') do (
            if not defined PYEXE call :try_python "%%~P"
        )
    )
)

if not defined PYEXE (
    echo [ERROR] No se encontro una instalacion funcional de Python.
    echo.
    echo Instalalo desde https://www.python.org/downloads/
    echo y marca la casilla "Add python.exe to PATH" durante la instalacion.
    echo.
    echo Si ya lo tenes instalado, desactiva el alias de la Microsoft Store en:
    echo Configuracion - Aplicaciones - Configuracion avanzada de aplicaciones
    echo - Alias de ejecucion de aplicaciones.
    echo.
    echo Alternativa: extrae un runtime portable de Python en:
    echo   %LOCAL_PYTHON%
    echo.
    pause
    exit /b 1
)

echo Usando Python: "%PYEXE%" %PYARG%
echo.

"%PYEXE%" %PYARG% -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)"
if !errorlevel! neq 0 (
    echo [ERROR] Se requiere Python 3.9 o superior.
    echo Actualizalo desde https://www.python.org/downloads/
    echo.
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

"%PYEXE%" %PYARG% "%ENHANCER%" %*
set "EXITCODE=!errorlevel!"

echo.
if !EXITCODE! neq 0 (
    echo [ERROR] El programa termino con el codigo !EXITCODE!. Revisa los mensajes de arriba.
) else (
    echo LocallyFPS termino correctamente.
)
echo.
pause
exit /b !EXITCODE!

:try_python
rem Valida un candidato: %1 = ruta al exe, %2 = argumento extra (opcional)
rem Descarta el alias de la Microsoft Store (stub que no ejecuta nada)
echo %~1 | findstr /i /c:"\WindowsApps\" >nul
if not errorlevel 1 (
    echo %~1 | findstr /i /c:"PythonSoftwareFoundation" >nul
    if errorlevel 1 exit /b 1
)
"%~1" %~2 -c "import sys" >nul 2>nul
if errorlevel 1 exit /b 1
set "PYEXE=%~1"
set "PYARG=%~2"
exit /b 0
