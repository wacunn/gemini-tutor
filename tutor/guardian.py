"""Child-Safety Watching Agent, Conversation Topic Reporter & Protective 'Bug' Circuit Breaker.

Calibrated specifically for Dylan (an 8-year-old who listens to heavy metal, engages in mature/adult
curiosity including death, thinks swearing is funny, and hates being babied or "Blippi'd"):
1. `instant_screen(kid_text, tutor_text)`: 0ms synchronous pre-gate catching ONLY unmistakable acute danger
   (first-person self-harm/suicidal intent, abuse/secrecy from parents, explicit pornography/exploitation,
   severe real-world weapons/poison, or AI boundary violations)—NEVER false-alarming on swearing, death
   curiosity, comic-book deaths, or heavy-metal imagery.
2. `watch_exchange(...)`: Independent Gemini Watching Agent inspecting BOTH the child's inputs and the AI's
   responses on every turn:
   - Logs a clear **Conversation Topics & Themes** report per session on `/parent`.
   - Quietly logs `"watch"` notes on `/parent` (WITHOUT interrupting or scolding!) when he uses strong
     swearing for laughs, explores mature/adult topics or curiosity about death, or mentions real-life
     school/social stress—giving Mom & Dad calm visibility without babying him.
   - Triggers `"nervous_stop"` (`ERR-G42` "App Bug" pause) STRICTLY for genuine acute child-safety danger.
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

# 0ms high-precision lexical red flags: ONLY unmistakable acute danger.
# Deliberately EXCLUDES swear words (shit/fuck/damn/hell/ass), curiosity about death, story deaths ("don't want to die!"), and potty/metal humor.
_INSTANT_KID_RED_FLAGS: list[tuple[str, str, re.Pattern[str]]] = [
    (
        "self_harm",
        "First-person self-harm or suicidal phrase detected in student input.",
        re.compile(
            r"(?<!don't\s)(?<!dont\s)(?<!didn't\s)(?<!didnt\s)(?<!doesn't\s)(?<!doesnt\s)(?<!not\s)(?<!never\s)"
            r"\b(kill\s+myself|i\s+(?:want|wanna)\s+to\s+die|wish\s+i\s+(?:was|were)\s+dead|hurt\s+myself|"
            r"cut\s+myself|hang\s+myself|end\s+my\s+life|i(?:'m|\s+am)\s+better\s+off\s+dead|commit\s+suicide)\b",
            re.I,
        ),
    ),
    (
        "secrecy_or_harm",
        "Secrecy-from-parents or personal abuse/harm disclosure detected.",
        re.compile(
            r"\b(don'?t\s+tell\s+(?:my\s+)?(?:mom|dad|parents)|keep\s+this\s+a\s+secret\s+from\s+(?:mom|dad|my\s+parents)|"
            r"touched\s+my\s+private|someone\s+is\s+hurting\s+me|hits\s+me\s+at\s+home)\b",
            re.I,
        ),
    ),
    (
        "sexual_explicit",
        "Explicit pornography, sexual act, or sexual exploitation phrase detected.",
        re.compile(
            r"\b(porn|porno|pornography|sex\s+with|having\s+sex|send\s+nudes|naked\s+pictures|"
            r"rape|raped|molest|molested|onlyfans|child\s+sex)\b",
            re.I,
        ),
    ),
    (
        "severe_danger",
        "Actionable real-world weapon or self-poisoning phrase detected.",
        re.compile(
            r"\b(how\s+to\s+make\s+a\s+bomb|bring\s+a\s+gun\s+to\s+school|school\s+shooting|shoot\s+up\s+the\s+school|"
            r"drink\s+bleach)\b",
            re.I,
        ),
    ),
]

_INSTANT_AI_RED_FLAGS = re.compile(
    r"\b(keep\s+this\s+(?:just\s+)?between\s+us|don'?t\s+tell\s+your\s+(?:mom|dad|parents)|"
    r"i(?:'m|\s+am)\s+your\s+(?:best\s+friend|secret\s+friend)|porn|sex\s+with|kill\s+yourself|hurt\s+yourself)\b",
    re.I,
)

WATCHER_SYSTEM = """You are the independent Child-Safety & Conversation-Topic Watching Agent overseeing an AI writing tutor working with {name}, a sharp, mature-curious 8-year-old child (Grade {grade}).

IMPORTANT CONTEXT FROM {name}'S PARENTS (DO NOT OVER-SAFETY OR BABY HIM):
- {name} listens to heavy metal (Megadeth, Metallica), engages in grown-up/adult topics, thinks swearing is funny, and is genuinely curious about death and mortality.
- His parents explicitly want visibility into his conversation topics on the Parent Page WITHOUT over-sensitive censorship, scolding, or false-alarm app freezes!

Your two jobs on every turn:
1. TOPIC AWARENESS FOR PARENTS:
   - Identify 1 to 4 concise topic tags (`topics`, e.g. `["skeleton battle", "curiosity about death"]` or `["alien crash", "swearing humor"]`).
   - Write `topic_summary`: 1 clear, factual sentence telling the parent what {name} has been writing/talking about in this session so far.

2. CALIBRATED 3-TIER CLASSIFICATION (`level`: `"ok"` | `"watch"` | `"nervous_stop"`):
   - `"ok"` (Normal / Edgy Kid Play — NEVER pause):
     * Creative stories, potty/gross-out humor (poop, farts, barf, butts), heavy-metal / dark comic aesthetics (skulls, skeletons, graves, demons, explosions, Megadeth vibes), comic-book battles or characters dying in a story, mild casual swearing ("hell", "damn", "crap", "ass", "badass"), science/history, or homework pushback ("this is boring").
   - `"watch"` (Quietly log a calm note on `/parent` for Mom & Dad — NEVER interrupt or freeze the session!):
     * **Swearing for laughs / shock** ("fuck", "shit", "bitch", "wtf", crude anatomy jokes): {name} thinks swearing is funny—NEVER trigger `"nervous_stop"` for swearing! Set `level: "watch"`, `category: "swearing_humor"`, and write a calm, non-judgmental `parent_note` (e.g. `"Used swear word ('shit') for comedic effect in his story."`).
     * **Curiosity about death, dying, mortality, war, or mature/adult topics** (e.g. asking what happens after people die, why things die, graves, plagues, crime/politics/history, existential questions): NEVER trigger `"nervous_stop"` for curiosity about death or adult topics! Set `level: "watch"`, `category: "mature_or_death_curiosity"`, and summarize calmly so his parents know what big topic was on his mind.
     * **Real-life emotional or social signals**: mentioning sadness, loneliness, mean kids/bullying, feeling stupid at school, or scary nightmares (`category: "emotional_watch"` or `"bullying_social"`).
   - `"nervous_stop"` (Immediate `ERR-G42` "App Bug" pause — RESERVED STRICTLY FOR GENUINE ACUTE DANGER):
     * **First-person self-harm or suicidal intent** about HIMSELF (e.g. "I want to kill myself", "I want to hurt myself", "I wish I were dead"). CRITICAL: Curiosity about death ("what happens when you die?") or characters dying in a story is NOT self-harm—NEVER use `"nervous_stop"` for those!
     * **Real-world abuse, predation, threats to {name}, or secrecy from parents** (someone hurting/touching him in real life, violence at home, or "don't tell mom/dad").
     * **Explicit sexual content, pornography, sexual solicitation, or grooming** (NOT mere swear words like "fuck" used as an expletive!).
     * **Actionable real-world severe danger** (making real weapons/bombs, self-poisoning, bringing weapons to school, taking drugs).
     * **AI boundary drift**: the AI acting like a human friend/secret confidant, asking private personal questions, or generating sexually explicit, graphic-gore, or self-harm content.

Return STRICT JSON:
{{"level": "ok|watch|nervous_stop",
  "category": "none|potty_humor|fantasy_action|swearing_humor|mature_or_death_curiosity|emotional_watch|bullying_social|self_harm|sexual_explicit|real_world_harm|dangerous_act|ai_boundary_drift",
  "topics": ["short tag 1", "short tag 2"],
  "topic_summary": "1-sentence summary of what the child is talking/writing about in this session",
  "parent_note": "empty if level=='ok'; otherwise 1 calm, factual sentence for Mom/Dad explaining what came up"}}"""


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
