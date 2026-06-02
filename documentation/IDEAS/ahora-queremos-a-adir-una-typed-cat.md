# Plan: Auto-fetch game artwork from multiple online sources

## Context
Apps tracked by TimeTrack (especially games) should be able to get artwork automatically — banners, posters, icons — without the user having to search manually. Games can come from Steam, GOG, Epic, itch.io, emulators or indie installers, so we need multiple sources in a priority waterfall. Non-game apps get their icon from the local exe.

---

## Image source UI (apps.html — Edit modal, image panel)

Current 3 modes become 4, reorganized into two groups:

```
ONLINE
  ○ URL              — user pastes any URL manually (existing)
  ○ Auto-detect      — queries all configured online sources by game name (NEW)

LOCAL
  ○ Upload           — file picker (existing)
  ○ From EXE         — extract icon from exe (existing)
```

**Auto-detect** calls `POST /api/apps/{id}/images/auto-fetch` and shows a spinner on the button while it runs. On completion, previews fill with whatever was found (icon/banner/poster each from their best source). If nothing found, shows "No results" message. Does NOT require user to re-save — images are written to DB immediately by the endpoint.

---

## Sources — priority waterfall

Each source is tried in order until a result is found **per image type** independently (icon may come from exe, banner from Steam CDN, poster from SteamGridDB).

| Priority | Source | Key needed | Covers | Image types |
|---|---|---|---|---|
| 1 | **Steam CDN** | None | Steam games (from ACF files or exe path) | banner (`header.jpg`), poster (`library_600x900.jpg`) |
| 2 | **SteamGridDB** | Free (user registers) | All games incl. non-Steam, indie, emulators | grids (banner), heroes (wide banner), icons, logos |
| 3 | **RAWG** | Free (user registers) | 500k+ games, all platforms | background image (banner), screenshot thumbnails |
| 4 | **Local exe** | None | All apps | icon (via PowerShell System.Drawing) |

**Icon**: always tried from local exe first (fastest, works for every app, no network).  
**Banner + Poster**: waterfall online sources for games; skip for non-game apps.

---

## Steam CDN — App ID detection (no key required)

1. Check if `exe_path` contains `\steamapps\common\` → extract game folder name
2. Scan `libraryfolders.vdf` in default Steam paths (`C:\Program Files (x86)\Steam\steamapps\`, etc.) to find all library locations
3. In each library, iterate `appmanifest_*.acf` files → parse with stdlib regex (no extra lib) → match `installdir` field against game folder
4. If App ID found → download from `https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/`:
   - `header.jpg` → `img_banner`
   - `library_600x900.jpg` → `img_poster`
5. Verify each URL with a HEAD request before downloading (not all games have all assets)

---

## SteamGridDB — search by name

- API key stored in `settings.sgdb_api_key` (empty = skip this source)
- Search: `GET https://www.steamgriddb.com/api/v2/search/autocomplete/{game_name}`
- Get grids: `GET https://www.steamgriddb.com/api/v2/grids/game/{id}?dimensions=460x215` → `img_banner`
- Get icons: `GET https://www.steamgriddb.com/api/v2/icons/game/{id}` → `img_icon`
- Get heroes: `GET https://www.steamgriddb.com/api/v2/heroes/game/{id}` → `img_banner` (if grid not found)
- Pick first result with `humor=false` and `nsfw=false`

---

## RAWG — search by name

- API key stored in `settings.rawg_api_key` (empty = skip)
- Search: `GET https://api.rawg.io/api/games?search={name}&key={key}&page_size=1`
- Uses `background_image` field → `img_banner`

---

## New backend file: `core/image_fetcher.py`

```python
def auto_fetch_images(app_id, display_name, exe_name, exe_path) -> dict:
    """
    Returns dict of what was written: {img_icon, img_banner, img_poster} or subset.
    Writes results directly to DB via update_tracked_app().
    Downloads files to IMAGES_DIR.
    """
```

Internal helpers:
- `_find_steam_app_id(exe_path)` → int | None
- `_download_steam(appid)` → dict
- `_search_steamgriddb(name)` → dict  
- `_search_rawg(name)` → dict
- `_extract_local_icon(exe_path, app_id)` → str | None (reuses existing PowerShell logic)
- `_download_image(url, dest_path)` → bool (urllib.request, no new deps)

---

## DB changes (`core/database.py`)

Add to settings seed:
```sql
INSERT OR IGNORE INTO settings (key, value) VALUES ('sgdb_api_key', '');
INSERT OR IGNORE INTO settings (key, value) VALUES ('rawg_api_key', '');
INSERT OR IGNORE INTO settings (key, value) VALUES ('auto_fetch_images', '0');
```

---

## API changes (`api/routes.py`)

### New endpoint
```
POST /api/apps/{app_id}/images/auto-fetch
```
Calls `image_fetcher.auto_fetch_images(...)` **synchronously** (returns when done).  
Returns `{"ok": true, "fetched": {"img_icon": "...", "img_banner": "...", "img_poster": "..."}}`.

### Modified `POST /api/apps`
After `add_tracked_app(...)`, if `get_setting("auto_fetch_images") == "1"`:
```python
threading.Thread(
    target=image_fetcher.auto_fetch_images,
    args=(app_id, display_name, exe_name, exe_path),
    daemon=True
).start()
```
The response to the client is immediate — fetch happens in background.

### Modified `GET /api/settings` + `POST /api/settings`
Add `sgdb_api_key`, `rawg_api_key`, `auto_fetch_images` to the model and response.

---

## Frontend changes

### `ui/apps.html` — image panel

Replace current `img-src-row` layout:
```
ONLINE
  [URL]  [Auto-detect]
LOCAL
  [Upload]  [From EXE]
```
`Auto-detect` button calls `POST /api/apps/{id}/images/auto-fetch`, shows loading spinner, then calls `renderImgTab()` + `renderApps()` on completion.

### `ui/static/shared.js` — openSettings

In `GET /api/settings` handler, populate new fields:
```javascript
document.getElementById('sgdbKeyInput').value  = s.sgdb_api_key  || '';
document.getElementById('rawgKeyInput').value   = s.rawg_api_key  || '';
document.getElementById('autoFetchToggle').checked = !!s.auto_fetch_images;
```

### Settings modal — Tracker tab (both pages share the same HTML)

Add a new section in the Tracker tab:
```
─── Image auto-fetch ────────────────────────────────
☑ Auto-fetch images when adding a new app

SteamGridDB API key   [__________________________]  Get free key ↗
RAWG API key          [__________________________]  Get free key ↗

Sources used (in order): Steam CDN → SteamGridDB → RAWG → Local EXE icon
─────────────────────────────────────────────────────
```

---

## Verification

1. **Steam game**: Add `dota2.exe` from a Steam install → banner and poster auto-fetched from Steam CDN, icon from exe.
2. **Non-Steam game** (with SGDB key): Add a GOG game → SteamGridDB grid appears as banner.
3. **General app** (no SGDB key, no RAWG key): Add `code.exe` → only icon extracted from exe.
4. **Auto-fetch on add**: Enable `auto_fetch_images`, add any app → images appear on the card within seconds without user touching the Edit modal.
5. **Manual Auto-detect button**: Open Edit on an existing app → click "🔍 Auto-detect" → spinner → images populate.
6. **No keys configured**: All online sources skipped gracefully, only exe icon attempted.

---

# Plan: Documentation in /documentation/

## Context
The user wants `/documentation/` to serve as the single source of truth for understanding the app — both what each feature does (product perspective) and how it's technically built (developer perspective). The existing `ui/info.md` and `backend/info.md` cover components but not features. A general overview file is also missing.

## Target structure

```
documentation/
├── app.md                    ← NEW: general overview, stack, how to run, key concepts
├── features/
│   ├── tracking.md           ← NEW: process tracking, sessions, pause/resume
│   ├── dashboard.md          ← NEW: charts, detail panel, day timeline
│   ├── manage-apps.md        ← NEW: filters, sort, view, images (banner/poster/icon)
│   ├── profiles.md           ← NEW: profiles, migration, export
│   ├── themes.md             ← NEW: theme system, custom editor, shared.js/css refactor
│   └── game-detection.md     ← NEW: auto-detection layers, notifications
├── ui/
│   └── info.md               ← EXISTS (technical component docs — keep, no change)
└── backend/
    └── info.md               ← EXISTS (technical component docs — keep, no change)
```

## Each file covers
- **app.md**: what TimeTrack is, tech stack, how to install/run, data directory, file layout
- **features/tracking.md**: how the 3s polling loop works, session lifecycle, pause/resume, auto-detect, exe_map
- **features/dashboard.md**: table, bar chart, line chart, detail panel modes (panel/modal/float), day timeline, session editing
- **features/manage-apps.md**: add form, collapsible sections, search+regex, sort/order/view, app images (upload/URL/EXE icon), game-detect config
- **features/profiles.md**: what a profile is, switching, migration, export, multi-profile use cases
- **features/themes.md**: THEMES object, CSS variables, shared.js/css architecture (why it was refactored, how overriding works), custom theme editor, accent effects
- **features/game-detection.md**: detection layers (launcher/GameMode/NVIDIA/heuristic/custom paths), SYSTEM_SKIP, dismissed list, notification modes

## Verification
Open each .md in the IDE — they should be self-contained: a new developer reading only that file should understand the feature without needing to read source code.

---

# Plan: App Image / Banner System

## Context
Apps in TimeTrack currently show only a color bar and text. This feature adds per-app artwork in three shapes (icon, banner, poster) that can be set via web URL or local file upload. Display is opt-in via a single global toggle in Settings → Visual. Images enhance the detail panel (banner), app cards (icon), and the edit modal (all three types as a management surface).

---

## Image Types

| Key | Shape | Primary surface |
|-----|-------|----------------|
| `img_icon` | Square ~1:1 | App cards (apps.html) + table rows (index.html) |
| `img_banner` | Wide landscape ~16:5 | Detail panel header (index.html) |
| `img_poster` | Portrait ~2:3 | Edit modal sidebar (apps.html) |

---

## 1 — Backend: `core/database.py`

### 1a. DB migration (follow existing `is_hidden` pattern)
Add three nullable TEXT columns to `tracked_apps` via `ALTER TABLE … ADD COLUMN IF NOT EXISTS`:
```sql
img_icon   TEXT DEFAULT NULL
img_banner TEXT DEFAULT NULL
img_poster TEXT DEFAULT NULL
```
Each value is either:
- A full URL (`https://…`) — browser fetches directly
- A relative path (`app-images/42_banner.webp`) — served from `/user-images/`

### 1b. DATA_DIR constant
Define next to `DB_PATH` using the same frozen-vs-dev logic:
```python
DATA_DIR = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent.parent
IMAGES_DIR = DATA_DIR / "app-images"
IMAGES_DIR.mkdir(exist_ok=True)
```

### 1c. Query updates
- `get_app(id)` and the list queries (`get_apps_for_profile`, `get_profile_summary`) must return the three new columns.
- Add `update_app_images(id, img_icon, img_banner, img_poster)` helper (or extend existing `update_app`).

---

## 2 — Backend: `api/routes.py`

### 2a. Extend existing `PATCH /api/apps/{id}`
Accept optional `img_icon`, `img_banner`, `img_poster` string fields (URL or null to clear).

### 2b. New `POST /api/apps/{id}/images/{img_type}`
```
img_type: "icon" | "banner" | "poster"
Body: multipart file upload (UploadFile)
```
- Validate `img_type`.
- Save file as `{id}_{img_type}{ext}` inside `IMAGES_DIR`.
- Delete any previous file for that slot.
- PATCH the corresponding column with the relative path `app-images/{filename}`.
- Return `{ path: "app-images/{filename}" }`.

### 2c. New `DELETE /api/apps/{id}/images/{img_type}`
- Delete the file from `IMAGES_DIR` (if local).
- NULL out the column.

### 2d. Settings
Add key `show_app_images` (default `"1"`) to the `settings` table seed. Expose it in `GET /api/settings` and `POST /api/settings`.

---

## 3 — `main.py`

Mount user-images directory (always, creating it if needed):
```python
app.mount("/user-images", StaticFiles(directory=str(IMAGES_DIR)), name="user-images")
```
This must be done unconditionally (not behind an `if _static.exists()` guard) since `IMAGES_DIR.mkdir()` already ensures it exists.

Import `IMAGES_DIR` from `core.database`.

---

## 4 — `ui/apps.html` — Edit Modal

### 4a. Image management section
Add below the existing fields in `.edit-fields`, before the action buttons:

```
┌─ Images ──────────────────────────────────────────┐
│  [Icon 1:1]  [Banner 16:5]  [Poster 2:3]  ← tabs │
│                                                    │
│  ○ URL  ○ Upload                                   │
│  [___________________________] [Choose…]           │
│  [preview thumbnail]   [✕ Clear]                  │
└───────────────────────────────────────────────────┘
```

JS: `openEdit` loads all three image values; `saveEdit` sends them via PATCH. File upload uses a separate fetch to `POST /api/apps/{id}/images/{type}` with FormData, then updates the stored value before saving.

### 4b. Card square icon (when `show_app_images = true`)
In `renderCard(a)`, if `a.img_icon` is set, render a small `<img>` (40×40px, `object-fit:cover`, rounded) in the card header left of `.card-name`. If not set, fall back to the existing colored accent bar only.

---

## 5 — `ui/index.html` — Detail Panel + Table

### 5a. Detail panel banner
Immediately after `.detail-head`, inject (only when `img_banner` is set and images are enabled):
```html
<div class="detail-banner">
  <img src="{resolveImg(img_banner)}" />
</div>
```
CSS: `width:100%; max-height:180px; object-fit:cover; border-bottom: 1px solid var(--border)`

`resolveImg(val)`: if val starts with `http`, return as-is; else prepend `/user-images/`.

### 5b. Table row icon
In the table render loop, left of the `.app-dot` span, add a 24×24 `<img>` when `img_icon` is set.

### 5c. Settings toggle
In Settings → Visual tab, add:
```
App Images
☑ Show images on cards and panels
(Fetches from web for URL images; local images served by the app)
```
Reads/writes `show_app_images` via `GET/POST /api/settings`. On change, call `renderApps()` / update detail panel if open.

---

## 6 — Migration Safety

- All three new columns have `DEFAULT NULL` — existing data is unaffected.
- The `IMAGES_DIR.mkdir(exist_ok=True)` in database.py runs at import time, so no restart risk.
- The `/user-images` mount is independent of the existing `/images` and `/static` mounts.

---

## Verification

1. **No images set**: App renders exactly as before (no layout shift, no broken img tags).
2. **URL image**: Paste `https://…/banner.jpg` in the banner field → save → open detail panel → banner renders.
3. **Local upload**: Click "Upload" in icon tab → pick file → preview appears → save → card shows icon.
4. **Clear**: Click ✕ → image nulled in DB → card/panel reverts to text-only.
5. **Toggle off**: Settings → uncheck "Show app images" → cards and panel hide all images instantly.
6. **Frozen mode**: Verify `IMAGES_DIR` resolves to the .exe directory (not _MEIPASS).
