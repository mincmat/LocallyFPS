@echo off
REM start.bat - lanzador de LocallyFPS para Windows.
REM
REM Detecta Python, lo instala si falta (via winget), recarga el PATH y ejecuta fps_enhancer.py.

setlocal enabledelayedexpansion
cd /d "%~dp0"

set "ENHANCER=%~dp0fps_enhancer.py"

if not exist "%ENHANCER%" (
    echo No se encontro fps_enhancer.py en: %~dp0
    echo Asegurate de que start.bat y fps_enhancer.py esten en la misma carpeta.
    pause
    exit /b 1
)

set "PYCMD="
where py >nul 2>nul
if %errorlevel%==0 (
    set "PYCMD=py -3"
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set "PYCMD=python"
    )
)

if "%PYCMD%"=="" (
    echo Python no esta instalado en este sistema.
    set /p RESP="Instalarlo ahora con winget? [S/n] "
    if /i "!RESP!"=="n" (
        echo Python es necesario para continuar.
        pause
        exit /b 1
    )
    where winget >nul 2>nul
    if %errorlevel%==0 (
        winget install --id=Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements
        
        REM magia negra para recargar el path sin cerrar la terminal
        for /f "delims=" %%I in ('powershell -NoProfile -Command "$m=[Environment]::GetEnvironmentVariable('PATH','Machine'); $u=[Environment]::GetEnvironmentVariable('PATH','User'); Write-Output ($m+';'+$u)"') do set "PATH=%%I"
    ) else (
        echo No se encontro winget en este sistema.
        echo Instala Python manualmente desde https://www.python.org/downloads/ y volve a correr start.bat
        pause
        exit /b 1
    )
    where py >nul 2>nul
    if %errorlevel%==0 (
        set "PYCMD=py -3"
    ) else (
        where python >nul 2>nul
        if %errorlevel%==0 (
            set "PYCMD=python"
        ) else (
            echo Hubo un bardo y no se detecta Python. Instala a mano o abri otra terminal.
            pause
            exit /b 1
        )
    )
)

%PYCMD% "%ENHANCER%" %*

if %errorlevel% neq 0 (
    echo.
    echo El programa termino con un error. Revisa los mensajes de arriba.
    pause
)