"""
TimeTrack — Entry Point con System Tray
Lanza el servidor uvicorn en background y muestra un icono en la bandeja del sistema.

Uso recomendado:
    .venv\Scripts\pythonw.exe tray.py   <- sin ventana de consola
    .venv\Scripts\python.exe  tray.py   <- con consola (debug)

No ejecutar con el Python del sistema — siempre usar el del venv.
"""

import sys
import threading
import webbrowser
import logging
import os
from pathlib import Path

# ── Resolver ruta base (funciona tanto con python.exe como pythonw.exe) ───────
# En modo frozen (PyInstaller --onedir), sys.executable apunta al .exe y sus
# recursos están en el mismo directorio; __file__ apuntaría al bytecode interno.
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)   # importante: cwd = carpeta del proyecto para imports

# Añadir al sys.path si fuera necesario (ej: ejecución directa sin venv activo)
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# ── Logging PRIMERO — antes de importar main (que también llama basicConfig) ──
# Al configurar aquí primero, el basicConfig de main.py queda como no-op y
# todos los logs (incluidos errores de uvicorn) van al archivo.
LOG_FILE = BASE_DIR / "timetrack.log"

_log_handlers: list[logging.Handler] = [
    logging.FileHandler(LOG_FILE, encoding="utf-8"),
]
if sys.stdout:   # python.exe tiene stdout; pythonw.exe lo devuelve None
    _log_handlers.append(logging.StreamHandler(sys.stdout))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
    handlers=_log_handlers,
)
logger = logging.getLogger("tray")

# ── Importaciones del proyecto ────────────────────────────────────────────────
try:
    import uvicorn
    from main import app, PORT
    from core.tracker import tracker
except ModuleNotFoundError as e:
    # Si falta uvicorn, probablemente se está usando el Python del sistema
    msg = (
        f"Error al importar módulo: {e}\n\n"
        "Asegúrate de ejecutar con el Python del venv:\n"
        r"  .venv\Scripts\pythonw.exe tray.py"
    )
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, "TimeTrack — Error", 0x10)
    except Exception:
        pass
    sys.exit(1)


# ── Iconos ────────────────────────────────────────────────────────────────────

def _make_icon_image(paused: bool = False):
    """Genera el icono del tray programáticamente. Morado=activo, gris=pausado."""
    from PIL import Image, ImageDraw
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    color = "#64748b" if paused else "#6366f1"
    d.ellipse([2, 2, size - 2, size - 2], fill=color)

    if paused:
        # Símbolo de pausa: dos barras verticales
        d.rectangle([18, 18, 27, 46], fill="white")
        d.rectangle([37, 18, 46, 46], fill="white")
    else:
        # Barras de gráfica de actividad
        bars = [(10, 44), (22, 30), (34, 36), (46, 20)]
        for x, y in bars:
            d.rectangle([x, y, x + 8, size - 10], fill="white")

    return img


# ── Tray icon ─────────────────────────────────────────────────────────────────

def _toggle_pause(icon, _item):
    """Alterna pausa/reanuda y actualiza el icono y tooltip."""
    if tracker.is_paused():
        tracker.resume()
        icon.icon    = _make_icon_image(paused=False)
        icon.title   = "TimeTrack — tracking"
    else:
        tracker.pause()
        icon.icon    = _make_icon_image(paused=True)
        icon.title   = "TimeTrack — paused"


def _pause_label(item) -> str:
    return "▶ Resume Tracking" if tracker.is_paused() else "⏸ Pause Tracking"


def _quit(icon, _item):
    icon.stop()
    os._exit(0)


def _respond_game(exe_name: str, action: str):
    """Respond to a pending game from the tray menu."""
    tracker.respond_to_game(exe_name, action)


def _pending_game_submenu_items():
    """Returns a list of MenuItems for pending games (used inside a submenu)."""
    import pystray
    pending = tracker.get_pending_games()
    items = []
    for g in pending:
        exe   = g["exe_name"]
        label = (g.get("display_name") or exe)
        truncated = label[:30] + "…" if len(label) > 30 else label
        items.append(pystray.MenuItem(
            f"🎮 {truncated}?",
            pystray.Menu(
                pystray.MenuItem(
                    "✓ Sí, registrar",
                    lambda i, it, e=exe: _respond_game(e, "yes"),
                ),
                pystray.MenuItem(
                    "✗ No",
                    lambda i, it, e=exe: _respond_game(e, "no"),
                ),
                pystray.MenuItem(
                    "✗ No preguntar más",
                    lambda i, it, e=exe: _respond_game(e, "never"),
                ),
            ),
        ))
    return items


def build_tray_icon():
    """Construye y retorna el pystray.Icon de TimeTrack."""
    import pystray

    menu = pystray.Menu(
        pystray.MenuItem(
            "Open Dashboard",
            lambda icon, item: webbrowser.open(f"http://127.0.0.1:{PORT}"),
            default=True,
        ),
        pystray.MenuItem(
            "🎮 Juegos detectados",
            pystray.Menu(_pending_game_submenu_items),
            visible=lambda item: bool(tracker.get_pending_games()),
        ),
        pystray.MenuItem(_pause_label, _toggle_pause),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit TimeTrack", _quit),
    )

    return pystray.Icon(
        "TimeTrack",
        _make_icon_image(paused=False),
        "TimeTrack — tracking",
        menu=menu,
    )


# ── Arranque ──────────────────────────────────────────────────────────────────

def _wait_for_server(timeout: float = 8.0):
    """Espera hasta que el servidor HTTP esté listo."""
    import time, urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{PORT}/api/tracker/status", timeout=1
            )
            return True
        except Exception:
            time.sleep(0.3)
    return False


def run_server():
    """Arranca uvicorn. log_config=None evita que uvicorn configure sus propios
    handlers (que fallan con pythonw.exe porque sys.stdout/stderr son None)."""
    try:
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=PORT,
            log_level="warning",
            log_config=None,   # <-- fix: no reconfigurar logging (crítico para pythonw)
        )
    except Exception:
        logger.exception("[Server] uvicorn falló al iniciar")


def main():
    logger.info("=" * 48)
    logger.info("  TimeTrack arrancando...")
    logger.info("  Dashboard -> http://127.0.0.1:%d", PORT)
    logger.info("  Log -> %s", LOG_FILE)
    logger.info("=" * 48)

    # Servidor en thread background
    server_thread = threading.Thread(target=run_server, daemon=True, name="uvicorn")
    server_thread.start()

    try:
        icon = build_tray_icon()

        # Abrir browser cuando el servidor esté listo
        def _open_when_ready():
            if _wait_for_server():
                webbrowser.open(f"http://127.0.0.1:{PORT}")
            else:
                logger.warning("Timeout esperando el servidor")

        threading.Thread(target=_open_when_ready, daemon=True).start()

        # Register game detection callback
        def _on_game_detected(exe_name: str, display_name: str):
            from core.notifications import send_game_prompt
            from core.database import get_setting
            mode = get_setting("notification_mode", "tray")
            send_game_prompt(
                exe_name, display_name, mode,
                on_yes=lambda: tracker.respond_to_game(exe_name, "yes"),
                on_no=lambda: tracker.respond_to_game(exe_name, "no"),
                on_never=lambda: tracker.respond_to_game(exe_name, "never"),
                tray_icon=icon,
            )

        tracker.set_notify_callback(_on_game_detected)

        logger.info("Tray icon activo. Clic derecho para opciones.")
        icon.run()   # bloqueante — mantiene el proceso vivo

    except ImportError:
        logger.warning("pystray/Pillow no disponibles — modo sin tray icon")
        logger.info("Abre http://127.0.0.1:%d en tu navegador", PORT)
        _wait_for_server()
        webbrowser.open(f"http://127.0.0.1:{PORT}")
        server_thread.join()

    except Exception as exc:
        logger.error("Error en tray icon: %s", exc, exc_info=True)
        server_thread.join()


if __name__ == "__main__":
    main()
