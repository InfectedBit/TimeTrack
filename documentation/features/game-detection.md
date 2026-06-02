# Feature: Detección automática de juegos

Cuando `game_detect=1`, el tracker identifica ejecutables que probablemente son juegos y pide confirmación antes de añadirlos al perfil activo. Así no se rastrea nada sin permiso explícito.

---

## Flujo completo

```
proceso nuevo detectado (no en _exe_map)
  │
  ├── game_detector.is_game(exe_name, exe_path)?
  │       NO → ignorar (o añadir si auto_detect=True)
  │       SÍ →
  │           is_dismissed(exe_name)? SÍ → ignorar silenciosamente
  │                                   NO →
  │                                       añadir a _pending_games
  │                                       enviar notificación al usuario
  │
usuario responde:
  "yes"   → add_tracked_app()  → tracker empieza a registrar sesiones
  "no"    → ignorar esta vez
  "never" → add_dismissed(exe_name) → nunca más se preguntará
```

---

## Capas de detección (en orden, primera coincidencia gana)

### 1. Launcher paths
Comprueba si la ruta del ejecutable contiene fragmentos de instaladores conocidos:

| Plataforma | Fragmentos buscados |
|---|---|
| Steam | `\steam\`, `\steamapps\`, `steam_api` |
| Epic Games | `\epic games\`, `\epicgames\` |
| GOG | `\gog galaxy\`, `\gogcom\`, `\gog games\` |
| Ubisoft | `\ubisoft\`, `\uplay\`, `\ubisoft connect\` |
| Xbox / Game Pass | `\xboxgames\`, `\modifiablewindowsapps\` |
| EA / Origin | `\origin games\`, `\ea games\`, `\electronic arts\` |
| Rockstar | `\rockstar games\` |
| Bethesda | `\bethesda.net\` |
| Battle.net | `\battle.net\`, `\blizzard entertainment\` |

### 2. Windows Game Mode (registro)
Lee `HKCU\System\GameConfigStore\Children\*\MatchedExeFullPath`. Si el exe aparece aquí, Windows ya lo tiene registrado como juego.

### 3. Perfiles NVIDIA DRS
Escanea ficheros `.nip` en `C:\ProgramData\NVIDIA Corporation\Drs\`. Si el exe está en algún perfil de NVIDIA, casi seguro es un juego.

### 4. Heurística
Condiciones:
- La ruta NO está bajo `C:\Windows\` ni `C:\Windows\System32`
- La ruta del exe o su directorio contiene palabras clave: `game`, `games`, `gaming`, `steam`, `epic`, `gog`, `play`, `launcher`

### 5. Rutas personalizadas
El usuario puede definir carpetas propias (p.ej. `M:\MRGames`). Cualquier exe dentro de esas carpetas se considera juego.

---

## Lista de exclusión (SYSTEM_SKIP)

Conjunto exhaustivo de exes que **nunca** se consideran juegos, aunque cumplan algún criterio:

- Procesos del sistema Windows (`svchost.exe`, `explorer.exe`, `dwm.exe`…)
- Navegadores (`chrome.exe`, `msedge.exe`, `firefox.exe`…)
- Herramientas de desarrollo (`code.exe`, `pycharm64.exe`, `node.exe`…)
- Apps comunes (`discord.exe`, `spotify.exe`, `vlc.exe`…)
- Procesos NVIDIA/AMD propios (`nvcontainer.exe`, `radeonsoftware.exe`…)
- Los propios ejecutables de los launchers (`steam.exe`, `epicgameslauncher.exe`…)

---

## Métodos de detección activos

El usuario puede activar/desactivar cada capa individualmente en Settings → Tracker → Métodos de detección (o en la sección "Detect games" de Manage Apps). Se persiste en la BD como JSON en `settings.detect_methods`.

---

## Lista "No preguntar más"

`dismissed_games(exe_name TEXT PK, dismissed_at)` — exes que el usuario respondió "Nunca".

Acciones:
- **Ver lista**: Settings → Tracker → Lista "No preguntar más" → 👁 Ver lista
- **Eliminar entrada**: botón `✕` junto al exe (vuelve a preguntar la próxima vez que aparezca)
- **Limpiar todo**: botón "✕ Limpiar lista"

---

## Notificaciones

Cuando se detecta un juego nuevo, se envía una notificación al usuario. Dos modos configurables en Settings → Tracker → Tipo de notificación:

| Modo | Descripción |
|---|---|
| **Tray menu** | El menú contextual de la bandeja muestra el juego detectado con opciones Añadir/Ignorar/Nunca. No requiere dependencias extra. |
| **Windows Toast** | Notificación nativa de Windows 11 con botones de acción. Requiere `pip install win11toast`. Si no está instalado, cae automáticamente al modo Tray. |

---

## Rutas personalizadas

Settings → Tracker → Rutas personalizadas (o Manage Apps → sección Add application → Detectar juegos).

Añadir una carpeta hace que cualquier exe dentro (en cualquier nivel de subdirectorio) se considere juego. Se persiste en la tabla `game_paths` y se recarga en `game_detector` inmediatamente al añadir/eliminar.

---

## Archivos relevantes

| Fichero | Rol |
|---|---|
| `core/game_detection.py` | Lógica de detección multicapa, `GameDetector.is_game()` |
| `core/tracker.py` | Llama a `game_detector.is_game()` y gestiona `_pending_games` |
| `core/notifications.py` | Envía la notificación al usuario |
| `api/routes.py` | `/tracker/pending-games/{exe}`, `/dismissed-games`, `/game-paths` |
| `ui/static/shared.js` | `setGameDetect`, `renderDetectMethods`, `loadGamePaths`, `clearDismissed` |
