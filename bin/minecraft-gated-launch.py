#!/usr/bin/env python3
"""Cross-platform Desktop Shortcut Gating Wrapper for Minecraft (Bedrock & Java).

Intercepts direct Desktop / Start Menu launches:
- If earned game time is available in Gemini Tutor, or Parent Override is active, or parent disabled
  gating for that edition (or zero Prism instances exist yet during initial setup), ensures the
  Gemini Tutor background watchdog is running silently and launches the requested Minecraft edition.
- If earned game time is `0:00` and no Parent Override is active, shows a native OS notification
  and opens Gemini Tutor instead.
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


def _parse_edition(argv: list[str]) -> str:
    for i, a in enumerate(argv):
        if a == "--edition" and i + 1 < len(argv):
            return argv[i + 1].strip().lower()
        if a.startswith("--edition="):
            return a.split("=", 1)[1].strip().lower()
    return "auto"


def main() -> None:
    edition = _parse_edition(sys.argv[1:])

    if "--parent-setup" in sys.argv:
        _ensure_tutor_server(open_ui=False)
        if not _post_json("/api/arcade/minecraft-parent-setup", {"edition": edition}):
            arcade.launch_minecraft(edition=edition, parent_setup=True)
        return

    java_flav = arcade.minecraft_java_flavor()
    first_time_setup = False
    if edition != "bedrock" and java_flav == "prism":
        inst = arcade.list_minecraft_instances()
        if len(inst["instances"]) == 0:
            first_time_setup = True

    rec = load_learner()
    arc = arcade.ensure_arcade(rec)
    enabled = bool(arc.get("enabled", True))
    is_bed = edition == "bedrock" or (edition == "auto" and not java_flav)
    gate_on = bool(arc.get("gate_bedrock", True)) if is_bed else bool(arc.get("gate_minecraft", True))
    avail = float(arc.get("game_seconds_available") or 0.0)
    override_on = arcade.is_parent_override_active(arc)

    if not first_time_setup and enabled and gate_on and not override_on and avail < 1.0:
        arcade._desktop_notify(
            "⛏️ Earn Minecraft Time in Gemini Tutor!",
            "You have 0:00 of game time banked. Opening Gemini Tutor so you can earn 2 min of gaming per 1 min of solid writing!",
            urgent=False,
        )
        _ensure_tutor_server(open_ui=True)
        return

    _ensure_tutor_server(open_ui=False)
    req_game = "minecraft_bedrock" if is_bed else ("minecraft_java" if edition == "java" else "minecraft")
    if not first_time_setup and _post_json("/api/arcade/start", {"game": req_game, "sandbox": 0}):
        return
    arcade.launch_minecraft(
        edition="bedrock" if is_bed else edition,
        instance_override=str(arc.get("minecraft_instance") or "") or None,
        parent_setup=first_time_setup,
    )


if __name__ == "__main__":
    main()
