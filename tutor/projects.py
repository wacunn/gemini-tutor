"""Persistent Multi-Session / Multi-Week Creative Projects & Multi-Scale Catalog.

Supports:
- Epic Graphic Novels (up to 100+ panels across chapters, starting with a causal
  Beginning -> Middle ('But/When') -> End ('So/Therefore') Story Spine, character continuity,
  speech bubbles + captions, intermediate Issue PDFs, and full Graphic Novel PDF export).
- Epic Illustrated Codex / Encyclopedia (multi-entry informational paragraphs -> PDF book).
- Medium Persuasive Pitch Book (4-page illustrated argument -> PDF).
- Quick Sprints (10-minute contraption compiler, 3-panel micro-strip, or live HTML5 mini-game).
"""

from __future__ import annotations

import json
import re
from typing import Any

from .config import PROJECTS, ensure_dirs
from .record import new_id, now_iso

PROJECT_MENU: list[dict[str, str]] = [
    {
        "key": "epic_graphic_novel",
        "label": "Full Comic Book (Multi-Week · PDF Book)",
        "scale": "epic",
        "time_est": "Multi-session (save anytime · up to 100 panels)",
        "summary": "Map your Beginning → Middle → End story arc first, then zoom in chapter by chapter with consistent characters, dialogue bubbles, and printable PDF issues.",
    },
    {
        "key": "epic_codex",
        "label": "Illustrated Monster & Invention Codex (PDF Book)",
        "scale": "epic",
        "time_est": "Multi-session (1–2 illustrated entries/day)",
        "summary": "Build a hardcover-style illustrated field guide of creatures, bosses, or contraptions—each entry gets an illustration and a sharp how-it-works paragraph.",
    },
    {
        "key": "medium_pitch",
        "label": "4-Page Illustrated Pitch ('Why We Should…' · PDF)",
        "scale": "medium",
        "time_est": "1–2 sessions (~20 min)",
        "summary": "Build an airtight, illustrated 4-page persuasive case for a real audience (Claim → Evidence → Counter-move → Final Pitch).",
    },
    {
        "key": "quick_strip",
        "label": "Quick 3-Panel Comic Strip (10 min)",
        "scale": "quick",
        "time_est": "Today (~10 min)",
        "summary": "Fast 3-panel setup, twist, and payoff—each panel renders as soon as your sentence compiles.",
    },
    {
        "key": "quick_game",
        "label": "Build a Live Mini-Game (10 min)",
        "scale": "quick",
        "time_est": "Today (~10 min)",
        "summary": "Code a custom playable game on the spot where complete sentences trigger the physics and rules.",
    },
]


def extract_dialogue(text: str) -> tuple[str, list[dict[str, str]]]:
    """Extracts quoted direct speech or 'Speaker: line' into structured comic speech bubbles while preserving caption."""
    bubbles: list[dict[str, str]] = []
    raw = (text or "").strip()

    # Pattern 1: Speaker: "line" or Speaker: line at start
    m_colon = re.match(r"^([A-Z][A-Za-z0-9 _-]{0,18}):\s*[\"']?([^\"']+)[\"']?$", raw)
    if m_colon:
        bubbles.append({"speaker": m_colon.group(1).strip(), "text": m_colon.group(2).strip()})
        return raw, bubbles

    # Pattern 2: Direct quotation marks inside narrative sentence: e.g. Eddie yelled, "Watch out!" or "Run!" shouted Bob.
    for m in re.finditer(r'"([^"]{2,120})"', raw):
        quote = m.group(1).strip()
        speaker = ""
        before = raw[: m.start()].strip()
        after = raw[m.end() :].strip()
        m_bef = re.search(r"([A-Z][a-zA-Z0-9]+)\s+(?:said|yelled|shouted|whispered|roared|asked|cried|warned|called|barked|grinned)[,:]?$", before)
        m_aft = re.match(r"^(?:said|yelled|shouted|whispered|roared|asked|cried|warned|called|barked)\s+([A-Z][a-zA-Z0-9]+)", after)
        if m_bef:
            speaker = m_bef.group(1)
        elif m_aft:
            speaker = m_aft.group(1)
        bubbles.append({"speaker": speaker, "text": quote})

    return raw, bubbles


def create_project(
    kind: str,
    author: str,
    audience: str = "Dad",
    title: str = "",
    style: str = "comic book ink with bold lines and vibrant flat colors",
    persist: bool = True,
) -> dict[str, Any]:
    ensure_dirs()
    pid = new_id("proj")
    default_titles = {
        "epic_graphic_novel": "Untitled Graphic Novel",
        "epic_codex": "Illustrated Codex",
        "medium_pitch": "The Official Case File",
        "quick_strip": "3-Panel Strip",
    }
    needs_spine = kind == "epic_graphic_novel"
    proj: dict[str, Any] = {
        "id": pid,
        "kind": kind,
        "scale": "epic" if kind.startswith("epic_") else ("medium" if kind.startswith("medium_") else "quick"),
        "title": title or default_titles.get(kind, "Untitled Project"),
        "author": author or "Author",
        "audience": audience or "Family",
        "style": style,
        "characters": "",
        "stage": "spine_beginning" if needs_spine else "drafting_panels",
        "spine": {
            "beginning": "",
            "middle": "",
            "end": "",
            "subplots": [],
            "complete": not needs_spine,
        },
        "chapters": [
            {
                "number": 1,
                "title": "Chapter 1: The Setup" if needs_spine else ("Entries" if kind == "epic_codex" else "Part 1"),
                "act": "Beginning",
                "panels": [],
            }
        ],
        "target_panels": 100 if kind == "epic_graphic_novel" else (12 if kind == "epic_codex" else (4 if kind == "medium_pitch" else 3)),
        "created": now_iso(),
        "updated": now_iso(),
    }
    if persist:
        save_project(proj)
    return proj


def save_project(proj: dict[str, Any]) -> None:
    ensure_dirs()
    proj["updated"] = now_iso()
    path = PROJECTS / f"{proj['id']}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(proj, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_project(pid: str) -> dict[str, Any] | None:
    ensure_dirs()
    clean = re.sub(r"[^a-zA-Z0-9_]", "", pid or "")
    if not clean:
        return None
    p = PROJECTS / f"{clean}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def list_projects() -> list[dict[str, Any]]:
    ensure_dirs()
    out = []
    for p in sorted(PROJECTS.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            d["panel_count"] = total_panels(d)
            out.append(d)
        except Exception:
            continue
    return out


def total_panels(proj: dict[str, Any]) -> int:
    return sum(len(ch.get("panels") or []) for ch in (proj.get("chapters") or []))


def all_panels(proj: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for ch in proj.get("chapters") or []:
        for p in ch.get("panels") or []:
            out.append({**p, "chapter": ch.get("number", 1), "chapter_title": ch.get("title", "")})
    return out


def current_chapter(proj: dict[str, Any]) -> dict[str, Any]:
    chapters = proj.setdefault("chapters", [{"number": 1, "title": "Chapter 1", "act": "Beginning", "panels": []}])
    ch = chapters[-1]
    # Auto-start a new chapter every 6 panels in an Epic Graphic Novel so 100-panel books have natural issue/chapter breaks!
    if proj.get("kind") == "epic_graphic_novel" and len(ch.get("panels") or []) >= 6:
        n = len(chapters) + 1
        act = "Beginning" if n <= 2 else ("Middle" if n <= 12 else "Climax & End")
        ch = {"number": n, "title": f"Chapter {n} ({act})", "act": act, "panels": []}
        chapters.append(ch)
    return ch


def add_panel_to_project(proj: dict[str, Any], sentence: str, scene: str = "", persist: bool = True) -> tuple[int, dict[str, Any]]:
    """Appends a new panel/entry to the current chapter, extracts any speech bubbles, saves, and returns (global_idx, panel_dict)."""
    ch = current_chapter(proj)
    caption, bubbles = extract_dialogue(sentence)
    pnum = total_panels(proj) + 1
    panel = {
        "number": pnum,
        "caption": caption,
        "dialogue": bubbles,
        "scene": scene or sentence,
        "image": None,
        "src": None,
        "status": "drawing",
    }
    ch.setdefault("panels", []).append(panel)
    if persist:
        save_project(proj)
    return pnum, panel


def update_panel_media(proj: dict[str, Any], panel_number: int, media_id: str | None, status: str) -> None:
    for ch in proj.get("chapters") or []:
        for p in ch.get("panels") or []:
            if p.get("number") == panel_number:
                p["status"] = status
                if media_id:
                    p["image"] = media_id
                    p["src"] = f"/media/{media_id}.jpg"
                save_project(proj)
                return


def recent_reference_media_ids(proj: dict[str, Any], limit: int = 2) -> list[str]:
    mids = [p["image"] for p in all_panels(proj) if p.get("image")]
    return mids[-limit:]


def project_ui_payload(proj: dict[str, Any]) -> dict[str, Any]:
    """Formats the full project state (Story Spine + Chapters + Panels + PDF download URL) for the browser Canvas."""
    return {
        "id": proj["id"],
        "kind": "book_project",
        "proj_kind": proj.get("kind", "epic_graphic_novel"),
        "scale": proj.get("scale", "epic"),
        "title": proj.get("title", "Untitled"),
        "author": proj.get("author", ""),
        "audience": proj.get("audience", ""),
        "stage": proj.get("stage", "drafting_panels"),
        "spine": proj.get("spine", {}),
        "chapters": proj.get("chapters", []),
        "panel_count": total_panels(proj),
        "target_panels": proj.get("target_panels", 100),
        "pdf_url": f"/api/project/{proj['id']}/pdf",
        "web_url": f"/project/{proj['id']}",
    }
