"""In-app updates: check GitHub for a newer version, download it, keep the kid's data, restart.

Works across macOS, Windows PC, and Chromebook (Linux) with zero git required.
The launcher (start.sh / start.cmd) restarts the server automatically when it exits with code 42.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

from .config import ROOT

REPO = os.environ.get("TUTOR_REPO", "wacunn/gemini-tutor")
BRANCH = os.environ.get("TUTOR_BRANCH", "main")
KEEP = {"data", ".env", ".venv", "logs", ".git"}
RESTART_CODE = 42


def local_version() -> str:
    try:
        return (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"


def _vtuple(v: str) -> tuple:
    out = []
    for p in v.strip().split("."):
        try:
            out.append(int(p))
        except ValueError:
            out.append(0)
    return tuple(out)


def _get(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "gemini-tutor-updater"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def check() -> dict:
    current = local_version()
    try:
        latest = _get(f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/VERSION?t={int(time.time())}").decode("utf-8").strip()
    except Exception as e:
        return {"current": current, "latest": None, "available": False, "error": f"Couldn't reach GitHub ({e.__class__.__name__})."}
    notes = ""
    try:
        notes = _get(f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/CHANGELOG.md?t={int(time.time())}").decode("utf-8")[:1500]
    except Exception:
        pass
    return {"current": current, "latest": latest, "available": _vtuple(latest) > _vtuple(current), "notes": notes}


def _uv() -> str | None:
    exe = "uv.exe" if os.name == "nt" else "uv"
    candidates = [
        shutil.which("uv"),
        str(Path.home() / ".local" / "bin" / exe),
        str(Path.home() / ".cargo" / "bin" / exe),
    ]
    if os.name == "nt":
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            candidates.append(str(Path(local_app) / "uv" / exe))
    for c in candidates:
        if c and Path(c).exists():
            return c
    return None


def _venv_python() -> Path | None:
    if os.name == "nt":
        p = ROOT / ".venv" / "Scripts" / "python.exe"
    else:
        p = ROOT / ".venv" / "bin" / "python"
    return p if p.exists() else None


def apply() -> dict:
    data = _get(f"https://codeload.github.com/{REPO}/tar.gz/refs/heads/{BRANCH}", timeout=120)
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
            tf.extractall(tmp)
        roots = [p for p in Path(tmp).iterdir() if p.is_dir()]
        if not roots:
            raise RuntimeError("download was empty")
        src = roots[0]
        if not (src / "server.py").exists():
            raise RuntimeError("download doesn't look like Gemini Tutor")
        for item in src.iterdir():
            if item.name in KEEP:
                continue
            dest = ROOT / item.name
            if dest.is_dir() and not dest.is_symlink():
                shutil.rmtree(dest)
            elif dest.exists():
                dest.unlink()
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)
    if os.name != "nt":
        for script in ("start.sh", "install.sh", "setup_minecraft_chromebook.sh", "bin/prism-gated-launch.sh"):
            p = ROOT / script
            if p.exists():
                try:
                    p.chmod(0o755)
                except OSError:
                    pass
    uv = _uv()
    venv_py = _venv_python()
    if uv and venv_py:
        subprocess.run([uv, "pip", "install", "--python", str(venv_py), "-q", "-r", str(ROOT / "requirements.txt")], check=False)
    elif venv_py:
        subprocess.run([str(venv_py), "-m", "pip", "install", "-q", "-r", str(ROOT / "requirements.txt")], check=False)
    return {"ok": True, "version": local_version()}


def restart_soon(delay: float = 1.0) -> None:
    def _go():
        time.sleep(delay)
        os._exit(RESTART_CODE)

    threading.Thread(target=_go, daemon=True).start()


def quit_soon(delay: float = 0.5) -> None:
    def _go():
        time.sleep(delay)
        os._exit(0)

    threading.Thread(target=_go, daemon=True).start()
