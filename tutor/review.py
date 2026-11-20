"""Post-session review: an expert pass over what actually happened, which updates the learner model.

This is where the system learns about the child between sessions. The live tutor reads the
updated model at the start of the next session.
"""

from __future__ import annotations

import json
import re
from typing import Any

from google import genai
from google.genai import types

from . import curriculum_tracker
from .config import FALLBACK_MODEL, HYDROGEN_MODEL, REVIEW_MODEL, SESSIONS, api_key
from .observers import targets_text
from .record import list_activities, load_learner, read_session, save_activity, save_learner

REVIEW_SYSTEM = """You are a team of specialists reviewing one tutoring session with a child:
a writing-instruction researcher (SRSD, Graham & Harris), a developmental spelling specialist
(Words Their Way stages: letter name-alphabetic, within word pattern, syllables and affixes, derivational relations),
a child psychologist who works with ADHD and motivation (self-determination theory, mindset),
and a game designer who knows what kids actually find fun.

Your job: turn what actually happened into an honest, evidence-based model of this child and a plan for next time.
- Ground every claim in specific evidence from the session (quote it). Say when evidence is thin. Don't overclaim from one session.
- Spelling: list misspellings exactly (meant vs wrote), group them into patterns, estimate developmental stage only if evidence supports it.
- Engagement: what made him lean in, what made him go flat or refuse, and timing. Long answers, fast responses, asking for more,
  laughing, designing features = engagement. Short answers, long pauses, "I don't know", changing the subject = disengagement.
- Hypotheses must be testable next session.
- ideas_to_try should be concrete and genuinely new where helpful — new kinds of activities or games, not variations on worksheets.
- The plan is a starting point for the live tutor, not a script. Keep it to what fits in 15 minutes.
- notes_for_parent: plain language, short, honest, useful; include anything the parent should try or watch for at home.
- expectation_ratings: evaluate ONLY the Ontario expectations that had direct evidence in this session using Ontario's 1–4 scale:
  1 = Emerging (needed heavy scaffolding), 2 = Approaching (succeeded with prompts), 3 = Solid Grade 3 Met (applied independently), 4 = Extending / Grade 4+.
  Quote exact words from the session in `evidence`. Omit expectations that had zero evidence today.
Return strict JSON only."""

SCHEMA_HINT = {
    "summary": "2-4 sentences: who this kid is as a learner, as of now",
    "session_recap": "3-5 sentences: what happened this session",
    "interests": ["..."],
    "audience": "who he wants to write for, if known",
    "writing": "what we know about his composing: spoken vs typed, organization, detail, voice (with evidence)",
    "typing": "speed/accuracy/tolerance (with evidence)",
    "spelling": {
        "stage": "estimate or 'not enough evidence'",
        "patterns": [{"pattern": "...", "evidence": ["meant X -> wrote Y"], "priority": "high|medium|low"}],
        "words_learned": ["..."],
    },
    "what_engages": ["specific, with evidence"],
    "what_shuts_down": ["specific, with evidence"],
    "hypotheses": [{"claim": "...", "evidence": "...", "confidence": "low|medium|high", "test_next": "..."}],
    "activity_feedback": [{"id": "activity id", "how_it_went": "..."}],
    "ideas_to_try": ["..."],
    "plan_next_session": "...",
    "notes_for_parent": "...",
    "expectation_ratings": [
        {"id": "exact expectation id from ONTARIO EXPECTATIONS list", "level": 2, "evidence": "short exact quote from session"}
    ],
}


def _transcript(events: list[dict[str, Any]], name: str) -> str:
    lines = []
    for e in events:
        t = e.get("t", 0)
        k = e.get("kind")
        mm = f"{int(t // 60):02d}:{int(t % 60):02d}"
        if k == "kid_said":
            lines.append(f"{mm} {name} (spoken): {e['text']}")
        elif k == "tutor_said":
            lines.append(f"{mm} Tutor: {e['text']}")
        elif k == "kid_typed":
            lines.append(f"{mm} {name} TYPED ({e.get('seconds')}s, {e.get('backspaces')} backspaces): {e['text']!r}")
        elif k == "kid_wrote":
            lines.append(f"{mm} {name} HANDWROTE (read exactly): {e.get('text')!r}")
        elif k == "kid_tapped":
            lines.append(f"{mm} {name} tapped: {e.get('value')!r}")
        elif k == "writing_check":
            from .thinking import summarize_check
            lines.append(f"{mm} [writing check{' (revision)' if not e.get('first_try') else ''}: {summarize_check(e.get('check') or {})}]")
        elif k == "ideas":
            names = ", ".join(i.get("name", "") for i in e.get("ideas", []))
            lines.append(f"{mm} [designer offered ideas: {names}]")
        elif k == "critic":
            s = e.get("state", {})
            lines.append(f"{mm} [education critic: {s.get('verdict')} — {s.get('issue','')} {s.get('advice','')}]")
        elif k == "tracker":
            s = e.get("state", {})
            lines.append(f"{mm} [engagement tracker: level {s.get('engagement',{}).get('level')} {s.get('engagement',{}).get('trend')}, risk {s.get('risk')}]")
        elif k == "critic_vet":
            lines.append(f"{mm} [critic vetted game spec '{e.get('title')}': approve={e.get('vet',{}).get('approve')}]")
        elif k == "tool":
            if e["name"] in ("note",):
                lines.append(f"{mm} [tutor note: {e['args'].get('category')}: {e['args'].get('detail')}]")
            elif e["name"] == "build_activity":
                lines.append(f"{mm} [tutor built activity: {e['args'].get('title')} — {e['args'].get('description','')[:400]} | why: {e['args'].get('why','')}]")
            else:
                lines.append(f"{mm} [tool {e['name']}: {json.dumps(e['args'], ensure_ascii=False)[:300]}]")
        elif k == "activity_event":
            lines.append(f"{mm} [activity event: {json.dumps(e.get('data'), ensure_ascii=False)[:300]}]")
        elif k == "activity_built":
            lines.append(f"{mm} [activity on screen: {e.get('id')} '{e.get('title')}' after {e.get('seconds')}s]")
        elif k == "piece_saved":
            lines.append(f"{mm} [piece saved: {e.get('title')} for {e.get('audience')}]")
        elif k == "session_end":
            lines.append(f"{mm} [session ended after {e.get('minutes')} min]")
    return "\n".join(lines)


def _stats(events: list[dict[str, Any]]) -> dict[str, Any]:
    kid_words = sum(len(e["text"].split()) for e in events if e.get("kind") == "kid_said")
    tutor_words = sum(len(e["text"].split()) for e in events if e.get("kind") == "tutor_said")
    typed = [e for e in events if e.get("kind") == "kid_typed"]
    chars = sum(len(e["text"]) for e in typed)
    secs = sum(e.get("seconds") or 0 for e in typed)
    writing = next((e.get("stats") for e in reversed(events) if e.get("kind") == "writing_stats"), {}) or {}
    return {
        "kid_spoken_words": kid_words,
        "tutor_spoken_words": tutor_words,
        "talk_ratio_kid_to_tutor": round(kid_words / tutor_words, 2) if tutor_words else None,
        "typed_entries": len(typed),
        "handwritten_entries": sum(1 for e in events if e.get("kind") == "kid_wrote"),
        "typed_chars": chars,
        "approx_chars_per_minute_while_typing": round(chars / (secs / 60), 1) if secs > 0 else None,
        "writing": writing,
    }


def _extract_json(text: str) -> dict[str, Any]:
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", t)
        if not m:
            raise
        return json.loads(m.group(0))


def review_session(session_id: str) -> dict[str, Any]:
    key = api_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set")
    rec = load_learner()
    name = rec.get("name") or "the child"
    events = read_session(session_id)
    if not events:
        raise RuntimeError("empty session")

    transcript = _transcript(events, name)
    stats = _stats(events)
    if stats["kid_spoken_words"] == 0 and stats["typed_entries"] == 0:
        result = {"session_recap": "Session had no input from the child; nothing to learn.", "skipped": True}
        (SESSIONS / f"{session_id}.review.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        _mark_reviewed(session_id)
        return result

    exp_list_txt = "\n".join(
        f"- {e['id']} ({e['code']} — {e['name']}): {e['desc']}" for e in curriculum_tracker.ONTARIO_EXPECTATIONS
    )
    prompt = (
        f"CHILD: {name}, grade {rec.get('grade', 3)}.\n\n"
        f"PARENT NOTES:\n" + "\n".join(f"- {n['note']}" for n in rec.get("parent_notes", [])) + "\n\n"
        f"ONTARIO EXPECTATIONS FOR REPORT CARD (use these exact ids in expectation_ratings):\n{exp_list_txt}\n\n"
        f"CURRENT REPORT CARD:\n{json.dumps(rec.get('report_card', {}), indent=2)}\n\n"
        f"SKILL TARGETS (Ontario Language 2023, quoted):\n{targets_text()}\n\n"
        f"CURRENT LEARNER MODEL (from earlier sessions; update it, keep what still holds, drop what was contradicted):\n"
        f"{json.dumps(rec.get('model', {}), indent=2)}\n\n"
        f"ACTIVITY LIBRARY:\n{json.dumps([{k: a.get(k) for k in ('id','title','summary','how_it_went')} for a in list_activities()[:15]], indent=2)}\n\n"
        f"SESSION STATS:\n{json.dumps(stats, indent=2)}\n\n"
        f"SESSION TRANSCRIPT:\n{transcript}\n\n"
        f"Return JSON with exactly these keys:\n{json.dumps(SCHEMA_HINT, indent=2)}"
    )

    client = genai.Client(api_key=key)
    last_err = None
    result = None
    for model in (REVIEW_MODEL, HYDROGEN_MODEL, "gemini-3.1-pro-preview", FALLBACK_MODEL):
        try:
            resp = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=REVIEW_SYSTEM,
                    temperature=0.3,
                    response_mime_type="application/json",
                ),
            )
            result = _extract_json(resp.text or "{}")
            result["_model"] = model
            break
        except Exception as e:
            last_err = e
    if result is None:
        raise RuntimeError(f"review failed: {last_err}")

    result["stats"] = stats
    (SESSIONS / f"{session_id}.review.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    rec = load_learner()
    model = rec.setdefault("model", {})
    for k in ("summary", "interests", "audience", "writing", "typing", "spelling", "what_engages",
              "what_shuts_down", "hypotheses", "ideas_to_try", "plan_next_session", "notes_for_parent"):
        if result.get(k) not in (None, "", [], {}):
            model[k] = result[k]
    rc = curriculum_tracker.ensure_report_card(rec)
    curriculum_tracker.merge_specialist_ratings(rc, result.get("expectation_ratings") or [], session_id)
    save_learner(rec)
    _mark_reviewed(session_id, result.get("session_recap", ""), stats)

    for fb in result.get("activity_feedback", []) or []:
        if fb.get("id") and fb.get("how_it_went"):
            try:
                save_activity({"id": fb["id"], "how_it_went": fb["how_it_went"]})
            except Exception:
                pass
    return result


def _mark_reviewed(session_id: str, recap: str = "", stats: dict[str, Any] | None = None) -> None:
    rec = load_learner()
    for s in rec.get("sessions", []):
        if s.get("id") == session_id:
            s["reviewed"] = True
            if recap:
                s["recap"] = recap
            if stats:
                w = stats.get("writing") or {}
                s["metrics"] = {
                    "complete_first_try_rate": w.get("complete_first_try_rate"),
                    "sentence_attempts": w.get("sentence_attempts"),
                    "typed_chars": stats.get("typed_chars"),
                    "kid_spoken_words": stats.get("kid_spoken_words"),
                    "talk_ratio_kid_to_tutor": stats.get("talk_ratio_kid_to_tutor"),
                    "misspellings": len(w.get("misspellings") or []),
                }
    save_learner(rec)
