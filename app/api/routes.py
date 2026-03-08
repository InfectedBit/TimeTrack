"""
AppTracker — API Routes
Todos los endpoints REST. Perfectamente alineados con lo que llama la UI.
"""

import psutil
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from core import database as db
from core.tracker import tracker

router = APIRouter(prefix="/api")


# ── Modelos ───────────────────────────────────────────────────────────────────

class ProfileCreate(BaseModel):
    name: str

class AppAdd(BaseModel):
    exe_name:     str
    display_name: Optional[str] = None
    category:     Optional[str] = "other"
    color:        Optional[str] = "#6366f1"
    profile_id:   Optional[int] = None

class AppUpdate(BaseModel):
    display_name:      Optional[str] = None
    category:          Optional[str] = None
    color:             Optional[str] = None
    is_active:         Optional[int] = None
    is_hidden:         Optional[int] = None
    cmdline_match:     Optional[str] = None
    main_process_only: Optional[int] = None

class TrackerSettings(BaseModel):
    auto_detect:  bool
    profile_id:   Optional[int]  = None
    game_detect:  Optional[bool] = None

class TrackerPause(BaseModel):
    paused: bool

class SessionUpdate(BaseModel):
    started_at: str
    ended_at:   str

class SessionMove(BaseModel):
    to_app_id: int
    date_from: Optional[str] = None
    date_to:   Optional[str] = None


# ── Tracker ───────────────────────────────────────────────────────────────────

@router.get("/tracker/status")
def tracker_status():
    """Estado del tracker + lista de apps activas ahora mismo."""
    return tracker.get_status()


@router.post("/tracker/pause")
def tracker_pause(body: TrackerPause):
    """Pausa o reanuda el tracking. Al pausar, cierra las sesiones activas."""
    if body.paused:
        tracker.pause()
    else:
        tracker.resume()
    return {"ok": True, "paused": body.paused}


@router.post("/tracker/settings")
def tracker_settings(body: TrackerSettings):
    """Actualiza auto_detect, game_detect y/o perfil activo del tracker."""
    if body.profile_id is not None:
        db.set_active_profile(body.profile_id)
    tracker.set_auto_detect(body.auto_detect, body.profile_id)
    if body.game_detect is not None:
        tracker.set_game_detect(body.game_detect)
    return {"ok": True}


# ── Perfiles ──────────────────────────────────────────────────────────────────

@router.get("/profiles")
def list_profiles():
    return db.get_profiles()


@router.post("/profiles", status_code=201)
def create_profile(body: ProfileCreate):
    try:
        return db.create_profile(body.name)
    except Exception as exc:
        raise HTTPException(400, str(exc))


@router.put("/profiles/{profile_id}/activate")
def activate_profile(profile_id: int):
    db.set_active_profile(profile_id)
    tracker.reload()
    return {"ok": True}


@router.delete("/profiles/{profile_id}")
def delete_profile(profile_id: int):
    db.delete_profile(profile_id)
    return {"ok": True}


# ── Apps por perfil ───────────────────────────────────────────────────────────

@router.get("/profiles/{profile_id}/apps")
def profile_apps(profile_id: int):
    """Lista de apps del perfil con flag is_running en tiempo real."""
    apps = db.get_tracked_apps(profile_id)
    status = tracker.get_status()
    running_exes  = {r["exe_name"] for r in status["running_now"]}
    running_since = {r["exe_name"]: r["since"] for r in status["running_now"]}
    for app in apps:
        app["is_running"]     = app["exe_name"] in running_exes
        app["running_since"]  = running_since.get(app["exe_name"])
    return apps


@router.get("/profiles/{profile_id}/summary")
def profile_summary(
    profile_id: int,
    days: int = Query(7, ge=1, le=365),
    date_from: Optional[str] = Query(None, alias="from"),
    date_to:   Optional[str] = Query(None, alias="to"),
):
    """Resumen de uso por app. Acepta ?days=N o ?from=YYYY-MM-DD&to=YYYY-MM-DD."""
    summary = db.get_app_summary(profile_id, days, date_from, date_to)
    status = tracker.get_status()
    running_exes = {r["exe_name"] for r in status["running_now"]}
    for item in summary:
        item["is_running"] = item["exe_name"] in running_exes
    return summary


# ── Apps (CRUD) ───────────────────────────────────────────────────────────────

@router.post("/apps", status_code=201)
def add_app(body: AppAdd):
    pid = body.profile_id or db.get_active_profile_id()
    app_id = db.add_tracked_app(
        pid,
        body.exe_name,
        body.display_name or "",
        body.category or "other",
        body.color or "#6366f1",
        auto_detected=0,
    )
    tracker.reload()
    return {"ok": True, "app_id": app_id}


@router.patch("/apps/{app_id}")
def update_app(app_id: int, body: AppUpdate):
    db.update_tracked_app(app_id, **body.model_dump(exclude_none=True))
    tracker.reload()
    return {"ok": True}


@router.delete("/apps/{app_id}")
def delete_app(app_id: int):
    db.remove_tracked_app(app_id)
    tracker.reload()
    return {"ok": True}


# ── Stats por app ──────────────────────────────────────────────────────────────

@router.get("/apps/{app_id}/stats")
def app_stats(
    app_id: int,
    days: int = Query(30, ge=1, le=365),
    date_from: Optional[str] = Query(None, alias="from"),
    date_to:   Optional[str] = Query(None, alias="to"),
):
    """Stats diarias de una app. Acepta ?days=N o ?from=YYYY-MM-DD&to=YYYY-MM-DD."""
    profile_id = db.get_active_profile_id()
    return db.get_daily_stats(profile_id, app_id, days, date_from, date_to)


@router.get("/apps/{app_id}/detail")
def app_detail(app_id: int, days: int = Query(30, ge=1, le=365)):
    """Totales agregados para el header del panel lateral: {total_secs, sessions, avg_secs, ...}."""
    return db.get_app_detail_stats(app_id, days)


@router.get("/apps/{app_id}/sessions")
def app_sessions(app_id: int, days: int = Query(30, ge=1, le=365)):
    """Lista de sesiones individuales: [{started_at, ended_at, duration_secs, date}]."""
    return db.get_sessions_list(app_id, days)


@router.get("/apps/{app_id}/weekly")
def app_weekly(app_id: int, weeks: int = Query(13, ge=1, le=52)):
    """Stats semanales para rango 3m: [{week, week_start, total_secs, sessions}]."""
    return db.get_weekly_stats(app_id, weeks)


@router.get("/apps/{app_id}/monthly")
def app_monthly(app_id: int, months: int = Query(12, ge=1, le=24)):
    """Stats mensuales para rango 1y: [{month, total_secs, sessions}]."""
    return db.get_monthly_stats(app_id, months)


# ── Edición de sesiones ───────────────────────────────────────────────────────

@router.delete("/sessions/{session_id}")
def delete_session(session_id: int):
    """Elimina una sesión individual."""
    db.delete_session(session_id)
    return {"ok": True}


@router.patch("/sessions/{session_id}")
def update_session(session_id: int, body: SessionUpdate):
    """Edita el inicio y fin de una sesión; recalcula duration_secs."""
    try:
        db.update_session(session_id, body.started_at, body.ended_at)
    except Exception as exc:
        raise HTTPException(400, f"Formato de fecha inválido: {exc}")
    return {"ok": True}


@router.delete("/apps/{app_id}/sessions")
def delete_sessions_range(
    app_id: int,
    date_from: str = Query(..., description="YYYY-MM-DD"),
    date_to:   str = Query(..., description="YYYY-MM-DD"),
):
    """Elimina todas las sesiones de una app dentro del rango de fechas (inclusive)."""
    count = db.delete_sessions_in_range(app_id, date_from, date_to)
    return {"ok": True, "deleted": count}


@router.post("/apps/{app_id}/sessions/move")
def move_sessions(app_id: int, body: SessionMove):
    """Mueve sesiones de app_id a to_app_id, opcionalmente filtradas por rango de fechas."""
    count = db.move_sessions(app_id, body.to_app_id, body.date_from, body.date_to)
    return {"ok": True, "moved": count}


# ── Procesos del sistema ──────────────────────────────────────────────────────

@router.get("/processes")
def list_processes():
    """Lista de procesos activos del sistema para el process-picker."""
    seen: set[str] = set()
    result: list[dict] = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            name = proc.info["name"]
            if name and name.lower() not in seen:
                seen.add(name.lower())
                result.append({"name": name, "exe": name.lower()})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return sorted(result, key=lambda x: x["name"].lower())


@router.get("/processes/{exe_name}/cmdlines")
def process_cmdlines(exe_name: str):
    """Lista de cmdlines de todas las instancias en ejecución del exe dado."""
    results = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if proc.info["name"] and proc.info["name"].lower() == exe_name.lower():
                cmdline = proc.info["cmdline"] or []
                results.append({"pid": proc.info["pid"], "cmdline": " ".join(cmdline)})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return results


# ── Migración y export de perfiles ───────────────────────────────────────────

class ProfileMigrate(BaseModel):
    from_id: int
    to_id:   int


@router.post("/profiles/migrate")
def migrate_profile(body: ProfileMigrate):
    """Mueve todos los apps y sesiones de from_id a to_id."""
    result = db.migrate_profile(body.from_id, body.to_id)
    tracker.reload()
    return result


@router.get("/profiles/{profile_id}/export")
def export_profile(profile_id: int):
    """Exporta el perfil completo (apps + sesiones) como JSON descargable."""
    import json
    from fastapi.responses import Response

    profiles = db.get_profiles()
    profile  = next((p for p in profiles if p["id"] == profile_id), None)
    if not profile:
        raise HTTPException(404, "Perfil no encontrado")

    apps     = db.get_tracked_apps(profile_id)
    app_ids  = [a["id"] for a in apps]

    # Obtener todas las sesiones de estos apps
    sessions: list[dict] = []
    if app_ids:
        from core.database import _fetch
        placeholders = ",".join("?" * len(app_ids))
        sessions = _fetch(
            f"SELECT * FROM sessions WHERE app_id IN ({placeholders}) ORDER BY started_at",
            tuple(app_ids)
        )

    payload = {
        "profile":  profile,
        "apps":     apps,
        "sessions": sessions,
    }
    filename = profile["name"].replace(" ", "_") + "_export.json"
    return Response(
        content=json.dumps(payload, indent=2, ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Game detection ────────────────────────────────────────────────────────────

class GameResponse(BaseModel):
    action: str   # 'yes' | 'no' | 'never'


@router.post("/tracker/pending-games/{exe_name}")
def respond_pending_game(exe_name: str, body: GameResponse):
    """Responde a un juego detectado pendiente. action: 'yes' | 'no' | 'never'."""
    if body.action not in ("yes", "no", "never"):
        raise HTTPException(400, "action must be 'yes', 'no', or 'never'")
    tracker.respond_to_game(exe_name, body.action)
    return {"ok": True}


# ── Global settings ───────────────────────────────────────────────────────────

class AppSettings(BaseModel):
    notification_mode: Optional[str]       = None   # 'toast' | 'tray'
    detect_methods:    Optional[list[str]] = None


class GamePathAdd(BaseModel):
    path: str


@router.get("/settings")
def get_app_settings():
    """Retorna configuración global (notification_mode, detect_methods, etc.)."""
    return {
        "notification_mode": db.get_setting("notification_mode", "tray"),
        "game_detect":       db.get_setting("game_detect", "0") == "1",
        "detect_methods":    db.get_detect_methods(),
    }


@router.post("/settings")
def update_app_settings(body: AppSettings):
    """Actualiza configuración global."""
    if body.notification_mode in ("toast", "tray"):
        db.set_setting("notification_mode", body.notification_mode)
    if body.detect_methods is not None:
        valid   = {"launcher", "custom", "gamemode", "nvidia", "heuristic"}
        methods = [m for m in body.detect_methods if m in valid]
        db.set_detect_methods(methods)
        from core.game_detection import game_detector
        game_detector.reload()
    return {"ok": True}


@router.delete("/dismissed-games")
def clear_dismissed_games():
    """Limpia toda la lista de juegos descartados ('No preguntar más')."""
    db.clear_dismissed()
    return {"ok": True}


@router.get("/dismissed-games")
def list_dismissed_games():
    """Lista de exes en la lista de 'No preguntar más'."""
    return db.get_dismissed_list()


@router.delete("/dismissed-games/{exe_name}")
def remove_dismissed_game(exe_name: str):
    """Elimina una entrada individual de la lista 'No preguntar más'."""
    db.remove_dismissed(exe_name)
    return {"ok": True}


@router.get("/stats/date-range")
def get_date_range():
    """Retorna {first_date, last_date} de todas las sesiones del perfil activo."""
    profile_id = db.get_active_profile_id()
    return db.get_date_range(profile_id)


@router.get("/sessions/day")
def sessions_for_day(
    date:    str           = Query(...,  description="YYYY-MM-DD start date"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD end date (multi-day view)"),
):
    """Sesiones de un rango de fechas (±1 día overflow) para apps visibles."""
    profile_id = db.get_active_profile_id()
    return db.get_sessions_for_day(profile_id, date, date_to)


# ── Game paths ────────────────────────────────────────────────────────────────

@router.get("/game-paths")
def list_game_paths():
    """Lista de rutas personalizadas para detección de juegos."""
    return db.get_game_paths()


@router.post("/game-paths", status_code=201)
def add_game_path(body: GamePathAdd):
    """Añade una ruta personalizada para detección de juegos."""
    if not body.path.strip():
        raise HTTPException(400, "path cannot be empty")
    path_id = db.add_game_path(body.path)
    from core.game_detection import game_detector
    game_detector.reload()
    return {"ok": True, "id": path_id}


@router.delete("/game-paths/{path_id}")
def remove_game_path(path_id: int):
    """Elimina una ruta personalizada por id."""
    db.remove_game_path(path_id)
    from core.game_detection import game_detector
    game_detector.reload()
    return {"ok": True}
