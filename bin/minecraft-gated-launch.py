#!/usr/bin/env python3
"""Cross-platform Desktop Shortcut Gating Wrapper for Minecraft (Windows `pythonw.exe`, macOS, Linux).

Intercepts direct Desktop / Start Menu launches:
- If earned game time is available in Gemini Tutor (or parent disabled gating, or zero Prism instances
  exist yet during initial setup), ensures the Gemini Tutor background watchdog is running silently and
  launches Minecraft (`prismlauncher.exe` or Official Minecraft Launcher).
- If earned game time is `0:00`, shows a native Windows 11 Toast notification and opens Gemini Tutor instead.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tutor import arcade  # noqa: E402
from tutor.record import load_learner  # noqa: E402

PORT = int(os.environ.get("PORT", "8787"))
BASE_URL = f"http://127.0.0.1:{PORT}"
_WIN_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if os.name == "nt" else 0


def _ensure_tutor_server(open_ui: bool) -> None:
    py = Path(sys.executable)
    if os.name == "nt":
        pyw = py.with_name("pythonw.exe")
        if pyw.is_file():
            py = pyw
    args = [str(py), str(ROOT / "launch.py")]
    if not open_ui:
        args.append("--no-open")
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | _WIN_NO_WINDOW
        subprocess.Popen(args, cwd=str(ROOT), creationflags=flags)
    else:
        subprocess.Popen(
            args,
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )


def _post_json(path: str, payload: dict) -> bool:
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{BASE_URL}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=2.5) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


def main() -> None:
    if "--parent-setup" in sys.argv:
        _ensure_tutor_server(open_ui=False)
        if not _post_json("/api/arcade/minecraft-parent-setup", {}):
            arcade.launch_minecraft(parent_setup=True)
        return

    flavor = arcade.minecraft_flavor()
    first_time_setup = False
    if flavor == "prism":
        inst = arcade.list_minecraft_instances()
        if len(inst["instances"]) == 0:
            first_time_setup = True

    rec = load_learner()
    arc = arcade.ensure_arcade(rec)
    enabled = bool(arc.get("enabled", True))
    gate_on = bool(arc.get("gate_minecraft", True))
    avail = float(arc.get("game_seconds_available") or 0.0)

    if not first_time_setup and enabled and gate_on and avail < 1.0:
        arcade._desktop_notify(
            "⛏️ Earn Minecraft Time in Gemini Tutor!",
            "You have 0:00 of game time banked. Opening Gemini Tutor so you can earn points!",
            urgent=False,
        )
        _ensure_tutor_server(open_ui=True)
        return

    _ensure_tutor_server(open_ui=False)
    if not first_time_setup and _post_json("/api/arcade/start", {"game": "minecraft", "sandbox": 0}):
        return
    arcade.launch_minecraft(
        instance_override=str(arc.get("minecraft_instance") or "") or None,
        parent_setup=first_time_setup,
    )


if __name__ == "__main__":
    main()
