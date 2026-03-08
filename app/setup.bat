@echo off
:: TimeTrack — Script de instalación y configuración
:: Ejecutar una vez tras clonar/descargar el proyecto.

title TimeTrack — Setup
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo  ╔══════════════════════════════════╗
echo  ║      TimeTrack — Setup                        ║
echo  ╚══════════════════════════════════╝
echo.

:: ── 1. Verificar Python ───────────────────────────────────────────────────────
echo [1/4] Verificando Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no encontrado. Instala Python 3.11+ desde python.org
    pause & exit /b 1
)
for /f "tokens=*" %%i in ('python --version 2^>^&1') do echo        %%i

:: ── 2. Crear entorno virtual ──────────────────────────────────────────────────
echo.
echo [2/4] Entorno virtual...
if exist ".venv\Scripts\python.exe" (
    echo        Ya existe — omitiendo creación
) else (
    echo        Creando .venv...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] No se pudo crear el entorno virtual.
        pause & exit /b 1
    )
)

:: ── 3. Instalar dependencias ──────────────────────────────────────────────────
echo.
echo [3/4] Instalando dependencias...
".venv\Scripts\pip.exe" install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERROR] Falló la instalación de dependencias.
    echo Prueba a ejecutar manualmente:
    echo   .venv\Scripts\pip.exe install -r requirements.txt
    pause & exit /b 1
)
echo        OK

:: ── 4. Crear accesos directos ─────────────────────────────────────────────────
echo.
echo [4/4] Creando accesos directos...
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "VBS=%SCRIPT_DIR%\TimeTrack-silent.vbs"

:: Acceso directo en el escritorio
set "DESKTOP=%USERPROFILE%\Desktop"
set "SHORTCUT=%DESKTOP%\TimeTrack.lnk"
powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT%'); $s.TargetPath = 'wscript.exe'; $s.Arguments = '\"%VBS%\"'; $s.WorkingDirectory = '%SCRIPT_DIR%'; $s.Description = 'TimeTrack - App Usage Tracker'; $s.Save()" ^
  >nul 2>&1
if exist "%SHORTCUT%" (
    echo        Acceso directo creado en el Escritorio
) else (
    echo        [advertencia] No se pudo crear el acceso directo en el escritorio
)

:: ── Resumen ───────────────────────────────────────────────────────────────────
echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║  ✓ TimeTrack instalado correctamente                                     ║
echo  ╠══════════════════════════════════════════════════════╣
echo  ║                                                                          ║
echo  ║  PARA INICIAR:                                                           ║
echo  ║    • Doble clic en TimeTrack.lnk (escritorio)                            ║
echo  ║    • O doble clic en TimeTrack-silent.vbs                                ║
echo  ║    • O TimeTrack.bat  (con consola, para debug)                          ║
echo  ║                                                                          ║
echo  ║  INICIO AUTOMÁTICO CON WINDOWS:                                          ║
echo  ║    1. Pulsa Win+R → escribe: shell:startup → Enter                       ║
echo  ║    2. Copia TimeTrack-silent.vbs a esa carpeta                           ║
echo  ║       (o el acceso directo del escritorio)                               ║
echo  ║                                                                          ║
echo  ║  DASHBOARD:  http://127.0.0.1:31337                                      ║
echo  ╚══════════════════════════════════════════════════════╝
echo.

set /p AUTOSTART="¿Añadir al inicio de Windows ahora? (s/n): "
if /i "%AUTOSTART%"=="s" (
    set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
    copy "%VBS%" "%STARTUP%\TimeTrack.vbs" >nul 2>&1
    if errorlevel 1 (
        echo [advertencia] No se pudo copiar al inicio automático.
    ) else (
        echo  ✓ TimeTrack se iniciará con Windows.
    )
)

echo.
pause
