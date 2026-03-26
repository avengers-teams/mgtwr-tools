@echo off
setlocal EnableExtensions
chcp 65001 >nul

cd /d "%~dp0"

set "PYTHON=python"
if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
)

set "APP_NAME=main.exe"
set "OUT_DIR=out"
set "NUITKA_VERSION=4.0.7"
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

echo [4/5] Upgrading Nuitka to %NUITKA_VERSION%
"%PYTHON%" -m pip install --upgrade "Nuitka==%NUITKA_VERSION%"
if errorlevel 1 goto :fail

echo [5/5] Building %APP_NAME%
if exist "%OUT_DIR%" rmdir /s /q "%OUT_DIR%"
if exist "main.build" rmdir /s /q "main.build"
if exist "main.dist" rmdir /s /q "main.dist"
if exist "main.onefile-build" rmdir /s /q "main.onefile-build"

"%PYTHON%" -m nuitka --onefile --mingw64 --show-memory --enable-plugin=pyqt5 --windows-console-mode=disable --python-flag=no_docstrings --output-dir=%OUT_DIR% --output-filename=%APP_NAME% --product-name="多功能数据分析处理工具" --company-name="Yserver" --product-version=%APP_VERSION% --file-version=%APP_VERSION% --file-description="多功能数据分析处理工具" --windows-icon-from-ico=assets/icons/favicon.ico --include-data-dir=assets=assets --include-data-files=version=version --include-qt-plugins=sensible,styles,imageformats --nofollow-import-to=pytest,unittest,IPython,jupyter,notebook --assume-yes-for-downloads main.py
if errorlevel 1 goto :fail

echo Build completed: %OUT_DIR%\%APP_NAME%
exit /b 0

:fail
echo Build failed.
exit /b 1
