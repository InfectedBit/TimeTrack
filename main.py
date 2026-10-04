"""
TimeTrack — FastAPI Application
Arranca el tracker en background + servidor HTTP local.
Punto de entrada para desarrollo: venv/Scripts/python.exe main.py
Para uso normal con tray icon: venv/Scripts/pythonw.exe tray.py
"""

import os
import sys
import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from core.database import init_db, IMAGES_DIR
from core.tracker import tracker
from core.version import __version__
from core import instance
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
    version=__version__,
    docs_url="/docs",
    redoc_url=None,
)

app.include_router(router)

# En modo frozen (PyInstaller --onedir), los recursos están junto al .exe
_base   = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).parent
UI_PATH = _base / "ui"

class NoCacheStaticFiles(StaticFiles):
    """shared.js / shared.css cambian a menudo: forzar revalidación en cada carga."""

    def file_response(self, *args, **kwargs):
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = "no-cache, must-revalidate"
        return resp


# Servir archivos estáticos si existe la carpeta (opcional: iconos, fuentes locales)
_static = UI_PATH / "static"
if _static.exists():
    app.mount("/static", NoCacheStaticFiles(directory=str(_static)), name="static")

_images = _base / "images"
if _images.exists():
    app.mount("/images", StaticFiles(directory=str(_images)), name="images")

# User-uploaded app images — extension-agnostic: if exact filename not found,
# serves any file with the same stem (e.g. DB stores .ico but disk has .png).
@app.get("/user-images/{filename}", include_in_schema=False)
def serve_user_image(filename: str):
    exact = IMAGES_DIR / filename
    if exact.exists():
        return FileResponse(str(exact))
    stem = Path(filename).stem
    for candidate in sorted(IMAGES_DIR.glob(f"{stem}.*")):
        return FileResponse(str(candidate))
    raise HTTPException(status_code=404, detail="Image not found")


# no-cache: el navegador debe revalidar siempre. Sin esto, tras editar la UI el
# navegador puede seguir mostrando la versión antigua hasta un recarga forzada.
_NO_CACHE = {"Cache-Control": "no-cache, must-revalidate"}


@app.get("/", include_in_schema=False)
def serve_index():
    return FileResponse(UI_PATH / "index.html", headers=_NO_CACHE)


@app.get("/apps-page", include_in_schema=False)
def serve_apps():
    return FileResponse(UI_PATH / "apps.html", headers=_NO_CACHE)


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

# Puerto PREFERIDO, configurable por entorno. El definitivo lo decide
# instance.startup_guard() al arrancar: si está ocupado, busca el siguiente libre.
PORT = instance.preferred_port()

if __name__ == "__main__":
    import webbrowser, threading

    # Mismo portero que en tray.py: ni dos trackers sobre una base, ni un bind
    # a un puerto ya ocupado.
    _port = instance.startup_guard()
    if _port is None:
        sys.exit(0)
    PORT = _port
    instance.write_lock(PORT)

    def _open_browser():
        import time
        time.sleep(1.2)
        webbrowser.open(f"http://127.0.0.1:{PORT}")

    threading.Thread(target=_open_browser, daemon=True).start()

    logger.info("Dashboard → http://127.0.0.1:%d", PORT)
    try:
        uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
    finally:
        instance.release()
