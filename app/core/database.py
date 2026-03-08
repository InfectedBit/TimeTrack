"""
AppTracker — Database Layer
SQLite con WAL mode, schema limpio y funciones bien alineadas con la API.
"""

import sys
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

# En modo frozen (PyInstaller), la DB vive junto al .exe; en dev, junto a main.py
DB_PATH = (
    Path(sys.executable).parent / "apptracker.db"
    if getattr(sys, 'frozen', False)
    else Path(__file__).parent.parent / "apptracker.db"
)

# Conexiones thread-local para seguridad en entornos multi-thread
_local = threading.local()


def get_connection() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA cache_size=-8000")   # 8 MB cache
        _local.conn = conn
    return _local.conn


def _q(sql: str, params=()):
    """Ejecuta query y retorna cursor (para INSERT/UPDATE/DELETE)."""
    return get_connection().execute(sql, params)


def _fetch(sql: str, params=()):
    """Ejecuta query y retorna lista de dicts."""
    rows = get_connection().execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def _commit():
    get_connection().commit()


# ─── INIT ─────────────────────────────────────────────────────────────────────

def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS profiles (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL UNIQUE,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            is_active   INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS tracked_apps (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id      INTEGER NOT NULL,
            exe_name        TEXT    NOT NULL,
            display_name    TEXT    NOT NULL,
            category        TEXT    NOT NULL DEFAULT 'other',
            color           TEXT    NOT NULL DEFAULT '#6366f1',
            auto_detected   INTEGER NOT NULL DEFAULT 0,
            is_active       INTEGER NOT NULL DEFAULT 1,
            added_at        TEXT    NOT NULL DEFAULT (datetime('now')),
            cmdline_match   TEXT,
            main_process_only INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE,
            UNIQUE(profile_id, exe_name)
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            app_id        INTEGER NOT NULL,
            profile_id    INTEGER NOT NULL,
            started_at    TEXT    NOT NULL,
            ended_at      TEXT,
            duration_secs INTEGER NOT NULL DEFAULT 0,
            date          TEXT    NOT NULL,
            FOREIGN KEY (app_id) REFERENCES tracked_apps(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_sessions_app_date
            ON sessions(app_id, date);
        CREATE INDEX IF NOT EXISTS idx_sessions_profile_date
            ON sessions(profile_id, date);

        INSERT OR IGNORE INTO profiles (name, is_active) VALUES ('Default', 1);

        CREATE TABLE IF NOT EXISTS dismissed_games (
            exe_name     TEXT PRIMARY KEY,
            dismissed_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        );

        INSERT OR IGNORE INTO settings (key, value) VALUES ('game_detect', '0');
        INSERT OR IGNORE INTO settings (key, value) VALUES ('notification_mode', 'tray');
        INSERT OR IGNORE INTO settings (key, value)
            VALUES ('detect_methods', '["launcher","custom","gamemode","nvidia","heuristic"]');

        CREATE TABLE IF NOT EXISTS game_paths (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            path     TEXT NOT NULL UNIQUE,
            added_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)

    # Migración segura: añadir columnas nuevas si la BD ya existe
    for col, defn in [
        ("cmdline_match",     "TEXT"),
        ("main_process_only", "INTEGER DEFAULT 0"),
        ("is_hidden",         "INTEGER NOT NULL DEFAULT 0"),
    ]:
        try:
            conn.execute(f"ALTER TABLE tracked_apps ADD COLUMN {col} {defn}")
        except Exception:
            pass  # La columna ya existe
    conn.commit()


# ─── PERFILES ─────────────────────────────────────────────────────────────────

def get_profiles() -> list[dict]:
    return _fetch("SELECT * FROM profiles ORDER BY created_at")


def create_profile(name: str) -> dict:
    _q("INSERT INTO profiles (name) VALUES (?)", (name,))
    _commit()
    return _fetch("SELECT * FROM profiles WHERE name=?", (name,))[0]


def set_active_profile(profile_id: int):
    _q("UPDATE profiles SET is_active=0")
    _q("UPDATE profiles SET is_active=1 WHERE id=?", (profile_id,))
    _commit()


def get_active_profile_id() -> int:
    rows = _fetch("SELECT id FROM profiles WHERE is_active=1 LIMIT 1")
    if rows:
        return rows[0]["id"]
    # Fallback: primer perfil disponible
    rows = _fetch("SELECT id FROM profiles LIMIT 1")
    return rows[0]["id"] if rows else 1


def delete_profile(profile_id: int):
    _q("DELETE FROM profiles WHERE id=? AND name != 'Default'", (profile_id,))
    _commit()


# ─── APPS ─────────────────────────────────────────────────────────────────────

def get_tracked_apps(profile_id: int) -> list[dict]:
    return _fetch(
        "SELECT * FROM tracked_apps WHERE profile_id=? ORDER BY display_name",
        (profile_id,)
    )


def add_tracked_app(
    profile_id: int,
    exe_name: str,
    display_name: str = "",
    category: str = "other",
    color: str = "#6366f1",
    auto_detected: int = 0,
) -> int:
    """Inserta o ignora si ya existe. Retorna el app_id."""
    exe_name = exe_name.lower().strip()
    if not display_name:
        display_name = exe_name.replace(".exe", "").replace("-", " ").replace("_", " ").title()
    cur = _q("""
        INSERT OR IGNORE INTO tracked_apps
            (profile_id, exe_name, display_name, category, color, auto_detected)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (profile_id, exe_name, display_name, category, color, auto_detected))
    _commit()
    if cur.lastrowid:
        return cur.lastrowid
    # Ya existía — devolver su id
    rows = _fetch(
        "SELECT id FROM tracked_apps WHERE profile_id=? AND exe_name=?",
        (profile_id, exe_name)
    )
    return rows[0]["id"] if rows else 0


def update_tracked_app(app_id: int, **kwargs):
    allowed = {
        "display_name", "category", "color", "is_active", "is_hidden",
        "auto_detected", "cmdline_match", "main_process_only",
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    set_clause = ", ".join(f"{k}=?" for k in fields)
    _q(f"UPDATE tracked_apps SET {set_clause} WHERE id=?",
       (*fields.values(), app_id))
    _commit()


def remove_tracked_app(app_id: int):
    _q("DELETE FROM tracked_apps WHERE id=?", (app_id,))
    _commit()


def get_exe_map(profile_id: int) -> dict[str, dict]:
    """Retorna {exe_lower: {app_id, cmdline_match, main_process_only}} para el tracker."""
    rows = _fetch(
        """SELECT id, exe_name, cmdline_match, main_process_only
           FROM tracked_apps WHERE profile_id=? AND is_active=1""",
        (profile_id,)
    )
    return {
        r["exe_name"]: {
            "app_id":           r["id"],
            "cmdline_match":    r["cmdline_match"],
            "main_process_only": r["main_process_only"],
        }
        for r in rows
    }


# ─── SESIONES ─────────────────────────────────────────────────────────────────

def start_session(app_id: int, profile_id: int) -> int:
    now = datetime.now()
    cur = _q("""
        INSERT INTO sessions (app_id, profile_id, started_at, date)
        VALUES (?, ?, ?, ?)
    """, (app_id, profile_id, now.isoformat(), now.strftime("%Y-%m-%d")))
    _commit()
    return cur.lastrowid


def end_session(session_id: int):
    now = datetime.now()
    rows = _fetch("SELECT started_at FROM sessions WHERE id=?", (session_id,))
    if not rows:
        return
    started = datetime.fromisoformat(rows[0]["started_at"])
    duration = max(0, int((now - started).total_seconds()))
    _q("UPDATE sessions SET ended_at=?, duration_secs=? WHERE id=?",
       (now.isoformat(), duration, session_id))
    _commit()


def close_orphan_sessions():
    """Cierra sesiones que quedaron abiertas (ej: crash del tracker)."""
    now = datetime.now()
    rows = _fetch("SELECT id, started_at FROM sessions WHERE ended_at IS NULL")
    for row in rows:
        started = datetime.fromisoformat(row["started_at"])
        duration = max(0, int((now - started).total_seconds()))
        _q("UPDATE sessions SET ended_at=?, duration_secs=? WHERE id=?",
           (now.isoformat(), duration, row["id"]))
    if rows:
        _commit()


# ─── ESTADÍSTICAS ─────────────────────────────────────────────────────────────

def get_app_summary(profile_id: int, days: int = 30,
                    date_from: str = None, date_to: str = None) -> list[dict]:
    """
    Resumen por app: total de tiempo, sesiones, última vez usada.
    Solo incluye apps activas (is_active=1) y no ocultas (is_hidden=0).
    Acepta rango absoluto (date_from/date_to) o ventana relativa (days).
    """
    if date_from and date_to:
        date_clause = "AND s.date >= ? AND s.date <= ?"
        params = (date_from, date_to, profile_id)
    else:
        date_clause = "AND s.date >= date('now', ?)"
        params = (f"-{days} days", profile_id)
    return _fetch(f"""
        SELECT
            ta.id,
            ta.exe_name,
            ta.display_name,
            ta.color,
            ta.category,
            ta.auto_detected,
            ta.cmdline_match,
            ta.main_process_only,
            ta.is_active,
            COALESCE(SUM(
                CASE WHEN s.ended_at IS NOT NULL THEN s.duration_secs
                     ELSE MAX(0, CAST(strftime('%s','now') - strftime('%s', s.started_at) AS INTEGER))
                END
            ), 0) AS total_secs,
            COUNT(s.id)       AS total_sessions,
            MAX(s.started_at) AS last_used
        FROM tracked_apps ta
        LEFT JOIN sessions s
            ON s.app_id = ta.id
           {date_clause}
        WHERE ta.profile_id = ?
          AND ta.is_active = 1
          AND ta.is_hidden = 0
        GROUP BY ta.id
        ORDER BY total_secs DESC
    """, params)


def get_daily_stats(profile_id: int, app_id: int, days: int = 30,
                    date_from: str = None, date_to: str = None) -> list[dict]:
    """Stats diarias para una app. Acepta rango absoluto o ventana relativa."""
    if date_from and date_to:
        where = "AND date >= ? AND date <= ?"
        params = (profile_id, app_id, date_from, date_to)
    else:
        where = "AND date >= date('now', ?)"
        params = (profile_id, app_id, f"-{days} days")
    return _fetch(f"""
        SELECT
            date,
            SUM(CASE WHEN ended_at IS NOT NULL THEN duration_secs
                     ELSE MAX(0, CAST(strftime('%s','now') - strftime('%s', started_at) AS INTEGER))
                END) AS total_secs,
            COUNT(*) AS sessions
        FROM sessions
        WHERE profile_id = ?
          AND app_id = ?
          {where}
        GROUP BY date
        ORDER BY date
    """, params)


def get_weekly_stats(app_id: int, weeks: int = 13) -> list[dict]:
    """Stats semanales para una app (para rango 3m). Incluye sesiones activas."""
    return _fetch("""
        SELECT
            strftime('%Y-W%W', date) AS week,
            MIN(date)                AS week_start,
            SUM(CASE WHEN ended_at IS NOT NULL THEN duration_secs
                     ELSE MAX(0, CAST(strftime('%s','now') - strftime('%s', started_at) AS INTEGER))
                END) AS total_secs,
            COUNT(*) AS sessions
        FROM sessions
        WHERE app_id = ?
          AND date >= date('now', ?)
        GROUP BY strftime('%Y-W%W', date)
        ORDER BY week
    """, (app_id, f"-{weeks * 7} days"))


def get_monthly_stats(app_id: int, months: int = 12) -> list[dict]:
    """Stats mensuales para una app (para rango 1y). Incluye sesiones activas."""
    return _fetch("""
        SELECT
            strftime('%Y-%m', date) AS month,
            SUM(CASE WHEN ended_at IS NOT NULL THEN duration_secs
                     ELSE MAX(0, CAST(strftime('%s','now') - strftime('%s', started_at) AS INTEGER))
                END) AS total_secs,
            COUNT(*) AS sessions
        FROM sessions
        WHERE app_id = ?
          AND date >= date('now', ?)
        GROUP BY strftime('%Y-%m', date)
        ORDER BY month
    """, (app_id, f"-{months * 31} days"))


def get_app_detail_stats(app_id: int, days: int = 30) -> dict:
    """Totales agregados para el header del panel de detalle. Incluye sesiones activas."""
    rows = _fetch("""
        SELECT
            COALESCE(SUM(
                CASE WHEN ended_at IS NOT NULL THEN duration_secs
                     ELSE MAX(0, CAST(strftime('%s','now') - strftime('%s', started_at) AS INTEGER))
                END
            ), 0) AS total_secs,
            COUNT(*) AS total_sessions,
            CAST(AVG(
                CASE WHEN ended_at IS NOT NULL THEN duration_secs
                     ELSE MAX(0, CAST(strftime('%s','now') - strftime('%s', started_at) AS INTEGER))
                END
            ) AS INTEGER) AS avg_secs,
            MIN(started_at) AS first_seen,
            MAX(started_at) AS last_used
        FROM sessions
        WHERE app_id = ?
          AND date >= date('now', ?)
    """, (app_id, f"-{days} days"))
    return rows[0] if rows else {
        "total_secs": 0, "total_sessions": 0,
        "avg_secs": 0, "first_seen": None, "last_used": None,
    }


def get_sessions_list(app_id: int, days: int = 30, limit: int = 200) -> list[dict]:
    """Lista de sesiones individuales ordenadas por inicio desc. Las activas aparecen al principio."""
    return _fetch("""
        SELECT
            id, started_at, ended_at,
            CASE WHEN ended_at IS NOT NULL THEN duration_secs
                 ELSE MAX(0, CAST(strftime('%s','now') - strftime('%s', started_at) AS INTEGER))
            END AS duration_secs,
            date
        FROM sessions
        WHERE app_id = ?
          AND date >= date('now', ?)
        ORDER BY started_at DESC
        LIMIT ?
    """, (app_id, f"-{days} days", limit))


def get_recent_sessions(profile_id: int, limit: int = 50) -> list[dict]:
    return _fetch("""
        SELECT s.*, ta.display_name, ta.color, ta.exe_name
        FROM sessions s
        JOIN tracked_apps ta ON ta.id = s.app_id
        WHERE s.profile_id = ?
          AND s.ended_at IS NOT NULL
        ORDER BY s.started_at DESC
        LIMIT ?
    """, (profile_id, limit))


# ─── EDICIÓN DE SESIONES ──────────────────────────────────────────────────────

def delete_session(session_id: int):
    """Elimina una sesión individual por su id."""
    _q("DELETE FROM sessions WHERE id=?", (session_id,))
    _commit()


def delete_sessions_in_range(app_id: int, date_from: str, date_to: str) -> int:
    """Elimina sesiones de una app entre date_from y date_to (inclusive, formato YYYY-MM-DD).
    Retorna el número de sesiones eliminadas."""
    cur = _q(
        "DELETE FROM sessions WHERE app_id=? AND date >= ? AND date <= ?",
        (app_id, date_from, date_to)
    )
    _commit()
    return cur.rowcount


def update_session(session_id: int, started_at: str, ended_at: str):
    """Actualiza inicio/fin de una sesión y recalcula duration_secs."""
    started = datetime.fromisoformat(started_at)
    ended   = datetime.fromisoformat(ended_at)
    duration = max(0, int((ended - started).total_seconds()))
    new_date = started.strftime("%Y-%m-%d")
    _q(
        "UPDATE sessions SET started_at=?, ended_at=?, duration_secs=?, date=? WHERE id=?",
        (started.isoformat(), ended.isoformat(), duration, new_date, session_id)
    )
    _commit()


def move_sessions(from_app_id: int, to_app_id: int,
                  date_from: str | None = None, date_to: str | None = None) -> int:
    """Reasigna sesiones de from_app_id a to_app_id (opcionalmente filtrado por rango de fechas).
    También actualiza profile_id del app destino. Retorna el número de sesiones movidas."""
    # Obtener profile_id del app destino
    rows = _fetch("SELECT profile_id FROM tracked_apps WHERE id=?", (to_app_id,))
    if not rows:
        return 0
    to_profile_id = rows[0]["profile_id"]

    if date_from and date_to:
        cur = _q(
            "UPDATE sessions SET app_id=?, profile_id=? WHERE app_id=? AND date >= ? AND date <= ?",
            (to_app_id, to_profile_id, from_app_id, date_from, date_to)
        )
    else:
        cur = _q(
            "UPDATE sessions SET app_id=?, profile_id=? WHERE app_id=?",
            (to_app_id, to_profile_id, from_app_id)
        )
    _commit()
    return cur.rowcount


# ─── SETTINGS ─────────────────────────────────────────────────────────────────

def get_setting(key: str, default: str = "") -> str:
    rows = _fetch("SELECT value FROM settings WHERE key=?", (key,))
    return rows[0]["value"] if rows else default


def set_setting(key: str, value: str):
    _q("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    _commit()


# ─── DISMISSED GAMES ──────────────────────────────────────────────────────────

def is_dismissed(exe_name: str) -> bool:
    rows = _fetch("SELECT 1 FROM dismissed_games WHERE exe_name=?", (exe_name.lower(),))
    return bool(rows)


def add_dismissed(exe_name: str):
    _q("INSERT OR REPLACE INTO dismissed_games (exe_name) VALUES (?)", (exe_name.lower(),))
    _commit()


def remove_dismissed(exe_name: str):
    _q("DELETE FROM dismissed_games WHERE exe_name=?", (exe_name.lower(),))
    _commit()


def get_dismissed_list() -> list[str]:
    return [r["exe_name"] for r in _fetch(
        "SELECT exe_name FROM dismissed_games ORDER BY dismissed_at DESC"
    )]


def clear_dismissed():
    _q("DELETE FROM dismissed_games")
    _commit()


def delete_sessions_since(app_id: int, since_iso: str) -> int:
    """Elimina sesiones de app_id cuyo started_at >= since_iso. Retorna filas eliminadas."""
    cur = _q(
        "DELETE FROM sessions WHERE app_id=? AND started_at >= ?",
        (app_id, since_iso),
    )
    _commit()
    return cur.rowcount


def count_sessions_for_app(app_id: int) -> int:
    """Retorna el número total de sesiones para app_id."""
    rows = _fetch("SELECT COUNT(*) AS c FROM sessions WHERE app_id=?", (app_id,))
    return rows[0]["c"] if rows else 0


def get_date_range(profile_id: int) -> dict:
    """Retorna {first_date, last_date} de todas las sesiones del perfil activo."""
    rows = _fetch(
        "SELECT MIN(date) AS first_date, MAX(date) AS last_date FROM sessions WHERE profile_id=?",
        (profile_id,),
    )
    if rows and rows[0]["first_date"]:
        return {"first_date": rows[0]["first_date"], "last_date": rows[0]["last_date"]}
    return {"first_date": None, "last_date": None}


def get_sessions_for_day(
    profile_id: int, date: str, date_to: str | None = None
) -> list[dict]:
    """Sesiones para un rango de fechas (±1 día overflow) excluyendo apps ocultas."""
    from datetime import datetime, timedelta
    dt_from  = datetime.strptime(date, "%Y-%m-%d")
    dt_to    = datetime.strptime(date_to, "%Y-%m-%d") if date_to else dt_from
    prev_day = (dt_from - timedelta(days=1)).strftime("%Y-%m-%d")
    next_day = (dt_to   + timedelta(days=1)).strftime("%Y-%m-%d")
    return _fetch(
        """
        SELECT s.id, s.app_id, a.display_name, a.color, a.exe_name,
               s.started_at, s.ended_at, s.duration_secs, s.date
        FROM   sessions s
        JOIN   tracked_apps a ON s.app_id = a.id
        WHERE  s.profile_id = ? AND s.date BETWEEN ? AND ?
          AND  a.is_active = 1 AND (a.is_hidden IS NULL OR a.is_hidden = 0)
        ORDER  BY s.started_at
        """,
        (profile_id, prev_day, next_day),
    )


# ─── GAME PATHS ───────────────────────────────────────────────────────────────

def get_game_paths() -> list[dict]:
    return _fetch("SELECT id, path, added_at FROM game_paths ORDER BY added_at")


def add_game_path(path: str) -> int:
    _q("INSERT OR IGNORE INTO game_paths (path) VALUES (?)", (path.strip(),))
    _commit()
    rows = _fetch("SELECT id FROM game_paths WHERE path=?", (path.strip(),))
    return rows[0]["id"] if rows else 0


def remove_game_path(path_id: int):
    _q("DELETE FROM game_paths WHERE id=?", (path_id,))
    _commit()


def get_detect_methods() -> list[str]:
    import json
    raw = get_setting(
        "detect_methods",
        '["launcher","custom","gamemode","nvidia","heuristic"]',
    )
    try:
        return json.loads(raw)
    except Exception:
        return ["launcher", "custom", "gamemode", "nvidia", "heuristic"]


def set_detect_methods(methods: list[str]):
    import json
    set_setting("detect_methods", json.dumps(methods))


# ─── MIGRACIÓN ────────────────────────────────────────────────────────────────

def migrate_profile(from_id: int, to_id: int) -> dict:
    """Mueve todos los apps y sesiones de from_id a to_id.
    Si un exe ya existe en el destino, redirige sus sesiones y elimina el app origen.
    El perfil origen queda vacío tras la migración."""
    from_apps  = get_tracked_apps(from_id)
    to_exe_map = {a["exe_name"]: a["id"] for a in get_tracked_apps(to_id)}

    for app in from_apps:
        if app["exe_name"] in to_exe_map:
            # El destino ya tiene este exe: redirigir sesiones y borrar el app origen
            _q("UPDATE sessions SET app_id=?, profile_id=? WHERE app_id=?",
               (to_exe_map[app["exe_name"]], to_id, app["id"]))
            _q("DELETE FROM tracked_apps WHERE id=?", (app["id"],))
        else:
            # Sin colisión: mover el registro de app al perfil destino
            _q("UPDATE tracked_apps SET profile_id=? WHERE id=?", (to_id, app["id"]))

    # Capturar sesiones huérfanas restantes
    _q("UPDATE sessions SET profile_id=? WHERE profile_id=?", (to_id, from_id))
    _commit()
    return {"ok": True}
