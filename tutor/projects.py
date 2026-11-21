"""Saved books, comics, pitches, and multi-chapter graphic novels.

Supports multiple independent books per format plus an isolated Parent Sandbox store:
- Full Graphic Novels (Beginning -> Finale -> as many Middle Plot Twists as the child wants,
  followed by multi-chapter panels with speech bubbles, captions, and printable PDF issues).
- 3-Source Fact & Invention Codices (reading comprehension + 3-sentence synthesis -> PDF book).
- 4-Page Persuasive Pitch Books (Claim -> Reason -> Counter-Argument -> Deal -> PDF).
- Quick 3-Panel Comic Strips & Mini-Games.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .config import PROJECTS, ensure_dirs
from .media import ART_STYLES, DEFAULT_STYLE_KEY, STYLE_BY_KEY, resolve_style_prompt
from .record import new_id, now_iso

SANDBOX_PROJECTS: dict[str, dict[str, Any]] = {}

KIND_BADGES: dict[str, str] = {
    "epic_graphic_novel": "Graphic Novel",
    "epic_codex": "Fact Codex",
    "medium_pitch": "Persuasive Pitch",
    "quick_strip": "3-Panel Strip",
}

PROJECT_MENU: list[dict[str, str]] = [
    {
        "key": "epic_graphic_novel",
        "label": "Full Comic Book (Multi-Chapter · PDF)",
        "scale": "epic",
        "time_est": "Save anytime · up to 100 panels",
        "summary": "Sketch your Beginning, Big Finale, and all the wild twists in the middle—then draw chapter by chapter.",
    },
    {
        "key": "epic_codex",
        "label": "Fact & Invention Codex (PDF Book)",
        "scale": "epic",
        "time_est": "1–2 illustrated entries per session",
        "summary": "Read 3 short real-world sources and build an illustrated science & invention encyclopedia.",
    },
    {
        "key": "medium_pitch",
        "label": "4-Page Persuasive Pitch ('Why We Should…')",
        "scale": "medium",
        "time_est": "1–2 sessions (~15 min)",
        "summary": "Build an illustrated 4-page case (Claim → Proof → Counter-Argument → Deal).",
    },
    {
        "key": "quick_strip",
        "label": "Quick 3-Panel Comic Strip",
        "scale": "quick",
        "time_est": "Today (~10 min)",
        "summary": "Fast 3-panel setup, twist, and punchline.",
    },
    {
        "key": "quick_game",
        "label": "Build a Live Mini-Game",
        "scale": "quick",
        "time_est": "Today (~10 min)",
        "summary": "Create a custom playable game controlled by complete sentences.",
    },
]


def extract_dialogue(text: str) -> tuple[str, list[dict[str, str]]]:
    """Extracts quoted speech or 'Speaker: line' into comic speech bubbles while preserving caption."""
    bubbles: list[dict[str, str]] = []
    raw = (text or "").strip()

    m_colon = re.match(r"^([A-Z][A-Za-z0-9 _-]{0,18}):\s*[\"']?([^\"']+)[\"']?$", raw)
    if m_colon:
        bubbles.append({"speaker": m_colon.group(1).strip(), "text": m_colon.group(2).strip()})
        return raw, bubbles

    for m in re.finditer(r'"([^"]{2,120})"', raw):
        quote = m.group(1).strip()
        speaker = ""
        before = raw[: m.start()].strip()
        after = raw[m.end() :].strip()
        m_bef = re.search(
            r"([A-Z][a-zA-Z0-9]+)\s+(?:said|yelled|shouted|whispered|roared|asked|cried|warned|called|barked|grinned)[,:]?$",
            before,
        )
        m_aft = re.match(r"^(?:said|yelled|shouted|whispered|roared|asked|cried|warned|called|barked)\s+([A-Z][a-zA-Z0-9]+)", after)
        if m_bef:
            speaker = m_bef.group(1)
        elif m_aft:
            speaker = m_aft.group(1)
        bubbles.append({"speaker": speaker, "text": quote})

    return raw, bubbles


def middle_beats_list(sp: dict[str, Any]) -> list[dict[str, Any]]:
    """Returns normalized list of middle plot beats (migrating legacy single `sp['middle']` string if present)."""
    beats = sp.get("middle_beats")
    if isinstance(beats, list) and beats:
        return beats
    legacy = (sp.get("middle") or "").strip()
    if legacy:
        return [
            {
                "text": legacy,
                "image": sp.get("middle_image"),
                "src": sp.get("middle_src"),
                "status": sp.get("middle_status") or ("done" if sp.get("middle_image") else "done"),
            }
        ]
    return []


def is_project_nonempty(proj: dict[str, Any]) -> bool:
    """True once a project has a custom title, at least 1 Story Spine beat, or at least 1 panel/entry."""
    if total_panels(proj) > 0:
        return True
    sp = proj.get("spine") or {}
    if sp.get("beginning") or sp.get("end") or sp.get("middle") or middle_beats_list(sp):
        return True
    if proj.get("custom_titled"):
        return True
    return False


def project_progress_label(proj: dict[str, Any]) -> str:
    kind = proj.get("kind", "epic_graphic_novel")
    badge = KIND_BADGES.get(kind, "Book")
    pcount = total_panels(proj)
    stage = proj.get("stage", "")
    sp = proj.get("spine") or {}
    if kind == "epic_graphic_novel" and stage.startswith("spine_") and pcount == 0:
        n_mid = len(middle_beats_list(sp))
        step = {
            "spine_beginning": "Plot: Kickoff",
            "spine_end": "Plot: Finale",
            "spine_middle": f"Plot: {n_mid} middle twist{'s' if n_mid != 1 else ''}",
        }.get(stage, "Plotting")
        return f"{badge} · {step}"
    if kind == "epic_codex":
        return f"{badge} · {pcount} entr{'y' if pcount == 1 else 'ies'}"
    if kind == "medium_pitch":
        return f"{badge} · {pcount}/4 pages"
    n_ch = len(proj.get("chapters") or [1])
    return f"{badge} · Ch.{n_ch} · {pcount} panel{'s' if pcount != 1 else ''}"


def create_project(
    kind: str,
    author: str,
    audience: str = "Dad",
    title: str = "",
    style_key: str = DEFAULT_STYLE_KEY,
    persist: bool = False,
    sandbox: bool = False,
) -> dict[str, Any]:
    ensure_dirs()
    pid = new_id("sbox_proj" if sandbox else "proj")
    default_titles = {
        "epic_graphic_novel": "Untitled Graphic Novel",
        "epic_codex": f"{author}'s Fact & Invention Codex" if author else "Fact & Invention Codex",
        "medium_pitch": f"Pitch for {audience}" if audience else "The Official Pitch",
        "quick_strip": "3-Panel Comic Strip",
    }
    clean_title = (title or "").strip()
    skey = style_key if style_key in STYLE_BY_KEY else DEFAULT_STYLE_KEY
    needs_spine = kind == "epic_graphic_novel"
    proj: dict[str, Any] = {
        "id": pid,
        "kind": kind,
        "scale": "epic" if kind.startswith("epic_") else ("medium" if kind.startswith("medium_") else "quick"),
        "title": clean_title or default_titles.get(kind, "Untitled Project"),
        "custom_titled": bool(clean_title),
        "author": author or "Author",
        "audience": audience or "Family",
        "style_key": skey,
        "style": resolve_style_prompt(skey),
        "characters": "",
        "stage": "spine_beginning" if needs_spine else "drafting_panels",
        "spine": {
            "beginning": "",
            "end": "",
            "middle_beats": [],
            "middle": "",
            "subplots": [],
            "complete": not needs_spine,
        },
        "chapters": [
            {
                "number": 1,
                "title": "Chapter 1: The Kickoff" if needs_spine else ("Entries" if kind == "epic_codex" else "Part 1"),
                "act": "Beginning",
                "panels": [],
            }
        ],
        "target_panels": 100 if kind == "epic_graphic_novel" else (12 if kind == "epic_codex" else (4 if kind == "medium_pitch" else 3)),
        "sandbox": sandbox,
        "created": now_iso(),
        "updated": now_iso(),
    }
    if sandbox:
        SANDBOX_PROJECTS[pid] = proj
    elif persist:
        save_project(proj, sandbox=False)
    return proj


def set_project_style(proj: dict[str, Any], style_key: str, sandbox: bool | None = None) -> bool:
    if style_key not in STYLE_BY_KEY:
        return False
    proj["style_key"] = style_key
    proj["style"] = resolve_style_prompt(style_key)
    if is_project_nonempty(proj):
        save_project(proj, sandbox=sandbox)
    return True


def save_project(proj: dict[str, Any], sandbox: bool | None = None) -> None:
    is_sb = proj.get("sandbox", False) if sandbox is None else sandbox
    proj["updated"] = now_iso()
    if is_sb:
        proj["sandbox"] = True
        SANDBOX_PROJECTS[proj["id"]] = proj
        return
    ensure_dirs()
    path = PROJECTS / f"{proj['id']}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(proj, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_project(pid: str) -> dict[str, Any] | None:
    clean = re.sub(r"[^a-zA-Z0-9_]", "", pid or "")
    if not clean:
        return None
    if clean in SANDBOX_PROJECTS:
        return SANDBOX_PROJECTS[clean]
    ensure_dirs()
    p = PROJECTS / f"{clean}.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    if not d.get("style_key"):
        d["style_key"] = DEFAULT_STYLE_KEY
        d["style"] = resolve_style_prompt(DEFAULT_STYLE_KEY)
    return d


def delete_project(pid: str, sandbox: bool = False) -> bool:
    clean = re.sub(r"[^a-zA-Z0-9_]", "", pid or "")
    if not clean:
        return False
    if clean in SANDBOX_PROJECTS:
        del SANDBOX_PROJECTS[clean]
        return True
    if sandbox:
        return False
    p = PROJECTS / f"{clean}.json"
    if p.exists():
        p.unlink()
        return True
    return False


def rename_project(pid: str, title: str) -> dict[str, Any] | None:
    proj = load_project(pid)
    if not proj:
        return None
    clean_t = (title or "").strip()[:80]
    if not clean_t:
        return proj
    proj["title"] = clean_t
    proj["custom_titled"] = True
    save_project(proj)
    return proj


def list_projects(sandbox: bool = False) -> list[dict[str, Any]]:
    if sandbox:
        items = [dict(d) for d in SANDBOX_PROJECTS.values() if is_project_nonempty(d)]
        items.sort(key=lambda x: x.get("updated", ""), reverse=True)
        for d in items:
            d["panel_count"] = total_panels(d)
            d["badge"] = KIND_BADGES.get(d.get("kind", ""), "Book")
            d["progress_label"] = project_progress_label(d)
        return items

    ensure_dirs()
    out = []
    for p in sorted(PROJECTS.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if not is_project_nonempty(d):
                continue
            d["panel_count"] = total_panels(d)
            d["badge"] = KIND_BADGES.get(d.get("kind", ""), "Book")
            d["progress_label"] = project_progress_label(d)
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
    chapters = proj.setdefault("chapters", [{"number": 1, "title": "Chapter 1: The Kickoff", "act": "Beginning", "panels": []}])
    ch = chapters[-1]
    if proj.get("kind") == "epic_graphic_novel" and len(ch.get("panels") or []) >= 5:
        n = len(chapters) + 1
        mbeats = middle_beats_list(proj.get("spine") or {})
        if n - 1 <= len(mbeats):
            act = f"Middle Twist {n - 1}"
            title = f"Chapter {n}: Twist {n - 1}"
        else:
            act = "The Big Finale"
            title = f"Chapter {n}: The Big Finale"
        ch = {"number": n, "title": title, "act": act, "panels": []}
        chapters.append(ch)
    return ch


def add_panel_to_project(
    proj: dict[str, Any],
    sentence: str,
    scene: str = "",
    persist: bool = True,
    sandbox: bool | None = None,
) -> tuple[int, dict[str, Any]]:
    """Appends a new panel/entry to the current chapter, extracts speech bubbles, saves, and returns (global_idx, panel_dict)."""
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
    is_sb = proj.get("sandbox", False) if sandbox is None else sandbox
    if is_sb:
        save_project(proj, sandbox=True)
    elif persist:
        save_project(proj, sandbox=False)
    return pnum, panel


def update_panel_media(proj: dict[str, Any], panel_number: int, media_id: str | None, status: str, sandbox: bool | None = None) -> None:
    for ch in proj.get("chapters") or []:
        for p in ch.get("panels") or []:
            if p.get("number") == panel_number:
                p["status"] = status
                if media_id:
                    p["image"] = media_id
                    p["src"] = f"/media/{media_id}.jpg"
                save_project(proj, sandbox=sandbox)
                return


def update_spine_media(proj: dict[str, Any], beat: str, media_id: str | None, status: str, sandbox: bool | None = None) -> None:
    sp = proj.setdefault("spine", {})
    if beat.startswith("middle_"):
        try:
            idx = int(beat.split("_", 1)[1])
        except ValueError:
            idx = -1
        mbeats = sp.setdefault("middle_beats", [])
        if 0 <= idx < len(mbeats):
            mbeats[idx]["status"] = status
            if media_id:
                mbeats[idx]["image"] = media_id
                mbeats[idx]["src"] = f"/media/{media_id}.jpg"
        save_project(proj, sandbox=sandbox)
        return

    sp[f"{beat}_status"] = status
    if media_id:
        sp[f"{beat}_image"] = media_id
        sp[f"{beat}_src"] = f"/media/{media_id}.jpg"
        if beat == "beginning":
            proj["cover_image"] = media_id
    save_project(proj, sandbox=sandbox)


def update_codex_sketch(proj: dict[str, Any], media_id: str | None, status: str, caption: str = "", sandbox: bool | None = None) -> None:
    proj["codex_sketch_status"] = status
    if caption:
        proj["codex_sketch_caption"] = caption
    if media_id:
        proj["codex_sketch_image"] = media_id
        proj["codex_sketch_src"] = f"/media/{media_id}.jpg"
        if not proj.get("cover_image"):
            proj["cover_image"] = media_id
    save_project(proj, sandbox=sandbox)


def recent_reference_media_ids(proj: dict[str, Any], limit: int = 2) -> list[str]:
    sp = proj.get("spine") or {}
    mbeat_imgs = [b.get("image") for b in middle_beats_list(sp) if b.get("image")]
    spine_mids = ([sp["beginning_image"]] if sp.get("beginning_image") else []) + mbeat_imgs + ([sp["end_image"]] if sp.get("end_image") else [])
    panel_mids = [p["image"] for p in all_panels(proj) if p.get("image")]
    combined = spine_mids + panel_mids
    return combined[-limit:]


def project_ui_payload(proj: dict[str, Any]) -> dict[str, Any]:
    """Formats the full project state (Plot Board + Art Styles + Chapters + Panels + PDF URL) for the browser Canvas."""
    sp = dict(proj.get("spine") or {})
    sp["middle_beats"] = middle_beats_list(sp)
    skey = proj.get("style_key") or DEFAULT_STYLE_KEY
    return {
        "id": proj["id"],
        "kind": "book_project",
        "proj_kind": proj.get("kind", "epic_graphic_novel"),
        "badge": KIND_BADGES.get(proj.get("kind", ""), "Book"),
        "progress_label": project_progress_label(proj),
        "scale": proj.get("scale", "epic"),
        "title": proj.get("title", "Untitled"),
        "author": proj.get("author", ""),
        "audience": proj.get("audience", ""),
        "style_key": skey,
        "style_label": STYLE_BY_KEY.get(skey, {}).get("label", "Notebook Ink Doodle"),
        "art_styles": ART_STYLES,
        "stage": proj.get("stage", "drafting_panels"),
        "spine": sp,
        "cover_src": f"/media/{proj['cover_image']}.jpg" if proj.get("cover_image") else None,
        "codex_sketch_src": proj.get("codex_sketch_src"),
        "codex_sketch_status": proj.get("codex_sketch_status"),
        "codex_sketch_caption": proj.get("codex_sketch_caption", ""),
        "codex_draft_sentences": proj.get("codex_draft_sentences", []),
        "chapters": proj.get("chapters", []),
        "panel_count": total_panels(proj),
        "target_panels": proj.get("target_panels", 100),
        "sandbox": bool(proj.get("sandbox")),
        "pdf_url": f"/api/project/{proj['id']}/pdf",
        "web_url": f"/project/{proj['id']}",
    }
