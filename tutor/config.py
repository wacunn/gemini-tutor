"""Paths, models, API-key handling, and cross-platform Gemini client factory."""

from __future__ import annotations

import os
import ssl
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SESSIONS = DATA / "sessions"
TEST_SESSIONS = DATA / "test_sessions"
ACTIVITIES = DATA / "activities"
PIECES = DATA / "pieces"
PROJECTS = DATA / "projects"
ENV_FILE = ROOT / ".env"

# Real-time voice tutor (requires v1alpha WebSocket endpoint across google-genai 1.x and 3.x)
LIVE_MODEL = os.environ.get("TUTOR_LIVE_MODEL", "gemini-3.8-live")
LIVE_FALLBACK_MODELS = (
    LIVE_MODEL,
    "gemini-2.5-flash-native-audio-preview-12-2025",
    "gemini-2.0-flash-live-001",
)
# Child modeling, critic, engagement tracker, and mechanic invention
HYDROGEN_MODEL = os.environ.get("TUTOR_HYDROGEN_MODEL", "gemini-4-hydrogen")
# Builds new activities/games on the spot
BUILDER_MODEL = os.environ.get("TUTOR_BUILDER_MODEL", "gemini-3.8-flash")
# Deep post-session specialist review updating the learner model
REVIEW_MODEL = os.environ.get("TUTOR_REVIEW_MODEL", "gemini-4-carbon")
# Sub-second synchronous clause/spelling check & 2-kernel generator on the hot turn path
FAST_MODEL = os.environ.get("TUTOR_FAST_MODEL", "gemini-3.5-flash")
FALLBACK_MODEL = os.environ.get("TUTOR_FALLBACK_MODEL", "gemini-3.8-flash")
# Small, fast model for light jobs (next story question + starters, background learning updates)
LITE_MODEL = os.environ.get("TUTOR_LITE_MODEL", "gemini-3.1-flash-lite")
# Adaptive coach decision model (judgment call each turn)
COACH_MODEL = os.environ.get("TUTOR_COACH_MODEL", FAST_MODEL)

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


def _ensure_ssl_certs() -> None:
    """Uses native OS certificate store (macOS Keychain / Windows Cert Store via truststore)
    with fallback to certifi so standalone Python in .app / .venv never fails SSL."""
    try:
        import truststore

        truststore.inject_into_ssl()
    except Exception:
        pass
    if os.environ.get("SSL_CERT_FILE") and Path(os.environ["SSL_CERT_FILE"]).exists():
        return
    vp = ssl.get_default_verify_paths()
    if vp.cafile and Path(vp.cafile).exists():
        return
    try:
        import certifi

        ca = certifi.where()
        if ca and Path(ca).exists():
            os.environ["SSL_CERT_FILE"] = ca
    except Exception:
        pass


_ensure_ssl_certs()


def ensure_dirs() -> None:
    for d in (DATA, SESSIONS, TEST_SESSIONS, ACTIVITIES, PIECES, PROJECTS):
        d.mkdir(parents=True, exist_ok=True)


def _read_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
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


def genai_client(*, live: bool = False) -> Any:
    """Creates a google-genai Client. Uses api_version='v1alpha' for Live Bidi WebSockets
    so google-genai 1.x, 2.x, and 3.x all connect cleanly without HTTP 404."""
    from google import genai

    _ensure_ssl_certs()
    key = api_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set")
    if live:
        return genai.Client(api_key=key, http_options={"api_version": "v1alpha"})
    return genai.Client(api_key=key)


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
