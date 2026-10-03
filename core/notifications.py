"""
TimeTrack — Notification Manager
Sends game-detection prompts via Windows Toast (win11toast) or tray balloon.

Toast mode: requires `pip install win11toast` — graceful fallback if unavailable.
Tray mode:  uses pystray's icon.notify() — no extra dependencies.
"""

import sys
import threading
import logging
from pathlib import Path

logger = logging.getLogger("notifications")

# ── Optional toast dependency ─────────────────────────────────────────────────

TOAST_AVAILABLE = False
TOAST_ERROR = ""
try:
    from win11toast import toast as _win11_toast
    TOAST_AVAILABLE = True
    logger.debug("[Notifications] win11toast available")
except ImportError as exc:
    TOAST_ERROR = str(exc)
    logger.debug("[Notifications] win11toast not installed — toast mode will use tray fallback")


# ── Identidad del remitente ───────────────────────────────────────────────────
# Windows atribuye cada toast a un AppUserModelID. Sin registrar uno propio, los
# avisos aparecen firmados como "Python" (y desde un .exe congelado, donde no hay
# ningún Python registrado, Windows puede descartarlos sin mostrar nada).
# Basta una clave en HKCU: no requiere permisos de administrador ni instalador.

APP_ID = "InfectedBit.TimeTrack"
_app_id_ready = False

# Referencia al icono de bandeja, para que la prueba desde Ajustes pueda usar el
# modo globo sin que la API tenga que conocer los interiores de tray.py.
_tray_icon_ref = None


def set_tray_icon(icon):
    global _tray_icon_ref
    _tray_icon_ref = icon


def _icon_path() -> str:
    """
    Ruta persistente al .ico que Windows mostrará junto al toast.

    En una build onefile los recursos viven en sys._MEIPASS, un directorio
    temporal que se borra al cerrar la app: registrar esa ruta dejaría el icono
    roto en cuanto TimeTrack no estuviera en marcha. Por eso se copia una vez al
    directorio de datos, que sí permanece.
    """
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent.parent))
    src = next((base / rel for rel in ("images/timetrack/TimeTrack.ico", "TimeTrack.ico")
                if (base / rel).exists()), None)
    if src is None:
        return ""
    if not getattr(sys, "frozen", False):
        return str(src)
    try:
        from core.database import DATA_DIR
        dst = DATA_DIR / "TimeTrack.ico"
        if not dst.exists() or dst.stat().st_size != src.stat().st_size:
            import shutil
            shutil.copy2(src, dst)
        return str(dst)
    except Exception:
        return str(src)


def ensure_app_id() -> bool:
    """Registra el AUMID en HKCU. Idempotente; seguro si falla."""
    global _app_id_ready
    if _app_id_ready:
        return True
    try:
        import winreg
        key = rf"Software\Classes\AppUserModelId\{APP_ID}"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:
            winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, "TimeTrack")
            icon = _icon_path()
            if icon:
                winreg.SetValueEx(k, "IconUri", 0, winreg.REG_SZ, icon)
        _app_id_ready = True
        logger.debug("[Notifications] AppUserModelID registrado: %s", APP_ID)
    except Exception as exc:
        logger.debug("[Notifications] No se pudo registrar el AppUserModelID: %s", exc)
    return _app_id_ready


def toast_status() -> dict:
    """Estado de la integración de toast, para mostrarlo en Ajustes."""
    return {
        "available": TOAST_AVAILABLE,
        "error": TOAST_ERROR,
        "app_id": APP_ID if _app_id_ready else "",
        "frozen": bool(getattr(sys, "frozen", False)),
    }


def send_test_toast(mode: str = "toast", tray_icon=None) -> dict:
    """Lanza una notificación de prueba desde Ajustes y dice qué ocurrió."""
    icon = tray_icon or _tray_icon_ref
    if mode == "toast" and not TOAST_AVAILABLE:
        return {"ok": False, "sent": "none",
                "detail": "win11toast no está disponible en esta instalación."}
    if mode != "toast":
        if icon is None:
            return {"ok": False, "sent": "none",
                    "detail": "El icono de bandeja no está activo."}
        _tray_prompt("Notificación de prueba", icon)
        return {"ok": True, "sent": "tray", "detail": "Globo de bandeja enviado."}

    ensure_app_id()
    try:
        _notify_async(
            "TimeTrack — notificación de prueba",
            "Si ves este aviso, los toast de Windows funcionan correctamente.",
        )
        return {"ok": True, "sent": "toast",
                "detail": "Toast enviado. Si no aparece, revisa Configuración de "
                          "Windows → Sistema → Notificaciones."}
    except Exception as exc:
        return {"ok": False, "sent": "none", "detail": f"Error al enviar: {exc}"}


def _notify_async(title: str, body: str):
    """Toast informativo sin botones, en un hilo (toast() es bloqueante)."""
    def _run():
        try:
            _win11_toast(title, body, app_id=APP_ID, duration="short")
        except Exception as exc:
            logger.error("[Notifications] Toast error: %s", exc)
    threading.Thread(target=_run, daemon=True, name="toast-test").start()


# ── Public API ────────────────────────────────────────────────────────────────

def send_game_prompt(
    exe_name: str,
    display_name: str,
    mode: str,
    on_yes,
    on_no,
    on_never,
    tray_icon=None,
):
    """
    Show a game tracking prompt.
    mode: 'toast' | 'tray'
    Callbacks (on_yes / on_no / on_never) are invoked from a background thread.
    """
    if mode == "toast" and TOAST_AVAILABLE:
        _toast_prompt(exe_name, display_name, on_yes, on_no, on_never)
    else:
        _tray_prompt(display_name, tray_icon)


# ── Toast implementation ──────────────────────────────────────────────────────

def _toast_prompt(exe_name, display_name, on_yes, on_no, on_never):
    """
    Show a Windows 10/11 toast notification with three action buttons.
    Runs in a daemon thread — toast() is blocking until user clicks or it times out.
    """
    ensure_app_id()

    def _run():
        try:
            result = _win11_toast(
                "TimeTrack — Juego detectado",
                f'¿Registrar "{display_name}"?\n({exe_name})',
                app_id=APP_ID,
                duration="long",
                scenario="reminder",
                buttons=[
                    {"content": "✓ Sí, registrar",   "arguments": "yes"},
                    {"content": "✗ No",               "arguments": "no"},
                    {"content": "✗ No preguntar más", "arguments": "never"},
                ],
            )
            if not result:
                return
            action = (result.get("arguments") or "").strip().lower()
            if action == "yes":
                on_yes()
            elif action == "never":
                on_never()
            else:
                on_no()
        except Exception as exc:
            logger.error("[Notifications] Toast error: %s", exc)

    threading.Thread(target=_run, daemon=True, name=f"toast-{exe_name}").start()


# ── Tray balloon implementation ───────────────────────────────────────────────

def _tray_prompt(display_name: str, tray_icon):
    """
    Show a tray balloon tip. No action buttons — user responds via tray menu or dashboard.
    """
    if tray_icon is None:
        return
    try:
        tray_icon.notify(
            f'¿Registrar "{display_name}"?\nAbre el tray menu o el dashboard para responder.',
            "TimeTrack — Juego detectado",
        )
    except Exception as exc:
        logger.debug("[Notifications] Tray notify failed: %s", exc)
