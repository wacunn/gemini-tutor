"""Gemini tutor server.  Run:  ./run.sh   then open http://localhost:8787"""

from __future__ import annotations

import asyncio
import html
import json
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.responses import FileResponse, HTMLResponse
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
    rec = load_learner()
    return {
        "has_key": bool(api_key()),
        "name": rec.get("name"),
        "grade": rec.get("grade"),
        "parent_title": rec.get("parent_title"),
        "voice": rec.get("voice"),
        "voices": VOICES,
        "sessions": len(rec.get("sessions", [])),
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


@app.post("/api/settings")
def settings(body: SettingsIn):
    rec = load_learner()
    for k in ("voice", "name", "parent_title"):
        v = getattr(body, k)
        if v:
            rec[k] = v.strip()
    save_learner(rec)
    return {"ok": True}


# ---------- parent view ----------

@app.get("/api/parent")
def parent_data():
    rec = load_learner()
    sessions = []
    for s in reversed(rec.get("sessions", [])):
        sessions.append({**s, "review": read_review(s["id"])})
    return {
        "learner": rec,
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
