"""Child-Safety Watching Agent, Conversation Topic Reporter & Protective 'Bug' Circuit Breaker.

Designed specifically for an 8-year-old learner:
1. `instant_screen(kid_text, tutor_text)`: 0ms synchronous pre-gate catching unmistakable red flags
   (self-harm, abuse/secrecy, sexual/adult content, severe real-world harm/weapons/drugs, or AI boundary drift)
   BEFORE any LLM or image generator runs—while never false-alarming on normal 8-year-old potty/cartoon humor.
2. `watch_exchange(...)`: Independent Gemini Watching Agent inspecting BOTH the child's inputs and the AI's
   responses on every turn:
   - Logs a clear **Conversation Topics & Themes** report per session for the Parent Page.
   - Flags `"watch"` items (e.g. school stress, sadness, bullying mentions, intense themes) for parents to see.
   - Triggers `"nervous_stop"` whenever a conversation makes the guardian nervous for an 8-year-old ->
     causing the tutor app to calmly "hit a little saving bug (ERR-G42)" and pause until a parent checks `/parent`.
"""

from __future__ import annotations

import json
import re
import threading
import time
from typing import Any

from google.genai import types

from .config import DATA, FALLBACK_MODEL, FAST_MODEL, LITE_MODEL, genai_client
from .record import now_iso

GUARDIAN_FILE = DATA / "guardian_log.json"
_LOCK = threading.RLock()

# 0ms high-precision lexical red flags (deliberately excludes harmless 8yo potty/cartoon words like poop/fart/zombie/sword)
_INSTANT_KID_RED_FLAGS: list[tuple[str, str, re.Pattern[str]]] = [
    (
        "self_harm",
        "Self-harm or suicidal phrase detected in student input.",
        re.compile(
            r"\b(kill\s+myself|want\s+to\s+die|wanna\s+die|wish\s+i\s+(?:was|were)\s+dead|hurt\s+myself|"
            r"cut\s+myself|hang\s+myself|end\s+my\s+life|better\s+off\s+dead|commit\s+suicide|suicide)\b",
            re.I,
        ),
    ),
    (
        "secrecy_or_harm",
        "Secrecy-from-parents or personal harm disclosure detected.",
        re.compile(
            r"\b(don'?t\s+tell\s+(?:my\s+)?(?:mom|dad|parents)|keep\s+this\s+a\s+secret\s+from\s+(?:mom|dad|my\s+parents)|"
            r"touched\s+my\s+private|someone\s+is\s+hurting\s+me|he\s+hits\s+me\s+at\s+home)\b",
            re.I,
        ),
    ),
    (
        "sexual_adult",
        "Explicit sexual or adult term detected.",
        re.compile(
            r"\b(porn|porno|pornography|sex\s+with|having\s+sex|naked\s+(?:girl|boy|woman|man|people|pictures)|"
            r"nudes|boobs|penis|vagina|cock|pussy|horny|rape|raped|molest|onlyfans|stripper)\b",
            re.I,
        ),
    ),
    (
        "severe_danger",
        "Real-world weapon, poison, or hard-drug phrase detected.",
        re.compile(
            r"\b(how\s+to\s+make\s+a\s+bomb|bring\s+a\s+gun\s+to\s+school|school\s+shooting|shoot\s+up\s+the\s+school|"
            r"drink\s+bleach|cocaine|heroin|fentanyl|crystal\s+meth)\b",
            re.I,
        ),
    ),
]

_INSTANT_AI_RED_FLAGS = re.compile(
    r"\b(keep\s+this\s+(?:just\s+)?between\s+us|don'?t\s+tell\s+your\s+(?:mom|dad|parents)|"
    r"i(?:'m|\s+am)\s+your\s+(?:best\s+friend|secret\s+friend)|porn|sex\s+with|suicide)\b",
    re.I,
)

WATCHER_SYSTEM = """You are the independent Child-Safety & Conversation-Topic Watching Agent overseeing an AI writing tutor working with {name}, an 8-year-old child (Grade {grade}).

Your two jobs on every turn:
1. TOPIC AWARENESS FOR PARENTS:
   - Identify 1 to 4 concise topic tags (`topics`, e.g. `["gassy cat", "alien spaceship", "potty humor"]` or `["school recess", "Minecraft dragon"]`).
   - Write `topic_summary`: 1 clear, factual sentence telling the parent what {name} has been writing/talking about in this session so far.

2. 8-YEAR-OLD SAFETY & WELLBEING CLASSIFICATION (`level`: `"ok"` | `"watch"` | `"nervous_stop"`):
   - `"ok"`: Normal 8-year-old creative play, silly gross-out/potty humor (poop, farts, barf, burps, butts), cartoon slapstick, aliens/monsters/zombies/Minecraft/weapons in clear fantasy context, animals, science, or normal homework pushback ("this is boring"). Do NOT overreact to harmless 8-year-old potty humor!
   - `"watch"`: Worth flagging quietly on the Parent Page WITHOUT interrupting the session—e.g. {name} mentions real-life sadness, loneliness, being bullied/mean kids, feeling stupid/hating himself at school, scary nightmares, family worries, or story violence getting unusually dark/grisly.
   - `"nervous_stop"`: Trigger an immediate protective "App Bug" pause so Mom/Dad checks in! Use `"nervous_stop"` whenever ANY of these appear in EITHER the child's input OR the AI tutor's output:
     * Self-harm, wanting to die, hurting oneself, or hurting real people/animals.
     * Sexual, explicit, adult, romantic, or body-inappropriate content for an 8-year-old.
     * Real-world abuse, threats, someone hurting/scaring the child, or requests to keep secrets from parents.
     * Real-world dangerous dares, self-poisoning, real weapons, illegal drugs/substances.
     * AI boundary drift: the AI acting like a human friend/confidant, asking private personal questions, or saying anything inappropriate for an 8-year-old.
     * Rule of thumb: if a responsible adult watching an 8-year-old would feel genuinely nervous letting this conversation continue unsupervised, choose `"nervous_stop"`.

Return STRICT JSON:
{{"level": "ok|watch|nervous_stop",
  "category": "none|potty_humor|fantasy_action|emotional_watch|bullying_social|dark_theme|self_harm|sexual_adult|real_world_harm|dangerous_act|ai_boundary_drift",
  "topics": ["short tag 1", "short tag 2"],
  "topic_summary": "1-sentence summary of what the child is talking/writing about in this session",
  "parent_note": "empty if level=='ok'; otherwise 1 clear factual sentence for the parent explaining what came up"}}"""


def _default_store() -> dict[str, Any]:
    return {
        "active_bug_lock": None,
        "sandbox_bug_lock": None,
        "turns_checked": 0,
        "alerts": [],
        "session_topics": {},
    }


def _load_unlocked() -> dict[str, Any]:
    if not GUARDIAN_FILE.exists():
        return _default_store()
    try:
        d = json.loads(GUARDIAN_FILE.read_text(encoding="utf-8"))
        if isinstance(d, dict):
            base = _default_store()
            base.update(d)
            return base
    except Exception:
        pass
    return _default_store()


def _save_unlocked(data: dict[str, Any]) -> None:
    GUARDIAN_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = GUARDIAN_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(GUARDIAN_FILE)


def get_bug_lock(sandbox: bool = False) -> dict[str, Any] | None:
    with _LOCK:
        d = _load_unlocked()
        key = "sandbox_bug_lock" if sandbox else "active_bug_lock"
        val = d.get(key)
        return val if isinstance(val, dict) else None


def clear_bug_lock(sandbox: bool | None = None) -> None:
    """Called by parent on `/parent` to clear the protective bug lock after reviewing."""
    with _LOCK:
        d = _load_unlocked()
        if sandbox is None or sandbox is False:
            d["active_bug_lock"] = None
        if sandbox is None or sandbox is True:
            d["sandbox_bug_lock"] = None
        _save_unlocked(d)


def record_protective_stop(
    session_id: str,
    category: str,
    reason: str,
    kid_quote: str = "",
    tutor_quote: str = "",
    sandbox: bool = False,
) -> dict[str, Any]:
    alert = {
        "time": now_iso(),
        "session_id": session_id,
        "code": "ERR-G42",
        "level": "nervous_stop",
        "category": category,
        "reason": reason,
        "kid_quote": (kid_quote or "")[:280],
        "tutor_quote": (tutor_quote or "")[:280],
        "sandbox": sandbox,
    }
    with _LOCK:
        d = _load_unlocked()
        lock_key = "sandbox_bug_lock" if sandbox else "active_bug_lock"
        d[lock_key] = alert
        d["alerts"] = ([alert] + (d.get("alerts") or []))[:50]
        st = d.setdefault("session_topics", {}).setdefault(
            session_id,
            {
                "session_id": session_id,
                "started": now_iso(),
                "updated": now_iso(),
                "sandbox": sandbox,
                "topics": [],
                "summary": "",
                "status": "nervous_stop",
                "notes": [],
                "samples": [],
            },
        )
        st["updated"] = now_iso()
        st["status"] = "nervous_stop"
        st.setdefault("notes", []).append(
            {"time": alert["time"], "level": "nervous_stop", "category": category, "note": reason, "quote": kid_quote[:200]}
        )
        _save_unlocked(d)
    return alert


def instant_screen(
    session_id: str,
    kid_text: str = "",
    tutor_text: str = "",
    sandbox: bool = False,
) -> dict[str, Any] | None:
    """0ms synchronous pre-screen. Returns a protective-stop alert dict if tripped, else None."""
    kt = (kid_text or "").strip()
    tt = (tutor_text or "").strip()
    if kt:
        for cat, reason, pat in _INSTANT_KID_RED_FLAGS:
            if pat.search(kt):
                return record_protective_stop(session_id, cat, reason, kid_quote=kt, tutor_quote=tt, sandbox=sandbox)
    if tt and _INSTANT_AI_RED_FLAGS.search(tt):
        return record_protective_stop(
            session_id,
            "ai_boundary_drift",
            "AI output crossed child-safety / secrecy boundary.",
            kid_quote=kt,
            tutor_quote=tt,
            sandbox=sandbox,
        )
    return None


def _local_topic_extract(kid_text: str, existing_topics: list[str]) -> list[str]:
    """0ms fallback topic tagger when API is rate-limited so Parent Page always gets topics."""
    words = [w.lower() for w in re.findall(r"[A-Za-z]{4,}", kid_text or "")]
    stop = {
        "that", "this", "with", "from", "have", "what", "when", "where", "because", "then", "they",
        "them", "their", "there", "whose", "into", "about", "after", "before", "finally", "main",
        "character", "story", "dylan", "looks", "right", "next", "part", "picture", "sentence",
    }
    picks = list(existing_topics)
    for w in words:
        if w not in stop and w not in picks:
            picks.append(w)
        if len(picks) >= 5:
            break
    return picks[:5]


def watch_exchange(
    session_id: str,
    rec: dict[str, Any],
    kid_text: str,
    tutor_text: str,
    recent_context: str = "",
    sandbox: bool = False,
) -> dict[str, Any]:
    """Independent Watching Agent: logs session topics & checks 8-year-old safety on every turn."""
    from . import blackboard

    # 1. Run 0ms instant screen first
    inst = instant_screen(session_id, kid_text, tutor_text, sandbox=sandbox)
    if inst:
        return inst

    name = rec.get("name") or "the student"
    grade = rec.get("grade", 3)
    kt = (kid_text or "").strip()
    tt = (tutor_text or "").strip()

    out_level = "ok"
    out_cat = "none"
    out_topics: list[str] = []
    out_summary = ""
    out_note = ""

    if blackboard.QUOTA.allow_background() and (kt or tt):
        sys_inst = WATCHER_SYSTEM.format(name=name, grade=grade)
        prompt = (
            f"RECENT SESSION CONTEXT:\n{recent_context[-900:] or '(start of session)'}\n\n"
            f"CHILD ({name}, age ~8) LATEST INPUT:\n{kt or '(none)'}\n\n"
            f"AI TUTOR LATEST OUTPUT:\n{tt or '(none)'}"
        )
        try:
            client = genai_client(timeout_ms=10000)
            for model in (LITE_MODEL, FAST_MODEL, FALLBACK_MODEL):
                try:
                    resp = client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=sys_inst,
                            temperature=0.0,
                            response_mime_type="application/json",
                            thinking_config=types.ThinkingConfig(thinking_budget=0),
                        ),
                    )
                    raw_j = re.sub(r"^```(?:json)?\s*|\s*```$", "", (resp.text or "").strip())
                    parsed = json.loads(raw_j)
                    if isinstance(parsed, dict):
                        lvl = str(parsed.get("level") or "ok").strip().lower()
                        if lvl in ("ok", "watch", "nervous_stop"):
                            out_level = lvl
                        out_cat = str(parsed.get("category") or "none").strip()
                        out_topics = [str(x).strip()[:36] for x in (parsed.get("topics") or []) if str(x).strip()][:5]
                        out_summary = str(parsed.get("topic_summary") or "").strip()[:240]
                        out_note = str(parsed.get("parent_note") or "").strip()[:260]
                        break
                except Exception as e:
                    blackboard.QUOTA.note_error("guardian", e)
                    if not blackboard.QUOTA.allow_background():
                        break
        except Exception:
            pass

    if out_level == "nervous_stop":
        return record_protective_stop(
            session_id,
            out_cat or "safety_concern",
            out_note or "Watching agent paused session due to an age-safety concern for an 8-year-old.",
            kid_quote=kt,
            tutor_quote=tt,
            sandbox=sandbox,
        )

    with _LOCK:
        d = _load_unlocked()
        d["turns_checked"] = int(d.get("turns_checked") or 0) + 1
        st = d.setdefault("session_topics", {}).setdefault(
            session_id,
            {
                "session_id": session_id,
                "started": now_iso(),
                "updated": now_iso(),
                "sandbox": sandbox,
                "topics": [],
                "summary": "",
                "status": "ok",
                "notes": [],
                "samples": [],
            },
        )
        st["updated"] = now_iso()
        merged_topics = list(st.get("topics") or [])
        for tp in out_topics or _local_topic_extract(kt, merged_topics):
            if tp and tp.lower() not in {x.lower() for x in merged_topics}:
                merged_topics.append(tp)
        st["topics"] = merged_topics[-8:]
        if out_summary:
            st["summary"] = out_summary
        elif kt and not st.get("summary"):
            st["summary"] = f'Writing about: "{kt[:120]}"'
        if kt and len(kt.split()) >= 2 and kt not in (st.get("samples") or []):
            st["samples"] = ((st.get("samples") or []) + [kt[:140]])[-6:]
        if out_level == "watch" and out_note:
            if st.get("status") != "nervous_stop":
                st["status"] = "watch"
            note_entry = {
                "time": now_iso(),
                "level": "watch",
                "category": out_cat,
                "note": out_note,
                "quote": kt[:200],
            }
            st.setdefault("notes", []).append(note_entry)
            d["alerts"] = ([{**note_entry, "session_id": session_id, "sandbox": sandbox}] + (d.get("alerts") or []))[:50]
        _save_unlocked(d)

    return {"level": out_level, "category": out_cat, "topics": out_topics, "summary": out_summary, "note": out_note}


def parent_report() -> dict[str, Any]:
    """Formats the full Child-Safety Watcher & Conversation Topics report for `/api/parent`."""
    with _LOCK:
        d = _load_unlocked()
        topics_map = d.get("session_topics") or {}
        topic_list = sorted(topics_map.values(), key=lambda x: x.get("updated") or "", reverse=True)[:25]
        return {
            "active_bug_lock": d.get("active_bug_lock"),
            "sandbox_bug_lock": d.get("sandbox_bug_lock"),
            "turns_checked": d.get("turns_checked", 0),
            "alerts": (d.get("alerts") or [])[:20],
            "sessions": topic_list,
        }
