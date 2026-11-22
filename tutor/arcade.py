"""Local Video Game Rewards engine (Fists of Doom + Windows / Chromebook / Mac Minecraft).

Active IF AND ONLY IF at least one supported game is installed locally on this computer:
  1. Fists of Doom: Toronto (`$HOME/FistsOfDoom` or `$FOD_DIR` — Windows PC, Mac, Chromebook)
  2. Minecraft:
     - Windows 11/10: Native Prism Launcher (`prismlauncher.exe`), Official Mojang/Xbox Launcher, or Minecraft Bedrock (`Minecraft.Windows.exe`)
     - Chromebook/Linux: Prism Launcher (`org.prismlauncher.PrismLauncher` `--user` Flatpak)
     - macOS: `/Applications/Prism Launcher.app`

How Writing Quality & Points Work
---------------------------------
* Never counts idle open-app time, fragments, gibberish, or avoidance:
  - Each writing turn's active window is bounded (`<= 75s`) so walking away earns `0s`.
  - Time spent drafting, revising grammar/verb endings, or sounding out spelling words buffers temporarily
    and ONLY commits to persistent credit when a verified Homework-Standard complete sentence (starting capital,
    end mark, complete clause, clean spelling/grammar) or Cover-Copy-Compare word retrieval succeeds.
* Progress persists across sessions in `learner.json` (`rec["arcade"]`):
  - Every `minutes_per_point` (default 15 min) of active solid writing earns **+1 Point** (so a 15-min session
    earns 1 Point and zero minutes are ever lost between sessions).
  - Reaching `points_to_unlock` points (default 2 Points = 30 min of solid writing) automatically converts into
    `reward_game_minutes` (default 15 min) of banked Video Game Time, configurable by parents on `/parent`.

How Game Time Enforcement Works
-------------------------------
* Fists of Doom: Runs embedded inside Gemini Tutor (`http://localhost:8788/?embedded=tutor`) with 5s heartbeats
  and auto-closes when banked time hits `0:00` (plus optional standalone app lock).
* Minecraft (Windows Native & Chromebook Crostini):
  - Windows: Monitored every 3s via windowless `tasklist` + verified `Win32_Process` Java `CommandLine` filtering
    (`javaw.exe`/`java.exe` + `Minecraft.Windows.exe`), fires native Windows 11 WinRT Toast notifications + chime
    with 1 minute remaining, gracefully closes & terminates Minecraft at `0:00`, and syncs a silent Windows
    `Startup` watchdog + gated Desktop shortcut (`bin/minecraft-gated-launch.py`).
  - Chromebook: Launched with `QT_QPA_PLATFORM=xcb` via `flatpak run org.prismlauncher.PrismLauncher`, monitored
    via `/proc`, warns via `notify-send`, and closes cleanly via `flatpak kill`.
"""

from __future__ import annotations

import copy
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

from .config import ROOT
from .record import load_learner, now_iso, save_learner

FOD_PORT = int(os.environ.get("FOD_PORT", "8788"))
PRISM_APP_ID = "org.prismlauncher.PrismLauncher"
_WIN_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if os.name == "nt" else 0

DEFAULT_ARCADE: dict[str, Any] = {
    "enabled": True,
    "minutes_per_point": 15,       # Takes 15 min of active solid writing to earn 1 point
    "points_to_unlock": 2,         # Default: 2 points (30 min solid writing) unlocks game time
    "reward_game_minutes": 15,     # Default: 15 min of video game time per unlock
    "lock_standalone": False,      # Optional parent setting: lock standalone Fists of Doom when bank is 0
    "gate_minecraft": True,        # Gate Chromebook Minecraft shelf icon & background JVM when bank is 0
    "minecraft_instance": "",      # Optional specific Prism instance ID ("" = auto / SelectedInstance)
    "committed_work_seconds": 0.0, # Active verified seconds toward next point (persisted across sessions)
    "points_towards_unlock": 0,    # Whole points earned toward next game unlock (persisted across sessions)
    "lifetime_work_seconds": 0.0,
    "lifetime_points_earned": 0,
    "lifetime_sentences_verified": 0,
    "game_seconds_available": 0.0,
    "lifetime_game_seconds_played": 0.0,
    "history": [],
}

# Isolated ephemeral state for `/?sandbox=1` so Parent Try-It never mutates the child's points or game bank.
_SANDBOX_ARCADE: dict[str, Any] = copy.deepcopy(DEFAULT_ARCADE)

MAX_TURN_ACTIVE_SECONDS = 75.0
MAX_PENDING_EFFORT_SECONDS = 120.0
MAX_ORAL_BUFFER_SECONDS = 150.0

_STATE_LOCK = threading.Lock()
_WATCHDOG_STARTED = False
_MC_LAUNCHED_AT = 0.0          # Gives up to 30s launcher boot grace before Java starts
_MC_WARNED_ONE_MIN = False
_PARENT_SETUP_UNTIL = 0.0      # Unlocked parent maintenance window for Microsoft login / instance setup


# ------------------------------------------------------------------ Local Game Discovery


def fod_install_dir() -> Path:
    override = (os.environ.get("FOD_DIR") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / "FistsOfDoom").resolve()


def is_fod_installed() -> bool:
    """True IF AND ONLY IF Fists of Doom is installed locally on this machine."""
    d = fod_install_dir()
    return d.is_dir() and (d / "server_multiplayer.py").is_file() and (d / "index.html").is_file()


def _is_win() -> bool:
    return os.name == "nt"


def _win_prism_exe() -> Path | None:
    """Locates native Windows `prismlauncher.exe` across standard Winget, installer, and Scoop paths."""
    if not _is_win():
        return None
    override = (os.environ.get("PRISM_EXE") or "").strip()
    if override and Path(override).is_file():
        return Path(override)
    home = Path.home()
    local_app = Path(os.environ.get("LOCALAPPDATA") or (home / "AppData" / "Local"))
    prog = Path(os.environ.get("ProgramFiles") or r"C:\Program Files")
    prog_x86 = Path(os.environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)")
    candidates = [
        local_app / "Programs" / "PrismLauncher" / "prismlauncher.exe",
        prog / "PrismLauncher" / "prismlauncher.exe",
        prog_x86 / "PrismLauncher" / "prismlauncher.exe",
        home / "scoop" / "apps" / "prismlauncher" / "current" / "prismlauncher.exe",
    ]
    which_p = shutil.which("prismlauncher.exe") or shutil.which("prismlauncher")
    if which_p:
        candidates.append(Path(which_p))
    for p in candidates:
        try:
            if p.is_file():
                return p
        except OSError:
            continue
    return None


def _win_official_minecraft_info() -> dict[str, Any]:
    """Detects Official Mojang / Xbox App Minecraft Launcher or Minecraft for Windows (Bedrock) on Windows."""
    if not _is_win():
        return {"installed": False, "exe": None, "has_store_launcher": False, "has_bedrock": False}
    home = Path.home()
    appdata = Path(os.environ.get("APPDATA") or (home / "AppData" / "Roaming"))
    local_app = Path(os.environ.get("LOCALAPPDATA") or (home / "AppData" / "Local"))
    prog = Path(os.environ.get("ProgramFiles") or r"C:\Program Files")
    prog_x86 = Path(os.environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)")
    sys_drive = os.environ.get("SystemDrive") or "C:\\"
    if len(sys_drive) == 2 and sys_drive[1] == ":":
        sys_drive = sys_drive + "\\"

    exe_candidates = [
        Path(sys_drive) / "XboxGames" / "Minecraft Launcher" / "Content" / "Minecraft.exe",
        prog_x86 / "Minecraft Launcher" / "MinecraftLauncher.exe",
        prog / "Minecraft Launcher" / "MinecraftLauncher.exe",
    ]
    found_exe: str | None = None
    for p in exe_candidates:
        try:
            if p.is_file():
                found_exe = str(p)
                break
        except OSError:
            continue

    pkgs_dir = local_app / "Packages"
    has_store_launcher = False
    has_bedrock = False
    try:
        if pkgs_dir.is_dir():
            for child in pkgs_dir.iterdir():
                nm = child.name
                if nm.startswith("Microsoft.4297127D64EC6_"):
                    has_store_launcher = True
                elif nm.startswith("Microsoft.MinecraftUWP_") or nm.startswith("Microsoft.MinecraftWindowsBeta_"):
                    has_bedrock = True
    except OSError:
        pass

    dot_mc = appdata / ".minecraft"
    has_dot_mc = False
    try:
        has_dot_mc = dot_mc.is_dir() and (
            (dot_mc / "launcher_profiles.json").is_file() or (dot_mc / "versions").is_dir()
        )
    except OSError:
        pass

    installed = bool(found_exe or has_store_launcher or has_bedrock or has_dot_mc)
    return {
        "installed": installed,
        "exe": found_exe,
        "has_store_launcher": has_store_launcher,
        "has_bedrock": has_bedrock,
    }


def prism_data_dir() -> Path:
    override = (os.environ.get("PRISM_DATA_DIR") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    home = Path.home()
    if _is_win():
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "PrismLauncher"
        return home / "AppData" / "Roaming" / "PrismLauncher"
    flatpak_data = home / ".var" / "app" / PRISM_APP_ID / "data" / "PrismLauncher"
    if flatpak_data.exists() or (home / ".local" / "share" / "flatpak" / "app" / PRISM_APP_ID).exists():
        return flatpak_data
    if sys.platform == "darwin":
        mac_dir = home / "Library" / "Application Support" / "PrismLauncher"
        if mac_dir.exists():
            return mac_dir
    return flatpak_data


def minecraft_flavor() -> str:
    """Returns `'prism'`, `'official'`, or `''` if Minecraft is not installed on this machine."""
    if (os.environ.get("PRISM_FORCE_INSTALLED") or "").strip() == "1":
        return "prism"
    home = Path.home()
    if _is_win():
        if _win_prism_exe() is not None:
            return "prism"
        pdir = prism_data_dir()
        if (pdir / "prismlauncher.cfg").is_file() or (pdir / "instances").is_dir():
            return "prism"
        if _win_official_minecraft_info()["installed"]:
            return "official"
        return ""
    if (home / ".local" / "share" / "flatpak" / "app" / PRISM_APP_ID).exists():
        return "prism"
    if (home / ".local" / "share" / "flatpak" / "exports" / "share" / "applications" / f"{PRISM_APP_ID}.desktop").exists():
        return "prism"
    if sys.platform == "darwin" and (
        Path("/Applications/Prism Launcher.app").exists() or (home / "Applications/Prism Launcher.app").exists()
    ):
        return "prism"
    return ""


def is_minecraft_installed() -> bool:
    """True IF AND ONLY IF a supported local Minecraft install (Prism or Official/Bedrock) exists."""
    return bool(minecraft_flavor())


def is_any_game_installed() -> bool:
    return is_fod_installed() or is_minecraft_installed()


def _parse_kv_cfg(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    try:
        for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("[") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    except OSError:
        pass
    return out


def list_minecraft_instances() -> dict[str, Any]:
    """Discovers installed Prism Launcher instances and selected default instance."""
    pdir = prism_data_dir()
    cfg = _parse_kv_cfg(pdir / "prismlauncher.cfg")
    selected = cfg.get("SelectedInstance", "").strip()
    inst_root = pdir / "instances"
    instances: list[dict[str, str]] = []
    if inst_root.is_dir():
        for child in sorted(inst_root.iterdir(), key=lambda p: p.name.lower()):
            if not child.is_dir() or child.name.startswith("_") or child.name.startswith("."):
                continue
            icfg_path = child / "instance.cfg"
            if not icfg_path.is_file() and not (child / "mmc-pack.json").is_file():
                continue
            icfg = _parse_kv_cfg(icfg_path)
            label = icfg.get("name") or child.name
            instances.append({"id": child.name, "name": label})
    valid_ids = {i["id"] for i in instances}
    default_id = selected if selected in valid_ids else (instances[0]["id"] if len(instances) == 1 else "")
    return {"instances": instances, "selected": selected, "default_id": default_id}


# ------------------------------------------------------------------ Minecraft Process Control & Shelf Gating


_MC_JAVA_MARKERS = (
    "org.prismlauncher",
    "prismlauncher",
    "net.minecraft",
    ".minecraft",
    "cpw.mods",
    "net.fabricmc",
    "mojang",
)


def _is_minecraft_java_cmdline(cmdline: str) -> bool:
    low = (cmdline or "").lower()
    return any(tok in low for tok in _MC_JAVA_MARKERS)


def minecraft_process_state() -> dict[str, bool]:
    """Inspects running processes across Windows, Linux/Chromebook, and macOS without console flashes."""
    launcher = False
    game_jvm = False

    # 1. Native Windows 11/10 (`tasklist` + conditional `Win32_Process` Java CommandLine check)
    if _is_win():
        has_java_proc = False
        try:
            out = subprocess.check_output(
                ["tasklist", "/FO", "CSV", "/NH"],
                text=True,
                timeout=2.0,
                creationflags=_WIN_NO_WINDOW,
            )
            for row in csv.reader(out.splitlines()):
                if not row:
                    continue
                img = row[0].strip().lower()
                if img in ("prismlauncher.exe", "minecraftlauncher.exe", "minecraft.exe"):
                    launcher = True
                elif img == "minecraft.windows.exe":
                    game_jvm = True
                elif img in ("javaw.exe", "java.exe"):
                    has_java_proc = True
        except Exception:
            pass

        if has_java_proc and not game_jvm:
            ps = shutil.which("powershell.exe") or "powershell"
            try:
                cmd_out = subprocess.check_output(
                    [
                        ps,
                        "-NoProfile",
                        "-NonInteractive",
                        "-Command",
                        "Get-CimInstance Win32_Process -Filter \"Name='javaw.exe' OR Name='java.exe'\" | Select-Object -ExpandProperty CommandLine",
                    ],
                    text=True,
                    timeout=3.0,
                    creationflags=_WIN_NO_WINDOW,
                )
                for line in cmd_out.splitlines():
                    if _is_minecraft_java_cmdline(line):
                        game_jvm = True
                        break
            except Exception:
                pass

        return {"launcher": launcher, "game_jvm": game_jvm, "any": launcher or game_jvm}

    # 2. Linux / Chromebook Crostini (`/proc`)
    proc_root = Path("/proc")
    if proc_root.is_dir():
        for entry in proc_root.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                raw = (entry / "cmdline").read_bytes()
                if not raw:
                    continue
                parts = [p.decode("utf-8", errors="ignore") for p in raw.split(b"\x00") if p]
                if not parts:
                    continue
                joined = " ".join(parts)
                if "prism-gated-launch.sh" in joined or "minecraft-gated-launch.py" in joined:
                    continue
                exe_name = Path(parts[0]).name.lower()
                if "prismlauncher" in exe_name:
                    launcher = True
                elif exe_name.startswith("java") and _is_minecraft_java_cmdline(joined):
                    game_jvm = True
            except OSError:
                continue
        return {"launcher": launcher, "game_jvm": game_jvm, "any": launcher or game_jvm}

    # 3. macOS fallback
    if sys.platform == "darwin":
        try:
            out = subprocess.check_output(["ps", "-axo", "command"], text=True, timeout=1.5)
            for line in out.splitlines():
                if "minecraft-gated-launch.py" in line:
                    continue
                if "Prism Launcher.app" in line or "prismlauncher" in line.lower():
                    launcher = True
                if "java" in line and _is_minecraft_java_cmdline(line):
                    game_jvm = True
        except Exception:
            pass
    return {"launcher": launcher, "game_jvm": game_jvm, "any": launcher or game_jvm}


def _desktop_notify(title: str, body: str, urgent: bool = False) -> None:
    """Shows a native OS notification (Windows 11 WinRT Toast + chime, Linux `notify-send`, macOS `osascript`)."""
    if _is_win():
        ps = shutil.which("powershell.exe") or "powershell"
        env = dict(os.environ)
        env["GT_TOAST_TITLE"] = title
        env["GT_TOAST_BODY"] = body
        env["GT_TOAST_URGENT"] = "1" if urgent else "0"
        ps_script = (
            "if ($env:GT_TOAST_URGENT -eq '1') { try { [console]::beep(880,160); [console]::beep(1046,200) } catch {} }; "
            "try { "
            "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null; "
            "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null; "
            "$t = [System.Security.SecurityElement]::Escape($env:GT_TOAST_TITLE); "
            "$b = [System.Security.SecurityElement]::Escape($env:GT_TOAST_BODY); "
            "$sc = if ($env:GT_TOAST_URGENT -eq '1') { ' scenario=\"reminder\"' } else { '' }; "
            "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument; "
            "$xml.LoadXml(\"<toast$sc><visual><binding template='ToastGeneric'><text>$t</text><text>$b</text></binding></visual></toast>\"); "
            "$toast = [Windows.UI.Notifications.ToastNotification]::new($xml); "
            "$appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe'; "
            "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast) "
            "} catch {}"
        )
        try:
            subprocess.Popen(
                [ps, "-NoProfile", "-NonInteractive", "-Command", ps_script],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_WIN_NO_WINDOW,
            )
        except Exception:
            pass
        return

    if sys.platform == "darwin":
        osa = shutil.which("osascript")
        if osa:
            safe_t = title.replace('"', '\\"')
            safe_b = body.replace('"', '\\"')
            try:
                subprocess.Popen(
                    [osa, "-e", f'display notification "{safe_b}" with title "{safe_t}"'],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass
        return

    ns = shutil.which("notify-send")
    if not ns:
        return
    cmd = [ns]
    if urgent:
        cmd.extend(["-u", "critical"])
    cmd.extend([title, body])
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def stop_minecraft() -> None:
    """Cleanly closes Minecraft & its launcher (Windows Java/Bedrock/Prism, Linux Flatpak, macOS)."""
    if _is_win():
        ps = shutil.which("powershell.exe") or "powershell"
        ps_kill = (
            "$mcJava = Get-CimInstance Win32_Process -Filter \"Name='javaw.exe' OR Name='java.exe'\" | "
            "Where-Object { $_.CommandLine -match 'prismlauncher|net\\.minecraft|\\.minecraft|cpw\\.mods|net\\.fabricmc|mojang' }; "
            "$mcApps = Get-Process -Name 'Minecraft.Windows','prismlauncher','MinecraftLauncher' -ErrorAction SilentlyContinue; "
            "foreach ($p in $mcApps) { try { $null = $p.CloseMainWindow() } catch {} }; "
            "foreach ($j in $mcJava) { try { $gp = Get-Process -Id $j.ProcessId -ErrorAction SilentlyContinue; if ($gp) { $null = $gp.CloseMainWindow() } } catch {} }; "
            "Start-Sleep -Milliseconds 1200; "
            "Stop-Process -Name 'Minecraft.Windows','prismlauncher','MinecraftLauncher' -Force -ErrorAction SilentlyContinue; "
            "foreach ($j in $mcJava) { Stop-Process -Id $j.ProcessId -Force -ErrorAction SilentlyContinue }"
        )
        try:
            subprocess.run(
                [ps, "-NoProfile", "-NonInteractive", "-Command", ps_kill],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=8.0,
                check=False,
                creationflags=_WIN_NO_WINDOW,
            )
        except Exception:
            pass
        return

    fp = shutil.which("flatpak")
    if fp:
        subprocess.run([fp, "kill", PRISM_APP_ID], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    if sys.platform == "darwin":
        subprocess.run(["pkill", "-f", "Prism Launcher"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def launch_minecraft(*, instance_override: str | None = None, parent_setup: bool = False) -> dict[str, Any]:
    """Launches Prism Launcher (or Official Windows Minecraft) directly into an instance or Parent Setup mode."""
    global _MC_LAUNCHED_AT, _MC_WARNED_ONE_MIN, _PARENT_SETUP_UNTIL
    flavor = minecraft_flavor()
    if not flavor:
        raise RuntimeError("Minecraft is not installed on this computer.")

    if parent_setup:
        _PARENT_SETUP_UNTIL = time.time() + 1800.0
    else:
        _MC_LAUNCHED_AT = time.time()
        _MC_WARNED_ONE_MIN = False

    chosen = ""
    if flavor == "prism":
        inst_info = list_minecraft_instances()
        valid_ids = {i["id"] for i in inst_info["instances"]}
        if not parent_setup:
            req = (instance_override or "").strip()
            if req and req in valid_ids:
                chosen = req
            elif inst_info["default_id"]:
                chosen = inst_info["default_id"]

    # 1. Native Windows 11/10
    if _is_win():
        prism_exe = _win_prism_exe()
        if prism_exe is not None:
            cmd = [str(prism_exe)]
            if chosen:
                cmd.extend(["--launch", chosen])
            subprocess.Popen(cmd, cwd=str(prism_exe.parent))
            return {"ok": True, "instance": chosen or None, "parent_setup": parent_setup, "flavor": "prism"}

        off = _win_official_minecraft_info()
        if off["exe"]:
            subprocess.Popen([off["exe"]])
            return {"ok": True, "instance": None, "parent_setup": parent_setup, "flavor": "official"}
        if off["has_store_launcher"]:
            subprocess.Popen(
                ["explorer.exe", r"shell:AppsFolder\Microsoft.4297127D64EC6_8wekyb3d8bbwe!Minecraft"],
                creationflags=_WIN_NO_WINDOW,
            )
            return {"ok": True, "instance": None, "parent_setup": parent_setup, "flavor": "official"}
        if off["has_bedrock"] or off["installed"]:
            subprocess.Popen(["explorer.exe", "minecraft://"], creationflags=_WIN_NO_WINDOW)
            return {"ok": True, "instance": None, "parent_setup": parent_setup, "flavor": "official"}
        raise RuntimeError("Could not locate Prism Launcher or Minecraft Launcher executable on Windows.")

    # 2. Chromebook / Linux (`flatpak`)
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "xcb"

    fp = shutil.which("flatpak")
    if fp and (Path.home() / ".local" / "share" / "flatpak" / "app" / PRISM_APP_ID).exists():
        # Ensure permanent XWayland override is applied for Crostini stability
        subprocess.run(
            [fp, "--user", "override", "--env=QT_QPA_PLATFORM=xcb", PRISM_APP_ID],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        cmd = [fp, "run", PRISM_APP_ID]
        if chosen:
            cmd.extend(["--launch", chosen])
        subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return {"ok": True, "instance": chosen or None, "parent_setup": parent_setup, "flavor": "prism"}

    # 3. macOS
    if sys.platform == "darwin":
        app_p = Path("/Applications/Prism Launcher.app")
        if not app_p.exists():
            app_p = Path.home() / "Applications/Prism Launcher.app"
        cmd = ["open", "-a", str(app_p)]
        if chosen:
            cmd.extend(["--args", "--launch", chosen])
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"ok": True, "instance": chosen or None, "parent_setup": parent_setup, "flavor": "prism"}

    raise RuntimeError("Could not find Prism Launcher binary on this system.")


def sync_minecraft_desktop_gate(gate_enabled: bool) -> None:
    """Syncs OS-level Minecraft gating (Windows Startup watchdog + Desktop shortcut, or ChromeOS `.desktop`)."""
    if sys.platform == "darwin":
        return

    if _is_win():
        ps = shutil.which("powershell.exe") or "powershell"
        pyw = ROOT / ".venv" / "Scripts" / "pythonw.exe"
        if not pyw.is_file():
            cand = Path(sys.executable).with_name("pythonw.exe")
            pyw = cand if cand.is_file() else Path(sys.executable)
        launch_py = ROOT / "launch.py"
        gated_py = ROOT / "bin" / "minecraft-gated-launch.py"
        prism_exe = _win_prism_exe()

        env = dict(os.environ)
        env["GT_GATE_ON"] = "1" if gate_enabled else "0"
        env["GT_PYW"] = str(pyw)
        env["GT_ROOT"] = str(ROOT)
        env["GT_LAUNCH"] = str(launch_py)
        env["GT_GATED_PY"] = str(gated_py)
        env["GT_PRISM_EXE"] = str(prism_exe) if prism_exe else ""

        ps_sync = (
            "$wsh = New-Object -ComObject WScript.Shell; "
            "$startup = [Environment]::GetFolderPath('Startup'); "
            "$desktop = [Environment]::GetFolderPath('Desktop'); "
            "$wdLnk = Join-Path $startup 'Gemini Tutor Watchdog.lnk'; "
            "if ($env:GT_GATE_ON -eq '1') { "
            "  if ($startup -and (Test-Path $startup)) { "
            "    $s = $wsh.CreateShortcut($wdLnk); "
            "    $s.TargetPath = $env:GT_PYW; "
            "    $s.Arguments = '\"' + $env:GT_LAUNCH + '\" --no-open'; "
            "    $s.WorkingDirectory = $env:GT_ROOT; "
            "    $s.Description = 'Gemini Tutor Background Minecraft Time-Gating Watchdog'; "
            "    $s.Save(); "
            "  }; "
            "  if ($desktop -and (Test-Path $desktop) -and (Test-Path $env:GT_GATED_PY)) { "
            "    $prismLnk = Join-Path $desktop 'Prism Launcher.lnk'; "
            "    if ((Test-Path $prismLnk) -or $env:GT_PRISM_EXE) { "
            "      $m = $wsh.CreateShortcut($prismLnk); "
            "      $m.TargetPath = $env:GT_PYW; "
            "      $m.Arguments = '\"' + $env:GT_GATED_PY + '\"'; "
            "      $m.WorkingDirectory = $env:GT_ROOT; "
            "      $m.Description = 'Prism Launcher (Earned Time via Gemini Tutor)'; "
            "      if ($env:GT_PRISM_EXE -and (Test-Path $env:GT_PRISM_EXE)) { $m.IconLocation = $env:GT_PRISM_EXE + ',0' }; "
            "      $m.Save(); "
            "    } "
            "  } "
            "} else { "
            "  if (Test-Path $wdLnk) { Remove-Item $wdLnk -Force -ErrorAction SilentlyContinue }; "
            "  $prismLnk = Join-Path $desktop 'Prism Launcher.lnk'; "
            "  if ((Test-Path $prismLnk) -and $env:GT_PRISM_EXE -and (Test-Path $env:GT_PRISM_EXE)) { "
            "    $m = $wsh.CreateShortcut($prismLnk); "
            "    if ($m.Arguments -like '*minecraft-gated-launch.py*') { "
            "      $m.TargetPath = $env:GT_PRISM_EXE; "
            "      $m.Arguments = ''; "
            "      $m.WorkingDirectory = Split-Path $env:GT_PRISM_EXE; "
            "      $m.IconLocation = $env:GT_PRISM_EXE + ',0'; "
            "      $m.Save(); "
            "    } "
            "  } "
            "}"
        )
        try:
            subprocess.run(
                [ps, "-NoProfile", "-NonInteractive", "-Command", ps_sync],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=6.0,
                check=False,
                creationflags=_WIN_NO_WINDOW,
            )
        except Exception:
            pass
        return

    home = Path.home()
    export_desktop = home / ".local" / "share" / "flatpak" / "exports" / "share" / "applications" / f"{PRISM_APP_ID}.desktop"
    local_desktop = home / ".local" / "share" / "applications" / f"{PRISM_APP_ID}.desktop"
    wrapper = ROOT / "bin" / "prism-gated-launch.sh"
    if not export_desktop.is_file() or not wrapper.is_file():
        return
    try:
        wrapper.chmod(0o755)
    except OSError:
        pass

    try:
        src_txt = export_desktop.read_text(encoding="utf-8", errors="ignore")
        local_desktop.parent.mkdir(parents=True, exist_ok=True)
        if gate_enabled:
            gated_txt = re.sub(
                r"^Exec=.*$",
                f'Exec="{wrapper}" %U',
                src_txt,
                flags=re.MULTILINE,
            )
            local_desktop.write_text(gated_txt, encoding="utf-8")
        else:
            if local_desktop.is_file():
                cur = local_desktop.read_text(encoding="utf-8", errors="ignore")
                if "prism-gated-launch.sh" in cur:
                    local_desktop.unlink()
    except OSError:
        pass


# ------------------------------------------------------------------ Persistent Record Helpers


def ensure_arcade(rec: dict[str, Any]) -> dict[str, Any]:
    arc = rec.get("arcade")
    if not isinstance(arc, dict):
        arc = copy.deepcopy(DEFAULT_ARCADE)
        rec["arcade"] = arc
    else:
        for k, v in DEFAULT_ARCADE.items():
            if k not in arc:
                arc[k] = copy.deepcopy(v)
    arc["minutes_per_point"] = max(5, min(60, int(arc.get("minutes_per_point") or 15)))
    arc["points_to_unlock"] = max(1, min(10, int(arc.get("points_to_unlock") or 2)))
    arc["reward_game_minutes"] = max(5, min(120, int(arc.get("reward_game_minutes") or 15)))
    arc["committed_work_seconds"] = max(0.0, float(arc.get("committed_work_seconds") or 0.0))
    arc["points_towards_unlock"] = max(0, int(arc.get("points_towards_unlock") or 0))
    arc["game_seconds_available"] = max(0.0, float(arc.get("game_seconds_available") or 0.0))
    return arc


def _active_record_and_arc(sandbox: bool = False) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if sandbox:
        return None, ensure_arcade({"arcade": _SANDBOX_ARCADE})
    rec = load_learner()
    return rec, ensure_arcade(rec)


def _persist(rec: dict[str, Any] | None, arc: dict[str, Any], sandbox: bool = False) -> None:
    if sandbox or rec is None:
        _SANDBOX_ARCADE.clear()
        _SANDBOX_ARCADE.update(copy.deepcopy(arc))
        return
    rec["arcade"] = arc
    save_learner(rec)


def _apply_thresholds(arc: dict[str, Any]) -> dict[str, Any]:
    """Converts accumulated `committed_work_seconds` -> Points -> Game Time."""
    sec_per_point = float(arc["minutes_per_point"] * 60)
    pts_needed = int(arc["points_to_unlock"])
    reward_min = int(arc["reward_game_minutes"])

    points_gained = 0
    while arc["committed_work_seconds"] + 1e-6 >= sec_per_point:
        arc["committed_work_seconds"] = max(0.0, arc["committed_work_seconds"] - sec_per_point)
        arc["points_towards_unlock"] += 1
        arc["lifetime_points_earned"] = int(arc.get("lifetime_points_earned") or 0) + 1
        points_gained += 1

    unlocked_minutes = 0
    while arc["points_towards_unlock"] >= pts_needed:
        arc["points_towards_unlock"] -= pts_needed
        arc["game_seconds_available"] += reward_min * 60.0
        unlocked_minutes += reward_min
        arc.setdefault("history", []).append(
            {
                "date": now_iso(),
                "kind": "earned",
                "minutes": reward_min,
                "writing_minutes": pts_needed * int(arc["minutes_per_point"]),
            }
        )
        arc["history"] = arc["history"][-40:]

    return {"points_gained": points_gained, "unlocked_minutes": unlocked_minutes}


def client_status(rec: dict[str, Any] | None = None, *, sandbox: bool = False, pending_seconds: float = 0.0) -> dict[str, Any]:
    fod_ok = is_fod_installed()
    mc_flavor = minecraft_flavor()
    mc_ok = bool(mc_flavor)
    plat = "windows" if _is_win() else ("mac" if sys.platform == "darwin" else "chromebook")
    installed = fod_ok or mc_ok
    if not installed:
        return {
            "installed": False,
            "platform": plat,
            "fod_installed": False,
            "minecraft_installed": False,
            "minecraft_flavor": "",
            "enabled": False,
            "visible": False,
        }

    if sandbox:
        arc = ensure_arcade({"arcade": _SANDBOX_ARCADE})
    else:
        if rec is None:
            rec = load_learner()
        arc = ensure_arcade(rec)

    enabled = bool(arc.get("enabled", True))
    mpp = int(arc["minutes_per_point"])
    ptu = int(arc["points_to_unlock"])
    rgm = int(arc["reward_game_minutes"])
    chunk_sec = mpp * 60
    committed = round(float(arc["committed_work_seconds"]), 1)
    avail_sec = round(float(arc["game_seconds_available"]), 1)
    pts = int(arc["points_towards_unlock"])
    total_target_min = mpp * ptu
    total_done_sec = pts * chunk_sec + committed

    mc_proc = minecraft_process_state() if mc_ok else {"launcher": False, "game_jvm": False, "any": False}
    mc_inst = list_minecraft_instances() if mc_flavor == "prism" else {"instances": [], "selected": "", "default_id": ""}
    mc_label = "Prism Launcher" if mc_flavor == "prism" else ("Minecraft Launcher" if mc_flavor == "official" else "Minecraft")

    return {
        "installed": True,
        "platform": plat,
        "fod_installed": fod_ok,
        "minecraft_installed": mc_ok,
        "minecraft_flavor": mc_flavor,
        "minecraft_label": mc_label,
        "enabled": enabled,
        "visible": enabled,
        "fod_port": FOD_PORT,
        "fod_dir": str(fod_install_dir()) if fod_ok else "",
        "minutes_per_point": mpp,
        "points_to_unlock": ptu,
        "total_work_minutes_needed": total_target_min,
        "reward_game_minutes": rgm,
        "lock_standalone": bool(arc.get("lock_standalone", False)),
        "gate_minecraft": bool(arc.get("gate_minecraft", True)),
        "minecraft_instance": str(arc.get("minecraft_instance") or ""),
        "minecraft_instances": mc_inst["instances"],
        "minecraft_default_instance": mc_inst["default_id"],
        "minecraft_running": mc_proc["any"],
        "minecraft_jvm_running": mc_proc["game_jvm"],
        "parent_setup_active": time.time() < _PARENT_SETUP_UNTIL,
        "points": pts,
        "committed_work_seconds": committed,
        "pending_effort_seconds": round(max(0.0, pending_seconds), 1),
        "chunk_target_seconds": chunk_sec,
        "total_progress_seconds": round(total_done_sec, 1),
        "total_target_seconds": total_target_min * 60,
        "game_seconds_available": avail_sec,
        "can_play": enabled and avail_sec >= 1.0,
        "lifetime_work_minutes": round(float(arc.get("lifetime_work_seconds") or 0.0) / 60.0, 1),
        "lifetime_points_earned": int(arc.get("lifetime_points_earned") or 0),
        "lifetime_sentences_verified": int(arc.get("lifetime_sentences_verified") or 0),
        "lifetime_game_minutes_played": round(float(arc.get("lifetime_game_seconds_played") or 0.0) / 60.0, 1),
        "history": list(reversed((arc.get("history") or [])[-15:])),
    }


def update_parent_settings(
    *,
    enabled: bool | None = None,
    minutes_per_point: int | None = None,
    points_to_unlock: int | None = None,
    reward_game_minutes: int | None = None,
    lock_standalone: bool | None = None,
    gate_minecraft: bool | None = None,
    minecraft_instance: str | None = None,
    grant_minutes: float | None = None,
    reset_bank: bool = False,
) -> dict[str, Any]:
    with _STATE_LOCK:
        rec = load_learner()
        arc = ensure_arcade(rec)
        if enabled is not None:
            arc["enabled"] = bool(enabled)
        if minutes_per_point is not None:
            arc["minutes_per_point"] = max(5, min(60, int(minutes_per_point)))
        if points_to_unlock is not None:
            arc["points_to_unlock"] = max(1, min(10, int(points_to_unlock)))
        if reward_game_minutes is not None:
            arc["reward_game_minutes"] = max(5, min(120, int(reward_game_minutes)))
        if lock_standalone is not None:
            arc["lock_standalone"] = bool(lock_standalone)
        if gate_minecraft is not None:
            arc["gate_minecraft"] = bool(gate_minecraft)
            sync_minecraft_desktop_gate(arc["gate_minecraft"])
        if minecraft_instance is not None:
            arc["minecraft_instance"] = minecraft_instance.strip()
        if grant_minutes and grant_minutes > 0:
            add_m = min(120.0, float(grant_minutes))
            arc["game_seconds_available"] += add_m * 60.0
            arc.setdefault("history", []).append({"date": now_iso(), "kind": "parent_bonus", "minutes": round(add_m, 1)})
        if reset_bank:
            arc["game_seconds_available"] = 0.0
            arc.setdefault("history", []).append({"date": now_iso(), "kind": "parent_reset", "minutes": 0})
            if arc.get("gate_minecraft", True) and is_minecraft_installed() and time.time() >= _PARENT_SETUP_UNTIL:
                stop_minecraft()
        _apply_thresholds(arc)
        save_learner(rec)
        return client_status(rec)


def consume_game_seconds(elapsed_seconds: float, *, sandbox: bool = False, source: str = "fod") -> dict[str, Any]:
    """Deducts active gameplay time (clamped per heartbeat) and returns updated status."""
    use_s = max(0.0, min(12.0, float(elapsed_seconds)))
    with _STATE_LOCK:
        rec, arc = _active_record_and_arc(sandbox=sandbox)
        before = float(arc["game_seconds_available"])
        actual = min(before, use_s)
        arc["game_seconds_available"] = max(0.0, before - actual)
        arc["lifetime_game_seconds_played"] = float(arc.get("lifetime_game_seconds_played") or 0.0) + actual
        if before > 0 and arc["game_seconds_available"] <= 0:
            arc.setdefault("history", []).append({"date": now_iso(), "kind": f"finished_{source}", "minutes": 0})
            arc["history"] = arc["history"][-40:]
        _persist(rec, arc, sandbox=sandbox)
        st = client_status(rec, sandbox=sandbox)
        st["expired"] = st["game_seconds_available"] < 1.0
        return st


# ------------------------------------------------------------------ Background Minecraft Watchdog


def _minecraft_watchdog_loop() -> None:
    global _MC_WARNED_ONE_MIN, _PARENT_SETUP_UNTIL
    last_tick = time.time()
    was_running = False

    while True:
        time.sleep(3.0)
        now = time.time()
        dt = min(6.0, max(0.0, now - last_tick))
        last_tick = now

        if not is_minecraft_installed():
            continue

        proc = minecraft_process_state()
        if not proc["any"]:
            if was_running and now < _PARENT_SETUP_UNTIL:
                # Parent closed Prism Launcher after setup — re-arm normal gating immediately!
                _PARENT_SETUP_UNTIL = 0.0
            was_running = False
            _MC_WARNED_ONE_MIN = False
            continue

        was_running = True
        if now < _PARENT_SETUP_UNTIL:
            continue

        with _STATE_LOCK:
            rec = load_learner()
            arc = ensure_arcade(rec)
            gate_on = bool(arc.get("gate_minecraft", True))
            enabled = bool(arc.get("enabled", True))
            avail = float(arc.get("game_seconds_available") or 0.0)

            if not enabled:
                if gate_on:
                    stop_minecraft()
                continue

            if avail <= 0.5:
                if gate_on:
                    _desktop_notify(
                        "Minecraft Time Finished!",
                        "Open Gemini Tutor and do some solid writing to earn your next Minecraft session.",
                        urgent=True,
                    )
                    stop_minecraft()
                continue

            # Give up to 30s of asset/launcher boot grace before the Java game window opens
            in_boot_grace = (not proc["game_jvm"]) and (now - _MC_LAUNCHED_AT < 30.0)
            if not in_boot_grace:
                actual = min(avail, dt)
                avail = max(0.0, avail - actual)
                arc["game_seconds_available"] = avail
                arc["lifetime_game_seconds_played"] = float(arc.get("lifetime_game_seconds_played") or 0.0) + actual

                if 0.5 < avail <= 60.0 and not _MC_WARNED_ONE_MIN:
                    _MC_WARNED_ONE_MIN = True
                    _desktop_notify(
                        "⏱ 1 Minute of Minecraft Left!",
                        "Press Esc → Save & Quit to Title now so your world is saved!",
                        urgent=True,
                    )

                if avail <= 0.5:
                    arc["game_seconds_available"] = 0.0
                    arc.setdefault("history", []).append({"date": now_iso(), "kind": "finished_minecraft", "minutes": 0})
                    arc["history"] = arc["history"][-40:]
                    save_learner(rec)
                    _desktop_notify(
                        "⛏️ Minecraft Time Is Up!",
                        "Great playing! Head back to Gemini Tutor to earn more points.",
                        urgent=True,
                    )
                    stop_minecraft()
                    continue

                save_learner(rec)


def start_background_watchdog() -> None:
    """Starts the singleton daemon watchdog for Chromebook Minecraft time-enforcement."""
    global _WATCHDOG_STARTED
    if _WATCHDOG_STARTED:
        return
    _WATCHDOG_STARTED = True
    try:
        if is_minecraft_installed():
            rec = load_learner()
            arc = ensure_arcade(rec)
            sync_minecraft_desktop_gate(bool(arc.get("gate_minecraft", True)))
    except Exception:
        pass
    t = threading.Thread(target=_minecraft_watchdog_loop, name="minecraft-watchdog", daemon=True)
    t.start()


# ------------------------------------------------------------------ Local Fists of Doom Server Supervisor


def _is_fod_server_up() -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{FOD_PORT}/api/version", timeout=1.0) as r:
            if r.status != 200:
                return False
            d = json.loads(r.read().decode("utf-8"))
            return d.get("app") == "fists-of-doom"
    except Exception:
        return False


def ensure_fod_running() -> bool:
    """Ensures the local Fists of Doom server is listening on FOD_PORT without opening a separate window."""
    if not is_fod_installed():
        return False
    if _is_fod_server_up():
        return True

    d = fod_install_dir()
    if os.name == "nt":
        candidates = [
            d / ".venv" / "Scripts" / "pythonw.exe",
            d / ".venv" / "Scripts" / "python.exe",
            Path(sys.executable),
        ]
    else:
        candidates = [
            d / ".venv" / "bin" / "python",
            Path(sys.executable),
        ]
    py = next((str(p) for p in candidates if p.exists()), sys.executable)
    env = dict(os.environ)
    env["PORT"] = str(FOD_PORT)

    launch_script = d / "launch.py"
    cmd = [py, str(launch_script), "--supervise"] if launch_script.is_file() else [py, str(d / "server_multiplayer.py")]

    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(cmd, cwd=str(d), env=env, creationflags=flags)
    else:
        subprocess.Popen(
            cmd,
            cwd=str(d),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    for _ in range(40):
        if _is_fod_server_up():
            return True
        time.sleep(0.25)
    return _is_fod_server_up()


# ------------------------------------------------------------------ Per-Session Quality Gate


def _norm_sentence(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", "", (text or "").lower())).strip()


class SessionArcadeTracker:
    """Tracks bounded, quality-verified active writing time within one TutorSession."""

    def __init__(self, *, sandbox: bool = False):
        self.sandbox = sandbox
        self.prompt_ts = time.time()
        self.pending_effort_seconds = 0.0
        self.oral_buffer_seconds = 0.0
        self.seen_sentences: set[str] = set()
        self.last_studied_count = 0
        self.last_intake_score = 0

    def reset_prompt_clock(self) -> None:
        self.prompt_ts = time.time()

    def _consume_turn_window(self, cap: float = MAX_TURN_ACTIVE_SECONDS) -> float:
        now = time.time()
        dt = max(0.0, now - self.prompt_ts)
        self.prompt_ts = now
        if dt < 1.2:
            return 1.2
        return min(dt, cap)

    def _reward_game_names(self) -> str:
        games = []
        if is_fod_installed():
            games.append("Fists of Doom")
        if is_minecraft_installed():
            games.append("Minecraft")
        return " or ".join(games) if games else "video game"

    def record_turn(
        self,
        *,
        how: str,
        raw_text: str,
        plan: dict[str, Any],
        ctrl: Any,
    ) -> dict[str, Any] | None:
        """Evaluates one student turn. Commits active seconds ONLY on verified high-quality work."""
        if not is_any_game_installed():
            self.reset_prompt_clock()
            return None

        with _STATE_LOCK:
            rec, arc = _active_record_and_arc(sandbox=self.sandbox)
            if not arc.get("enabled", True):
                self.reset_prompt_clock()
                return None

        turn_sec = self._consume_turn_window()
        kind = str(plan.get("kind") or "")
        words = re.findall(r"[A-Za-z']+", raw_text or "")
        word_count = len(words)

        # 1. Disengagement / pushback / off-task / avoidance -> 0 credit!
        if kind in ("DISENGAGED", "PUSHBACK", "OFF_TASK", "META_CHAT") or getattr(ctrl, "avoidance_streak", 0) >= 2:
            if getattr(ctrl, "avoidance_streak", 0) >= 2:
                self.pending_effort_seconds = max(0.0, self.pending_effort_seconds * 0.5)
            return None

        # 2. Check if a Cover-Copy-Compare spelling word retrieval just succeeded
        studied_now = len(getattr(ctrl, "studied_words_today", []) or [])
        word_retrieved = studied_now > self.last_studied_count
        self.last_studied_count = studied_now

        # 3. Check if a verified complete sentence / Story Spine beat / Codex inference locked in!
        verified_text = ""
        if kind == "COMPLETE_SENTENCE":
            verified_text = str(plan.get("full_paragraph") or plan.get("repaired_text") or raw_text or "").strip()
        elif plan.get("spine_draw"):
            verified_text = str((plan["spine_draw"] or {}).get("text") or raw_text or "").strip()
        elif plan.get("codex_sketch"):
            verified_text = str(raw_text or "").strip()

        is_verified_sentence = False
        if verified_text:
            norm = _norm_sentence(verified_text)
            v_words = re.findall(r"[A-Za-z']+", verified_text)
            if len(v_words) >= 3 and norm and norm not in self.seen_sentences:
                self.seen_sentences.add(norm)
                is_verified_sentence = True

        if is_verified_sentence or word_retrieved:
            commit_sec = turn_sec + self.pending_effort_seconds + self.oral_buffer_seconds
            self.pending_effort_seconds = 0.0
            self.oral_buffer_seconds = 0.0
            return self._commit_seconds(commit_sec, verified_sentence=is_verified_sentence)

        # 4. Productive oral story logic construction (`ORAL_STORY_INTAKE`) — buffered ONLY until Panel 1 is written!
        proj = getattr(ctrl, "project", None) or {}
        if proj.get("stage") in ("oral_intake", "verbal_jam"):
            intake = proj.get("oral_intake") or {}
            pillars = [bool(intake.get(k)) for k in ("who_problem", "why_worse", "big_obstacle", "earned_ending")]
            score_now = sum(1 for x in pillars if x)
            if score_now > self.last_intake_score and word_count >= 4:
                self.oral_buffer_seconds = min(MAX_ORAL_BUFFER_SECONDS, self.oral_buffer_seconds + min(turn_sec, 45.0))
            self.last_intake_score = score_now
            return None

        # 5. Genuine drafting / spelling-fix / grammar-revision / handwriting effort toward a real sentence:
        is_productive_revision = (
            (how in ("typed", "handwritten") and word_count >= 3)
            or (how == "tap" and getattr(ctrl, "pending_sentence", ""))
            or (how == "voice_clip" and getattr(ctrl, "pending_sentence", ""))
        )
        if is_productive_revision:
            self.pending_effort_seconds = min(MAX_PENDING_EFFORT_SECONDS, self.pending_effort_seconds + turn_sec)
            return {
                "milestone": "progress",
                "arcade": client_status(sandbox=self.sandbox, pending_seconds=self.pending_effort_seconds),
            }

        return None

    def record_verified_lettering(self, text: str) -> dict[str, Any] | None:
        """Credits verified multi-word comic dialogue/caption lettering (>= 4 words, non-duplicate)."""
        if not is_any_game_installed():
            return None
        with _STATE_LOCK:
            _, arc = _active_record_and_arc(sandbox=self.sandbox)
            if not arc.get("enabled", True):
                return None
        words = re.findall(r"[A-Za-z']+", text or "")
        norm = _norm_sentence(text)
        if len(words) < 4 or not norm or norm in self.seen_sentences:
            return None
        self.seen_sentences.add(norm)
        turn_sec = self._consume_turn_window(cap=35.0)
        return self._commit_seconds(turn_sec, verified_sentence=True)

    def record_art_approved(self) -> None:
        self.reset_prompt_clock()

    def _commit_seconds(self, seconds: float, *, verified_sentence: bool) -> dict[str, Any]:
        game_label = self._reward_game_names()
        with _STATE_LOCK:
            rec, arc = _active_record_and_arc(sandbox=self.sandbox)
            add_s = max(0.0, float(seconds))
            arc["committed_work_seconds"] = float(arc.get("committed_work_seconds") or 0.0) + add_s
            arc["lifetime_work_seconds"] = float(arc.get("lifetime_work_seconds") or 0.0) + add_s
            if verified_sentence:
                arc["lifetime_sentences_verified"] = int(arc.get("lifetime_sentences_verified") or 0) + 1

            res = _apply_thresholds(arc)
            _persist(rec, arc, sandbox=self.sandbox)
            status = client_status(rec, sandbox=self.sandbox, pending_seconds=self.pending_effort_seconds)

        if res["unlocked_minutes"] > 0:
            mins = res["unlocked_minutes"]
            return {
                "milestone": "unlocked",
                "unlocked_minutes": mins,
                "points_gained": res["points_gained"],
                "message": f"🎮 VIDEO GAME TIME EARNED! +{mins} min of {game_label} unlocked!",
                "tutor_note": (
                    f" [GAME REWARD UNLOCKED: He just completed {status['total_work_minutes_needed']} minutes of solid, "
                    f"high-quality writing and earned {mins} minutes of {game_label} time! Briefly congratulate him in "
                    f"1 short clause and let him know he can click Play {game_label} at the top whenever he's ready or keep writing.]"
                ),
                "arcade": status,
            }
        if res["points_gained"] > 0:
            rem_pts = max(1, status["points_to_unlock"] - status["points"])
            return {
                "milestone": "point",
                "unlocked_minutes": 0,
                "points_gained": res["points_gained"],
                "message": (
                    f"⭐ +{res['points_gained']} Video Game Point! "
                    f"({status['points']}/{status['points_to_unlock']} pts — {rem_pts * status['minutes_per_point']}m more solid writing unlocks {game_label}!)"
                ),
                "tutor_note": "",
                "arcade": status,
            }
        return {
            "milestone": "progress",
            "unlocked_minutes": 0,
            "points_gained": 0,
            "message": "",
            "tutor_note": "",
            "arcade": status,
        }
