# Feature: Temas visuales y arquitectura de estilos compartidos

Sistema de temas de color para la UI, con soporte para temas personalizados, efectos de acento y una arquitectura de CSS/JS compartido entre las dos páginas.

---

## Temas incluidos

9 temas predefinidos: Synthwave (por defecto), Nord, Gruvbox, Catppuccin, Midnight, Tokyo Night, Dracula, Monokai, Solarized Dark.

Cada tema define 9 variables CSS:

| Variable | Descripción |
|---|---|
| `--bg` | Fondo base |
| `--surface` | Superficies (cards, sidebar, modales) |
| `--border` | Bordes y separadores |
| `--accent` | Color primario de acento (botones, links activos) |
| `--accent2` | Acento secundario (badges auto-detected) |
| `--green` | Indicadores "en ejecución" |
| `--text` | Texto principal |
| `--muted` | Texto secundario / labels |
| `--danger` | Acciones destructivas |

---

## Cambiar de tema

Settings → Visual → Color theme. Al seleccionar un tema, `applyTheme(themeId)` llama a `document.documentElement.style.setProperty` para cada variable. El cambio es inmediato y persiste en `localStorage` (`tt_prefs.theme`).

---

## Color de acento personalizado

Dentro del tema seleccionado, se puede sobreescribir solo `--accent` con cualquier color. Se guarda en `tt_prefs.accent_override`. El botón Reset vuelve al acento del tema base.

---

## Editor de temas personalizados

Settings → Visual → Color theme → Custom theme editor (sub-panel colapsable).

Muestra un picker de color por cada una de las 9 variables. Al guardar, el tema se almacena en `tt_prefs.custom_themes` (array en localStorage) con un ID único tipo `ct_<timestamp>`. Los temas personalizados aparecen bajo los predefinidos en el selector de swatches.

---

## Efectos de acento

*(Feature visual opcional, actualmente desactivado en la UI pero el código existe en `shared.js`/`index.html`)*

Tipos de efecto: `solid` (ninguno), `glow`, `pulse`, `breathe`, `wave`, `gradient`. Se aplican inyectando un `<style id="accent-fx">` en el `<head>` con `@keyframes` y propiedades CSS. Se activan por `applyAccentEffect(effect, accentColor)`.

---

## Formato de horas en gráficas

Settings → Visual → Hour format:
- **Decimal** (`1.5h`) — número con decimales, útil para exportar
- **Humano** (`1h 30m`) — más legible en el panel

Se guarda en `tt_prefs.hourFormat`. La función `fmtHours(h)` en `index.html` usa este valor.

---

## Arquitectura shared.js / shared.css

### Por qué existen

Antes del refactor, `index.html` y `apps.html` contenían cada uno su propia copia de todo el código de temas, settings, perfiles, etc. Esto causaba que un cambio en un fichero no se reflejase en el otro, y el panel de Settings funcionaba diferente en cada página.

### Cómo funciona ahora

Ambas páginas cargan **primero** los ficheros compartidos:
```html
<head>
  <link rel="stylesheet" href="/static/shared.css">
  ...
</head>
<body>
  ...
  <script src="/static/shared.js"></script>
  <script>
    // código page-specific aquí
  </script>
</body>
```

**`shared.css`** — todos los estilos que aparecen igual en las dos páginas: sidebar, botones, modales, Settings modal, swatches, perfiles. Los estilos page-specific van en el `<style>` inline de cada página.

**`shared.js`** — todas las funciones compartidas: THEMES, api(), getPrefs/savePrefs, applyTheme, renderThemeSwatches, openSettings, setGameDetect, loadGamePaths, loadProfilesSettings, pollResources, etc.

### Regla de sobreescritura

Como JavaScript carga en orden, si una función está en `shared.js` Y también se define en el `<script>` inline de la página, **la definición de la página gana** (la última definición prevalece). Esto permite que `index.html` tenga su propia versión de `setHourFormat` que también actualiza las gráficas Chart.js, sin modificar la versión base de `shared.js`.

### Regla crítica: no redeclarar

`let` y `const` en el scope global NO se pueden declarar dos veces en el mismo contexto de página — causaría un `SyntaxError` que mataría todo el JS. Las variables ya declaradas en `shared.js` (`THEMES`, `allProfiles`, `profileId`, `showImages`, `hourFormat`, `_dismissedOpen`, `DETECT_METHODS`, `_CE_VARS`) **no deben redeclararse** en ninguna página.

### initShared()

Función de arranque compartida que aplica el tema guardado, fija `hourFormat` y limpia estilos de efectos de acento residuales. Cada página la llama al inicio de su propio `init()`.

---

## Persistencia

Toda la preferencia visual se guarda en `localStorage` bajo la clave `tt_prefs` (objeto JSON):

| Clave | Tipo | Descripción |
|---|---|---|
| `theme` | string | ID del tema activo |
| `accent_override` | string\|null | Color hex de acento manual |
| `custom_themes` | array | Temas personalizados creados |
| `hourFormat` | `'decimal'\|'human'` | Formato de horas en gráficas |
| `detail_mode` | `'panel'\|'modal'\|'float'` | Modo del panel de detalle |
| `apps_sort` | `'default'\|'alpha'` | Ordenación en Manage Apps |
| `apps_dir` | `'asc'\|'desc'` | Dirección de ordenación |
| `apps_view` | `'grid'\|'list'` | Vista en Manage Apps |
| `apps_regex` | bool | Modo regex en búsqueda |
| `section_add_open` | bool | Estado del acordeón Add application |
| `section_apps_open` | bool | Estado del acordeón Tracked applications |
| `game_detect_open` | bool | Estado del acordeón de detección de juegos |

---

## Archivos relevantes

| Fichero | Rol |
|---|---|
| `ui/static/shared.css` | CSS base compartido |
| `ui/static/shared.js` | THEMES, applyTheme, renderThemeSwatches, openSettings, initShared... |
| `ui/index.html` | Overrides page-specific (setHourFormat con chart update) |
| `ui/apps.html` | Overrides page-specific (confirmAutoDetect) |
