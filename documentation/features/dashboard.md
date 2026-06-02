# Feature: Dashboard

Página principal (`/`, `ui/index.html`). Muestra el resumen de uso de todas las apps del perfil activo y permite explorar el detalle de cada una.

---

## Tabla de apps

Lista todas las apps con `is_active=1` e `is_hidden=0`. Columnas:

| Columna | Fuente |
|---|---|
| Nombre + exe | `tracked_apps.display_name / exe_name` |
| Estado | `is_running` (calculado en tiempo real desde el tracker) |
| Sesiones | `COUNT(sessions)` en el periodo seleccionado |
| Tiempo total | `SUM(duration_secs)` formateado |
| Barra de uso | % relativo al máximo del periodo |

Haciendo clic en una fila se abre el **panel de detalle** de esa app.

---

## Filtro temporal

Botones de periodo rápido: **7d · 30d · 3m · 1y**. También hay un calendario para seleccionar un rango personalizado. El periodo aplica a la tabla, las gráficas y el cálculo de la barra de uso.

---

## Gráfica de barras — Top apps

Top 10 apps por horas en el periodo. Actualiza en lugar sin animación para no romper el estado del zoom. Eje Y formateado según la preferencia de horas (decimal `1.5h` o humano `1h30m`).

---

## Gráfica de líneas — Evolución temporal

Muestra la evolución de uso de múltiples apps a lo largo del tiempo. Soporta:

- **Modo línea**: una línea por app, eje X por días/semanas/meses
- **Modo barras apiladas**: mismas apps pero como barras
- **Zoom**: arrastra para hacer zoom, doble clic para resetear (chartjs-plugin-zoom + hammerjs)
- **Modo horario**: al hacer clic en una barra/punto del día actual, cambia a vista de 48 slots de 30 min

Configuración del comportamiento:
- `casualUseDays` — apps con 1 uso aparecen como punto si llevan N días sin actividad
- `inactivityTailDays` — extiende la línea X días antes/después de actividad

---

## Panel de detalle de app

Se abre al hacer clic en una fila de la tabla. Tres modos seleccionables en Settings:

| Modo | Comportamiento |
|---|---|
| **Panel lateral** | Desliza desde el borde derecho, overlay semitransparente |
| **Modal centrado** | Ventana centrada sobre el dashboard |
| **Flotante** | Ventana arrastrable libremente, sin overlay |

### Contenido del panel
1. Cabecera: nombre, exe, badge "● live" si está en ejecución ahora
2. **Banner** (si la app tiene `img_banner` configurado y `show_app_images=1`)
3. Stats: tiempo total, sesiones, media por sesión
4. Botones de rango: 7d / 30d / 3m / 1y
5. Gráfica de barras de uso diario/semanal/mensual
6. Lista de sesiones individuales con acciones

### Acciones en sesiones del panel
- **Editar**: modificar inicio/fin de una sesión (recalcula duración)
- **Eliminar**: borrar una sesión individual
- **⌫ Range**: borrar todas las sesiones de un rango de fechas
- **→ Move**: mover sesiones a otra app del mismo perfil

---

## Timeline diario

Modal con gráfica de Gantt horizontal que muestra las sesiones de todas las apps en un día/rango. Se abre haciendo clic en una barra de la gráfica de líneas (modo horario) o desde el botón del calendario.

Controles: navegar día anterior/siguiente, seleccionar rango 1d/3d/7d/14d/30d o personalizado.

---

## Indicador de apps en ejecución

`statusRefresh()` hace polling cada 3 s a `GET /api/tracker/status`. Actualiza:
- Los badges "● Running" en la tabla
- El estado del tracker en la barra lateral (● running / ⏸ paused / ○ stopped)
- Los datos de CPU/RAM del proceso de tracking

---

## Notificaciones de juegos pendientes

Si `game_detect=1` y se detecta un juego, aparece un banner en la parte superior del dashboard con el nombre del ejecutable y tres opciones:
- **Añadir** → el juego se añade al perfil activo
- **Ignorar** → descarta esta detección
- **Nunca** → añade el exe a la lista "No preguntar más"

---

## Archivos relevantes

| Fichero | Rol |
|---|---|
| `ui/index.html` | Toda la lógica del dashboard |
| `ui/static/shared.js` | `api()`, temas, settings modal, perfiles |
| `api/routes.py` | `/profiles/{id}/summary`, `/apps/{id}/stats`, `/apps/{id}/detail`, `/sessions/day` |
| `core/database.py` | `get_app_summary`, `get_daily_stats`, `get_sessions_for_day` |
