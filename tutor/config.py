"""Paths, models, and API-key handling."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SESSIONS = DATA / "sessions"
TEST_SESSIONS = DATA / "test_sessions"
ACTIVITIES = DATA / "activities"
PIECES = DATA / "pieces"
ENV_FILE = ROOT / ".env"

# Real-time voice tutor (verified available via models.list with bidiGenerateContent)
LIVE_MODEL = os.environ.get("TUTOR_LIVE_MODEL", "gemini-3.8-live")
# Child modeling, critic, engagement tracker, and mechanic invention
HYDROGEN_MODEL = os.environ.get("TUTOR_HYDROGEN_MODEL", "gemini-4-hydrogen")
# Builds new activities/games on the spot
BUILDER_MODEL = os.environ.get("TUTOR_BUILDER_MODEL", "gemini-3.8-flash")
# Deep post-session specialist review updating the learner model
REVIEW_MODEL = os.environ.get("TUTOR_REVIEW_MODEL", "gemini-4-carbon")
# Sub-second synchronous clause/spelling check & 2-kernel generator on the hot turn path
FAST_MODEL = os.environ.get("TUTOR_FAST_MODEL", "gemini-3.5-flash")
FALLBACK_MODEL = "gemini-3.5-flash"

VOICES = [
    ("Umbriel", "easy-going"),
    ("Achird", "friendly"),
    ("Zubenelgenubi", "casual"),
    ("Sulafat", "warm"),
    ("Charon", "informative"),
    ("Iapetus", "clear"),
    ("Algenib", "gravelly"),
    ("Puck", "upbeat"),
]


def ensure_dirs() -> None:
    for d in (DATA, SESSIONS, TEST_SESSIONS, ACTIVITIES, PIECES):
        d.mkdir(parents=True, exist_ok=True)


def _read_env_file(path: Path) -> dict:
    out = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        if v:
            out[k.strip()] = v
    return out


def load_env() -> None:
    for path in (Path.home() / ".env", ENV_FILE):
        for k, v in _read_env_file(path).items():
            os.environ.setdefault(k, v)


def api_key() -> str | None:
    load_env()
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def save_api_key(value: str) -> None:
    value = value.strip()
    if not value:
        raise ValueError("empty key")
    existing = _read_env_file(ENV_FILE)
    existing["GEMINI_API_KEY"] = value
    ENV_FILE.write_text("".join(f"{k}={v}\n" for k, v in existing.items()), encoding="utf-8")
    try:
        os.chmod(ENV_FILE, 0o600)
    except OSError:
        pass
    os.environ["GEMINI_API_KEY"] = value
