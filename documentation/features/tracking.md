# Feature: Process Tracking & Sessions

Núcleo de TimeTrack. Detecta qué programas están abiertos y cuánto tiempo llevan ejecutándose, registrando sesiones en SQLite.

---

## Cómo funciona el loop

`core/tracker.py` — clase `ProcessTracker`, instancia singleton `tracker`.

```
cada 3 segundos (POLL_INTERVAL):
  1. psutil.process_iter() → lista de PIDs activos
  2. para cada PID activo:
       exe_name = proceso.exe_name().lower()
       si exe_name en _exe_map → app conocida → abrir sesión si no estaba abierta
  3. para cada PID en _active_pids:
       si PID ya no existe → end_session() → cerrar sesión
  4. cada 30 ciclos → recargar _exe_map desde BD (MAP_RELOAD)
```

`_exe_map`: diccionario `{exe_lower: {app_id, cmdline_match, main_process_only}}` cargado desde `tracked_apps` donde `is_active=1`.

---

## Ciclo de vida de una sesión

```
proceso abre  →  start_session(app_id, profile_id)  →  sesión con ended_at=NULL
proceso cierra →  end_session(session_id)             →  duration_secs calculado
```

Si el tracker se cierra inesperadamente (crash), `close_orphan_sessions()` cierra todas las sesiones con `ended_at IS NULL` al arrancar de nuevo, usando `datetime.now()` como fin aproximado.

### Qué se guarda en cada sesión
| Campo | Descripción |
|---|---|
| `started_at` | ISO datetime del momento de detección |
| `ended_at` | ISO datetime del cierre (NULL si activa) |
| `duration_secs` | `(ended_at - started_at)` en segundos |
| `date` | YYYY-MM-DD — desnormalizado para queries rápidas |

---

## Pausa y reanudación

`POST /api/tracker/pause {"paused": true/false}`

- **Pausar**: cierra todas las sesiones activas (`end_session` para cada PID en `_active_pids`), vacía `_active_pids`, activa `_paused = True`. El thread sigue corriendo pero `scan()` retorna inmediatamente.
- **Reanudar**: `_paused = False`. En el siguiente ciclo, los procesos en marcha abren nuevas sesiones.

Estado visible en la bandeja: icono **morado** = activo, **gris** = pausado.

---

## Auto-detect

Cuando `auto_detect = True` (configurable en Settings), cualquier proceso no presente en `_exe_map` se añade automáticamente como nueva app. Excluye los exes en `SYSTEM_SKIP` (procesos del sistema, navegadores, IDEs…).

Se activa/desactiva vía `POST /api/tracker/settings`.

---

## Filtros por app

Dos campos opcionales en `tracked_apps` que refinan cuándo se abre sesión:

| Campo | Función |
|---|---|
| `cmdline_match` | Sólo cuenta instancias cuyo cmdline contenga este texto (case-insensitive). Útil para wrappers: `javaw.exe` + `"net.minecraft"` → solo Minecraft, no otros .jar. |
| `main_process_only` | Ignora procesos hijo con el mismo exe. Útil para Chrome (un proceso por pestaña). Identifica el padre por PID más bajo. |

---

## Estados visibles en la API

`GET /api/tracker/status` devuelve:

```json
{
  "running": true,
  "paused": false,
  "auto_detect": false,
  "profile_id": 1,
  "tracked_count": 12,
  "active_pids": [1234, 5678],
  "running_now": [{"exe_name": "chrome.exe", "since": "2025-05-30T10:00:00"}],
  "cpu_pct": 0.1,
  "mem_mb": 42
}
```

`running_now` alimenta los badges "● running" en el dashboard y en Manage Apps.

---

## Excluir o silenciar una app

| Acción | Campo BD | Efecto |
|---|---|---|
| **Excluir** (`🚫`) | `is_active = 0` | El tracker ignora el exe. No abre sesiones. Oculta del dashboard. |
| **Ocultar** (`👁`) | `is_hidden = 1` | El tracker sigue rastreando. No aparece en el dashboard ni en `/summary`. |

---

## Archivos relevantes

| Fichero | Rol |
|---|---|
| `core/tracker.py` | Loop de monitoreo, clase `ProcessTracker` |
| `core/database.py` | `start_session`, `end_session`, `close_orphan_sessions`, `get_exe_map` |
| `api/routes.py` | `GET /tracker/status`, `POST /tracker/pause`, `POST /tracker/settings` |
