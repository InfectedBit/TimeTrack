"""
TimeTrack — Notification Manager
Sends game-detection prompts via Windows Toast (win11toast) or tray balloon.

Toast mode: requires `pip install win11toast` — graceful fallback if unavailable.
Tray mode:  uses pystray's icon.notify() — no extra dependencies.
"""

import threading
import logging

logger = logging.getLogger("notifications")

# ── Optional toast dependency ─────────────────────────────────────────────────

TOAST_AVAILABLE = False
try:
    from win11toast import toast as _win11_toast
    TOAST_AVAILABLE = True
    logger.debug("[Notifications] win11toast available")
except ImportError:
    logger.debug("[Notifications] win11toast not installed — toast mode will use tray fallback")


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
    def _run():
        try:
            result = _win11_toast(
                "TimeTrack — Juego detectado",
                f'¿Registrar "{display_name}"?\n({exe_name})',
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
