"""
TimeTrack — instancia única y resolución de puerto.

Dos trackers sobre la misma base de datos se pisan: ambos escanean procesos y
ambos insertan sesiones, así que el historial sale duplicado y los latidos del
heartbeat se solapan. Este módulo garantiza que solo haya uno vivo por carpeta
de datos, y que el puerto HTTP no choque con otro programa del usuario.

Tres decisiones que conviene no deshacer:

1. **El candado es por carpeta de datos, no por máquina.** El conflicto real es
   la base de datos compartida. Dos copias de TimeTrack en carpetas distintas
   tienen bases separadas y pueden convivir — es lo que permite tener el
   entorno de desarrollo abierto junto al .exe instalado.

2. **La autoridad es el sondeo HTTP, no el PID.** Un apagón deja un
   instance.json huérfano; si se creyera a ciegas, bloquearía el siguiente
   arranque para siempre.

3. **Nunca dos trackers vivos.** Si el relevo ordenado falla, se abre el
   dashboard de la instancia vieja y se sale. Duplicar sesiones es peor que no
   actualizar.
"""

import ctypes
import hashlib
import json
import logging
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path

from core.database import DATA_DIR
from core.version import __version__, version_tuple

logger = logging.getLogger("instance")

LOCK_PATH    = DATA_DIR / "instance.json"
DEFAULT_PORT = 31337
PORT_SCAN    = 20     # 31337..31356 antes de rendirse

# Margen para que la instancia vieja cierre sesiones y suelte el puerto.
TAKEOVER_TIMEOUT = 20.0
# Espera cuando el candado está tomado pero nadie responde aún (arranque simultáneo).
BOOT_GRACE = 12.0

# Cabecera obligatoria en /api/instance/shutdown. Hace doble función: identifica
# a quien pide el relevo y actúa de anti-CSRF — una página web cualquiera no
# puede añadir cabeceras propias sin un preflight CORS, que no respondemos.
TAKEOVER_HEADER = "X-TimeTrack-Takeover"

# El handle del mutex debe seguir vivo durante todo el proceso: si se recoge, el
# candado se libera y otra instancia podría arrancar encima.
_mutex_handle = None
_shutdown_hook = None
_state: dict = {"port": None, "started_at": None}


# ── Identidad ─────────────────────────────────────────────────────────────────

def describe() -> dict:
    """Quién soy. Lo que un segundo arranque lee para decidir qué hacer."""
    return {
        "app":        "TimeTrack",
        "version":    __version__,
        "pid":        os.getpid(),
        "port":       _state["port"],
        "started_at": _state["started_at"],
        "data_dir":   str(DATA_DIR),
        "frozen":     bool(getattr(sys, "frozen", False)),
    }


# ── Puerto ────────────────────────────────────────────────────────────────────

def preferred_port() -> int:
    raw = os.environ.get("TIMETRACK_PORT")
    if raw:
        try:
            return int(raw)
        except ValueError:
            logger.warning("TIMETRACK_PORT=%r no es un número; uso %d", raw, DEFAULT_PORT)
    return DEFAULT_PORT


def _port_is_free(port: int) -> bool:
    """
    Sin SO_REUSEADDR a propósito: en Windows esa opción permite engancharse a un
    puerto que otro proceso ya tiene, que es exactamente lo que queremos detectar.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def resolve_port(preferred: int | None = None) -> int:
    """
    Primer puerto libre a partir del preferido. Antes, si el 31337 estaba
    ocupado por otro programa, uvicorn fallaba al hacer bind *después* de que
    el tracker ya hubiera arrancado: el icono decía "tracking" y el dashboard
    era inalcanzable.
    """
    first = preferred if preferred is not None else preferred_port()

    for port in range(first, first + PORT_SCAN):
        if _port_is_free(port):
            if port != first:
                logger.warning("Puerto %d ocupado por otro programa → uso el %d", first, port)
            return port

    logger.error("Ningún puerto libre entre %d y %d; intento el %d igualmente",
                 first, first + PORT_SCAN - 1, first)
    return first


# ── Fichero de candado ────────────────────────────────────────────────────────

def read_lock() -> dict | None:
    try:
        with open(LOCK_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def write_lock(port: int) -> None:
    """Deja constancia de puerto y versión para que un segundo arranque nos encuentre."""
    _state["port"] = port
    _state["started_at"] = _state["started_at"] or datetime.now().isoformat(timespec="seconds")

    tmp = LOCK_PATH.with_name(LOCK_PATH.name + ".tmp")
    try:
        tmp.write_text(json.dumps(describe(), indent=2), encoding="utf-8")
        os.replace(tmp, LOCK_PATH)   # atómico: nadie lee un fichero a medias
    except OSError as exc:
        logger.debug("No pude escribir %s: %s", LOCK_PATH.name, exc)


def clear_lock() -> None:
    """Borra el candado solo si es nuestro: no pisar el de quien nos releva."""
    data = read_lock()
    if data and data.get("pid") not in (None, os.getpid()):
        return
    try:
        LOCK_PATH.unlink(missing_ok=True)
    except OSError:
        pass


# ── Mutex de Windows ──────────────────────────────────────────────────────────

def _mutex_name() -> str:
    """
    Un nombre de mutex no admite '\\' y tiene longitud limitada, así que se
    hashea la ruta de datos normalizada. 'Local\\' lo deja en la sesión actual.
    """
    key = str(DATA_DIR).rstrip("\\/").lower()
    return "Local\\TimeTrack-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def acquire_mutex() -> bool:
    """
    True si somos la única instancia para esta carpeta de datos.

    Windows libera el mutex al morir el proceso, incluso si se mata o se cuelga,
    así que "tomado" significa siempre "hay alguien vivo" — sin falsos positivos
    heredados de un apagón.
    """
    global _mutex_handle

    if _mutex_handle:
        return True
    if not sys.platform.startswith("win"):
        return True   # el .exe es solo Windows; en otros SO no estorbamos

    ERROR_ALREADY_EXISTS = 183
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        kernel32.CreateMutexW.restype  = ctypes.c_void_p   # HANDLE: 64 bits, no c_int
        handle = kernel32.CreateMutexW(None, False, _mutex_name())
        err = ctypes.get_last_error()
    except Exception as exc:
        logger.debug("No pude crear el mutex (%s); sigo sin candado", exc)
        return True

    if not handle:
        logger.debug("CreateMutexW falló (error %d); sigo sin candado", err)
        return True   # un fallo del candado no debe impedir usar la app

    if err == ERROR_ALREADY_EXISTS:
        ctypes.WinDLL("kernel32").CloseHandle(ctypes.c_void_p(handle))
        return False

    _mutex_handle = handle
    return True


def release() -> None:
    """Suelta candado y fichero. Se llama al salir por el menú o al ser relevado."""
    global _mutex_handle

    clear_lock()
    if _mutex_handle and sys.platform.startswith("win"):
        try:
            kernel32 = ctypes.WinDLL("kernel32")
            kernel32.CloseHandle(ctypes.c_void_p(_mutex_handle))
        except Exception:
            pass
    _mutex_handle = None


# ── Diálogo entre instancias ──────────────────────────────────────────────────

def probe(port: int, timeout: float = 1.5) -> dict | None:
    """
    Pregunta quién escucha en `port`. None si no hay nadie o si lo que hay no es
    TimeTrack: el 31337 puede estar ocupado por un programa ajeno, y mandarle un
    POST de apagado sería como poco descortés.
    """
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/instance", timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None

    if not isinstance(data, dict) or data.get("app") != "TimeTrack":
        return None
    # Una instancia con OTRA carpeta de datos no es asunto nuestro.
    if data.get("data_dir") and Path(data["data_dir"]) != DATA_DIR:
        return None
    return data


def _find_live_instance() -> dict | None:
    """Busca la instancia viva: primero donde dice el candado, luego por barrido."""
    data = read_lock()
    if data and isinstance(data.get("port"), int):
        found = probe(data["port"])
        if found:
            return found

    # Candado ausente o con un puerto que ya no sirve (la instancia vieja pudo
    # arrancar en el 31338 porque el 31337 estaba pillado ese día).
    first = preferred_port()
    for port in range(first, first + PORT_SCAN):
        found = probe(port, timeout=0.4)
        if found:
            return found
    return None


def request_shutdown(port: int, timeout: float = 5.0) -> bool:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/instance/shutdown",
        method="POST",
        data=b"{}",
        headers={"Content-Type": "application/json", TAKEOVER_HEADER: __version__},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception as exc:
        logger.warning("La instancia del puerto %d rechazó el relevo: %s", port, exc)
        return False


def _stand_down(other: dict) -> bool:
    """Pide el relevo y espera. El mutex libre es la prueba de que ya no está."""
    if not request_shutdown(other["port"]):
        return False

    deadline = time.time() + TAKEOVER_TIMEOUT
    while time.time() < deadline:
        time.sleep(0.4)
        if probe(other["port"], timeout=0.5) is None and acquire_mutex():
            return True
    return False


def shutdown_now(delay: float = 0.4) -> None:
    """
    Cierre ordenado a petición de una instancia más nueva.

    El retardo deja salir la respuesta HTTP antes de morir; si no, quien pide el
    relevo ve un error de conexión y cree que lo hemos rechazado.
    """
    def _run():
        time.sleep(delay)
        if _shutdown_hook:
            try:
                _shutdown_hook()
            except Exception:
                logger.exception("Fallo en el cierre ordenado")
        else:
            # Sin tray (p.ej. `python main.py`): al menos cerrar las sesiones
            # abiertas, que os._exit no ejecuta el shutdown de FastAPI.
            try:
                from core.tracker import tracker
                tracker.stop()
            except Exception:
                logger.exception("No pude detener el tracker")
        release()
        logger.info("Relevado por una versión más nueva. Adiós.")
        os._exit(0)

    threading.Thread(target=_run, daemon=True, name="takeover").start()


def set_shutdown_hook(fn) -> None:
    """tray.py registra aquí cómo cerrarse: quitar el icono y parar el tracker."""
    global _shutdown_hook
    _shutdown_hook = fn


def _open_dashboard(port: int) -> None:
    """
    Fire-and-forget. En Windows, webbrowser.open() puede hacer p.wait() sobre el
    proceso que lanza el navegador; si ese proceso tarda o se cuelga (sin
    consola, sin navegador por defecto, un diálogo "¿con qué programa abrir?"),
    NO debe arrastrar con él la resolución de instancias — esto se llama desde
    startup_guard(), antes incluso de que exista el icono de la bandeja, así
    que un bloqueo aquí dejaría el proceso sin ninguna forma de cerrarlo salvo
    el Administrador de tareas.
    """
    def _go():
        try:
            webbrowser.open(f"http://127.0.0.1:{port}")
        except Exception:
            pass
    threading.Thread(target=_go, daemon=True, name="open-dashboard").start()


# ── Portero ───────────────────────────────────────────────────────────────────

def startup_guard() -> int | None:
    """
    Resuelve el conflicto de instancias y devuelve el puerto a usar.

    None significa "no arranques": ya hay una instancia que debe seguir siendo
    la buena. En ese caso se abre su dashboard, que es lo que el usuario
    esperaba al hacer doble clic en el .exe.
    """
    if acquire_mutex():
        # Nadie más. Puede quedar un instance.json huérfano de un apagón; da
        # igual, lo sobreescribimos con el nuestro.
        return resolve_port()

    other = _find_live_instance()

    if other is None:
        # Candado tomado pero nadie contesta: hay un proceso vivo que aún no
        # escucha (doble clic rápido) o está colgado. Le damos margen.
        logger.info("Otra instancia está arrancando; espero a que responda...")
        deadline = time.time() + BOOT_GRACE
        while time.time() < deadline and other is None:
            time.sleep(0.5)
            other = _find_live_instance()

    if other is None:
        # Preferimos no arrancar antes que arriesgar dos trackers sobre la misma
        # base. El usuario puede cerrar el proceso colgado desde el Administrador.
        logger.error("Hay otro proceso de TimeTrack vivo que no responde. "
                     "Ciérralo desde el Administrador de tareas y vuelve a intentarlo.")
        return None

    mine, theirs = version_tuple(__version__), version_tuple(other.get("version"))

    if mine <= theirs:
        logger.info("Ya hay una instancia viva (v%s, puerto %s, pid %s) — abro su dashboard y salgo.",
                    other.get("version"), other.get("port"), other.get("pid"))
        _open_dashboard(other["port"])
        return None

    logger.info("Relevo: v%s sustituye a la v%s (puerto %s, pid %s).",
                __version__, other.get("version"), other.get("port"), other.get("pid"))

    if not _stand_down(other):
        logger.error("La v%s no se cerró a tiempo; abro su dashboard y salgo para no "
                     "tener dos trackers sobre la misma base de datos.", other.get("version"))
        _open_dashboard(other["port"])
        return None

    logger.info("La instancia anterior se cerró correctamente.")
    return resolve_port()
