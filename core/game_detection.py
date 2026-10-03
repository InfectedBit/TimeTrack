"""
TimeTrack — Game Detection
Multi-layer heuristic for identifying game executables without requiring any
external API during the hot scan path. Detection is lazy-initialized on first use.

Layers (evaluated in order, first match wins):
  1. Launcher path fragments  — check exe_path for Steam/Epic/GOG/Ubisoft etc.
  2. Windows Game Mode registry — HKCU\\System\\GameConfigStore
  3. NVIDIA DRS profiles       — C:\\ProgramData\\NVIDIA Corporation\\Drs\\*.nip
  4. Heuristic                 — exe_path outside Windows/System32, has game keywords
"""

import re
import logging
from pathlib import Path

logger = logging.getLogger("game_detector")


# ── Always-skip sets ──────────────────────────────────────────────────────────

SYSTEM_SKIP: frozenset[str] = frozenset([
    # Windows core
    "system", "registry", "smss.exe", "csrss.exe", "wininit.exe",
    "winlogon.exe", "services.exe", "lsass.exe", "lsaiso.exe",
    "svchost.exe", "taskhostw.exe", "sihost.exe", "fontdrvhost.exe",
    "dwm.exe", "explorer.exe", "shellexperiencehost.exe",
    "startmenuexperiencehost.exe", "runtimebroker.exe",
    "searchindexer.exe", "searchhost.exe", "searchapp.exe",
    "ctfmon.exe", "dllhost.exe", "conhost.exe", "cmd.exe",
    "powershell.exe", "pwsh.exe", "msiexec.exe", "wuauclt.exe",
    "spoolsv.exe", "taskmgr.exe", "notepad.exe", "mspaint.exe",
    "calc.exe", "wmiprvse.exe", "wbemcons.exe", "audiodg.exe",
    "dashost.exe", "securityhealthservice.exe", "vgc.exe",
    # Browsers
    "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe",
    "opera.exe", "vivaldi.exe", "iexplore.exe", "arc.exe",
    "thorium.exe", "waterfox.exe", "librewolf.exe",
    # Dev tools
    "code.exe", "cursor.exe", "devenv.exe", "devenv.com",
    "pycharm64.exe", "idea64.exe", "rider64.exe", "clion64.exe",
    "goland64.exe", "webstorm64.exe", "phpstorm64.exe",
    "node.exe", "python.exe", "pythonw.exe", "java.exe", "javaw.exe",
    "git.exe", "git-lfs.exe", "bash.exe", "wsl.exe", "wslhost.exe",
    "wt.exe", "windowsterminal.exe",
    # Common apps (not games)
    "discord.exe", "discordptb.exe", "discordcanary.exe",
    "slack.exe", "teams.exe", "zoom.exe", "skype.exe",
    "spotify.exe", "vlc.exe", "mpv.exe", "mpc-hc64.exe",
    "obs64.exe", "obs-browser.exe", "streamlabs obs.exe",
    "notepad++.exe", "7zfm.exe", "7zg.exe", "winrar.exe",
    "totalcmd.exe", "totalcmd64.exe", "everything.exe",
    "lively.exe", "rainmeter.exe", "sharex.exe", "greenshot.exe",
    "malwarebytes.exe", "mbam.exe", "avastui.exe",
    # NVIDIA/AMD system processes
    "nvcontainer.exe", "nvtelemetrycontainer.exe",
    "nvdisplay.container.exe", "nvcpluiapp.exe", "nvsphelper64.exe",
    "nvspcaps64.exe", "nvvsvc.exe", "nvsiworkaround.exe",
    "amdow.exe", "radeonsoftware.exe", "radeoninstaller.exe",
    # Launcher executables themselves (not the games they run)
    "steam.exe", "steamwebhelper.exe", "steamservice.exe",
    "epicgameslauncher.exe", "galaxyclient.exe", "galaxyclient helper.exe",
    "upc.exe", "ubisoft connect.exe", "ubisoftgamelauncher.exe",
    "origin.exe", "eadesktop.exe", "easteamproxy.exe",
    "battlenet.exe", "blizzard error.exe", "agent.exe",
    "bethesda.net_launcher.exe", "glyph.exe", "itch.exe",
    "xboxapp.exe", "gamingservices.exe", "gamingservicesnet.exe",
    "playnite.desktop.exe", "playnite.fullscreen.exe",
    "gog.com downloader.exe", "goggalaxy.exe",
    "riot client services.exe", "riotclientservices.exe",
    "riotclient.exe",
])

# Path fragments that confirm a game exe (regex applied to lowercased path)
LAUNCHER_PATH_PATTERNS: list[str] = [
    r"steamapps[\\/]common[\\/]",
    r"epic games[\\/]",
    r"gog galaxy[\\/]games[\\/]",
    r"ubisoft game launcher[\\/]games[\\/]",
    r"ubisoft connect[\\/]games[\\/]",
    r"ea games[\\/]",
    r"ea desktop[\\/]",
    r"origin games[\\/]",
    r"blizzard entertainment[\\/]",
    r"xboxgames[\\/]",
    r"windowsapps[\\/]microsoft\.xbox",
    r"bethesda\.net[\\/]games[\\/]",
    r"rockstar games[\\/]",
    r"itch[\\/]apps[\\/]",
    r"heroic[\\/]games[\\/]",          # Heroic Games Launcher (GOG/Epic alternative)
    r"playnite[\\/]games[\\/]",
]
_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in LAUNCHER_PATH_PATTERNS]

# Keywords in path (outside Windows dir) that hint at a game
GAME_PATH_KEYWORDS = [
    "games", r"\bgame\b", "steam", "epic", "gog", "ubisoft",
    "ea games", "origin", "battle.net", "blizzard", "rockstar",
    "riot", "bethesda", "itch", "heroic",
]
_GAME_KEYWORD_RE = re.compile(
    "|".join(GAME_PATH_KEYWORDS), re.IGNORECASE
)


class GameDetector:
    """
    Stateful detector that lazy-loads registry/filesystem data on first call.
    Thread-safe for reads after initialization (initialization itself is single-threaded
    since it happens at first detection check, typically within the tracker thread).
    """

    def __init__(self):
        self._initialized    = False
        self._game_mode_exes: set[str]  = set()   # from Windows GameConfigStore
        self._nvidia_exes:    set[str]  = set()   # from NVIDIA DRS .nip profiles
        self._steam_path:     str | None = None
        self._custom_paths:   list[str] = []      # user-defined paths (normalized)
        self._enabled_methods: set[str] = {       # which detection layers are on
            "launcher", "custom", "gamemode", "nvidia", "heuristic"
        }

    # ── Lazy init ─────────────────────────────────────────────────────────────

    def _lazy_init(self):
        if self._initialized:
            return
        self._initialized = True

        for name, fn in [
            ("GameConfigStore", self._load_game_mode_registry),
            ("NVIDIA DRS",      self._load_nvidia_profiles),
            ("Steam path",      self._find_steam_path),
            ("Custom paths",    self._load_custom_paths),
            ("Detect methods",  self._load_detect_methods),
        ]:
            try:
                fn()
            except Exception as exc:
                logger.debug("[GameDetector] %s load failed: %s", name, exc)

    def _load_game_mode_registry(self):
        import winreg
        key_path = r"System\GameConfigStore\Children"
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path)
        except FileNotFoundError:
            return
        i = 0
        while True:
            try:
                sub_name = winreg.EnumKey(key, i)
                sub = winreg.OpenKey(key, sub_name)
                try:
                    val, _ = winreg.QueryValueEx(sub, "ExecutableName")
                    if val:
                        self._game_mode_exes.add(Path(val).name.lower())
                except FileNotFoundError:
                    pass
                finally:
                    winreg.CloseKey(sub)
                i += 1
            except OSError:
                break
        winreg.CloseKey(key)
        logger.debug("[GameDetector] GameConfigStore: %d exe(s)", len(self._game_mode_exes))

    def _load_nvidia_profiles(self):
        """Parse NVIDIA DRS .nip XML profiles for known game executables."""
        import xml.etree.ElementTree as ET
        drs_dir = Path(r"C:\ProgramData\NVIDIA Corporation\Drs")
        if not drs_dir.exists():
            return
        count = 0
        for nip in drs_dir.glob("*.nip"):
            try:
                tree = ET.parse(nip)
                for elem in tree.iter():
                    if elem.tag == "Property" and elem.get("name") in (
                        "EXE_PATH_INFORMATION", "PROCESS_NAME", "ExecutablePath",
                    ):
                        raw = elem.get("value", "")
                        if raw.lower().endswith(".exe"):
                            self._nvidia_exes.add(Path(raw).name.lower())
                            count += 1
            except Exception:
                pass
        logger.debug("[GameDetector] NVIDIA DRS: %d exe(s)", count)

    def _load_custom_paths(self):
        from core.database import get_game_paths
        self._custom_paths = [
            p["path"].replace("\\", "/").rstrip("/").lower() + "/"
            for p in get_game_paths()
        ]
        logger.debug("[GameDetector] Custom paths: %d", len(self._custom_paths))

    def _load_detect_methods(self):
        from core.database import get_detect_methods
        self._enabled_methods = set(get_detect_methods())
        logger.debug("[GameDetector] Enabled methods: %s", self._enabled_methods)

    def _find_steam_path(self):
        import winreg
        for hive, path in [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
            (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\Valve\Steam"),
        ]:
            try:
                key = winreg.OpenKey(hive, path)
                val, _ = winreg.QueryValueEx(key, "InstallPath")
                winreg.CloseKey(key)
                self._steam_path = str(val).lower()
                logger.debug("[GameDetector] Steam: %s", self._steam_path)
                return
            except (FileNotFoundError, OSError):
                continue

    def reload(self):
        """Force re-initialization on the next detection call (e.g. after settings change)."""
        self._initialized     = False
        self._game_mode_exes.clear()
        self._nvidia_exes.clear()
        self._steam_path      = None
        self._custom_paths    = []
        self._enabled_methods = {"launcher", "custom", "gamemode", "nvidia", "heuristic"}

    # ── Public API ────────────────────────────────────────────────────────────

    def is_likely_game(self, exe_name: str, exe_path: str = "") -> tuple[bool, str]:
        """
        Returns (is_game, detected_via).
        exe_name: lowercase .exe filename
        exe_path: full path from psutil.Process.exe() — may be empty if AccessDenied
        """
        self._lazy_init()

        exe_lower = exe_name.lower()

        # Hard exclusions — always skip
        if exe_lower in SYSTEM_SKIP:
            return False, ""

        if exe_path:
            path_norm  = exe_path.replace("\\", "/")
            path_lower = path_norm.lower()

            # Layer 1: Built-in launcher path patterns (most reliable)
            if "launcher" in self._enabled_methods:
                for pat in _COMPILED_PATTERNS:
                    if pat.search(path_norm):
                        launcher = pat.pattern.split(r"[\\/]")[0].strip(r"[\\/]")
                        return True, f"launcher path ({launcher})"

            # Layer 2: User-defined custom paths
            if "custom" in self._enabled_methods:
                for cp in self._custom_paths:
                    if path_lower.startswith(cp):
                        return True, "custom path"

        # Layer 3: Windows Game Mode registry
        if "gamemode" in self._enabled_methods and exe_lower in self._game_mode_exes:
            return True, "Windows Game Mode"

        # Layer 4: NVIDIA DRS profiles
        if "nvidia" in self._enabled_methods and exe_lower in self._nvidia_exes:
            return True, "NVIDIA profile"

        # Layer 5: Heuristic — path available, not in system dirs, has game keywords
        if "heuristic" in self._enabled_methods and exe_path:
            path_lower_h = exe_path.lower().replace("\\", "/")
            if (path_lower_h.startswith("c:/windows") or
                    path_lower_h.startswith("/windows")):
                return False, ""
            if _GAME_KEYWORD_RE.search(path_lower_h):
                return True, "heuristic (path keyword)"

        return False, ""

    def get_steam_display_name(self, exe_path: str) -> str | None:
        """
        Extract the Steam game folder name from the exe path as a nicer display name.
        e.g. .../steamapps/common/Cyberpunk 2077/bin/x64/Cyberpunk2077.exe → 'Cyberpunk 2077'
        """
        if not exe_path:
            return None
        try:
            parts = Path(exe_path).parts
            for i, part in enumerate(parts):
                if part.lower() == "common" and i > 0 and "steamapps" in parts[i - 1].lower():
                    if i + 1 < len(parts):
                        return parts[i + 1]
        except Exception:
            pass
        return None


# Singleton used by tracker.py
game_detector = GameDetector()
