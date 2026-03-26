@echo off
setlocal EnableExtensions
chcp 65001 >nul

cd /d "%~dp0"

set "PYTHON=python"
if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
)

set "APP_NAME=main"
set "OUT_DIR=out"
set "VERSION_FILE=version"
set "APP_VERSION="

if not exist "%VERSION_FILE%" (
    echo Missing version file: %VERSION_FILE%
    goto :fail
)

for /f "usebackq delims=" %%i in ("%VERSION_FILE%") do (
    if not defined APP_VERSION set "APP_VERSION=%%i"
)

if not defined APP_VERSION (
    echo Version file is empty: %VERSION_FILE%
    goto :fail
)

echo [0/5] Using version: %APP_VERSION%

echo [1/5] Using Python: %PYTHON%
"%PYTHON%" --version
if errorlevel 1 goto :fail

echo [2/5] Upgrading pip
"%PYTHON%" -m pip install --upgrade pip
if errorlevel 1 goto :fail

echo [3/5] Installing dependencies
"%PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 goto :fail

echo [4/5] Installing PyInstaller
"%PYTHON%" -m pip install --upgrade pyinstaller
if errorlevel 1 goto :fail

echo [5/5] Building %APP_NAME%.exe
:: 清理之前的构建残留
if exist "%OUT_DIR%" rmdir /s /q "%OUT_DIR%"
if exist "build" rmdir /s /q "build"
if exist "%APP_NAME%.spec" del /q "%APP_NAME%.spec"

:: 执行 PyInstaller 打包
:: 注意：Windows 下 --add-data 的源路径和目标路径之间必须用分号 (;) 分隔
"%PYTHON%" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name="%APP_NAME%" ^
    --icon="assets/icons/favicon.ico" ^
    --add-data="assets;assets" ^
    --add-data="version;." ^
    --exclude-module="IPython" ^
    --exclude-module="jupyter" ^
    --exclude-module="notebook" ^
    --distpath="%OUT_DIR%" ^
    --workpath="build" ^
    main.py

if errorlevel 1 goto :fail

echo Build completed: %OUT_DIR%\%APP_NAME%.exe
exit /b 0

:fail
echo Build failed.
exit /b 1