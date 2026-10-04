@echo off
setlocal EnableExtensions

rem ================================================================
rem Build completo do Universo Bot: PyInstaller ONEDIR + Inno Setup
rem Requisitos: Python 3.11+, Inno Setup 6 e arquivos do projeto
rem ================================================================

cd /d "%~dp0"
title Gerando instalador do Universo Bot

set "APP_NAME=Universo Bot"
set "ENTRY=main.py"
set "LOGO=UniBotLogo.png"
set "ICON=UniBotLogo.ico"
set "ASSETS_DIR=assets"
set "DIST_DIR=dist_installer_app"
set "BUILD_DIR=build_installer_app"
set "SPEC_FILE=Universo Bot.spec"
set "ISS_FILE=universo_bot_instalador.iss"
set "OUTPUT_DIR=instalador"

if not exist "%ENTRY%" (
    echo [ERRO] Nao encontrei "%ENTRY%".
    pause
    exit /b 1
)
if not exist "%LOGO%" (
    echo [ERRO] Nao encontrei "%LOGO%".
    echo Coloque a logo usada pelo aplicativo na mesma pasta do projeto.
    pause
    exit /b 1
)
if not exist "%ICON%" (
    echo [ERRO] Nao encontrei "%ICON%".
    pause
    exit /b 1
)
if not exist "%ASSETS_DIR%\openai.png" (
    echo [ERRO] Nao encontrei a pasta "%ASSETS_DIR%" com os logos dos provedores.
    pause
    exit /b 1
)
if not exist "%ISS_FILE%" (
    echo [ERRO] Nao encontrei "%ISS_FILE%".
    pause
    exit /b 1
)

where py >nul 2>nul
if errorlevel 1 (
    where python >nul 2>nul
    if errorlevel 1 (
        echo [ERRO] Python nao foi encontrado no PATH.
        pause
        exit /b 1
    )
    set "PYTHON=python"
) else (
    set "PYTHON=py"
)

set "ISCC="
where ISCC.exe >nul 2>nul
if not errorlevel 1 set "ISCC=ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%USERPROFILE%\AppData\Local\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%USERPROFILE%\AppData\Local\Programs\Inno Setup 6\ISCC.exe"
for /f "tokens=2,*" %%A in ('reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\ISCC.exe" /ve 2^>nul ^| find "REG_SZ"') do if not defined ISCC set "ISCC=%%B"
for /f "tokens=2,*" %%A in ('reg query "HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\ISCC.exe" /ve 2^>nul ^| find "REG_SZ"') do if not defined ISCC set "ISCC=%%B"
for /f "tokens=2,*" %%A in ('reg query "HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\ISCC.exe" /ve 2^>nul ^| find "REG_SZ"') do if not defined ISCC set "ISCC=%%B"
if not defined ISCC (
    echo [ERRO] Inno Setup 6 nao foi encontrado.
    echo O compilador ISCC.exe nao esta no PATH nem nos caminhos conhecidos.
    echo Instale-o por: https://jrsoftware.org/isdl.php
    pause
    exit /b 1
)
echo Inno Setup encontrado em: "%ISCC%"

echo.
echo [1/6] Atualizando ferramentas Python...
%PYTHON% -m pip install --upgrade pip pyinstaller
if errorlevel 1 goto :fail

echo.
echo [2/6] Instalando dependencias...
%PYTHON% -m pip install --upgrade pillow keyring mss openai pynput
if errorlevel 1 goto :fail

echo.
echo [3/6] Limpando build anterior...
if exist "%DIST_DIR%" rmdir /s /q "%DIST_DIR%"
if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"
if exist "%OUTPUT_DIR%" rmdir /s /q "%OUTPUT_DIR%"
if exist "%SPEC_FILE%" del /q "%SPEC_FILE%"

 echo.
echo [4/6] Gerando aplicativo ONEDIR...
%PYTHON% -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onedir ^
    --windowed ^
    --name "%APP_NAME%" ^
    --distpath "%DIST_DIR%" ^
    --workpath "%BUILD_DIR%" ^
    --specpath . ^
    --icon "%ICON%" ^
    --add-data "%LOGO%;." ^
    --add-data "%ASSETS_DIR%;assets" ^
    --collect-submodules keyring ^
    --collect-submodules pynput ^
    --collect-all mss ^
    --hidden-import keyring.backends.Windows ^
    --hidden-import pynput.keyboard._win32 ^
    --hidden-import pynput.mouse._win32 ^
    "%ENTRY%"
if errorlevel 1 goto :fail
if not exist "%DIST_DIR%\%APP_NAME%\%APP_NAME%.exe" goto :fail

echo.
echo [5/6] Gerando instalador com Inno Setup...
"%ISCC%" /DMyAppVersion=1.0.0 "%ISS_FILE%"
if errorlevel 1 goto :fail
if not exist "%OUTPUT_DIR%\UniversoBot-Setup.exe" goto :fail

echo.
echo [6/6] Build concluido.
echo Instalador: "%~dp0%OUTPUT_DIR%\UniversoBot-Setup.exe"
echo.
echo Teste o instalador em uma maquina limpa antes de distribuir.
pause
exit /b 0

:fail
echo.
echo [ERRO] O build falhou. Verifique as mensagens acima.
pause
exit /b 1
