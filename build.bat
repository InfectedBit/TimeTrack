@echo off
:: TimeTrack -- Build standalone .exe with PyInstaller
:: Output: dist\TimeTrack\TimeTrack.exe  +  dist\TimeTrack.zip

title TimeTrack -- Build
cd /d "%~dp0"

echo.
echo  ============================================================
echo     TimeTrack -- Build standalone .exe
echo  ============================================================
echo.

:: -- 1. Check venv -------------------------------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found.
    echo         Run setup.bat first.
    pause & exit /b 1
)

:: -- 2. Install / verify PyInstaller ------------------------------------------
echo [1/5] Checking PyInstaller...
".venv\Scripts\python.exe" -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo       Installing PyInstaller...
    ".venv\Scripts\pip.exe" install pyinstaller --quiet
    if errorlevel 1 (
        echo [ERROR] Could not install PyInstaller.
        pause & exit /b 1
    )
)
echo       OK

:: -- 3. Generate .ico from favicon PNG ----------------------------------------
echo.
echo [2/5] Generating icon ( favicon_1.png -> TimeTrack.ico )...
".venv\Scripts\python.exe" -c "from PIL import Image; img=Image.open('images/timetrack/favicon_1.png').convert('RGBA'); img.save('images/timetrack/TimeTrack.ico', format='ICO', sizes=[(16,16),(32,32),(48,48),(256,256)])"
if errorlevel 1 (
    echo       [warning] Could not generate .ico -- building without custom icon.
) else (
    echo       OK
)

:: -- 4. Clean previous build --------------------------------------------------
echo.
echo [3/6] Cleaning previous build...
if exist "build"              rmdir /s /q "build"
if exist "dist\TimeTrack"     rmdir /s /q "dist\TimeTrack"
if exist "dist\TimeTrack.zip" del /q "dist\TimeTrack.zip"
if exist "dist\TimeTrack.exe" del /q "dist\TimeTrack.exe"
echo       OK

:: -- 5. Compile onedir (faster startup, ships as ZIP) --------------------------
echo.
echo [4/6] Compiling onedir build (may take 1-2 min)...
".venv\Scripts\pyinstaller.exe" TimeTrack.spec --noconfirm
if errorlevel 1 (
    echo.
    echo [ERROR] Compilation failed. Check the messages above.
    pause & exit /b 1
)
echo       OK

:: -- 6. Compile onefile (single self-contained .exe) ---------------------------
:: This is the PRIMARY release artifact. The onedir .exe does NOT work on its
:: own -- it needs its _internal\ folder beside it, and users who copy just the
:: .exe end up with a program that starts but never opens. onefile cannot be
:: broken that way.
echo.
echo [5/6] Compiling onefile build (single .exe)...
".venv\Scripts\pyinstaller.exe" TimeTrack-onefile.spec --noconfirm
if errorlevel 1 (
    echo.
    echo [ERROR] onefile compilation failed. Check the messages above.
    pause & exit /b 1
)
echo       OK

:: -- 7. Create distributable zip ----------------------------------------------
echo.
echo [6/6] Creating ZIP for distribution...
powershell -NoProfile -Command "Compress-Archive -Path 'dist\TimeTrack' -DestinationPath 'dist\TimeTrack.zip' -Force"
if errorlevel 1 (
    echo       [warning] Could not create ZIP.
) else (
    echo       OK
)

:: -- Summary ------------------------------------------------------------------
echo.
echo  ============================================================
echo   Build complete!
echo  ------------------------------------------------------------
echo   dist\TimeTrack.exe   single file -- RECOMMENDED for release
echo   dist\TimeTrack.zip   folder build -- faster startup, unzip it ALL
echo.
echo   Upload BOTH as GitHub Release assets.
echo   Never share dist\TimeTrack\TimeTrack.exe on its own: that copy
echo   needs its _internal\ folder next to it.
echo  ============================================================
echo.
pause
