@echo off
setlocal
echo [Macula] Setting up MSVC build environment...
call "C:\Program Files (x86)\Microsoft Visual Studio\2019\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Visual Studio 2019 Build Tools not found.
    echo         Install from: https://visualstudio.microsoft.com/visual-cpp-build-tools/
    pause
    exit /b 1
)
echo [Macula] Starting dev server...
cd /d "%~dp0"
npm run tauri dev
