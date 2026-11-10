@echo off
REM ===========================================================================
REM Build RiverWatchAISBridge.exe with PyInstaller.
REM
REM Requirements (Windows 10/11, run once from an Administrator PowerShell or
REM Developer Command Prompt):
REM
REM   1. Install Python 3.10+ from https://www.python.org/downloads/windows/
REM      Check "Add Python to PATH" during install.
REM   2. py -3 -m venv .venv
REM      .venv\Scripts\activate
REM   3. pip install --upgrade pip pyinstaller
REM
REM Then run this script:
REM
REM   build_windows.bat
REM
REM Output:
REM   dist\RiverWatchAISBridge\RiverWatchAISBridge.exe
REM   dist\RiverWatchAISBridge\riverwatch_bridge.example.ini
REM   dist\RiverWatchAISBridge\README.md
REM
REM Distribute the entire `dist\RiverWatchAISBridge\` folder to end users
REM (zip it). The folder is self-contained - no Python install needed
REM on the user's machine.
REM ===========================================================================

setlocal
pushd "%~dp0"

where pyinstaller >nul 2>nul
if errorlevel 1 (
    echo [build] pyinstaller not on PATH - falling back to "py -m PyInstaller"
    set "PYI=py -m PyInstaller"
) else (
    set "PYI=pyinstaller"
)

echo [build] Cleaning previous build artefacts
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist

echo [build] Running PyInstaller
%PYI% --clean -y riverwatch_ais_bridge.spec
if errorlevel 1 (
    echo [build] PyInstaller failed.
    popd
    exit /b 1
)

echo.
echo [build] SUCCESS
echo [build] Distribute the contents of:  %CD%\dist\RiverWatchAISBridge\
echo.
popd
endlocal
