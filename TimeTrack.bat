@echo off
:: TimeTrack — Lanzador con consola (para desarrollo / debug)
:: Muestra la consola con los logs del servidor.
:: Para uso normal (sin consola), usa TimeTrack-silent.vbs o el acceso directo.

title TimeTrack
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] No se encuentra el entorno virtual.
    echo Ejecuta primero: setup.bat
    pause
    exit /b 1
)

echo.
echo  ╔══════════════════════════════════╗
echo  ║         TimeTrack v1.0           ║
echo  ║  Dashboard: http://127.0.0.1:7842║
echo  ╚══════════════════════════════════╝
echo.
echo  Minimiza esta ventana — no la cierres.
echo  El icono aparece en la barra de tareas (system tray).
echo.

".venv\Scripts\python.exe" tray.py
