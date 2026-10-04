"""
TimeTrack — inicio automático con Windows.

TimeTrack es portable (sin instalador, datos junto al .exe), así que no hay
ningún sitio central donde registrar "dónde vive la instalación". En vez de
eso, cada arranque se autocomprueba: si el acceso directo de la carpeta de
inicio de Windows no existe, o apunta a una ruta distinta a la actual, se
(re)escribe. Así, si el usuario mueve la carpeta de instalación, basta con que
abra el .exe una vez desde el nuevo sitio para que el inicio automático se
repare solo — Windows no avisa de accesos directos rotos al arrancar (fallan
en silencio), así que depender de que el usuario "vea un error" no es fiable.

Solo actúa en builds congeladas (el .exe real); en modo desarrollo es un no-op,
para no sembrar accesos directos a python.exe en el inicio de nadie.
"""

import logging
import os
import subprocess
import sys
from pathlib import Path

from core import database as db

logger = logging.getLogger("autostart")

SETTING_ENABLED = "autostart_enabled"
SETTING_TARGET  = "autostart_target"   # última ruta de .exe para la que se escribió el atajo
LINK_NAME       = "TimeTrack.lnk"


def _startup_dir() -> Path:
    """
    Carpeta de inicio de Windows (shell:startup) para el usuario actual.

    TIMETRACK_STARTUP_DIR permite redirigirla en tests: nunca se debe escribir
    ni borrar un acceso directo en la carpeta de inicio REAL de quien ejecuta
    las pruebas.
    """
    override = os.environ.get("TIMETRACK_STARTUP_DIR")
    if override:
        return Path(override)
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def shortcut_path() -> Path:
    return _startup_dir() / LINK_NAME


def current_target() -> Path | None:
    """Ruta del .exe actual, o None si no tiene sentido (modo desarrollo)."""
    if not getattr(sys, "frozen", False):
        return None
    return Path(sys.executable).resolve()


def is_enabled() -> bool:
    return db.get_setting(SETTING_ENABLED, "1") == "1"


def status() -> dict:
    target = current_target()
    return {
        "supported": target is not None,
        "enabled":   is_enabled(),
        "path":      str(shortcut_path()),
    }


def _ps_quote(value) -> str:
    """Literal de cadena de PowerShell (comillas simples): sin interpolación de
    $variables ni backticks, solo duplicar comillas simples internas."""
    return "'" + str(value).replace("'", "''") + "'"


def _icon_location() -> str:
    try:
        from core.notifications import _icon_path
        return _icon_path()
    except Exception:
        return ""


def _write_shortcut(target: Path, link: Path) -> bool:
    """
    Crea o sobrescribe el .lnk vía COM (WScript.Shell) a través de PowerShell.

    Se descarta escribir el binario .lnk a mano: el formato (MS-SHLLINK) es
    quisquilloso con rutas Unicode y listas de PIDL, y un error ahí deja un
    acceso directo que Explorer no sabe resolver. Pasar por PowerShell usa la
    misma COM que usaría cualquier instalador, sin añadir pywin32 como
    dependencia de Python (que además da guerra con el caché de gencache al
    empaquetar con PyInstaller).
    """
    try:
        link.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    icon = _icon_location()
    icon_line = f"$sc.IconLocation = {_ps_quote(icon + ',0')}" if icon else ""
    script = (
        "$ws = New-Object -ComObject WScript.Shell\n"
        f"$sc = $ws.CreateShortcut({_ps_quote(str(link))})\n"
        f"$sc.TargetPath = {_ps_quote(str(target))}\n"
        f"$sc.WorkingDirectory = {_ps_quote(str(target.parent))}\n"
        "$sc.WindowStyle = 7\n"
        f"{icon_line}\n"
        "$sc.Save()\n"
    )
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if r.returncode != 0:
            logger.warning("powershell devolvió %d al crear el acceso directo: %s",
                           r.returncode, r.stderr.decode(errors="replace").strip())
        return r.returncode == 0
    except Exception as exc:
        logger.warning("No se pudo crear el acceso directo de inicio: %s", exc)
        return False


def _remove_shortcut() -> None:
    try:
        shortcut_path().unlink(missing_ok=True)
    except OSError as exc:
        logger.debug("No se pudo borrar el acceso directo de inicio: %s", exc)
    db.set_setting(SETTING_TARGET, "")


def reconcile() -> None:
    """
    Repara el acceso directo si hace falta. Pensada para llamarse en CADA
    arranque (de Windows o manual): es la única forma de recuperarse de un
    atajo roto por un traslado de carpeta, porque Windows no avisa de accesos
    directos rotos al arrancar — el siguiente arranque manual es quien lo
    arregla, no un diálogo de error.
    """
    target = current_target()
    if target is None or not is_enabled():
        return

    link = shortcut_path()
    stored = db.get_setting(SETTING_TARGET, "")
    if stored == str(target) and link.exists():
        return   # ya apunta donde debe; no tocar nada en el caso normal

    if _write_shortcut(target, link):
        db.set_setting(SETTING_TARGET, str(target))


def set_enabled(enabled: bool) -> dict:
    db.set_setting(SETTING_ENABLED, "1" if enabled else "0")
    if enabled:
        db.set_setting(SETTING_TARGET, "")   # fuerza reescritura aunque no haya cambiado la ruta
        reconcile()
    else:
        _remove_shortcut()
    return status()
