"""
TimeTrack — FastAPI Application
Arranca el tracker en background + servidor HTTP local.
Punto de entrada para desarrollo: venv/Scripts/python.exe main.py
Para uso normal con tray icon: venv/Scripts/pythonw.exe tray.py
"""

import sys
import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from core.database import init_db
from core.tracker import tracker
from api.routes import router

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")

# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="TimeTrack",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
)

app.include_router(router)

# En modo frozen (PyInstaller --onedir), los recursos están junto al .exe
_base   = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).parent
UI_PATH = _base / "ui"

# Servir archivos estáticos si existe la carpeta (opcional: iconos, fuentes locales)
_static = UI_PATH / "static"
if _static.exists():
    app.mount("/static", StaticFiles(directory=str(_static)), name="static")

_images = _base / "images"
if _images.exists():
    app.mount("/images", StaticFiles(directory=str(_images)), name="images")


@app.get("/", include_in_schema=False)
def serve_index():
    return FileResponse(UI_PATH / "index.html")


@app.get("/apps-page", include_in_schema=False)
def serve_apps():
    return FileResponse(UI_PATH / "apps.html")


# ── Lifecycle ─────────────────────────────────────────────────────────────────

@app.on_event("startup")
def on_startup():
    logger.info("Iniciando TimeTrack...")
    init_db()
    tracker.start()
    logger.info("Tracker iniciado ✓")


@app.on_event("shutdown")
def on_shutdown():
    logger.info("Deteniendo tracker...")
    tracker.stop()


# ── Entrada directa ───────────────────────────────────────────────────────────

PORT = 31337

if __name__ == "__main__":
    import webbrowser, threading

    def _open_browser():
        import time
        time.sleep(1.2)
        webbrowser.open(f"http://127.0.0.1:{PORT}")

    threading.Thread(target=_open_browser, daemon=True).start()

    logger.info("Dashboard → http://127.0.0.1:%d", PORT)
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
