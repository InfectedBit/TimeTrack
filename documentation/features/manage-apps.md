# Feature: Manage Apps

Página de gestión de aplicaciones rastreadas (`/apps-page`, `ui/apps.html`). Permite añadir, editar, filtrar y eliminar apps, además de gestionar la detección automática de juegos y las imágenes asociadas a cada app.

---

## Secciones colapsables

La página se divide en dos secciones tipo acordeón. El estado abierto/cerrado se persiste en `localStorage`.

### ➕ Add application

**Formulario de alta manual**: proceso (.exe), nombre visible, color. El botón **📋 Pick from running** abre un modal con la lista de procesos activos del sistema para seleccionar uno directamente.

**Detección automática de juegos** (sub-card colapsable):
- Toggle on/off sincronizado con Settings → Tracker
- Métodos de detección (checkboxes): Launcher paths, Game Mode, NVIDIA DRS, Heurística, Rutas personalizadas
- Rutas personalizadas: añadir/eliminar carpetas donde buscar juegos
- Lista "No preguntar más": ver y limpiar exes descartados

> Ver `features/game-detection.md` para el detalle de los métodos.

---

### 📋 Tracked applications

Lista de todas las apps del perfil activo con sus controles.

#### Filtros y controles

| Control | Descripción | Persiste |
|---|---|---|
| **Búsqueda** | Filtra por `display_name` o `exe_name` en tiempo real | — |
| **`.*` Regex** | Activa modo regex en la búsqueda | `localStorage` |
| **Type** | All / Manual / Auto-detected | — |
| **Sort** | Default (orden BD) / A–Z (con cabeceras de letra por grupo) | `localStorage` |
| **Order** | ↑ ascendente / ↓ descendente | `localStorage` |
| **View** | ⊞ Grid (multi-columna) / ≡ List (una por fila) | `localStorage` |

La búsqueda regex muestra el campo en rojo si la expresión es inválida (sin filtrar mientras tanto).

Cuando Sort=A–Z, las apps se agrupan bajo cabeceras `[A] ─────`, `[B] ─────`, etc. El Order afecta al orden de los grupos y al orden dentro de cada grupo.

#### Acciones por app (tarjeta)

| Botón | Acción |
|---|---|
| `👁` | Alternar visibilidad en el dashboard (`is_hidden`). La app sigue trackeándose. |
| `🚫` | Excluir/reactivar del tracker (`is_active`). Excluida = no se registran sesiones. |
| `Edit` | Abre el modal de edición |
| `Delete` | Elimina la app y todas sus sesiones (con confirmación) |

---

## Modal de edición

Campos editables:
- **Display name** y **Color**
- **Cmdline filter**: texto que debe estar en el cmdline del proceso (útil para wrappers como `javaw.exe`)
- **Track main process only**: ignora procesos hijo con el mismo exe
- **Images**: panel con tres pestañas (Icon / Banner / Poster)

### Panel de imágenes

Tres tipos de imagen por app:

| Tipo | Proporción | Donde aparece |
|---|---|---|
| **Icon 1:1** | Cuadrado | Tarjetas en Manage Apps, filas de tabla en Dashboard |
| **Banner** | Horizontal (~16:5) | Cabecera del panel de detalle en Dashboard |
| **Poster** | Vertical (~2:3) | Gestión en el modal Edit |

Cada tipo soporta tres fuentes:

**URL** — pega una URL de imagen. Se carga directamente desde la web (requiere conexión). Se aplica al hacer clic en "Set".

**Upload** — selector de fichero. El fichero se sube al servidor (`POST /api/apps/{id}/images/{type}`) y se guarda en `images/app-images/{id}_{type}.ext`. Se aplica inmediatamente.

**From EXE** (solo icono) — extrae el icono incrustado en el `.exe` de la app. Requiere que el proceso esté en ejecución o que el exe esté en PATH. Usa PowerShell + `System.Drawing.Icon::ExtractAssociatedIcon` internamente.

**Clear** — elimina la imagen. Si era un fichero local, lo borra del disco y nullifica la BD.

La visibilidad de las imágenes en el dashboard y las tarjetas se controla con el toggle **App Images** en Settings → Visual (ver `features/themes.md`).

---

## Control del tracker desde Manage Apps

La barra lateral muestra el estado del tracker (● running / ⏸ paused) y el consumo de CPU/RAM. El botón **⚙ Settings** abre el panel de configuración global (idéntico al del dashboard).

---

## Archivos relevantes

| Fichero | Rol |
|---|---|
| `ui/apps.html` | Toda la lógica de Manage Apps |
| `ui/static/shared.js` | Settings modal, perfiles, game detect, game paths |
| `api/routes.py` | CRUD de apps, imágenes, procesos, settings |
| `core/database.py` | `get_tracked_apps`, `update_tracked_app`, `get_app_summary` |
