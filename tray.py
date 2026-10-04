r"""
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
#
# core.database define dónde viven los datos (TimeTrackData/) y migra el layout
# antiguo al importarse. Solo usa la stdlib, así que es seguro traerlo antes de
# configurar el logging y antes del bloque que detecta dependencias ausentes.
from core.database import LOG_PATH, DATA_DIR, MIGRATED_FILES

LOG_FILE = LOG_PATH

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
    from core import instance
    from core import autostart
    from core.version import __version__
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

# Referencia al icono: la necesita el cierre ordenado cuando una versión más
# nueva nos releva, para que el icono desaparezca en el acto y no quede un
# fantasma en la bandeja hasta que el usuario pase el ratón por encima.
_icon_ref = None


def _title(paused: bool = False) -> str:
    """
    Tooltip del icono. El puerto aparece solo cuando NO es el habitual, que es
    justo el caso en el que el usuario necesita saberlo.
    """
    estado = "paused" if paused else "tracking"
    sufijo = f" (:{PORT})" if PORT != instance.DEFAULT_PORT else ""
    return f"TimeTrack — {estado}{sufijo}"


def _toggle_pause(icon, _item):
    """Alterna pausa/reanuda y actualiza el icono y tooltip."""
    if tracker.is_paused():
        tracker.resume()
        icon.icon    = _make_icon_image(paused=False)
        icon.title   = _title(paused=False)
    else:
        tracker.pause()
        icon.icon    = _make_icon_image(paused=True)
        icon.title   = _title(paused=True)


def _pause_label(item) -> str:
    return "▶ Resume Tracking" if tracker.is_paused() else "⏸ Pause Tracking"


def _quit(icon, _item):
    icon.stop()
    # Cierra las sesiones vivas antes de matar el proceso: os._exit no ejecuta
    # el shutdown de FastAPI, así que sin esto quedarían huérfanas.
    try:
        tracker.stop()
    except Exception:
        pass
    # Suelta el candado y borra instance.json: sin esto, el siguiente arranque
    # tendría que descubrir por sondeo que ya no hay nadie.
    try:
        instance.release()
    except Exception:
        pass
    os._exit(0)


def _orderly_shutdown():
    """
    Cierre a petición de una instancia más nueva (POST /api/instance/shutdown).
    Mismo orden que _quit, pero sin matar el proceso: de eso se encarga
    instance.shutdown_now() una vez ha salido la respuesta HTTP.
    """
    logger.info("Una versión más nueva pide el relevo; cerrando ordenadamente...")
    if _icon_ref is not None:
        try:
            _icon_ref.stop()
        except Exception:
            pass
    try:
        tracker.stop()
    except Exception:
        logger.exception("No pude detener el tracker al ser relevado")


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
        _title(paused=False),
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
    global PORT, _icon_ref

    logger.info("=" * 48)
    logger.info("  TimeTrack v%s arrancando...", __version__)
    logger.info("  Datos -> %s", DATA_DIR)
    logger.info("  Log   -> %s", LOG_FILE)

    # Portero: una sola instancia por carpeta de datos y un puerto que de
    # verdad esté libre. Devuelve None cuando ya hay una instancia que debe
    # seguir siendo la buena — entonces nos limitamos a salir, porque ella ya
    # ha abierto su dashboard.
    port = instance.startup_guard()
    if port is None:
        logger.info("=" * 48)
        return
    PORT = port
    instance.write_lock(PORT)
    instance.set_shutdown_hook(_orderly_shutdown)

    logger.info("  Dashboard -> http://127.0.0.1:%d", PORT)
    logger.info("=" * 48)
    if MIGRATED_FILES:
        logger.info("Datos de una versión anterior movidos a %s: %s",
                    DATA_DIR.name, ", ".join(MIGRATED_FILES))

    # Servidor en thread background
    server_thread = threading.Thread(target=run_server, daemon=True, name="uvicorn")
    server_thread.start()

    def _check_autostart():
        # Espera a que init_db() (disparado por el evento startup de FastAPI)
        # haya creado la tabla settings; si no, autostart.reconcile() explota
        # con "no such table" en un hilo sin consola donde nadie vería el error.
        if not _wait_for_server():
            logger.warning("Autostart: el servidor no respondió a tiempo; comprobación omitida")
            return
        try:
            autostart.reconcile()
        except Exception:
            logger.exception("Autostart: fallo al comprobar/reparar el acceso directo")

    threading.Thread(target=_check_autostart, daemon=True, name="autostart").start()

    try:
        icon = build_tray_icon()
        _icon_ref = icon

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

        # Permite que el botón "Probar" de Ajustes use el modo globo
        try:
            from core.notifications import set_tray_icon, ensure_app_id
            set_tray_icon(icon)
            ensure_app_id()
        except Exception as exc:
            logger.debug("Notificaciones: %s", exc)

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
