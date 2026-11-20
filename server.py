"""Gemini tutor server.  Run:  ./run.sh   then open http://localhost:8787"""

from __future__ import annotations

import asyncio
import html
import json
import re
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from tutor.config import ROOT, VOICES, api_key, ensure_dirs, save_api_key
from tutor.live import TutorSession
from tutor.record import (
    list_activities,
    list_pieces,
    load_activity,
    load_learner,
    load_piece,
    now_iso,
    read_review,
    read_session,
    save_learner,
)
from tutor.review import review_session

ensure_dirs()
STATIC = ROOT / "static"
app = FastAPI(title="Gemini Tutor")


@app.middleware("http")
async def no_cache(request, call_next):
    resp = await call_next(request)
    resp.headers["Cache-Control"] = "no-store"
    return resp


app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.get("/")
def index():
    return FileResponse(str(STATIC / "index.html"))


@app.get("/parent")
def parent_page():
    return FileResponse(str(STATIC / "parent.html"))


# ---------- setup / state ----------

class SetupIn(BaseModel):
    name: str
    grade: int = 3
    parent_title: str = "Dad"
    voice: str = "Umbriel"
    note: Optional[str] = None
    api_key: Optional[str] = None


@app.get("/api/state")
def state():
    from tutor.projects import list_projects

    rec = load_learner()
    projs = [
        {
            "id": p["id"],
            "title": p.get("title", "Untitled"),
            "kind": p.get("kind", ""),
            "panel_count": p.get("panel_count", 0),
            "pdf_url": f"/api/project/{p['id']}/pdf",
        }
        for p in list_projects()[:6]
    ]
    return {
        "has_key": bool(api_key()),
        "name": rec.get("name"),
        "grade": rec.get("grade"),
        "parent_title": rec.get("parent_title"),
        "voice": rec.get("voice"),
        "voices": VOICES,
        "sessions": len(rec.get("sessions", [])),
        "projects": projs,
        "pieces": [{"id": p["id"], "title": p["title"], "audience": p.get("audience", "")} for p in list_pieces()[:12]],
    }


@app.post("/api/setup")
def setup(body: SetupIn):
    if not body.name.strip():
        raise HTTPException(400, "Name is required")
    rec = load_learner()
    rec["name"] = body.name.strip()
    rec["grade"] = max(1, min(12, body.grade))
    rec["parent_title"] = body.parent_title.strip() or "Dad"
    rec["voice"] = body.voice or "Umbriel"
    if body.note and body.note.strip():
        rec.setdefault("parent_notes", []).append({"date": now_iso(), "note": body.note.strip()})
    save_learner(rec)
    if body.api_key and body.api_key.strip():
        save_api_key(body.api_key)
    return {"ok": True}


class KeyIn(BaseModel):
    api_key: str


@app.post("/api/key")
def set_key(body: KeyIn):
    try:
        save_api_key(body.api_key)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


class NoteIn(BaseModel):
    note: str


@app.post("/api/parent-note")
def parent_note(body: NoteIn):
    rec = load_learner()
    rec.setdefault("parent_notes", []).append({"date": now_iso(), "note": body.note.strip()})
    save_learner(rec)
    return {"ok": True}


class SettingsIn(BaseModel):
    voice: Optional[str] = None
    name: Optional[str] = None
    parent_title: Optional[str] = None
    grade: Optional[int] = None


@app.post("/api/settings")
def settings(body: SettingsIn):
    rec = load_learner()
    for k in ("voice", "name", "parent_title"):
        v = getattr(body, k)
        if v:
            rec[k] = v.strip()
    if body.grade is not None:
        rec["grade"] = max(1, min(12, body.grade))
    save_learner(rec)
    return {"ok": True}


# ---------- parent view ----------

@app.get("/api/parent")
def parent_data():
    from tutor.curriculum_tracker import ensure_report_card, format_report_for_ui
    from tutor.projects import list_projects

    rec = load_learner()
    rc = ensure_report_card(rec)
    sessions = []
    for s in reversed(rec.get("sessions", [])):
        sessions.append({**s, "review": read_review(s["id"])})
    return {
        "learner": rec,
        "report_card": format_report_for_ui(rc),
        "projects": list_projects(),
        "sessions": sessions,
        "activities": list_activities(),
        "pieces": list_pieces(),
    }


_prewarm_running = False


def _prewarm_job():
    global _prewarm_running
    try:
        from tutor.thinking import invent
        import json as _json, time as _time

        rec = load_learner()
        plan = (rec.get("model") or {}).get("plan_next_session") or ""
        situation = (
            "A session is about to start. Generate strong opening activities he can start within seconds, "
            "using what we already know about him (don't ask him what he likes). "
            + (f"Suggested plan from the last review: {plan}" if plan else "This is the first session.")
        )
        out = invent(situation, "complete sentences", rec, [a.get("title", "") for a in list_activities()[:8]])
        from tutor.config import DATA

        (DATA / "opening_ideas.json").write_text(
            _json.dumps({"made": _time.time(), "sessions": len(rec.get("sessions", [])), "ideas": out.get("ideas", [])}, indent=2)
        )
    except Exception as e:
        print("prewarm failed:", e)
    finally:
        _prewarm_running = False


@app.post("/api/prewarm")
def prewarm():
    """Called when the start screen loads: get opening ideas ready before he types anything."""
    global _prewarm_running
    import json as _json, threading, time as _time
    from tutor.config import DATA

    if not api_key() or not load_learner().get("name"):
        return {"ok": False}
    f = DATA / "opening_ideas.json"
    if f.exists():
        try:
            d = _json.loads(f.read_text())
            if _time.time() - d.get("made", 0) < 6 * 3600 and d.get("sessions") == len(load_learner().get("sessions", [])):
                return {"ok": True, "cached": True}
        except Exception:
            pass
    if not _prewarm_running:
        _prewarm_running = True
        threading.Thread(target=_prewarm_job, daemon=True).start()
    return {"ok": True, "cached": False}


@app.get("/api/version")
def version_info():
    from tutor import updater

    return {"version": updater.local_version(), "repo": updater.REPO}


@app.get("/api/update/check")
async def update_check():
    from tutor import updater

    return await asyncio.to_thread(updater.check)


@app.post("/api/update/apply")
async def update_apply():
    from tutor import updater

    try:
        res = await asyncio.to_thread(updater.apply)
    except Exception as e:
        raise HTTPException(500, f"Update failed: {e}")
    updater.restart_soon()
    return res


@app.post("/api/quit")
def quit_app():
    from tutor import updater

    updater.quit_soon()
    return {"ok": True}


@app.post("/api/clear-history")
def clear_history():
    """Clears test/past session history and learned model while keeping child setup, parent notes, and API key."""
    import shutil
    from tutor.config import ACTIVITIES, DATA, PIECES, PROJECTS, SESSIONS
    from tutor.curriculum_tracker import default_report_card
    from tutor.record import DEFAULT_LEARNER

    rec = load_learner()
    rec["sessions"] = []
    rec["model"] = json.loads(json.dumps(DEFAULT_LEARNER["model"]))
    rec["report_card"] = default_report_card()
    save_learner(rec)
    for folder in (SESSIONS, PIECES, ACTIVITIES, PROJECTS):
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)
            folder.mkdir(parents=True, exist_ok=True)
    oi = DATA / "opening_ideas.json"
    if oi.exists():
        oi.unlink()
    return {"ok": True}


@app.get("/api/live")
def live_state():
    """Latest critic/tracker/stats for the most recent session (parent's live view)."""
    from tutor.live import LIVE

    if not LIVE:
        return {"active": False}
    sid = list(LIVE.keys())[-1]
    return {"active": not LIVE[sid].get("ended"), "session_id": sid, **LIVE[sid]}


@app.get("/api/session/{sid}")
def session_events(sid: str):
    return {"events": read_session(sid), "review": read_review(sid)}


@app.post("/api/review/{sid}")
async def run_review(sid: str):
    try:
        return await asyncio.to_thread(review_session, sid)
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/activity/{aid}", response_class=HTMLResponse)
def activity_page(aid: str):
    act = load_activity(aid)
    if not act:
        raise HTTPException(404)
    return HTMLResponse(act["html"])


@app.get("/media/{mid}.jpg")
def media_file(mid: str):
    from tutor.media import media_path

    p = media_path(mid)
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(str(p), media_type="image/jpeg")


@app.get("/api/project/{pid}/pdf")
async def project_pdf(pid: str):
    from tutor.pdf_book import build_project_pdf
    from tutor.projects import load_project

    proj = load_project(pid)
    if not proj:
        raise HTTPException(404, "Project not found")
    pdf_bytes = await asyncio.to_thread(build_project_pdf, proj)
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", proj.get("title") or "Comic_Book").strip("_") or "Comic_Book"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.pdf"'},
    )


@app.get("/project/{pid}", response_class=HTMLResponse)
def project_page(pid: str):
    from tutor.projects import load_project, total_panels

    proj = load_project(pid)
    if not proj:
        raise HTTPException(404, "Project not found")
    sp = proj.get("spine") or {}
    spine_html = ""
    if sp.get("beginning") or sp.get("middle") or sp.get("end"):
        spine_html = (
            "<div class='spine'>"
            f"<div><strong>Act I · Beginning:</strong> {html.escape(sp.get('beginning') or '…')}</div>"
            f"<div><strong>Act II · Middle:</strong> {html.escape(sp.get('middle') or '…')}</div>"
            f"<div><strong>Act III · End:</strong> {html.escape(sp.get('end') or '…')}</div>"
            "</div>"
        )
    ch_blocks = ""
    for ch in proj.get("chapters") or []:
        cells = ""
        for pp in ch.get("panels") or []:
            img = f"<img src='/media/{pp['image']}.jpg'>" if pp.get("image") else "<div class='blank'>Rendering…</div>"
            bubs = "".join(
                f"<div class='bub'><strong>{html.escape(b.get('speaker',''))}{': ' if b.get('speaker') else ''}</strong>{html.escape(b.get('text',''))}</div>"
                for b in (pp.get("dialogue") or [])
            )
            cells += f"<figure><div class='art-wrap'><span class='pno'>{pp.get('number','')}</span>{img}{bubs}</div><figcaption>{html.escape(pp.get('caption') or '')}</figcaption></figure>"
        if cells:
            ch_blocks += f"<h2>{html.escape(ch.get('title', 'Chapter'))}</h2><div class='comic'>{cells}</div>"
    aud = f"<div class='for'>For {html.escape(proj['audience'])}</div>" if proj.get("audience") else ""
    return HTMLResponse(f"""<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(proj.get('title','Book'))}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{{font-family:'Google Sans Text',-apple-system,sans-serif;max-width:960px;margin:40px auto;padding:0 24px 64px;color:#1d1d1f;background:#faf9f6;line-height:1.6}}
.top{{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap}}
h1{{font-size:36px;margin:0 0 4px}} h2{{margin:32px 0 12px;font-size:22px}}
.by{{color:#555}} .for{{color:#777;font-style:italic;margin-bottom:20px}}
.btn{{display:inline-block;background:#1a56c4;color:#fff;text-decoration:none;padding:10px 20px;border-radius:999px;font-weight:600}}
.spine{{background:#fff;border:2px solid #222;border-radius:14px;padding:16px 20px;margin:20px 0;display:grid;gap:8px}}
.comic{{display:grid;grid-template-columns:repeat(2,1fr);gap:16px;margin:16px 0}}
.comic figure{{margin:0;border:4px solid #111;background:#fff;display:flex;flex-direction:column}}
.art-wrap{{position:relative;aspect-ratio:4/3;background:#eee;overflow:hidden}}
.art-wrap img{{width:100%;height:100%;object-fit:cover;display:block}}
.pno{{position:absolute;top:0;left:0;background:#111;color:#fff;padding:3px 10px;font-weight:700;font-size:14px;z-index:2}}
.bub{{position:relative;z-index:2;margin:8px 10px 0 44px;background:#fff;border:2.5px solid #111;border-radius:14px;padding:6px 12px;font-size:14px;display:inline-block;box-shadow:2px 2px 0 #111}}
.blank{{display:grid;place-items:center;height:100%;color:#888}}
.comic figcaption{{padding:10px 14px;background:#faf6e8;font-size:16px;border-top:3px solid #111;flex:1}}
@media(max-width:700px){{.comic{{grid-template-columns:1fr}}}}
</style></head><body>
<div class="top"><div><h1>{html.escape(proj.get('title','Untitled'))}</h1>
<div class="by">Written &amp; Created by {html.escape(proj.get('author',''))} · {total_panels(proj)} panel(s)</div>{aud}</div>
<a class="btn" href="/api/project/{html.escape(proj['id'])}/pdf">Download PDF Book</a></div>
{spine_html}{ch_blocks or "<p>Story Spine started—panels appear here as you write!</p>"}
</body></html>""")


@app.get("/api/piece/{pid}/pdf")
async def piece_pdf(pid: str):
    from tutor.pdf_book import build_project_pdf

    p = load_piece(pid)
    if not p:
        raise HTTPException(404)
    comic = p.get("comic") or {}
    pseudo_proj = {
        "id": p["id"],
        "kind": "quick_strip",
        "title": p.get("title", "Comic"),
        "author": p.get("author", ""),
        "audience": p.get("audience", ""),
        "spine": {},
        "chapters": [{"number": 1, "title": p.get("title", "Part 1"), "panels": [
            {"number": idx + 1, "caption": cp.get("caption", ""), "dialogue": [], "image": cp.get("image")}
            for idx, cp in enumerate(comic.get("panels") or [])
        ]}],
    }
    pdf_bytes = await asyncio.to_thread(build_project_pdf, pseudo_proj)
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", p.get("title") or "Piece").strip("_") or "Piece"
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{safe_name}.pdf"'})


@app.get("/piece/{pid}", response_class=HTMLResponse)
def piece_page(pid: str):
    p = load_piece(pid)
    if not p:
        raise HTTPException(404)
    paras = "".join(f"<p>{html.escape(seg['text'])}</p>" for seg in p.get("segments", []) if seg.get("text"))
    comic_html = ""
    comic = p.get("comic")
    if comic and any(pp.get("image") for pp in comic.get("panels", [])):
        cells = ""
        for pp in comic["panels"]:
            img = f"<img src='/media/{pp['image']}.jpg'>" if pp.get("image") else "<div class='blank'></div>"
            cells += f"<figure>{img}<figcaption>{html.escape(pp.get('caption') or '')}</figcaption></figure>"
        comic_html = f"<div class='comic'>{cells}</div>"
    aud = f"<div class='for'>For {html.escape(p['audience'])}</div>" if p.get("audience") else ""
    return HTMLResponse(f"""<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(p['title'])}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{{font-family:Charter,'Iowan Old Style',Georgia,serif;max-width:900px;margin:48px auto;padding:0 24px;color:#1d1d1f;line-height:1.65;font-size:20px}}
h1{{font-size:36px;margin:0 0 4px}} .by{{color:#555}} .for{{color:#777;font-style:italic;margin-bottom:28px}}
.comic{{display:grid;grid-template-columns:repeat(2,1fr);gap:14px;margin:24px 0}}
.comic figure{{margin:0;border:3px solid #111;background:#fff}} .comic img{{width:100%;display:block}}
.comic .blank{{aspect-ratio:4/3;background:#eee}}
.comic figcaption{{padding:8px 12px;font-family:'Comic Neue','Trebuchet MS',sans-serif;font-size:18px;border-top:3px solid #111}}
@media print{{body{{margin:0}}}}
</style></head><body>
<h1>{html.escape(p['title'])}</h1><div class="by">by {html.escape(p.get('author',''))}</div>{aud}{comic_html}{paras}
</body></html>""")


# ---------- live session ----------

@app.websocket("/ws/live")
async def ws_live(ws: WebSocket):
    await ws.accept()
    test_mode = ws.query_params.get("test") == "1"
    session = TutorSession(ws, test_mode=test_mode)
    try:
        await session.run()
    finally:
        sid = session.id
        if not test_mode:
            # Review in the background so the learner model is ready for next time.
            async def _bg():
                try:
                    await asyncio.to_thread(review_session, sid)
                except Exception as e:
                    print("review failed:", e)

            asyncio.create_task(_bg())
        try:
            await ws.close()
        except Exception:
            pass
