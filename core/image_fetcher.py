"""
TimeTrack — Image Fetcher
Auto-fetches artwork (icon / banner / poster) for tracked apps.

Sources (priority waterfall):
  1. Local exe icon    — no key, all apps (PowerShell System.Drawing)
  2. Steam CDN         — no key, Steam games (local ACF detection)
  3. Steam Store API   — no key, any Steam game found by name search
  4. SteamGridDB       — free API key, all PC games incl. non-Steam, emulators
  5. GOG API           — no key, GOG catalogue
  6. RAWG              — free API key, 500k+ games

Search uses display_name (user's custom name) and cleaned exe_name as fallback.
Call `auto_fetch_images(app_id, display_name, exe_name)` — it resolves exe_path
internally via `find_exe_on_system` and writes results directly to DB.
"""

import re
import subprocess
import logging
import threading
from pathlib import Path
from urllib import request as urllib_request, error as urllib_error
from urllib.parse import quote

import psutil

from core.database import IMAGES_DIR, get_setting, update_tracked_app, get_app_by_id, get_game_paths

logger = logging.getLogger("image_fetcher")

# Suppress PowerShell/cmd console windows on Windows
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# ── Fetch status & cancellation ───────────────────────────────────────────────
_fetch_status: dict = {}          # app_id → {running, fetched, cancelled}
_cancel_event = threading.Event()

def cancel_fetch() -> None:
    """Signal any running fetch/search to stop at the next checkpoint."""
    _cancel_event.set()

def reset_cancel() -> None:
    _cancel_event.clear()

def get_fetch_status(app_id: int) -> dict:
    return dict(_fetch_status.get(app_id, {"running": False, "fetched": {}, "cancelled": False}))

def _is_cancelled() -> bool:
    return _cancel_event.is_set()

_STEAM_DEFAULT_PATHS = [
    Path("C:/Program Files (x86)/Steam/steamapps"),
    Path("C:/Program Files/Steam/steamapps"),
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def _download_image(url: str, dest: Path) -> bool:
    """Download url to dest. Returns True on success."""
    try:
        req = urllib_request.Request(url, headers={"User-Agent": "TimeTrack/1.0"})
        with urllib_request.urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                return False
            dest.write_bytes(resp.read())
        return dest.exists() and dest.stat().st_size > 0
    except Exception as exc:
        logger.debug("Download failed %s: %s", url, exc)
        return False


def _head_ok(url: str) -> bool:
    """Quick HEAD check — returns True if URL returns 200."""
    try:
        req = urllib_request.Request(url, method="HEAD", headers={"User-Agent": "TimeTrack/1.0"})
        with urllib_request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


def _clean_name(name: str) -> str:
    """Normalize a game name for fuzzy matching."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _run_ps(script: str, timeout: int = 15) -> str | None:
    """Run a PowerShell script invisibly; return first valid file path in stdout or None."""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=timeout,
            creationflags=_NO_WINDOW,
        )
        for line in r.stdout.strip().splitlines():
            p = line.strip()
            if p and Path(p).exists():
                return p
    except Exception as exc:
        logger.debug("PS search failed/timed out: %s", exc)
    return None


def _delete_slot(app_id: int, img_type: str):
    """Delete any existing local file for this image slot."""
    for old in IMAGES_DIR.glob(f"{app_id}_{img_type}.*"):
        try:
            old.unlink()
        except Exception:
            pass


def _save_slot(url: str, app_id: int, img_type: str, ext: str) -> str | None:
    """Download image to the slot file. Returns relative path or None.
    Does NOT clean up other extensions — auto_fetch_images does that once
    the final winner for each slot is known, avoiding deletion of files
    that are still referenced in the DB while a replacement is being tried."""
    dest = IMAGES_DIR / f"{app_id}_{img_type}{ext}"
    if not _download_image(url, dest):
        return None
    return f"images/app-images/{dest.name}"


# ── Source 1: Steam CDN ───────────────────────────────────────────────────────

def _parse_acf_field(content: str, field: str) -> str | None:
    m = re.search(rf'"{field}"\s+"([^"]+)"', content, re.IGNORECASE)
    return m.group(1) if m else None


def _find_steam_library_paths() -> list[Path]:
    """Return all Steam library steamapps directories from libraryfolders.vdf."""
    paths: list[Path] = []
    for base in _STEAM_DEFAULT_PATHS:
        vdf = base / "libraryfolders.vdf"
        if not vdf.exists():
            continue
        paths.append(base)
        try:
            content = vdf.read_text(encoding="utf-8", errors="ignore")
            for p in re.findall(r'"path"\s+"([^"]+)"', content):
                lib = Path(p) / "steamapps"
                if lib.exists():
                    paths.append(lib)
        except Exception:
            pass
    return paths


def _find_steam_app_id(exe_path: str) -> int | None:
    """Try to find the Steam App ID from the exe path via .acf manifest files."""
    if not exe_path or "steamapps" not in exe_path.lower():
        return None

    exe = Path(exe_path)
    # Extract game folder from path: …\steamapps\common\<GameFolder>\…
    parts = [p.lower() for p in exe.parts]
    try:
        ci = parts.index("common")
        game_folder = exe.parts[ci + 1].lower()
    except (ValueError, IndexError):
        return None

    for lib in _find_steam_library_paths():
        for acf in lib.glob("appmanifest_*.acf"):
            try:
                content = acf.read_text(encoding="utf-8", errors="ignore")
                install_dir = _parse_acf_field(content, "installdir")
                if install_dir and install_dir.lower() == game_folder:
                    app_id_str = _parse_acf_field(content, "appid")
                    if app_id_str and app_id_str.isdigit():
                        return int(app_id_str)
            except Exception:
                continue
    return None


def _download_steam(app_id: int, db_app_id: int) -> dict:
    """Download banner + poster from Steam CDN. Returns {img_banner, img_poster}."""
    base = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}"
    result = {}

    if _head_ok(f"{base}/header.jpg"):
        r = _save_slot(f"{base}/header.jpg", db_app_id, "banner", ".jpg")
        if r:
            result["img_banner"] = r
            logger.info("Steam banner fetched for app %d (steam %d)", db_app_id, app_id)

    for poster_url in [f"{base}/library_600x900.jpg", f"{base}/library_600x900_2x.jpg"]:
        if _head_ok(poster_url):
            r = _save_slot(poster_url, db_app_id, "poster", ".jpg")
            if r:
                result["img_poster"] = r
                logger.info("Steam poster fetched for app %d (steam %d)", db_app_id, app_id)
            break

    return result


# ── Source 2: SteamGridDB ─────────────────────────────────────────────────────

def _sgdb_get(path: str, api_key: str) -> dict | None:
    url = f"https://www.steamgriddb.com/api/v2{path}"
    try:
        req = urllib_request.Request(url, headers={
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "TimeTrack/1.0",
        })
        with urllib_request.urlopen(req, timeout=10) as resp:
            import json
            data = json.loads(resp.read())
            return data if data.get("success") else None
    except Exception as exc:
        logger.debug("SGDB request failed %s: %s", path, exc)
        return None


def _search_steamgriddb(name: str, app_id: int, api_key: str) -> dict:
    """Search SteamGridDB by name. Returns {img_banner, img_icon}."""
    result = {}
    if not api_key:
        return result

    search = _sgdb_get(f"/search/autocomplete/{quote(name)}", api_key)
    if not search or not search.get("data"):
        return result
    game_id = search["data"][0]["id"]

    # Banner: grids first, then heroes
    grids = _sgdb_get(f"/grids/game/{game_id}?humor=false&nsfw=false&dimensions=460x215", api_key)
    if not grids or not grids.get("data"):
        grids = _sgdb_get(f"/heroes/game/{game_id}?humor=false&nsfw=false", api_key)

    if grids and grids.get("data"):
        url = grids["data"][0].get("url", "")
        if url:
            ext = Path(url.split("?")[0]).suffix or ".jpg"
            r = _save_slot(url, app_id, "banner", ext)
            if r:
                result["img_banner"] = r
                logger.info("SGDB banner fetched for app %d", app_id)

    # Icon
    icons = _sgdb_get(f"/icons/game/{game_id}?humor=false&nsfw=false", api_key)
    if icons and icons.get("data"):
        url = icons["data"][0].get("url", "")
        if url:
            ext = Path(url.split("?")[0]).suffix or ".png"
            r = _save_slot(url, app_id, "icon", ext)
            if r:
                result["img_icon"] = r
                logger.info("SGDB icon fetched for app %d", app_id)

    return result


# ── Source 3: RAWG ────────────────────────────────────────────────────────────

def _search_rawg(name: str, app_id: int, api_key: str) -> dict:
    """Search RAWG by name. Returns {img_banner}."""
    result = {}
    if not api_key:
        return result

    url = f"https://api.rawg.io/api/games?search={quote(name)}&key={api_key}&page_size=1"
    try:
        req = urllib_request.Request(url, headers={"User-Agent": "TimeTrack/1.0"})
        with urllib_request.urlopen(req, timeout=10) as resp:
            import json
            data = json.loads(resp.read())
            results = data.get("results", [])
            if not results:
                return result
            bg = results[0].get("background_image", "")
            if not bg:
                return result
            ext = Path(bg.split("?")[0]).suffix or ".jpg"
            r = _save_slot(bg, app_id, "banner", ext)
            if r:
                result["img_banner"] = r
                logger.info("RAWG banner fetched for app %d", app_id)
    except Exception as exc:
        logger.debug("RAWG failed for '%s': %s", name, exc)

    return result


# ── Exe locator ───────────────────────────────────────────────────────────────

def find_exe_on_system(exe_name: str) -> str | None:
    """
    Locate an exe on Windows. Six interruptible stages (checks _cancel_event between each).
      1. Running processes  (psutil, instant)
      2. Windows PATH       (where, ~1s, no window)
      3. Registry Uninstall (~2s, timeout 10s)
      4. User game paths    (depth 5, timeout 15s)
      5. Standard dirs      (depth 2, timeout 8s)
      6. Non-C: drives      (depth 3, timeout 20s)
    """
    exe_lower = exe_name.lower()
    name_safe = exe_name.replace("'", "''")

    # 1. Running processes
    try:
        for proc in psutil.process_iter(["name", "exe"]):
            try:
                if proc.info["name"] and proc.info["name"].lower() == exe_lower:
                    p = proc.info.get("exe") or ""
                    if p and Path(p).exists():
                        return p
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception:
        pass
    if _is_cancelled(): return None

    # 2. Windows PATH
    try:
        r = subprocess.run(
            ["where", exe_name], capture_output=True, text=True,
            timeout=5, creationflags=_NO_WINDOW,
        )
        if r.returncode == 0:
            for line in r.stdout.strip().splitlines():
                p = line.strip()
                if p and Path(p).exists():
                    return p
    except Exception:
        pass
    if _is_cancelled(): return None

    # 3. Registry Uninstall keys
    result = _run_ps(r"""
$n = 'EXE'
$keys = @(
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
    'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
    'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*'
)
foreach ($k in $keys) {
    Get-ItemProperty $k -ErrorAction SilentlyContinue | ForEach-Object {
        $ic = $_.DisplayIcon; $lo = $_.InstallLocation
        if ($ic -and $ic -like "*$n*") {
            $p = ($ic -split ',')[0].Trim('"').Trim()
            if (Test-Path $p) { Write-Output $p; exit }
        }
        if ($lo -and $lo.Trim() -ne '' -and (Test-Path (Join-Path $lo $n))) {
            Write-Output (Join-Path $lo $n); exit
        }
    }
}
""".replace('EXE', name_safe), timeout=10)
    if result: return result
    if _is_cancelled(): return None

    # 4. User-configured game library paths (depth 5)
    user_game_paths = [row["path"] for row in get_game_paths()]
    if user_game_paths:
        dirs_ps = "@(" + ", ".join(f"'{p.replace(chr(39), chr(39)*2)}'" for p in user_game_paths) + ")"
        result = _run_ps(r"""
$n = 'EXE'
foreach ($d in DIRS) {
    if (-not (Test-Path $d)) { continue }
    $f = Get-ChildItem -Path $d -Filter $n -Recurse -EA SilentlyContinue -Depth 5 | Select-Object -First 1
    if ($f) { Write-Output $f.FullName; exit }
}
""".replace('EXE', name_safe).replace('DIRS', dirs_ps), timeout=15)
        if result: return result
    if _is_cancelled(): return None

    # 5. Standard install dirs (depth 2)
    result = _run_ps(r"""
$n = 'EXE'
foreach ($d in @('C:\Program Files', 'C:\Program Files (x86)', "$env:LOCALAPPDATA\Programs", "$env:LOCALAPPDATA", "$env:APPDATA")) {
    if (-not (Test-Path $d)) { continue }
    $f = Get-ChildItem -Path $d -Filter $n -Recurse -EA SilentlyContinue -Depth 2 | Select-Object -First 1
    if ($f) { Write-Output $f.FullName; exit }
}
""".replace('EXE', name_safe), timeout=8)
    if result: return result
    if _is_cancelled(): return None

    # 6. Non-C: drives — depth 3 (shallower = faster; covers most game installs)
    result = _run_ps(r"""
$n = 'EXE'
$drives = Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Root -ne 'C:\' } | ForEach-Object { $_.Root }
foreach ($d in $drives) {
    if (-not (Test-Path $d)) { continue }
    $f = Get-ChildItem -Path $d -Filter $n -Recurse -EA SilentlyContinue -Depth 3 | Select-Object -First 1
    if ($f) { Write-Output $f.FullName; exit }
}
""".replace('EXE', name_safe), timeout=20)
    return result


# ── Source 4: Local exe icon ──────────────────────────────────────────────────

def _extract_local_icon(exe_path: str, app_id: int) -> str | None:
    """Extract icon from exe using PowerShell System.Drawing. Returns relative path or None."""
    if not exe_path or not Path(exe_path).exists():
        return None

    out = IMAGES_DIR / f"{app_id}_icon.png"
    exe_safe = exe_path.replace("'", "''")
    out_safe  = str(out).replace("'", "''")

    ps = (
        "Add-Type -AssemblyName System.Drawing; "
        f"$i=[System.Drawing.Icon]::ExtractAssociatedIcon('{exe_safe}'); "
        f"$b=$i.ToBitmap(); $b.Save('{out_safe}'); "
        "$i.Dispose(); $b.Dispose()"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, timeout=15, creationflags=_NO_WINDOW,
        )
    except Exception as exc:
        logger.debug("PowerShell icon extraction failed: %s", exc)
        return None

    if out.exists() and out.stat().st_size > 0:
        # Remove old files of different extension (e.g. old .jpg from a previous auto-fetch)
        for old in IMAGES_DIR.glob(f"{app_id}_icon.*"):
            if old != out:
                try: old.unlink()
                except Exception: pass
        logger.info("Local icon extracted for app %d", app_id)
        return f"images/app-images/{out.name}"
    return None


# ── Source 5: Steam Store search (no key) ────────────────────────────────────

def _search_steam_store(name: str, app_id: int) -> dict:
    """Search Steam Store by game name (no API key). Returns {img_banner, img_poster}."""
    import json
    result = {}
    url = f"https://store.steampowered.com/api/storesearch/?term={quote(name)}&l=english&cc=US"
    try:
        req = urllib_request.Request(url, headers={"User-Agent": "TimeTrack/1.0"})
        with urllib_request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        items = data.get("items", [])
        if not items:
            return result
        steam_appid = items[0]["id"]
        logger.debug("Steam Store search '%s' → appid %d", name, steam_appid)
        result = _download_steam(steam_appid, app_id)
    except Exception as exc:
        logger.debug("Steam Store search failed for '%s': %s", name, exc)
    return result


# ── Source 6: GOG (no key) ────────────────────────────────────────────────────

def _search_gog(name: str, app_id: int) -> dict:
    """Search GOG by game name (no API key). Returns {img_banner}."""
    import json
    result = {}
    url = f"https://api.gog.com/products?search={quote(name)}&mediaType=game"
    try:
        req = urllib_request.Request(url, headers={"User-Agent": "TimeTrack/1.0"})
        with urllib_request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        products = data.get("products", [])
        if not products:
            return result
        # GOG image field is protocol-relative: "//images-1.gog.com/..."
        img = products[0].get("image", "")
        if not img:
            return result
        if img.startswith("//"):
            img = "https:" + img
        ext = Path(img.split("?")[0]).suffix or ".jpg"
        r = _save_slot(img, app_id, "banner", ext)
        if r:
            result["img_banner"] = r
            logger.info("GOG banner fetched for app %d", app_id)
    except Exception as exc:
        logger.debug("GOG search failed for '%s': %s", name, exc)
    return result


# ── Search term helpers ───────────────────────────────────────────────────────

def _clean_exe_for_search(exe_name: str) -> str:
    """
    Derive a human-readable search term from an exe filename.
    e.g. 'PathOfTitans-Win64-Shipping.exe' → 'Path Of Titans'
         'ForzaHorizon6.exe'               → 'Forza Horizon 6'
         'dyinglightgame_thebeast_x64_rwdi.exe' → 'Dyinglight Game Thebeast'
    """
    name = re.sub(r'\.(exe|dll)$', '', exe_name, flags=re.IGNORECASE)
    # Strip common technical suffixes (Unreal, Unity, etc.)
    name = re.sub(
        r'[-_](win64|win32|x64|x86|shipping|rwdi|final|release|retail|'
        r'launcher|game|client|app|dx11|dx12|vulkan|epic|steam)$',
        '', name, flags=re.IGNORECASE
    )
    # Remove trailing version numbers
    name = re.sub(r'[-_]v?\d+[\d.]*$', '', name, flags=re.IGNORECASE)
    # Split CamelCase
    name = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
    # Replace separators with spaces
    name = name.replace('_', ' ').replace('-', ' ')
    return ' '.join(name.split()).strip()


def _search_terms(display_name: str, exe_name: str) -> list[str]:
    """Return ordered list of search terms to try: display_name first, then cleaned exe."""
    terms = [display_name]
    clean = _clean_exe_for_search(exe_name)
    if clean and clean.lower() != display_name.lower():
        terms.append(clean)
    return terms


def _merge(fetched: dict, new: dict):
    """Add keys from new into fetched only if not already present."""
    for k, v in new.items():
        if k not in fetched:
            fetched[k] = v


# ── Orchestrator ──────────────────────────────────────────────────────────────

def auto_fetch_images(app_id: int, display_name: str, exe_name: str, exe_path: str = "") -> dict:
    """
    Fetch artwork for an app. Priority waterfall per image type:
      icon   → local exe → SGDB (key) → Steam Store search icon
      banner → Steam CDN (local) → Steam Store search → SGDB (key) → GOG → RAWG (key)
      poster → Steam CDN (local) → SGDB (key) → Steam Store search

    Uses display_name and cleaned exe_name as search terms.
    Writes results directly to DB. Returns dict of what was written.
    """
    sgdb_key = get_setting("sgdb_api_key", "")
    rawg_key = get_setting("rawg_api_key", "")
    fetched: dict[str, str] = {}

    # Resolve exe path if not provided or stale
    if not exe_path or not Path(exe_path).exists():
        exe_path = find_exe_on_system(exe_name) or ""

    terms = _search_terms(display_name, exe_name)

    # --- Icon: local exe first (fast, no network) ---
    icon_path = _extract_local_icon(exe_path, app_id)
    if icon_path:
        fetched["img_icon"] = icon_path

    # --- Steam CDN (local install detection) ---
    if not _is_cancelled():
        steam_id = _find_steam_app_id(exe_path)
        if steam_id:
            _merge(fetched, _download_steam(steam_id, app_id))

    # --- Steam Store search by name (free, no key) ---
    if not _is_cancelled() and ("img_banner" not in fetched or "img_poster" not in fetched):
        for term in terms:
            if _is_cancelled(): break
            r = _search_steam_store(term, app_id)
            _merge(fetched, r)
            if "img_banner" in fetched and "img_poster" in fetched:
                break

    # --- SteamGridDB (key required) ---
    if not _is_cancelled() and sgdb_key and ("img_banner" not in fetched or "img_icon" not in fetched):
        for term in terms:
            if _is_cancelled(): break
            r = _search_steamgriddb(term, app_id, sgdb_key)
            _merge(fetched, r)
            if "img_banner" in fetched and "img_icon" in fetched:
                break

    # --- GOG (free, no key) ---
    if not _is_cancelled() and "img_banner" not in fetched:
        for term in terms:
            if _is_cancelled(): break
            r = _search_gog(term, app_id)
            _merge(fetched, r)
            if "img_banner" in fetched:
                break

    # --- RAWG (key required) ---
    if not _is_cancelled() and rawg_key and "img_banner" not in fetched:
        for term in terms:
            if _is_cancelled(): break
            r = _search_rawg(term, app_id, rawg_key)
            _merge(fetched, r)
            if "img_banner" in fetched:
                break

    # --- Final cleanup: for each resolved slot, delete files with other extensions ---
    # This runs once, after all sources are tried, so we only delete what we won't use.
    for db_key, rel_path in fetched.items():
        img_type = db_key[4:]  # "img_icon" → "icon"
        winner = IMAGES_DIR / Path(rel_path).name
        for old in IMAGES_DIR.glob(f"{app_id}_{img_type}.*"):
            if old != winner:
                try:
                    old.unlink()
                except Exception:
                    pass

    # --- Persist to DB ---
    if fetched:
        update_tracked_app(app_id, **fetched)
        logger.info("Auto-fetch complete for app %d: %s", app_id, list(fetched.keys()))
    else:
        logger.info("Auto-fetch found nothing for app %d (%s / %s)", app_id, display_name, exe_name)

    return fetched


# ── Thread helpers ────────────────────────────────────────────────────────────

def auto_fetch_background(app_id: int, display_name: str, exe_name: str, exe_path: str = ""):
    """Start auto_fetch_images in a daemon thread; resets cancel flag and records status."""
    reset_cancel()
    _fetch_status[app_id] = {"running": True, "fetched": {}, "cancelled": False}

    def _run():
        try:
            result = auto_fetch_images(app_id, display_name, exe_name, exe_path)
        except Exception as exc:
            logger.debug("auto_fetch_background error for app %d: %s", app_id, exc)
            result = {}
        _fetch_status[app_id] = {
            "running": False,
            "fetched": result,
            "cancelled": _is_cancelled(),
        }

    threading.Thread(target=_run, daemon=True, name=f"imgfetch-{app_id}").start()


def _run_batch_fetch(apps: list[dict]):
    """Process apps sequentially in a single thread with pauses to keep CPU low."""
    import time
    reset_cancel()
    total = len(apps)
    for i, app in enumerate(apps, 1):
        if _is_cancelled():
            logger.info("Batch fetch cancelled at %d/%d", i, total)
            break
        try:
            logger.info("Batch fetch %d/%d: %s", i, total, app.get("display_name", ""))
            auto_fetch_images(app["id"], app["display_name"], app["exe_name"])
        except Exception as exc:
            logger.debug("Batch fetch error for app %d: %s", app["id"], exc)
        if i < total and not _is_cancelled():
            time.sleep(1.5)
    logger.info("Batch fetch complete: %d apps processed", total)


def start_batch_fetch(apps: list[dict]):
    """Fire-and-forget: process apps sequentially in a single daemon thread."""
    if not apps:
        return
    t = threading.Thread(target=_run_batch_fetch, args=(apps,), daemon=True, name="imgfetch-batch")
    t.start()
