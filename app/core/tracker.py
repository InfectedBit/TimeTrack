"""
TimeTrack — Process Tracker
Loop de monitoreo eficiente usando psutil.
Detecta apertura/cierre de procesos y registra sesiones en SQLite.
Soporta modo auto-detect, pausa/reanuda, filtro por cmdline y main-process-only.
"""

import time
import threading
import logging
from datetime import datetime

try:
    import psutil
except ImportError:
    raise SystemExit("psutil no está instalado. Ejecuta: pip install psutil")

from core.database import (
    get_active_profile_id,
    get_exe_map,
    add_tracked_app,
    remove_tracked_app,
    start_session,
    end_session,
    close_orphan_sessions,
    get_setting,
    set_setting,
    is_dismissed,
    add_dismissed,
    delete_sessions_since,
    count_sessions_for_app,
)

logger = logging.getLogger("tracker")

POLL_INTERVAL = 3.0    # segundos entre scans
MAP_RELOAD    = 30     # cada N ciclos recarga la lista de apps rastreadas


class ProcessTracker:
    """
    Monitorea procesos del sistema en segundo plano.
    Un único thread demonio + psutil para consumo mínimo de CPU.

    _exe_map estructura: {exe_lower: {"app_id", "cmdline_match", "main_process_only"}}
    """

    def __init__(self):
        self._lock        = threading.Lock()
        self._running     = False
        self._thread: threading.Thread | None = None

        # Estado interno
        self._active_pids: dict[int, dict] = {}   # pid → {app_id, session_id, exe, since}
        self._exe_map:     dict[str, dict] = {}   # exe_lower → config dict
        self._profile_id   = 1
        self._auto_detect  = False
        self._paused       = False
        self._cycle        = 0

        # Estado público (leído por la API sin lock, tolera datos levemente stale)
        self.running_now: list[dict] = []   # [{exe_name, since}, ...]

        # ── Game detection ────────────────────────────────────────────────────
        self._game_detect    = False
        # exe_lower → {path, detected_via, display_name, since}
        self._pending_games: dict[str, dict] = {}
        self._ignored_session: set[str] = set()  # "No" this session
        self._notified_exes:  set[str] = set()   # already sent notification
        self._notify_callback = None              # fn(exe_name, display_name)

        # Monitoreo de recursos del propio proceso
        self._own_proc = psutil.Process()
        self._own_proc.cpu_percent(interval=None)   # Primera llamada para "calentar" el contador

    # ── Control ──────────────────────────────────────────────────────────────

    def start(self):
        if self._running:
            return
        self._running = True
        self._game_detect = get_setting("game_detect", "0") == "1"
        close_orphan_sessions()
        self._reload_config()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="tracker"
        )
        self._thread.start()
        logger.info("[Tracker] Iniciado — intervalo: %.1fs, auto_detect: %s",
                    POLL_INTERVAL, self._auto_detect)

    def stop(self):
        self._running = False
        with self._lock:
            for info in self._active_pids.values():
                end_session(info["session_id"])
            self._active_pids.clear()
            self.running_now = []
        logger.info("[Tracker] Detenido")

    def reload(self):
        """Llamar tras añadir/eliminar apps desde la UI."""
        self._reload_config()

    def set_auto_detect(self, enabled: bool, profile_id: int | None = None):
        with self._lock:
            self._auto_detect = enabled
            if profile_id is not None:
                self._profile_id = profile_id
        self._reload_config()
        logger.info("[Tracker] auto_detect=%s", enabled)

    def set_game_detect(self, enabled: bool):
        with self._lock:
            self._game_detect = enabled
        set_setting("game_detect", "1" if enabled else "0")
        logger.info("[Tracker] game_detect=%s", enabled)

    def get_pending_games(self) -> list[dict]:
        with self._lock:
            return [{"exe_name": k, **v} for k, v in self._pending_games.items()]

    def respond_to_game(self, exe_name: str, action: str):
        """
        Handle user response to a game detection prompt.
        action: 'yes' | 'no' | 'never'

        'yes'   → session was already recording; just keep everything as-is.
        'no'    → undo: stop tracking, delete sessions since detection.
        'never' → same as 'no' + add to dismissed list.
        """
        exe_lower = exe_name.lower()
        with self._lock:
            game = self._pending_games.pop(exe_lower, {})
            if not game:
                return

        if action == "yes":
            # Session is already recording — nothing to change
            logger.info("[Tracker] Game accepted: %s", exe_lower)
            return

        # 'no' or 'never': undo tracking -----------------------------------
        app_id = game.get("app_id")
        since  = game.get("since")

        # Remove from exe_map so scan stops tracking this exe
        with self._lock:
            self._exe_map.pop(exe_lower, None)
            # End + remove any active sessions for this exe in-memory
            to_close = [
                (pid, info["session_id"])
                for pid, info in self._active_pids.items()
                if info["exe"] == exe_lower
            ]
            for pid, _ in to_close:
                self._active_pids.pop(pid)
            self._ignored_session.add(exe_lower)

        # Close sessions cleanly, then delete them all since detection
        for _pid, session_id in to_close:
            end_session(session_id)

        if app_id and since:
            deleted = delete_sessions_since(app_id, since)
            logger.info("[Tracker] Game %s (%s): deleted %d session(s) since %s",
                        exe_lower, action, deleted, since)
            # If no sessions remain (app was just added for this detection) → remove it
            if count_sessions_for_app(app_id) == 0:
                remove_tracked_app(app_id)
                logger.info("[Tracker] Removed pending app: %s (app_id=%d)", exe_lower, app_id)

        if action == "never":
            add_dismissed(exe_lower)
            logger.info("[Tracker] Game never-ask: %s", exe_lower)
        else:
            logger.info("[Tracker] Game rejected (session): %s", exe_lower)

    def set_notify_callback(self, fn):
        """Register a callback fn(exe_name, display_name) called when a new game is detected."""
        self._notify_callback = fn

    def pause(self):
        """
        Pausa el tracking. Cierra todas las sesiones activas limpiamente.
        El loop sigue corriendo pero no abre nuevas sesiones.
        """
        with self._lock:
            if self._paused:
                return
            self._paused = True
            for info in self._active_pids.values():
                end_session(info["session_id"])
            self._active_pids.clear()
            self.running_now = []
        logger.info("[Tracker] Pausado")

    def resume(self):
        """Reanuda el tracking. El siguiente scan detectará los procesos activos."""
        with self._lock:
            self._paused = False
        logger.info("[Tracker] Reanudado")

    def is_paused(self) -> bool:
        with self._lock:
            return self._paused

    def get_status(self) -> dict:
        with self._lock:
            d = {
                "running":        self._running,
                "paused":         self._paused,
                "auto_detect":    self._auto_detect,
                "game_detect":    self._game_detect,
                "profile_id":     self._profile_id,
                "tracked_count":  len(self._exe_map),
                "active_pids":    len(self._active_pids),
                "running_now":    list(self.running_now),
                "pending_games":  [
                    {"exe_name": k, "display_name": v.get("display_name") or k}
                    for k, v in self._pending_games.items()
                ],
            }
        # CPU/RAM fuera del lock (no bloqueante)
        try:
            d["cpu_pct"] = round(self._own_proc.cpu_percent(interval=None), 1)
            d["mem_mb"]  = round(self._own_proc.memory_info().rss / 1024 / 1024, 1)
        except Exception:
            d["cpu_pct"] = 0.0
            d["mem_mb"]  = 0.0
        return d

    # ── Loop principal ───────────────────────────────────────────────────────

    def _loop(self):
        while self._running:
            try:
                self._cycle += 1
                if self._cycle % MAP_RELOAD == 0:
                    self._reload_config()
                self._scan()
            except Exception as exc:
                logger.error("[Tracker] Error en scan: %s", exc)
            time.sleep(POLL_INTERVAL)

    def _reload_config(self):
        profile_id = get_active_profile_id()
        new_map = get_exe_map(profile_id)
        with self._lock:
            self._profile_id = profile_id
            self._exe_map = new_map
        logger.debug("[Tracker] Mapa recargado: %d apps (profile=%d)",
                     len(new_map), profile_id)

    def _scan(self):
        """
        Escaneo O(n) de procesos activos.
        1. Obtiene todos los pids activos de una sola vez (process_iter).
        2. Aplica filtros: main_process_only (ppid) y cmdline_match.
        3. Detecta nuevos (start_session) y cerrados (end_session).
        4. En modo auto_detect, auto-añade procesos desconocidos a la BD.
        5. En modo game_detect, identifica posibles juegos y los pone en cola.
        """
        with self._lock:
            if self._paused:
                return
            exe_map      = dict(self._exe_map)
            profile_id   = self._profile_id
            auto_detect  = self._auto_detect
            game_detect  = self._game_detect
            ignored_exes = self._ignored_session | self._notified_exes

        # ── Leer procesos del sistema ──
        current_pids:    dict[int, str]   = {}   # pid → exe_lower
        new_exes:        set[str]          = set()  # for auto_detect
        game_candidates: dict[str, str]    = {}   # exe → full path (for game_detect)

        try:
            for proc in psutil.process_iter(["pid", "name", "ppid"]):
                try:
                    raw = proc.info["name"]
                    if not raw:
                        continue
                    exe = raw.lower()
                    pid = proc.info["pid"]
                    ppid = proc.info.get("ppid") or 0

                    if exe not in exe_map:
                        if auto_detect:
                            new_exes.add(exe)
                        elif game_detect and exe not in ignored_exes:
                            try:
                                exe_path = proc.exe()
                            except (psutil.AccessDenied, psutil.NoSuchProcess):
                                exe_path = ""
                            game_candidates[exe] = exe_path
                        continue

                    cfg = exe_map[exe]

                    # Filtro 1 — main_process_only: saltar subprocesos del mismo exe
                    if cfg["main_process_only"]:
                        try:
                            if psutil.Process(ppid).name().lower() == exe:
                                continue  # Es un hijo — lo ignoramos
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass  # Padre no accesible: tratar como proceso principal

                    # Filtro 2 — cmdline_match: verificar línea de comandos
                    if cfg["cmdline_match"]:
                        try:
                            cmdline = " ".join(proc.cmdline())
                            if cfg["cmdline_match"].lower() not in cmdline.lower():
                                continue  # No coincide → no es el proceso que buscamos
                        except (psutil.AccessDenied, psutil.NoSuchProcess):
                            continue  # Sin acceso a cmdline → saltar por seguridad

                    current_pids[pid] = exe

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception as exc:
            logger.warning("[Tracker] Error listando procesos: %s", exc)
            return

        # ── Auto-añadir nuevos exes a la BD (si auto_detect) ──
        if auto_detect and new_exes:
            for exe in new_exes:
                app_id = add_tracked_app(
                    profile_id, exe,
                    auto_detected=1,
                )
                if app_id:
                    exe_map[exe] = {
                        "app_id":           app_id,
                        "cmdline_match":    None,
                        "main_process_only": 0,
                    }
                    logger.info("[Tracker] Auto-añadido: %s (app_id=%d)", exe, app_id)
            with self._lock:
                self._exe_map.update(exe_map)

        # ── Detectar posibles juegos (si game_detect) ──
        if game_detect and game_candidates:
            from core.game_detection import game_detector
            for exe, exe_path in game_candidates.items():
                is_game, via = game_detector.is_likely_game(exe, exe_path)
                if not is_game:
                    continue
                if is_dismissed(exe):
                    continue
                steam_name   = game_detector.get_steam_display_name(exe_path)
                display_name = (steam_name or
                                exe.replace(".exe", "").replace("-", " ")
                                   .replace("_", " ").title())
                since = datetime.now().isoformat()

                # Añadir a tracked_apps inmediatamente → la sesión empieza a grabarse
                app_id = add_tracked_app(profile_id, exe, display_name, auto_detected=1)
                app_entry = {"app_id": app_id, "cmdline_match": None, "main_process_only": 0}

                with self._lock:
                    self._exe_map[exe] = app_entry          # activa tracking en el próximo scan
                    self._pending_games[exe] = {
                        "path":         exe_path,
                        "detected_via": via,
                        "display_name": display_name,
                        "since":        since,
                        "app_id":       app_id,
                    }
                    self._notified_exes.add(exe)

                logger.info("[Tracker] Game detected: %s (via %s, app_id=%d)", exe, via, app_id)
                if self._notify_callback:
                    try:
                        self._notify_callback(exe, display_name)
                    except Exception as exc:
                        logger.debug("[Tracker] notify_callback error: %s", exc)

        with self._lock:
            # ── Procesos nuevos (abiertos) ──
            for pid, exe in current_pids.items():
                if pid not in self._active_pids and exe in exe_map:
                    app_id = exe_map[exe]["app_id"]
                    session_id = start_session(app_id, profile_id)
                    since = datetime.now().isoformat()
                    self._active_pids[pid] = {
                        "app_id":     app_id,
                        "session_id": session_id,
                        "exe":        exe,
                        "since":      since,
                    }
                    logger.info("[Tracker] Abierto: %s (pid=%d)", exe, pid)

            # ── Procesos cerrados ──
            closed = [pid for pid in self._active_pids if pid not in current_pids]
            for pid in closed:
                info = self._active_pids.pop(pid)
                end_session(info["session_id"])
                logger.info("[Tracker] Cerrado: %s (pid=%d)", info["exe"], pid)

            # ── Actualizar running_now (lista pública) ──
            seen: dict[str, str] = {}
            for info in self._active_pids.values():
                exe = info["exe"]
                if exe not in seen:
                    seen[exe] = info["since"]
            self.running_now = [
                {"exe_name": exe, "since": since}
                for exe, since in seen.items()
            ]


# Instancia global (singleton)
tracker = ProcessTracker()
