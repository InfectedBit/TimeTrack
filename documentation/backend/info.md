# Backend — Documentación de componentes

Servidor HTTP local (FastAPI + uvicorn) + loop de tracking de procesos (psutil) + detección de juegos. Toda la persistencia es SQLite con WAL mode.

---

## Estructura

```
(raíz del proyecto)
├── main.py             FastAPI app — rutas estáticas + ciclo de vida
├── tray.py             Punto de entrada — bandeja del sistema (pystray)
├── requirements.txt    Dependencias Python
│
├── api/
│   └── routes.py       Todos los endpoints REST (/api/…)
│
└── core/
    ├── database.py     Capa SQLite — schema, migraciones, queries
    ├── tracker.py      Loop de monitoreo de procesos (psutil)
    ├── game_detection.py  Heurística de detección de juegos
    └── notifications.py   Notificaciones de juegos (toast / tray)
```

---

## `tray.py` — Punto de entrada

Lanzador recomendado de la aplicación. Arranca uvicorn en un thread demonio y muestra un icono en la bandeja del sistema de Windows.

### Lógica de arranque
1. Resuelve `BASE_DIR` (funciona tanto con `python.exe` como `pythonw.exe` y en modo frozen PyInstaller)
2. Configura logging antes de importar `main` (evita que `basicConfig` de uvicorn sobreescriba la config)
3. Lanza `uvicorn.run(app, ...)` en un thread daemon
4. Crea el icono de bandeja con `pystray`

### Icono de bandeja
El icono se genera programáticamente con `Pillow` (no carga un `.ico`). Colores:
- **Morado** (`#a855f7`) — tracking activo
- **Gris** (`#64748b`) — tracker pausado

### Menú contextual
| Elemento | Acción |
|---|---|
| Open TimeTrack | Abre `http://127.0.0.1:{PORT}` en el navegador |
| ⏸ Pause / ▶ Resume | Llama a `POST /api/tracker/pause` |
| Quit | Detiene el tracker y cierra la app |

### Modos de ejecución
```
.venv\Scripts\pythonw.exe tray.py   # producción — sin consola
.venv\Scripts\python.exe  tray.py   # debug — con consola y logs visibles
TimeTrack-silent.vbs                # wrapper VBScript para pythonw (acceso directo)
TimeTrack.bat                       # wrapper para python con consola
```

---

## `main.py` — FastAPI Application

Define la app FastAPI, monta rutas estáticas y gestiona el ciclo de vida del servidor.

### Montaje de rutas estáticas
| URL prefix | Directorio | Condición |
|---|---|---|
| `/static` | `ui/static/` | solo si existe |
| `/images` | `images/` | solo si existe |
| `/user-images` | `images/app-images/` | siempre (creado en database.py) |

### Endpoints de páginas HTML
| Ruta | Fichero |
|---|---|
| `GET /` | `ui/index.html` |
| `GET /apps-page` | `ui/apps.html` |

### Ciclo de vida
- **startup**: `init_db()` + `tracker.start()`
- **shutdown**: `tracker.stop()`

### Puerto
Definido como constante `PORT` en `main.py`. Importado por `tray.py`. Configurable editando directamente el fichero.

---

## `api/routes.py` — Endpoints REST

Router FastAPI con prefijo `/api`. Todos los endpoints devuelven JSON.

### Tracker
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/tracker/status` | Estado + lista de procesos activos ahora mismo |
| POST | `/tracker/pause` | Pausa o reanuda el tracking |
| POST | `/tracker/settings` | Cambia auto_detect, game_detect y/o perfil activo |

### Perfiles
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/profiles` | Lista de perfiles |
| POST | `/profiles` | Crear perfil |
| PUT | `/profiles/{id}/activate` | Activar perfil |
| DELETE | `/profiles/{id}` | Eliminar perfil (no puede eliminar Default) |
| POST | `/profiles/migrate` | Mover apps+sesiones de un perfil a otro |
| GET | `/profiles/{id}/export` | Exportar perfil como JSON descargable |
| GET | `/profiles/{id}/apps` | Apps del perfil con flag `is_running` en tiempo real |
| GET | `/profiles/{id}/summary` | Resumen de uso por app (acepta `?days=N` o `?from=&to=`) |

### Apps (CRUD)
| Método | Ruta | Descripción |
|---|---|---|
| POST | `/apps` | Añadir app |
| PATCH | `/apps/{id}` | Editar app (display_name, color, cmdline, is_active, is_hidden, img_*) |
| DELETE | `/apps/{id}` | Eliminar app y todas sus sesiones |

### Imágenes de apps
| Método | Ruta | Descripción |
|---|---|---|
| POST | `/apps/{id}/images/{type}` | Subir imagen (multipart). `type`: icon \| banner \| poster |
| DELETE | `/apps/{id}/images/{type}` | Eliminar imagen (borra fichero local si procede) |
| POST | `/apps/{id}/images/icon/extract-exe` | Extraer icono del .exe vía PowerShell |

### Stats por app
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/apps/{id}/stats` | Stats diarias (acepta `?days` o `?from=&to=`) |
| GET | `/apps/{id}/detail` | Totales agregados para el panel de detalle |
| GET | `/apps/{id}/sessions` | Lista de sesiones individuales |
| GET | `/apps/{id}/weekly` | Stats semanales |
| GET | `/apps/{id}/monthly` | Stats mensuales |

### Edición de sesiones
| Método | Ruta | Descripción |
|---|---|---|
| DELETE | `/sessions/{id}` | Eliminar una sesión |
| PATCH | `/sessions/{id}` | Editar inicio/fin (recalcula duración) |
| DELETE | `/apps/{id}/sessions` | Borrar rango de fechas (`?from=&to=`) |
| POST | `/apps/{id}/sessions/move` | Mover sesiones a otra app |

### Configuración global
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/settings` | `notification_mode`, `game_detect`, `detect_methods`, `show_app_images` |
| POST | `/settings` | Actualiza uno o varios campos |

### Detección de juegos
| Método | Ruta | Descripción |
|---|---|---|
| POST | `/tracker/pending-games/{exe}` | Responder a juego pendiente: `yes\|no\|never` |
| DELETE | `/dismissed-games` | Limpiar lista "No preguntar más" |
| GET | `/dismissed-games` | Listar exes descartados |
| DELETE | `/dismissed-games/{exe}` | Eliminar entrada individual |
| GET | `/game-paths` | Rutas personalizadas de detección |
| POST | `/game-paths` | Añadir ruta |
| DELETE | `/game-paths/{id}` | Eliminar ruta |

### Procesos del sistema
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/processes` | Lista de procesos activos (para process picker) |
| GET | `/processes/{exe}/cmdlines` | Cmdlines de instancias en ejecución de un exe |

### Stats globales
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/stats/date-range` | Primera y última fecha con sesiones del perfil activo |
| GET | `/sessions/day` | Sesiones de un rango de fechas para el timeline |

---

## `core/database.py` — Capa de datos

SQLite con WAL mode, conexiones thread-local. Todo el acceso a datos pasa por este módulo.

### Rutas de datos
| Contexto | Ruta |
|---|---|
| Modo dev | `<raíz_proyecto>/apptracker.db` |
| Modo frozen (PyInstaller) | `<directorio_exe>/apptracker.db` |
| Imágenes de apps | `<DATA_DIR>/images/app-images/` |

### Schema de tablas
```sql
profiles(id, name, created_at, is_active)

tracked_apps(id, profile_id, exe_name, display_name, category, color,
             auto_detected, is_active, added_at, cmdline_match,
             main_process_only, is_hidden, img_icon, img_banner, img_poster)

sessions(id, app_id, profile_id, started_at, ended_at, duration_secs, date)

settings(key TEXT PK, value TEXT)   -- pares clave-valor

dismissed_games(exe_name TEXT PK, dismissed_at)

game_paths(id, path, added_at)
```

### Campos relevantes de `tracked_apps`
| Campo | Descripción |
|---|---|
| `is_active` | 0 = excluida del tracker y del dashboard |
| `is_hidden` | 1 = oculta del dashboard pero sigue trackeándose |
| `cmdline_match` | Filtro de cmdline para wrappers (javaw.exe, python.exe…) |
| `main_process_only` | Ignora procesos hijo con el mismo exe |
| `img_icon/banner/poster` | URL o ruta relativa `images/app-images/{filename}` |

### Claves de `settings`
| Clave | Valores | Descripción |
|---|---|---|
| `game_detect` | `0\|1` | Detección automática de juegos |
| `notification_mode` | `tray\|toast` | Canal de notificación |
| `detect_methods` | JSON array | Métodos de detección activos |
| `show_app_images` | `0\|1` | Mostrar imágenes en UI |

### Migración
`init_db()` usa `ALTER TABLE ... ADD COLUMN` con `try/except` para añadir columnas nuevas sin romper bases de datos existentes.

### Funciones principales
| Función | Descripción |
|---|---|
| `init_db()` | Crea tablas, inserta defaults, ejecuta migraciones |
| `get_exe_map(profile_id)` | `{exe_lower: {app_id, cmdline_match, main_process_only}}` — usado por el tracker cada ciclo |
| `get_app_summary(profile_id, days, ...)` | Resumen agregado: total_secs, sesiones, last_used, img_* |
| `start_session / end_session` | Gestión del ciclo de vida de una sesión |
| `close_orphan_sessions()` | Cierra sesiones sin `ended_at` (crashes anteriores) |
| `get_setting / set_setting` | Acceso a la tabla settings |

---

## `core/tracker.py` — Process Tracker

Loop de monitoreo en un thread daemon. Detecta apertura y cierre de procesos y registra sesiones en SQLite.

### Parámetros
| Constante | Valor | Descripción |
|---|---|---|
| `POLL_INTERVAL` | 3.0 s | Tiempo entre scans completos de psutil |
| `MAP_RELOAD` | 30 ciclos | Frecuencia de recarga de `exe_map` desde BD |

### Ciclo de vida de una sesión
```
proceso aparece → start_session() → pid en _active_pids
proceso desaparece → end_session() → pid eliminado de _active_pids
```

### Estados del tracker
- **running** — thread activo, scan cada 3 s
- **paused** — thread activo pero `scan()` retorna inmediatamente; todas las sesiones abiertas se cierran al pausar
- **stopped** — thread no iniciado o detenido

### Auto-detect
Cuando `_auto_detect = True`, todo proceso no presente en `exe_map` se añade automáticamente como app nueva (excepto los de `SYSTEM_SKIP` definidos en game_detection.py).

### Game detect
Si `game_detect = True`, los procesos identificados como juegos (por `game_detector.is_game()`) generan una notificación al usuario para confirmar antes de añadirlos.

### API pública (usada por routes.py)
| Método | Descripción |
|---|---|
| `tracker.start()` | Inicia el thread de monitoreo |
| `tracker.stop()` | Para el thread |
| `tracker.pause() / resume()` | Pausa/reanuda sin detener el thread |
| `tracker.reload()` | Recarga `exe_map` en el próximo ciclo |
| `tracker.get_status()` | Devuelve estado completo incluyendo `running_now` |
| `tracker.respond_to_game(exe, action)` | Responde a un juego pendiente (`yes/no/never`) |

### Instancia singleton
```python
from core.tracker import tracker   # instancia global del módulo
```

---

## `core/game_detection.py` — Detección de juegos

Heurística multicapa para identificar ejecutables de juegos. Lazy-initialized en el primer uso. No hace llamadas de red.

### Capas de detección (en orden, gana la primera coincidencia)

| Capa | Condición |
|---|---|
| **Launcher paths** | La ruta del exe contiene fragmentos de Steam, Epic, GOG, Ubisoft, Xbox, EA, Rockstar… |
| **Windows Game Mode** | `HKCU\System\GameConfigStore\Children\{…}\MatchedExeFullPath` |
| **NVIDIA DRS** | Ficheros `.nip` en `C:\ProgramData\NVIDIA Corporation\Drs\` |
| **Heurística** | Ruta fuera de `Windows/System32`, contiene palabras clave de juegos en el path |
| **Custom paths** | Rutas definidas por el usuario en la BD (`game_paths` table) |

### Lista de exclusión (`SYSTEM_SKIP`)
Conjunto exhaustivo de exes del sistema, navegadores, IDEs, apps comunes y procesos de NVIDIA/AMD que nunca se consideran juegos.

### Instancia singleton
```python
from core.game_detection import game_detector
game_detector.is_game(exe_name, exe_path)   # → bool
game_detector.reload()                       # recarga rutas personalizadas desde BD
```

---

## `core/notifications.py` — Notificaciones

Envía la prompt de confirmación de juego detectado. Dos modos:

| Modo | Requisito | Comportamiento |
|---|---|---|
| `toast` | `pip install win11toast` | Notificación nativa de Windows con botones Sí/No/Nunca |
| `tray` | siempre disponible | Actualiza el menú de la bandeja con la app detectada |

Si `win11toast` no está instalado, el modo `toast` cae automáticamente a `tray`.

Las callbacks (`on_yes`, `on_no`, `on_never`) se ejecutan desde un thread en segundo plano.

---

## `requirements.txt` — Dependencias

| Paquete | Uso |
|---|---|
| `fastapi` | Framework web, validación con Pydantic |
| `uvicorn[standard]` | Servidor ASGI |
| `psutil` | Monitoreo de procesos del sistema |
| `pystray` | Icono de bandeja del sistema |
| `Pillow` | Generación del icono de bandeja |
| `pydantic` | Validación de modelos de request |
| `python-multipart` | Soporte de `UploadFile` en FastAPI (imágenes) |
| `win11toast` | *(opcional)* Notificaciones toast de Windows 11 |

> Usar siempre el Python del venv (`.venv\Scripts\python.exe`), nunca el del sistema.
