# TimeTrack — Visión general

Aplicación de escritorio para Windows que registra automáticamente cuánto tiempo usas cada programa. Corre en segundo plano como icono de bandeja, sin consola visible, y expone un panel web local para ver estadísticas y gestionar qué se rastrea.

---

## ¿Qué hace?

- Detecta qué ejecutables están abiertos cada 3 segundos (via `psutil`)
- Registra sesiones con inicio y fin exactos en SQLite
- Muestra gráficas de uso por app, día, semana y mes
- Permite gestionar manualmente qué apps se rastrean y cuáles no
- Detecta juegos automáticamente con confirmación previa
- Soporta múltiples perfiles de usuario independientes

---

## Stack técnico

| Capa | Tecnología |
|---|---|
| Servidor HTTP | FastAPI + uvicorn (puerto local configurable) |
| Persistencia | SQLite 3 con WAL mode |
| Monitoreo de procesos | psutil (Python) |
| Bandeja del sistema | pystray + Pillow |
| Frontend | HTML + CSS + JavaScript vanilla (sin bundler) |
| Gráficas | Chart.js 4.x (CDN) |

---

## Cómo ejecutar

```
# Primera vez
setup.bat                          # crea el venv e instala dependencias

# Uso normal (sin consola)
TimeTrack-silent.vbs               # lanza pythonw.exe tray.py
# o el acceso directo del escritorio

# Modo debug (con consola y logs)
TimeTrack.bat                      # lanza python.exe tray.py

# Equivalente manual
.venv\Scripts\pythonw.exe tray.py  # silencioso
.venv\Scripts\python.exe  tray.py  # con consola
```

> **Importante:** nunca usar el Python del sistema. Siempre el del venv.

Una vez en marcha: `http://localhost:<PORT>` en el navegador.

---

## Datos del usuario

Todos los datos se guardan junto al ejecutable (o junto a `main.py` en dev):

```
<directorio_datos>/
├── apptracker.db          Base de datos SQLite principal
├── apptracker.db-shm      WAL shared memory
├── apptracker.db-wal      WAL log
├── timetrack.log          Log de errores y eventos
└── images/
    └── app-images/        Imágenes de apps (iconos, banners, pósters)
```

---

## Estructura de ficheros del proyecto

```
TimeTrack/
├── main.py              FastAPI app + montaje de rutas estáticas
├── tray.py              Punto de entrada: bandeja del sistema
├── requirements.txt     Dependencias Python
│
├── api/
│   └── routes.py        Todos los endpoints REST (/api/…)
│
├── core/
│   ├── database.py      Schema SQLite, migraciones, queries
│   ├── tracker.py       Loop de monitoreo de procesos (3 s)
│   ├── game_detection.py  Heurística de detección de juegos
│   └── notifications.py   Notificaciones toast / tray
│
├── ui/                  Frontend (servido por FastAPI)
│   ├── index.html       Dashboard
│   ├── apps.html        Manage Apps
│   └── static/
│       ├── shared.css   Estilos comunes (ambas páginas)
│       └── shared.js    Lógica compartida (ambas páginas)
│
├── images/
│   ├── timetrack/
│   │   └── favicon_1.png
│   └── app-images/      Imágenes de usuario (iconos/banners/pósters)
│
└── documentation/
    ├── app.md           ← Este fichero
    ├── features/        Documentación por característica
    ├── ui/info.md       Arquitectura técnica del frontend
    └── backend/info.md  Arquitectura técnica del backend
```

---

## Páginas web

| URL | Fichero | Descripción |
|---|---|---|
| `/` | `ui/index.html` | Dashboard: gráficas, tabla de apps, detalle |
| `/apps-page` | `ui/apps.html` | Gestión de apps, filtros, imágenes |

---

## Rutas estáticas

| URL prefix | Directorio | Uso |
|---|---|---|
| `/static` | `ui/static/` | shared.css, shared.js |
| `/images` | `images/` | Favicon y assets de la app |
| `/user-images` | `images/app-images/` | Imágenes subidas por el usuario |

---

## Base de datos — tablas principales

| Tabla | Descripción |
|---|---|
| `profiles` | Perfiles de usuario independientes |
| `tracked_apps` | Apps registradas con su configuración |
| `sessions` | Sesiones individuales con inicio/fin/duración |
| `settings` | Configuración global clave-valor |
| `dismissed_games` | Juegos marcados como "no preguntar más" |
| `game_paths` | Rutas personalizadas para detección de juegos |

---

## Para saber más

| Tema | Fichero |
|---|---|
| Tracking de procesos y sesiones | `features/tracking.md` |
| Dashboard y gráficas | `features/dashboard.md` |
| Gestión de apps, filtros e imágenes | `features/manage-apps.md` |
| Perfiles | `features/profiles.md` |
| Temas visuales y shared.js/css | `features/themes.md` |
| Detección automática de juegos | `features/game-detection.md` |
| Arquitectura técnica frontend | `ui/info.md` |
| Arquitectura técnica backend | `backend/info.md` |
