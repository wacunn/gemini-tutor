"""The learner record: who the child is, what we've learned, and what we've tried.

Everything here is plain JSON on disk under data/ (gitignored).
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from .config import ACTIVITIES, DATA, PIECES, SESSIONS, TEST_SESSIONS, ensure_dirs

LEARNER_FILE = DATA / "learner.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"


DEFAULT_LEARNER: dict[str, Any] = {
    "name": None,
    "grade": 3,
    "parent_title": "Dad",
    "voice": "Umbriel",
    "parent_notes": [],
    # Skill targets live in curriculum/targets.md (sourced from the Ontario Language curriculum, 2023).
    # Filled in by the post-session review. Starts empty on purpose: we haven't met him yet.
    "model": {
        "summary": "",
        "interests": [],
        "audience": "",
        "writing": "",
        "spelling": {"stage": "", "patterns": [], "words_learned": []},
        "typing": "",
        "what_engages": [],
        "what_shuts_down": [],
        "hypotheses": [],
        "ideas_to_try": [],
        "plan_next_session": "",
        "notes_for_parent": "",
    },
    "sessions": [],
}


def load_learner() -> dict[str, Any]:
    ensure_dirs()
    if not LEARNER_FILE.exists():
        return json.loads(json.dumps(DEFAULT_LEARNER))
    data = json.loads(LEARNER_FILE.read_text(encoding="utf-8"))
    for k, v in DEFAULT_LEARNER.items():
        data.setdefault(k, json.loads(json.dumps(v)))
    return data


def save_learner(rec: dict[str, Any]) -> None:
    ensure_dirs()
    tmp = LEARNER_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    tmp.replace(LEARNER_FILE)


def is_set_up() -> bool:
    return bool(load_learner().get("name"))


# ---------- sessions ----------

class SessionLog:
    """Append-only event log for one session (crash-safe JSONL)."""

    def __init__(self, session_id: str, test_mode: bool = False):
        ensure_dirs()
        self.id = session_id
        base = TEST_SESSIONS if test_mode else SESSIONS
        self.path = base / f"{session_id}.jsonl"
        self.started = time.time()

    def add(self, event_kind: str, **data: Any) -> None:
        evt = {"t": round(time.time() - self.started, 2), "kind": event_kind, **data}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(evt) + "\n")


def read_session(session_id: str, test_mode: bool = False) -> list[dict[str, Any]]:
    path = (TEST_SESSIONS if test_mode else SESSIONS) / f"{session_id}.jsonl"
    if not path.exists() and not test_mode:
        alt = TEST_SESSIONS / f"{session_id}.jsonl"
        if alt.exists():
            path = alt
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def read_review(session_id: str) -> dict[str, Any] | None:
    path = SESSIONS / f"{session_id}.review.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


# ---------- activities built on the spot ----------

SANDBOX_ACTIVITIES: dict[str, dict[str, Any]] = {}
SANDBOX_PIECES: dict[str, dict[str, Any]] = {}


def save_activity(activity: dict[str, Any], sandbox: bool = False) -> None:
    aid = activity["id"]
    if sandbox or aid.startswith("sbox_"):
        prev = SANDBOX_ACTIVITIES.get(aid, {})
        SANDBOX_ACTIVITIES[aid] = {**prev, **activity, "sandbox": True}
        return
    ensure_dirs()
    act_copy = dict(activity)
    html = act_copy.pop("html", None)
    if html is not None:
        (ACTIVITIES / f"{aid}.html").write_text(html, encoding="utf-8")
    meta_path = ACTIVITIES / f"{aid}.json"
    meta = {}
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.update(act_copy)
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def load_activity(aid: str) -> dict[str, Any] | None:
    if aid in SANDBOX_ACTIVITIES:
        return dict(SANDBOX_ACTIVITIES[aid])
    meta_path = ACTIVITIES / f"{aid}.json"
    html_path = ACTIVITIES / f"{aid}.html"
    if not meta_path.exists() or not html_path.exists():
        return None
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["html"] = html_path.read_text(encoding="utf-8")
    return meta


def delete_activity(aid: str, sandbox: bool = False) -> bool:
    if aid in SANDBOX_ACTIVITIES:
        del SANDBOX_ACTIVITIES[aid]
        return True
    if sandbox:
        return False
    removed = False
    for ext in (".json", ".html"):
        p = ACTIVITIES / f"{aid}{ext}"
        if p.exists():
            p.unlink()
            removed = True
    return removed


def list_activities(sandbox: bool = False) -> list[dict[str, Any]]:
    if sandbox:
        return [{k: v for k, v in d.items() if k != "html"} for d in reversed(list(SANDBOX_ACTIVITIES.values()))]
    ensure_dirs()
    out = []
    for p in sorted(ACTIVITIES.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out


# ---------- finished pieces of writing ----------

def save_piece(piece: dict[str, Any], sandbox: bool = False) -> None:
    pid = piece["id"]
    if sandbox or pid.startswith("sbox_"):
        SANDBOX_PIECES[pid] = {**piece, "sandbox": True}
        return
    ensure_dirs()
    (PIECES / f"{pid}.json").write_text(json.dumps(piece, indent=2), encoding="utf-8")


def load_piece(pid: str) -> dict[str, Any] | None:
    if pid in SANDBOX_PIECES:
        return dict(SANDBOX_PIECES[pid])
    p = PIECES / f"{pid}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def delete_piece(pid: str, sandbox: bool = False) -> bool:
    if pid in SANDBOX_PIECES:
        del SANDBOX_PIECES[pid]
        return True
    if sandbox:
        return False
    p = PIECES / f"{pid}.json"
    if p.exists():
        p.unlink()
        return True
    return False


def list_pieces(sandbox: bool = False) -> list[dict[str, Any]]:
    if sandbox:
        return list(reversed(list(SANDBOX_PIECES.values())))
    ensure_dirs()
    out = []
    for p in sorted(PIECES.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out
