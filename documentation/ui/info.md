# UI — Documentación de componentes

Capa frontend de TimeTrack. Sin bundler ni framework: HTML + CSS + JS vanilla servidos directamente por FastAPI mediante `FileResponse`.

---

## Estructura

```
ui/
├── index.html          Dashboard principal
├── apps.html           Gestión de aplicaciones rastreadas
└── static/
    ├── shared.css      Estilos comunes (cargado por ambas páginas)
    └── shared.js       Lógica compartida (cargado por ambas páginas)
```

---

## `index.html` — Dashboard

**Ruta:** `/`

Panel principal de estadísticas de uso. Carga gráficas con Chart.js.

### Responsabilidades
- Tabla de apps con tiempo de uso, sesiones y barra de actividad
- Gráfica de barras: top 10 apps por horas (seleccionable por periodo)
- Gráfica de líneas: evolución temporal de múltiples apps
- Panel de detalle de app (modos: lateral / modal centrado / flotante arrastrable)
- Modal de timeline diario con selección de rango
- Modales de gestión de sesiones: editar, borrar rango, mover entre apps
- Indicador de apps con tracking activo en tiempo real (polling cada 3 s)
- Notificaciones de juegos detectados pendientes de confirmación

### Dependencias externas (CDN)
| Librería | Uso |
|---|---|
| `chart.js@4.4.0` | Todas las gráficas |
| `hammerjs@2.0.8` | Soporte touch para zoom en gráficas |
| `chartjs-plugin-zoom@2.2.0` | Zoom/pan en gráfica de líneas |

### Estado JS principal
| Variable | Tipo | Descripción |
|---|---|---|
| `lastSummary` | `Array` | Último resultado de `/api/profiles/{id}/summary` |
| `detailApp` | `Object\|null` | App cuyo panel de detalle está abierto |
| `detailDays` | `number` | Ventana temporal del panel de detalle (7/30/90/365) |
| `chartBar/chartLine/chartDetail` | `Chart\|null` | Instancias Chart.js activas |
| `days/dateFrom/dateTo` | mixed | Filtro temporal del dashboard |

### Funciones clave (page-specific)
- `dataRefresh()` — recarga summary + charts cada 15 s
- `statusRefresh()` — actualiza badges "running" cada 3 s
- `renderSummary(data)` — pinta la tabla de apps
- `openDetail(appId)` — abre el panel de detalle de una app
- `renderBarChart / renderLineChart / renderDetailChart` — actualiza las gráficas
- `fmtHours(h)` — formatea horas en decimal o `Xh Ym` según preferencia

---

## `apps.html` — Manage Apps

**Ruta:** `/apps-page`

Página de gestión de aplicaciones rastreadas.

### Secciones (colapsables, estado persistido en `localStorage`)
1. **➕ Add application** — formulario de alta manual + detección automática de juegos
2. **📋 Tracked applications** — listado filtrable y ordenable de todas las apps

### Filtros y controles del listado
| Control | Opciones | Persistencia |
|---|---|---|
| Búsqueda texto | plain text / regex (`.*`) | — |
| Type | All / Manual / Auto-detected | — |
| Sort | Default / A–Z (con cabeceras de letra) | `localStorage` |
| Order | ↑ asc / ↓ desc | `localStorage` |
| View | ⊞ Grid / ≡ List | `localStorage` |

### Modal de edición de app
Campos: display name, color, cmdline filter, main-process-only, **Images** (Icon 1:1 / Banner / Poster).

El panel de imágenes soporta:
- **URL** — se carga directamente desde la web
- **Upload** — sube el fichero al servidor (`POST /api/apps/{id}/images/{type}`)
- **From EXE** (solo icono) — extrae el icono del ejecutable vía PowerShell + `System.Drawing`
- **Clear** — borra la imagen del servidor y nullifica la BD

### Estado JS principal (page-specific)
| Variable | Descripción |
|---|---|
| `allApps` | Lista completa de apps del perfil activo |
| `currentTab/Sort/View/Dir/Search` | Estado de filtros y vista |
| `isRegex` | Modo regex en búsqueda |
| `editImgType/editImgSrc` | Pestaña activa en el panel de imágenes del modal |

### Funciones clave (page-specific)
- `renderApps()` — aplica filtros/orden y renderiza `renderCard()` en el grid
- `renderCard(a)` — genera el HTML de una tarjeta de app
- `loadApps()` — descarga apps + summary del perfil activo y fusiona
- `loadTrackerSettings()` — carga `auto_detect` y `game_detect` desde la API

---

## `static/shared.css` — Estilos compartidos

Cargado en `<head>` de **ambas** páginas antes del `<style>` inline de cada una. CSS custom properties (`--bg`, `--surface`, `--accent`…) que los temas sobreescriben en runtime vía `applyTheme()`.

### Bloques incluidos
| Bloque | Clases principales |
|---|---|
| Variables y reset | `:root`, `*`, `body`, `body::before` |
| Layout | `.shell` |
| Sidebar | `nav`, `.logo`, `.nav-link`, `.profile-section`, `.resource-bar`, `.settings-btn` |
| Botones | `.btn`, `.btn-primary`, `.btn-danger`, `.btn-ghost`, `.btn-sm` |
| Toggle switch | `.toggle`, `.toggle-slider` |
| Modal base | `.modal-bg`, `.modal`, `.modal-head`, `.modal-close`, `.proc-item` |
| Settings modal | `.settings-modal`, `.settings-tabs`, `.settings-tab`, `.settings-body` |
| Settings accordion | `.settings-section`, `.section-title`, `.section-arrow`, `.section-body` |
| Mode options | `.mode-opt*` |
| Format options | `.fmt-opt` |
| Theme swatches | `.theme-swatch*`, `.custom-editor-grid` |
| Perfil list | `.profile-list-item*`, `.mini-select`, `.modal-foot` |
| Scrollbar | `::-webkit-scrollbar*` |

> Los estilos **no** se duplican en las páginas. Cualquier override page-specific se escribe en el `<style>` inline de esa página.

---

## `static/shared.js` — Lógica compartida

Cargado con `<script src="/static/shared.js">` **antes** del `<script>` inline de cada página. Las funciones definidas en el script inline de la página **sobreescriben** la versión compartida donde el comportamiento difiere (e.g. `setHourFormat` en `index.html` también actualiza las gráficas).

> **Regla de redeclaración:** `let`/`const` no pueden declararse dos veces en el mismo scope. Las variables ya declaradas en shared.js **no** deben redeclararse en ninguna página.

### Variables globales compartidas
| Variable | Valor inicial | Descripción |
|---|---|---|
| `THEMES` | objeto | Definición de todos los temas visuales |
| `allProfiles` | `[]` | Perfiles cargados desde la API |
| `profileId` | `null` | ID del perfil activo |
| `hourFormat` | `'decimal'` | Formato de horas en gráficas |
| `showImages` | `true` | Si se muestran imágenes de apps |
| `_dismissedOpen` | `false` | Si el listado de dismissed games está expandido |

### Grupos de funciones
| Grupo | Funciones |
|---|---|
| Utilidades | `api()`, `esc()`, `hexToRgb()`, `fmtTime()`, `fmtDate()`, `resolveImg()` |
| Preferencias | `getPrefs()`, `savePrefs()` |
| Temas | `applyTheme()`, `selectTheme()`, `renderThemeSwatches()`, `onAccentChange()`, `resetAccent()` |
| Efectos accent | `applyAccentEffect()`, `_accentMouseMove()` |
| Custom theme editor | `buildCustomEditorGrid()`, `saveCustomTheme()`, `deleteCustomTheme()`, `resetCustomEditor()` |
| Settings modal | `openSettings()`, `closeSettings()`, `switchSettingsTab()`, `selectMode()`, `setHourFormat()` |
| Imágenes | `setShowImages()` |
| Game detection | `setGameDetect()`, `setNotifMode()`, `clearDismissed()`, `toggleDismissedList()`, `loadDismissedList()`, `undismiss()` |
| Métodos detección | `renderDetectMethods()`, `toggleDetectMethod()`, `DETECT_METHODS` |
| Rutas juegos | `loadGamePaths()`, `addGamePath()`, `addGamePathMain()`, `removeGamePath()` |
| Perfiles | `loadProfilesSettings()`, `newProfile()`, `activateProfile()`, `deleteProfile()`, `confirmMigrate()`, `doExportProfile()` |
| Sidebar | `pollResources()` |
| Init | `initShared()` |

### `initShared()`
Llamado al inicio de `init()` en cada página. Aplica el tema guardado, fija `hourFormat` y limpia estilos de efecto de acento de sesiones anteriores.
