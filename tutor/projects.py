"""Saved books, comics, pitches, and multi-chapter graphic novels.

Supports multiple independent books per format plus an isolated Parent Sandbox store:
- Full Graphic Novels (Beginning -> Finale -> as many Middle Plot Twists as the child wants,
  followed by multi-chapter panels with speech bubbles, captions, and printable PDF issues).
- 3-Source Fact & Invention Codices (reading comprehension + 3-sentence synthesis -> PDF book).
- 4-Page Persuasive Pitch Books (Claim -> Reason -> Counter-Argument -> Deal -> PDF).
- Quick 3-Panel Comic Strips & Mini-Games.
"""

from __future__ import annotations

from datetime import datetime
import json
import re
from typing import Any

from .config import PROJECTS, ensure_dirs
from .media import ART_STYLES, DEFAULT_STYLE_KEY, STYLE_BY_KEY, resolve_style_prompt
from .record import new_id, now_iso

SANDBOX_PROJECTS: dict[str, dict[str, Any]] = {}

KIND_BADGES: dict[str, str] = {
    "epic_graphic_novel": "Graphic Novel",
    "story_jam_novel": "Story Jam Comic",
    "how_to_tutorial": "How-To Tutorial",
    "minecraft_diary": "Minecraft Diary",
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
        "key": "story_jam_novel",
        "label": "100-Page Story Jam (Talk It Out First → Comic)",
        "scale": "epic",
        "time_est": "Verbal back-and-forth → up to 100 panels",
        "summary": "Build a giant story out loud back-and-forth first (what happens, then what happens next?), then write & draw panel by panel.",
    },
    {
        "key": "how_to_tutorial",
        "label": "Illustrated How-To Tutorial (e.g. How to Play Minecraft)",
        "scale": "epic",
        "time_est": "Step-by-step illustrated guide · PDF",
        "summary": "Write and illustrate an official step-by-step survival or strategy guide for beginners.",
    },
    {
        "key": "minecraft_diary",
        "label": "What I Did in Minecraft Today (Illustrated Diary)",
        "scale": "epic",
        "time_est": "Ongoing illustrated journal · PDF",
        "summary": "Turn what you built, mined, or survived in Minecraft today into an illustrated gamer diary.",
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


_SPEECH_VERBS = r"(?:said|says|yelled|yells|shouted|shouts|whispered|whispers|roared|roars|asked|asks|cried|cries|warned|warns|called|calls|barked|barks|grinned|screamed|screams|groaned|groans|thought|thinks|wondered|wonders)"


def _infer_bubble_kind(quote: str, verb: str = "") -> str:
    vb = (verb or "").lower()
    q = (quote or "").strip()
    if vb in ("thought", "thinks", "wondered", "wonders"):
        return "thought"
    letters = [c for c in q if c.isalpha()]
    all_caps = len(letters) >= 3 and all(c.isupper() for c in letters)
    if all_caps or vb in ("yelled", "yells", "shouted", "shouts", "roared", "roars", "screamed", "screams"):
        return "shout"
    return "speech"


def _default_bubble_pos(idx: int) -> tuple[int, int]:
    slots = [(10, 8), (44, 24), (14, 46), (46, 56)]
    return slots[idx % len(slots)]


def extract_dialogue(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Extracts quoted speech or 'Speaker: line' into positioned comic speech bubbles,
    and strips redundant speech-wrapper clauses from the narrator caption so quotes aren't printed twice."""
    bubbles: list[dict[str, Any]] = []
    raw = (text or "").strip()
    if not raw:
        return "", []

    m_colon = re.match(r"^([A-Z][A-Za-z0-9 _-]{0,18}):\s*[\"“']?([^\"”']+)[\"”']?$", raw)
    if m_colon:
        spk = m_colon.group(1).strip()
        qtxt = m_colon.group(2).strip()
        bx, by = _default_bubble_pos(0)
        bubbles.append(
            {
                "id": new_id("bub"),
                "speaker": spk,
                "text": qtxt,
                "kind": _infer_bubble_kind(qtxt),
                "x": bx,
                "y": by,
            }
        )
        return "", bubbles

    # Match straight or curly double quotes
    quote_spans: list[tuple[int, int]] = []
    for idx_q, m in enumerate(re.finditer(r'["“]([^"”]{1,140})["”]', raw)):
        quote = m.group(1).strip()
        if not quote:
            continue
        speaker = ""
        verb = ""
        before = raw[: m.start()].strip()
        after = raw[m.end() :].strip()
        m_bef = re.search(rf"([A-Z][a-zA-Z0-9]+)\s+({_SPEECH_VERBS})\s*[,:]?$", before)
        m_aft = re.match(rf"^[, ]*({_SPEECH_VERBS})\s+([A-Z][a-zA-Z0-9]+)\s*[.!?]?", after)
        span_start, span_end = m.start(), m.end()
        if m_bef:
            speaker, verb = m_bef.group(1), m_bef.group(2)
            # Also trim leading ", and Name yelled," if preceded by a narrative clause
            lead_conj = re.search(rf"(?:[,;]\s*(?:and|so|then|but)\s+)?[A-Z][a-zA-Z0-9]+\s+{_SPEECH_VERBS}\s*[,:]?\s*$", raw[: m.start()])
            if lead_conj:
                span_start = lead_conj.start()
        elif m_aft:
            verb, speaker = m_aft.group(1), m_aft.group(2)
            span_end = m.end() + m_aft.end()
        bx, by = _default_bubble_pos(idx_q)
        bubbles.append(
            {
                "id": new_id("bub"),
                "speaker": speaker,
                "text": quote,
                "kind": _infer_bubble_kind(quote, verb),
                "x": bx,
                "y": by,
            }
        )
        quote_spans.append((span_start, span_end))

    if not bubbles:
        return raw, []

    # Build clean narrator caption from any remaining non-speech narration
    rem_parts: list[str] = []
    pos = 0
    for s0, s1 in quote_spans:
        if s0 > pos:
            rem_parts.append(raw[pos:s0])
        pos = max(pos, s1)
    if pos < len(raw):
        rem_parts.append(raw[pos:])
    rem = " ".join(" ".join(rem_parts).split()).strip(" ,;:-")
    if rem and len(re.findall(r"[A-Za-z']+", rem)) >= 3:
        if not re.search(r"[.!?]$", rem):
            rem += "."
        rem = rem[:1].upper() + rem[1:]
        return rem, bubbles
    return "", bubbles


def _normalize_bubbles(bubbles: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx, b in enumerate(bubbles or []):
        if not isinstance(b, dict):
            continue
        txt = str(b.get("text") or "").strip()
        if not txt:
            continue
        dx, dy = _default_bubble_pos(idx)
        out.append(
            {
                "id": str(b.get("id") or f"bub_{idx + 1}"),
                "speaker": str(b.get("speaker") or "").strip()[:28],
                "text": txt[:160],
                "kind": b.get("kind") if b.get("kind") in ("speech", "shout", "thought") else _infer_bubble_kind(txt),
                "x": max(2, min(84, int(round(float(b.get("x", dx)))))),
                "y": max(2, min(78, int(round(float(b.get("y", dy)))))),
            }
        )
    return out


def mutate_lettering_holder(holder: dict[str, Any], action: str, data: dict[str, Any]) -> bool:
    """Applies add_bubble / edit_bubble / delete_bubble / move_bubble / set_caption to any panel-like dict."""
    bubs = _normalize_bubbles(holder.get("dialogue"))
    if action == "add_bubble":
        txt = str(data.get("text") or "").strip()
        if not txt:
            return False
        dx, dy = _default_bubble_pos(len(bubs))
        kind = str(data.get("kind") or "speech").strip().lower()
        if kind not in ("speech", "shout", "thought"):
            kind = _infer_bubble_kind(txt)
        bubs.append(
            {
                "id": new_id("bub"),
                "speaker": str(data.get("speaker") or "").strip()[:28],
                "text": txt[:160],
                "kind": kind,
                "x": max(2, min(84, int(round(float(data.get("x", dx)))))),
                "y": max(2, min(78, int(round(float(data.get("y", dy)))))),
            }
        )
        holder["dialogue"] = bubs[:6]
        return True

    if action == "edit_bubble":
        bid = str(data.get("bubble_id") or "").strip()
        txt = str(data.get("text") or "").strip()
        if not bid or not txt:
            return False
        kind = str(data.get("kind") or "").strip().lower()
        for b in bubs:
            if b["id"] == bid:
                b["text"] = txt[:160]
                if "speaker" in data:
                    b["speaker"] = str(data.get("speaker") or "").strip()[:28]
                if kind in ("speech", "shout", "thought"):
                    b["kind"] = kind
                holder["dialogue"] = bubs
                return True
        return False

    if action == "delete_bubble":
        bid = str(data.get("bubble_id") or "").strip()
        before_n = len(bubs)
        bubs = [b for b in bubs if b["id"] != bid]
        holder["dialogue"] = bubs
        return len(bubs) != before_n

    if action == "move_bubble":
        bid = str(data.get("bubble_id") or "").strip()
        for b in bubs:
            if b["id"] == bid:
                b["x"] = max(2, min(84, int(round(float(data.get("x", b["x"]))))))
                b["y"] = max(2, min(78, int(round(float(data.get("y", b["y"]))))))
                holder["dialogue"] = bubs
                return True
        return False

    if action == "set_caption":
        holder["caption"] = str(data.get("caption") or "").strip()[:320]
        holder["caption_edited"] = True
        return True

    return False


def middle_beats_list(sp: dict[str, Any]) -> list[dict[str, Any]]:
    """Returns normalized list of middle plot beats (migrating legacy single `sp['middle']` string if present)."""
    beats = sp.get("middle_beats")
    raw_list: list[dict[str, Any]] = []
    if isinstance(beats, list) and beats:
        raw_list = [dict(b) for b in beats if isinstance(b, dict)]
    else:
        legacy = (sp.get("middle") or "").strip()
        if legacy:
            raw_list = [
                {
                    "text": legacy,
                    "image": sp.get("middle_image"),
                    "src": sp.get("middle_src"),
                    "status": sp.get("middle_status") or ("done" if sp.get("middle_image") else "done"),
                }
            ]
    for b in raw_list:
        if "caption" not in b and "dialogue" not in b:
            cap, bubs = extract_dialogue(b.get("text") or "")
            b["caption"] = cap
            b["dialogue"] = bubs
        else:
            b.setdefault("caption", b.get("text") or "")
            b["dialogue"] = _normalize_bubbles(b.get("dialogue"))
    return raw_list


def is_project_nonempty(proj: dict[str, Any]) -> bool:
    """True once a project has a custom title, Story Spine/Jam beats, tutorial topic, or at least 1 panel/entry."""
    if total_panels(proj) > 0:
        return True
    if proj.get("jam_beats") or proj.get("tutorial_topic"):
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
    if kind == "story_jam_novel":
        n_jam = len(proj.get("jam_beats") or [])
        if stage == "verbal_jam" and pcount == 0:
            return f"{badge} · {n_jam} spoken beat{'s' if n_jam != 1 else ''}"
        return f"{badge} · {pcount} panel{'s' if pcount != 1 else ''} ({n_jam} beats)"
    if kind == "how_to_tutorial":
        return f"{badge} · {pcount} step{'s' if pcount != 1 else ''}"
    if kind == "minecraft_diary":
        return f"{badge} · {pcount} log panel{'s' if pcount != 1 else ''}"
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


def _today_short() -> str:
    return datetime.now().strftime("%b %d")


def create_project(
    kind: str,
    author: str,
    audience: str = "Dad",
    title: str = "",
    style_key: str = "",
    persist: bool = False,
    sandbox: bool = False,
) -> dict[str, Any]:
    ensure_dirs()
    pid = new_id("sbox_proj" if sandbox else "proj")
    today_lbl = _today_short()
    default_titles = {
        "epic_graphic_novel": "Untitled Graphic Novel",
        "story_jam_novel": "Untitled 100-Page Story",
        "how_to_tutorial": "How to Play Minecraft: Official Guide",
        "minecraft_diary": f"{author}'s Minecraft Diary" if author else "Minecraft Adventure Diary",
        "epic_codex": f"{author}'s Fact & Invention Codex" if author else "Fact & Invention Codex",
        "medium_pitch": f"Pitch for {audience}" if audience else "The Official Pitch",
        "quick_strip": "3-Panel Comic Strip",
    }
    clean_title = (title or "").strip()
    if style_key and style_key in STYLE_BY_KEY:
        skey = style_key
    elif kind in ("how_to_tutorial", "minecraft_diary"):
        skey = "blocky_voxel"
    else:
        skey = DEFAULT_STYLE_KEY
    needs_spine = kind == "epic_graphic_novel"
    if needs_spine:
        init_stage = "spine_beginning"
    elif kind == "story_jam_novel":
        init_stage = "verbal_jam"
    elif kind == "how_to_tutorial" and not clean_title:
        init_stage = "tutorial_topic"
    else:
        init_stage = "drafting_panels"

    if needs_spine or kind == "story_jam_novel":
        ch1_title = "Chapter 1: The Kickoff"
    elif kind == "how_to_tutorial":
        ch1_title = "Step-by-Step Survival & Strategy Guide"
    elif kind == "minecraft_diary":
        ch1_title = f"Minecraft Log · {today_lbl}"
    elif kind == "epic_codex":
        ch1_title = "Entries"
    else:
        ch1_title = "Part 1"

    target_map = {
        "epic_graphic_novel": 100,
        "story_jam_novel": 100,
        "how_to_tutorial": 8,
        "minecraft_diary": 24,
        "epic_codex": 12,
        "medium_pitch": 4,
        "quick_strip": 3,
    }
    proj: dict[str, Any] = {
        "id": pid,
        "kind": kind,
        "scale": "epic" if kind in ("epic_graphic_novel", "story_jam_novel", "how_to_tutorial", "minecraft_diary", "epic_codex") else ("medium" if kind.startswith("medium_") else "quick"),
        "title": clean_title or default_titles.get(kind, "Untitled Project"),
        "custom_titled": bool(clean_title),
        "tutorial_topic": clean_title if kind == "how_to_tutorial" and clean_title else "",
        "jam_beats": [],
        "author": author or "Author",
        "audience": audience or "Family",
        "style_key": skey,
        "style": resolve_style_prompt(skey),
        "characters": "",
        "stage": init_stage,
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
                "title": ch1_title,
                "date_key": today_lbl if kind == "minecraft_diary" else "",
                "act": "Beginning",
                "panels": [],
            }
        ],
        "target_panels": target_map.get(kind, 6),
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


def add_jam_beat(
    proj: dict[str, Any],
    note: str,
    title_hint: str = "",
    sandbox: bool | None = None,
) -> dict[str, Any]:
    """Appends one spoken/brainstormed story beat to `proj['jam_beats']` during Verbal Story Jam."""
    jlist = proj.setdefault("jam_beats", [])
    entry = {
        "id": new_id("jb"),
        "note": (note or "").strip()[:240],
        "written": False,
    }
    jlist.append(entry)
    if title_hint and not proj.get("custom_titled") and proj.get("title", "").startswith("Untitled"):
        proj["title"] = title_hint.strip()[:64]
    save_project(proj, sandbox=sandbox)
    return entry


def remove_jam_beat(proj: dict[str, Any], beat_id: str, sandbox: bool | None = None) -> bool:
    jlist = proj.get("jam_beats") or []
    before = len(jlist)
    proj["jam_beats"] = [b for b in jlist if b.get("id") != beat_id]
    if len(proj["jam_beats"]) != before:
        save_project(proj, sandbox=sandbox)
        return True
    return False


def next_unwritten_jam_beat(proj: dict[str, Any]) -> tuple[int, dict[str, Any] | None]:
    """Returns (1-based beat_index, beat_dict) for the next spoken Story Jam beat not yet turned into a panel."""
    for idx, b in enumerate(proj.get("jam_beats") or [], 1):
        if not b.get("written"):
            return idx, b
    return 0, None


def current_chapter(proj: dict[str, Any]) -> dict[str, Any]:
    chapters = proj.setdefault("chapters", [{"number": 1, "title": "Chapter 1: The Kickoff", "act": "Beginning", "panels": []}])
    ch = chapters[-1]
    kind = proj.get("kind", "")
    if kind == "minecraft_diary":
        today_lbl = _today_short()
        if ch.get("date_key") and ch.get("date_key") != today_lbl and (ch.get("panels") or []):
            n = len(chapters) + 1
            ch = {"number": n, "title": f"Minecraft Log · {today_lbl}", "date_key": today_lbl, "act": today_lbl, "panels": []}
            chapters.append(ch)
        return ch
    if kind in ("epic_graphic_novel", "story_jam_novel") and len(ch.get("panels") or []) >= 5:
        n = len(chapters) + 1
        mbeats = middle_beats_list(proj.get("spine") or {})
        if mbeats and n - 1 <= len(mbeats):
            act = f"Middle Twist {n - 1}"
            title = f"Chapter {n}: Twist {n - 1}"
        else:
            act = f"Chapter {n}"
            title = f"Chapter {n}"
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
    kind = proj.get("kind", "")
    if kind == "how_to_tutorial":
        badge = f"STEP {pnum}"
    elif kind == "minecraft_diary":
        badge = f"{_today_short().upper()} · #{pnum}"
    else:
        badge = ""
    # Mark next unwritten Story Jam beat as written when turning spoken outline into panels
    for jb in proj.get("jam_beats") or []:
        if not jb.get("written"):
            jb["written"] = True
            jb["panel_number"] = pnum
            break
    panel = {
        "number": pnum,
        "badge": badge,
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
                    p["verified"] = False
                    if not proj.get("cover_image"):
                        proj["cover_image"] = media_id
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
                mbeats[idx]["verified"] = False
        save_project(proj, sandbox=sandbox)
        return

    sp[f"{beat}_status"] = status
    if media_id:
        sp[f"{beat}_image"] = media_id
        sp[f"{beat}_src"] = f"/media/{media_id}.jpg"
        sp[f"{beat}_verified"] = False
        if beat == "beginning":
            proj["cover_image"] = media_id
    save_project(proj, sandbox=sandbox)


def get_art_text(proj: dict[str, Any], target: str) -> str:
    sp = proj.get("spine") or {}
    if target.startswith("spine:"):
        beat = target.split(":", 1)[1]
        if beat.startswith("middle_"):
            try:
                idx = int(beat.split("_", 1)[1])
                mbs = middle_beats_list(sp)
                return mbs[idx].get("text", "") if 0 <= idx < len(mbs) else ""
            except ValueError:
                return ""
        return str(sp.get(beat) or "")
    if target.startswith("panel:"):
        try:
            pnum = int(target.split(":", 1)[1])
        except ValueError:
            return ""
        for ch in proj.get("chapters") or []:
            for p in ch.get("panels") or []:
                if p.get("number") == pnum:
                    return str(p.get("scene") or p.get("caption") or "")
    return ""


def mark_art_verified(proj: dict[str, Any], target: str, sandbox: bool | None = None) -> None:
    sp = proj.setdefault("spine", {})
    if target.startswith("spine:"):
        beat = target.split(":", 1)[1]
        if beat.startswith("middle_"):
            try:
                idx = int(beat.split("_", 1)[1])
                mbs = sp.setdefault("middle_beats", middle_beats_list(sp))
                if 0 <= idx < len(mbs):
                    mbs[idx]["verified"] = True
            except ValueError:
                pass
        else:
            sp[f"{beat}_verified"] = True
        save_project(proj, sandbox=sandbox)
        return
    if target.startswith("panel:"):
        try:
            pnum = int(target.split(":", 1)[1])
        except ValueError:
            return
        for ch in proj.get("chapters") or []:
            for p in ch.get("panels") or []:
                if p.get("number") == pnum:
                    p["verified"] = True
                    save_project(proj, sandbox=sandbox)
                    return


def prepare_art_redraw(proj: dict[str, Any], target: str, extra_detail: str, sandbox: bool | None = None) -> dict[str, Any] | None:
    """Combines original sentence + child's clarifying detail, sets status='drawing', and returns redraw descriptor."""
    orig = get_art_text(proj, target)
    combined = f"{orig.rstrip()} ({extra_detail.strip()})" if orig else extra_detail.strip()
    sp = proj.setdefault("spine", {})
    if target.startswith("spine:"):
        beat = target.split(":", 1)[1]
        if beat.startswith("middle_"):
            try:
                idx = int(beat.split("_", 1)[1])
                mbs = sp.setdefault("middle_beats", middle_beats_list(sp))
                if 0 <= idx < len(mbs):
                    mbs[idx]["status"] = "drawing"
                    mbs[idx]["verified"] = False
            except ValueError:
                return None
        else:
            sp[f"{beat}_status"] = "drawing"
            sp[f"{beat}_verified"] = False
        save_project(proj, sandbox=sandbox)
        return {"kind": "spine", "beat": beat, "scene": combined}
    if target.startswith("panel:"):
        try:
            pnum = int(target.split(":", 1)[1])
        except ValueError:
            return None
        for ch in proj.get("chapters") or []:
            for p in ch.get("panels") or []:
                if p.get("number") == pnum:
                    p["scene"] = combined
                    p["status"] = "drawing"
                    p["verified"] = False
                    save_project(proj, sandbox=sandbox)
                    return {"kind": "panel", "panel": pnum, "scene": combined}
    return None


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


def latest_art_target(proj: dict[str, Any]) -> str:
    """Returns the target identifier ('panel:N' or 'spine:...') of the most recently added scene."""
    panels = all_panels(proj)
    if panels:
        return f"panel:{panels[-1].get('number', len(panels))}"
    sp = proj.get("spine") or {}
    mbs = middle_beats_list(sp)
    if mbs:
        return f"spine:middle_{len(mbs) - 1}"
    if sp.get("end"):
        return "spine:end"
    if sp.get("beginning"):
        return "spine:beginning"
    return ""


def undo_or_move_beat(proj: dict[str, Any], target: str, move_end_to_middle: bool = False, sandbox: bool | None = None) -> tuple[str, str]:
    """Undoes the beat at `target` (returning its text so the child can edit/replace it),
    OR when `move_end_to_middle=True` moves an accidental `spine:end` sentence into `middle_beats[0]` and reopens `spine_end`!"""
    sp = proj.setdefault("spine", {})
    if move_end_to_middle and sp.get("end"):
        moved_txt = str(sp.get("end") or "")
        mbs = list(middle_beats_list(sp))
        moved_beat: dict[str, Any] = {
            "text": moved_txt,
            "image": sp.get("end_image"),
            "src": sp.get("end_src"),
            "status": sp.get("end_status") or ("done" if sp.get("end_image") else None),
            "verified": False,
        }
        if "end_caption" in sp or "end_dialogue" in sp:
            moved_beat["caption"] = sp.get("end_caption", "")
            moved_beat["dialogue"] = _normalize_bubbles(sp.get("end_dialogue"))
        mbs.append(moved_beat)
        sp["middle_beats"] = mbs
        sp["middle"] = " ".join(b.get("text", "") for b in mbs)
        for k_clr in ("end", "end_image", "end_src", "end_status", "end_caption", "end_dialogue"):
            sp.pop(k_clr, None)
        sp["end"] = ""
        sp["end_verified"] = False
        proj["stage"] = "spine_end"
        save_project(proj, sandbox=sandbox)
        return moved_txt, "moved_to_middle"

    if target == "spine:beginning":
        old_txt = str(sp.get("beginning") or "")
        for k_clr in ("beginning_image", "beginning_src", "beginning_status", "beginning_caption", "beginning_dialogue"):
            sp.pop(k_clr, None)
        sp["beginning"] = ""
        sp["beginning_verified"] = False
        proj["stage"] = "spine_beginning"
        save_project(proj, sandbox=sandbox)
        return old_txt, "undone"

    if target == "spine:end":
        old_txt = str(sp.get("end") or "")
        for k_clr in ("end_image", "end_src", "end_status", "end_caption", "end_dialogue"):
            sp.pop(k_clr, None)
        sp["end"] = ""
        sp["end_verified"] = False
        proj["stage"] = "spine_end"
        save_project(proj, sandbox=sandbox)
        return old_txt, "undone"

    if target.startswith("spine:middle_"):
        removed = remove_art_beat(proj, target, sandbox=sandbox)
        proj["stage"] = "spine_middle"
        save_project(proj, sandbox=sandbox)
        return removed, "undone"

    if target.startswith("panel:"):
        removed = remove_art_beat(proj, target, sandbox=sandbox)
        return removed, "undone"

    return "", "noop"


def remove_art_beat(proj: dict[str, Any], target: str, sandbox: bool | None = None) -> str:
    """Removes an accidental/unwanted middle twist or panel so a book never gets permanently stuck."""
    sp = proj.setdefault("spine", {})
    if target.startswith("spine:middle_"):
        try:
            idx = int(target.split("_", 1)[1])
        except ValueError:
            return ""
        mbs = list(middle_beats_list(sp))
        if 0 <= idx < len(mbs):
            removed = mbs.pop(idx).get("text", "")
            sp["middle_beats"] = mbs
            sp["middle"] = " ".join(b.get("text", "") for b in mbs)
            if proj.get("stage") == "drafting_panels" and not all_panels(proj) and not mbs:
                proj["stage"] = "spine_middle"
            save_project(proj, sandbox=sandbox)
            return removed
    if target.startswith("panel:"):
        try:
            pnum = int(target.split(":", 1)[1])
        except ValueError:
            return ""
        for ch in proj.get("chapters") or []:
            plist = ch.get("panels") or []
            for i, p in enumerate(plist):
                if p.get("number") == pnum:
                    removed = plist.pop(i).get("caption", "")
                    # Renumber subsequent panels cleanly
                    num = 1
                    for c2 in proj.get("chapters") or []:
                        for p2 in c2.get("panels") or []:
                            p2["number"] = num
                            num += 1
                    save_project(proj, sandbox=sandbox)
                    return removed
    return ""


def chronological_scene_context(proj: dict[str, Any], target: str = "") -> str:
    """Builds strictly CHRONOLOGICAL character & setting context up to `target` (NEVER leaking future Finale settings like 'on the moon' into earlier Earth scenes!)."""
    sp = proj.get("spine") or {}
    bits: list[str] = []
    if proj.get("characters"):
        bits.append(f"Characters: {proj['characters'][:180]}")
    beg = (sp.get("beginning") or "").strip()
    mbs = middle_beats_list(sp)

    if target == "spine:beginning":
        return " | ".join(bits)

    if target == "spine:end":
        if beg:
            bits.append(f"Story start: {beg[:180]}")
        if mbs:
            bits.append(f"Earlier twist: {mbs[-1].get('text', '')[:160]}")
        bits.append("Draw the BIG FINALE scene described above.")
        return " | ".join(bits)

    if target.startswith("spine:middle_"):
        try:
            idx = int(target.split("_", 1)[1])
        except ValueError:
            idx = len(mbs) - 1
        if beg:
            bits.append(f"Story start (initial setting/characters): {beg[:180]}")
        prev_twists = [b.get("text", "").strip() for b in mbs[: max(0, idx)] if b.get("text")]
        if prev_twists:
            bits.append(f"Immediately preceding scene right before this moment: {' -> '.join(prev_twists[-2:])[:260]}")
        bits.append("CRITICAL: Draw ONLY this current middle moment in its CURRENT setting right after the preceding scene (do NOT jump ahead to future finale locations!).")
        return " | ".join(bits)

    # Panel context: chronological kickoff + middle twists + preceding panels (never future finale unless at end)
    if beg:
        bits.append(f"Story start: {beg[:160]}")
    panels = all_panels(proj)
    pnum = len(panels)
    if target.startswith("panel:"):
        try:
            pnum = int(target.split(":", 1)[1])
        except ValueError:
            pass
    prev_panels = [p.get("caption", "") for p in panels if p.get("number", 0) < pnum and p.get("caption")]
    if prev_panels:
        bits.append(f"Immediately preceding panel(s): {' -> '.join(prev_panels[-2:])[:240]}")
    elif mbs:
        bits.append(f"Plot context: {mbs[0].get('text', '')[:180]}")
    bits.append("Draw ONLY this exact panel's current moment and current location.")
    return " | ".join(bits)


def recent_reference_media_ids(proj: dict[str, Any], limit: int = 2, target: str = "") -> list[str]:
    """Returns reference images ONLY from chronologically earlier or matching beats—NEVER leaking future Finale art (`end_image`) into Middle Twists or early Chapters!"""
    sp = proj.get("spine") or {}
    mbs = middle_beats_list(sp)
    beg_id = [sp["beginning_image"]] if sp.get("beginning_image") else []

    if target == "spine:beginning":
        return []
    if target == "spine:end":
        mbeat_imgs = [b["image"] for b in mbs if b.get("image")]
        return (beg_id + mbeat_imgs)[-limit:]
    if target.startswith("spine:middle_"):
        try:
            idx = int(target.split("_", 1)[1])
        except ValueError:
            idx = len(mbs)
        prior_mids = [b["image"] for b in mbs[: max(0, idx)] if b.get("image")]
        return (beg_id + prior_mids)[-limit:]
    if target.startswith("panel:"):
        try:
            pnum = int(target.split(":", 1)[1])
        except ValueError:
            pnum = 999999
        prior_mids = [b["image"] for b in mbs if b.get("image")]
        prior_panels = [p["image"] for p in all_panels(proj) if p.get("image") and p.get("number", 0) < pnum]
        return (beg_id + prior_mids + prior_panels)[-limit:]

    mbeat_imgs = [b["image"] for b in mbs if b.get("image")]
    panel_mids = [p["image"] for p in all_panels(proj) if p.get("image")]
    combined = beg_id + mbeat_imgs + panel_mids
    return combined[-limit:]


def set_spine_beat_text(sp: dict[str, Any], beat: str, raw_text: str) -> None:
    """Sets `beginning` or `end` text on `sp` AND extracts initial `caption` + `dialogue` speech bubbles."""
    cap, bubs = extract_dialogue(raw_text)
    sp[beat] = raw_text
    sp[f"{beat}_caption"] = cap
    sp[f"{beat}_dialogue"] = bubs
    sp[f"{beat}_caption_edited"] = False


def apply_comic_lettering(
    proj: dict[str, Any],
    target: str,
    action: str,
    data: dict[str, Any],
    sandbox: bool | None = None,
) -> bool:
    """Applies speech/shout/thought bubble or caption edits to `spine:...` or `panel:...` targets and saves."""
    sp = proj.setdefault("spine", {})
    changed = False
    if target in ("spine:beginning", "spine:end"):
        beat = target.split(":", 1)[1]
        if f"{beat}_caption" not in sp and f"{beat}_dialogue" not in sp:
            cap0, bub0 = extract_dialogue(sp.get(beat) or "")
            sp[f"{beat}_caption"] = cap0
            sp[f"{beat}_dialogue"] = bub0
        holder = {
            "caption": sp.get(f"{beat}_caption", sp.get(beat, "")),
            "dialogue": sp.get(f"{beat}_dialogue") or [],
            "caption_edited": bool(sp.get(f"{beat}_caption_edited")),
        }
        changed = mutate_lettering_holder(holder, action, data)
        if changed:
            sp[f"{beat}_caption"] = holder["caption"]
            sp[f"{beat}_dialogue"] = holder["dialogue"]
            sp[f"{beat}_caption_edited"] = holder.get("caption_edited", False)
    elif target.startswith("spine:middle_"):
        try:
            idx = int(target.split("_", 1)[1])
        except ValueError:
            return False
        mbs = middle_beats_list(sp)
        if 0 <= idx < len(mbs):
            changed = mutate_lettering_holder(mbs[idx], action, data)
            if changed:
                sp["middle_beats"] = mbs
    elif target.startswith("panel:"):
        try:
            pnum = int(target.split(":", 1)[1])
        except ValueError:
            return False
        for ch in proj.get("chapters") or []:
            for p in ch.get("panels") or []:
                if p.get("number") == pnum:
                    changed = mutate_lettering_holder(p, action, data)
                    break

    if changed:
        save_project(proj, sandbox=sandbox)
    return changed


def project_ui_payload(proj: dict[str, Any]) -> dict[str, Any]:
    """Formats the full project state (Plot Board + Art Styles + Chapters + Panels + PDF URL) for the browser Canvas."""
    sp = dict(proj.get("spine") or {})
    sp["middle_beats"] = middle_beats_list(sp)
    for beat_k in ("beginning", "end"):
        if sp.get(beat_k):
            if f"{beat_k}_caption" not in sp and f"{beat_k}_dialogue" not in sp:
                c0, b0 = extract_dialogue(sp.get(beat_k) or "")
                sp[f"{beat_k}_caption"] = c0
                sp[f"{beat_k}_dialogue"] = b0
            else:
                sp.setdefault(f"{beat_k}_caption", sp.get(beat_k) or "")
                sp[f"{beat_k}_dialogue"] = _normalize_bubbles(sp.get(f"{beat_k}_dialogue"))
    norm_chapters = []
    for ch in proj.get("chapters") or []:
        c_copy = dict(ch)
        p_list = []
        for p in ch.get("panels") or []:
            p_copy = dict(p)
            p_copy["dialogue"] = _normalize_bubbles(p.get("dialogue"))
            p_list.append(p_copy)
        c_copy["panels"] = p_list
        norm_chapters.append(c_copy)
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
        "jam_beats": proj.get("jam_beats") or [],
        "tutorial_topic": proj.get("tutorial_topic") or "",
        "cover_src": f"/media/{proj['cover_image']}.jpg" if proj.get("cover_image") else None,
        "codex_sketch_src": proj.get("codex_sketch_src"),
        "codex_sketch_status": proj.get("codex_sketch_status"),
        "codex_sketch_caption": proj.get("codex_sketch_caption", ""),
        "codex_draft_sentences": proj.get("codex_draft_sentences", []),
        "chapters": norm_chapters,
        "panel_count": total_panels(proj),
        "target_panels": proj.get("target_panels", 100),
        "sandbox": bool(proj.get("sandbox")),
        "pdf_url": f"/api/project/{proj['id']}/pdf",
        "web_url": f"/project/{proj['id']}",
    }
