"""Adaptive AI Coach: sense -> decide -> act -> learn.

Instead of hard-coded pedagogy gates, an LLM Coach looks at the writing diagnostics, how the child is
behaving right now (speed, backspaces, pushback, whether he followed the last request, chip use),
and a persistent learner model (skill evidence, hypotheses under test, what works, today's state),
then decides per turn:

  - accept the sentence now (art draws), or ask for ONE change first,
  - which single thing to focus on (or nothing),
  - how much scaffolding (story question, starter chips, partial frame, model sentence),
  - for spelling, which rung of the ladder (find-them-yourself -> count hint -> highlighted word ->
    "which of these is it?" then type it -> full word-part card),
  - what to say in plain, story-flavoured kid language.

Code here only enforces guardrails (streak ceiling, naming the exact word, no school vocabulary,
validation against the diagnostics, fallback) and keeps the evidence ledger the Coach reasons over.
"""

from __future__ import annotations

import datetime as _dt
import json
import random
import re
import time
from typing import Any

from google.genai import types

from . import config
from .config import genai_client

COACH_MODEL = config.COACH_MODEL  # the per-turn judgment call
LEARN_MODEL = config.COACH_MODEL  # background learning: no kid is waiting, so use the stronger model (lite hallucinated evidence in sims)
MAX_CONSECUTIVE_FIXES = 2

FOCUS_TYPES = (
    "none",
    "complete_sentence",
    "run_on",
    "capital",
    "end_mark",
    "spelling",
    "verb_ending",
    "connector",
    "dialogue",
    "word_choice",
)
SCAFFOLDS = ("none", "story_question", "starter_chips", "partial_frame", "model_sentence")

DEFAULT_HYPOTHESES = [
    ("H1", "He tolerates one fix per sentence without disengaging."),
    ("H2", "Capitals and end marks can be asked for from day one without hurting engagement."),
    ("H3", "Starter chips with 'because'/'when' lead him to write linked cause-and-effect sentences."),
    ("H4", "Fix requests framed in story language get less pushback than rule-framed requests."),
    ("H5", "His willingness drops after about 12 minutes in a session."),
    ("H6", "Voice-first drafting helps on low-energy days."),
    ("H7", "On good days he can find his own spelling mistakes when told some are there."),
]

SKILL_KEYS = ("complete", "capital", "end_mark", "spelling_clean", "verb_endings", "connector", "dialogue")

# Kid-facing words that make it feel like a worksheet. "capital", "period", "spelling" are allowed.
SCHOOL_VOCAB = re.compile(
    r"\b(tier\s*\d*|connectors?|conjunctions?|clauses?|fragments?|run-?ons?|end punctuation|punctuation|"
    r"complete sentences?|full sentences?|grammar|power-?ups?|subject|predicate|act\s+(?:i{1,3}|1|2|3)\b|"
    r"mastery|expectation|curriculum|rubric)",
    re.I,
)
_SANITIZE = [
    (re.compile(r"\bcomplete sentences?\b", re.I), "sentence"),
    (re.compile(r"\bfull sentences?\b", re.I), "sentence"),
    (re.compile(r"\bend punctuation\b", re.I), "ending mark"),
    (re.compile(r"\bpunctuation\b", re.I), "marks"),
    (re.compile(r"\bconnectors?\b", re.I), "linking word"),
    (re.compile(r"\bconjunctions?\b", re.I), "linking word"),
    (re.compile(r"\bpower-?ups?\b", re.I), "upgrade"),
    (re.compile(r"\btier\s*\d*\b", re.I), ""),
    (re.compile(r"\bgrammar\b", re.I), "wording"),
    (re.compile(r"\bfragments?\b", re.I), "half-idea"),
    (re.compile(r"\brun-?ons?\b", re.I), "long chain"),
]


COACH_SYSTEM = """You are the adaptive writing coach inside a comic-book and story app for {name}, a Grade {grade} boy with ADHD.
The app is secretly his Grade 3 writing program. Your two goals, equally important:
  (1) He WANTS to keep playing (engagement, competence, autonomy, fun, immediate art).
  (2) He actually gets better at writing: complete sentences, capitals and end marks, spelling, verb endings, linking ideas with words like because/when/but/so, dialogue, and word choice.
These goals conflict turn by turn. Your job is to balance them FOR HIM, TODAY, using evidence, not fixed rules.

HOW YOU DECIDE EACH TURN
- Estimate today's state ONLY from the BEHAVIOUR FACTS. Start at "medium" and move it with evidence: short or shrinking sentences, lowercase starts, "idk"/pushback, ignored requests, slowing down, or many minutes in => lower; long detailed sentences, quick compliance, self-corrections => higher. Do not call him "high energy" just because his story is fun.
- Decide: accept now (art draws immediately) OR ask for exactly ONE change first. Never stack corrections. Everything you don't ask about goes in "deferred" (logged for the parent to see), so leaving things is fine.
- Complete sentences (who/what + does what) are his #1 school gap; weigh them heavily. But you may still accept an imperfect sentence when pressing would cost more than it teaches today.
- Good-energy days: push a bit harder and occasionally (about 1 in 4 turns) TEST a slightly harder ask to learn whether he's ready. Low-energy days: accept more, scaffold more, keep art flowing, suggest voice.
- Never ask for the same fix twice in a row if he just ignored it; switch to more support or accept and defer.
- Don't drift into never teaching: when his state is medium or high and you have NOT asked for anything in the last 3 writing turns while real issues keep showing up, you should usually ask for one thing now (lightest scaffold that will work). Choose the issue that matters most for him (see the skill evidence), not just the easiest.
- He has had {consecutive} fix requests in a row on this sentence. Hard limit is {max_fixes}; at the limit you must accept.

SCAFFOLDING (pick the lightest that will work; fade as evidence shows he can do it alone)
- "story_question": a curious question that naturally draws out the skill (e.g. "Why did Bob barf?" elicits "because").
- "starter_chips": 2-3 tappable sentence starters built from HIS story (e.g. "Bob barfed because…", "When the cat walked in, …"). Never a full sentence for him to copy.
- "partial_frame": put part of his own words in the box with a gap to finish.
- "model_sentence": show one example about a DIFFERENT moment, then he writes his own.
- "next_scaffold": for the NEXT story question, should starter chips be offered? Use "starter_chips" until evidence shows he uses linking words without them; bring them back on hard days.

SPELLING LADDER (choose spell_rung 1-5 when focus = "spelling"; he always ends up typing the word himself)
 1 find-them-yourself: "I think I see a spelling mistake in there—can you find it?" (do NOT name the word)
 2 count hint: "I spot 2 words that look off." (do NOT name the words)
 3 point to the word: name the exact word; it gets highlighted in his sentence
 4 which-one-is-it: give spell_options = 2-3 spellings INCLUDING the correct one; he picks, then types it
 5 full word help: word-part breakdown card (e.g. smell + y)
 Move toward rung 1 as he succeeds; start lower on tired days or for patterns he keeps missing.

KID LANGUAGE (kid_words and input_prompt)
- Brief, warm, playful reactions to HIS STORY ("Oh no, poor guy!", "That's a super stinky situation!") are great!
- NEVER use cutesy/babyish metaphors for WRITING RULES: NEVER say "make that first letter big and tall like a superhero", "put a little dot to stop the sentence", or "so the printer doesn't crash". For the writing fix itself, ALWAYS use plain normal words: "Capitalize the first letter.", "Add a period at the end.", "Check the spelling of 'fase'."
- Avoid dry curriculum jargon (conjunction, clause, predicate, tier, Act I/II/III), while normal words ("capital", "period", "question mark", "sentence", "spelling") are completely fine.
- NEVER suggest plot ideas, potions, rockets, or "Does X or Y happen?" story options. It is 100% his story.
- Never say "wrong" about him; you are an AI tutor, not his friend.

Return STRICT JSON only:
{{"today_state":{{"energy":"high|medium|low","willingness":"high|medium|low","note":"short"}},
 "accept":true,
 "focus":"none|complete_sentence|run_on|capital|end_mark|spelling|verb_ending|connector|dialogue|word_choice",
 "focus_word":"exact word from his sentence if spelling/verb_ending/word_choice, else empty",
 "focus_correct":"correct form if spelling/verb_ending, else empty",
 "spell_rung":0,
 "spell_options":[],
 "scaffold":"none|story_question|starter_chips|partial_frame|model_sentence",
 "chips":[],
 "prefill":"text to put in his box (usually his own sentence; a partial frame if scaffold=partial_frame)",
 "kid_words":"what to say to him",
 "input_prompt":"very short line for the input bar",
 "suggest_pen":false,
 "deferred":["short issue notes you chose not to raise"],
 "next_scaffold":"none|starter_chips",
 "rationale":"1-2 sentences for the parent explaining WHY this decision for this kid today",
 "hypothesis_updates":[{{"id":"H1","direction":"for|against","evidence":"short"}}],
 "what_works_add":"optional short observation about what works for him, else empty"}}"""


# ---------------------------------------------------------------- learner model


def ensure_model(rec: dict[str, Any]) -> dict[str, Any]:
    m = rec.setdefault("coach_model", {})
    m.setdefault("skill_stats", {k: [] for k in SKILL_KEYS})
    for k in SKILL_KEYS:
        m["skill_stats"].setdefault(k, [])
    if not m.get("hypotheses"):
        m["hypotheses"] = [
            {"id": hid, "text": txt, "for": 0, "against": 0, "evidence": []} for hid, txt in DEFAULT_HYPOTHESES
        ]
    m.setdefault("what_works", [])
    m.setdefault("decisions", [])
    m.setdefault("deferred", [])
    m.setdefault("day_states", [])
    m.setdefault("push_log", [])
    m.setdefault("spell_rungs", {})  # pattern/word -> last successful rung
    m.setdefault("self_catches", 0)
    m.setdefault("ai_catches", 0)
    return m


def _rate(xs: list[int]) -> str:
    if not xs:
        return "no data yet"
    n = len(xs)
    return f"{sum(xs)}/{n} recent first drafts"


def record_first_draft_stats(model: dict[str, Any], chk: dict[str, Any]) -> None:
    """Unprompted skill evidence: only call on a FIRST draft (not a revision we asked for)."""
    sents = chk.get("sentences") or []
    if not sents:
        return
    feats = chk.get("features") or {}
    ss = model["skill_stats"]

    def push(k: str, v: bool) -> None:
        ss[k] = (ss.get(k) or [])[-29:] + [1 if v else 0]

    push("complete", all(s.get("issue") == "none" for s in sents))
    push("capital", all(s.get("capital_ok") for s in sents))
    push("end_mark", all(s.get("end_ok") for s in sents))
    push("spelling_clean", not chk.get("misspellings"))
    push("verb_endings", not chk.get("grammar_fixes"))
    push("connector", bool(feats.get("has_connector")))
    push("dialogue", bool(feats.get("has_dialogue")))


def _skills_summary(model: dict[str, Any]) -> str:
    ss = model.get("skill_stats") or {}
    labels = {
        "complete": "Complete sentences (unprompted)",
        "capital": "Starting capital",
        "end_mark": "End mark",
        "spelling_clean": "No misspellings",
        "verb_endings": "Verb endings/agreement OK",
        "connector": "Uses linking words (because/when/but/so)",
        "dialogue": "Uses dialogue",
    }
    return "\n".join(f"- {labels[k]}: {_rate(ss.get(k) or [])}" for k in SKILL_KEYS)


def _hyp_summary(model: dict[str, Any]) -> str:
    out = []
    for h in model.get("hypotheses") or []:
        ev = "; ".join(e.get("evidence", "") for e in (h.get("evidence") or [])[-2:])
        out.append(f"- {h['id']} ({h.get('for', 0)} for / {h.get('against', 0)} against): {h['text']}" + (f" | recent: {ev}" if ev else ""))
    return "\n".join(out)


def apply_learning(model: dict[str, Any], decision: dict[str, Any], sentence: str) -> None:
    today = _dt.date.today().isoformat()
    for hu in decision.get("hypothesis_updates") or []:
        if not isinstance(hu, dict):
            continue
        for h in model["hypotheses"]:
            if h["id"] == str(hu.get("id", "")).strip().upper():
                d = str(hu.get("direction", "")).lower()
                if d == "for":
                    h["for"] = h.get("for", 0) + 1
                elif d == "against":
                    h["against"] = h.get("against", 0) + 1
                else:
                    continue
                h["evidence"] = (h.get("evidence") or [])[-9:] + [{"date": today, "direction": d, "evidence": str(hu.get("evidence", ""))[:160]}]
    ww = str(decision.get("what_works_add") or "").strip()
    if ww and ww not in model["what_works"]:
        model["what_works"] = model["what_works"][-14:] + [ww[:160]]
    for d in decision.get("deferred") or []:
        if str(d).strip():
            model["deferred"] = model["deferred"][-59:] + [{"date": today, "sentence": sentence[:160], "issue": str(d)[:120]}]
    ts = decision.get("today_state") or {}
    if ts:
        states = [s for s in model["day_states"] if s.get("date") != today]
        model["day_states"] = (states + [{"date": today, **{k: ts.get(k) for k in ("energy", "willingness", "note")}}])[-21:]
    model["decisions"] = model["decisions"][-59:] + [
        {
            "time": _dt.datetime.now().isoformat(timespec="seconds"),
            "sentence": sentence[:160],
            "accept": bool(decision.get("accept")),
            "focus": decision.get("focus"),
            "scaffold": decision.get("scaffold"),
            "spell_rung": decision.get("spell_rung") or 0,
            "kid_words": str(decision.get("kid_words") or "")[:200],
            "rationale": str(decision.get("rationale") or "")[:300],
            "guardrail": decision.get("guardrail") or "",
            "latency_s": decision.get("latency_s"),
        }
    ]


# ---------------------------------------------------------------- outcome of the previous request


def outcome_of_last_request(last: dict[str, Any] | None, chk: dict[str, Any], raw: str) -> dict[str, Any]:
    """Did he do what we asked? Also counts self-catches for spelling rungs 1-2."""
    if not last:
        return {}
    focus = last.get("focus")
    sents = chk.get("sentences") or []
    ms_now = {m["wrote"].lower() for m in (chk.get("misspellings") or [])}
    gf_now = {g["wrote"].lower() for g in (chk.get("grammar_fixes") or [])}
    complied: bool | None = None
    self_caught: list[str] = []
    if focus == "complete_sentence":
        complied = bool(sents) and all(s.get("issue") == "none" for s in sents)
    elif focus == "run_on":
        complied = not any(s.get("issue") == "run_on" for s in sents)
    elif focus == "capital":
        complied = bool(sents) and all(s.get("capital_ok") for s in sents)
    elif focus == "end_mark":
        complied = bool(sents) and all(s.get("end_ok") for s in sents)
    elif focus == "spelling":
        prev = {w.lower() for w in (last.get("misspelled") or [])}
        fixed = [w for w in prev if w not in ms_now and not re.search(rf"\b{re.escape(w)}\b", raw.lower())]
        complied = bool(fixed) if prev else None
        if (last.get("spell_rung") or 0) in (1, 2):
            self_caught = fixed
    elif focus == "verb_ending":
        fw = (last.get("focus_word") or "").lower()
        complied = fw not in gf_now and not re.search(rf"\b{re.escape(fw)}\b", raw.lower()) if fw else None
    elif focus == "connector":
        complied = bool((chk.get("features") or {}).get("has_connector"))
    elif focus == "dialogue":
        complied = bool((chk.get("features") or {}).get("has_dialogue"))
    prev_words = set(re.findall(r"[a-z']+", (last.get("sentence") or "").lower()))
    now_words = set(re.findall(r"[a-z']+", raw.lower()))
    same_idea = bool(prev_words) and len(prev_words & now_words) / max(1, len(prev_words)) >= 0.5
    return {
        "last_focus": focus,
        "complied": complied,
        "kept_same_idea": same_idea,
        "self_caught_words": self_caught,
    }


# ---------------------------------------------------------------- the decision


def _diag_summary(chk: dict[str, Any]) -> str:
    lines = []
    for s in chk.get("sentences") or []:
        lines.append(
            f"- \"{s.get('text', '')[:120]}\": issue={s.get('issue')}, capital_ok={s.get('capital_ok')}, end_ok={s.get('end_ok')}, type={s.get('clause_type')}"
        )
    ms = chk.get("misspellings") or []
    if ms:
        lines.append("- misspellings: " + ", ".join(f"{m['wrote']}->{m['meant']}" for m in ms))
    gf = chk.get("grammar_fixes") or []
    if gf:
        lines.append("- verb/agreement: " + ", ".join(f"{g['wrote']}->{'/'.join(g.get('options') or [])}" for g in gf))
    f = chk.get("features") or {}
    lines.append(
        f"- has_linking_word={f.get('has_connector')}, has_dialogue={f.get('has_dialogue')}, dialogue_punct_ok={f.get('dialogue_punct_ok')}, weak_words={f.get('weak_words')}"
    )
    return "\n".join(lines) or "(no diagnostics)"


def _call(system: str, prompt: str, model: str | None = None) -> dict[str, Any] | None:
    client = genai_client()
    resp = client.models.generate_content(
        model=model or COACH_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.35,
            response_mime_type="application/json",
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    t = (resp.text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        out = json.loads(t)
    except json.JSONDecodeError:
        mm = re.search(r"\{[\s\S]*\}", t)
        out = json.loads(mm.group(0)) if mm else None
    return out if isinstance(out, dict) else None


def decide(
    rec: dict[str, Any],
    session: dict[str, Any],
    raw: str,
    how: str,
    chk: dict[str, Any],
    signals: dict[str, Any],
    context: str,
    story: str,
    model: str | None = None,
) -> dict[str, Any] | None:
    """Returns a validated, guardrailed decision dict, or None if the Coach is unavailable (caller falls back)."""
    use_model = model
    model = ensure_model(rec)
    name = rec.get("name") or "the student"
    notes = "\n".join(f"- {n.get('note', '')}" for n in (rec.get("parent_notes") or [])[:8]) or "(none)"
    turns = session.get("turns") or []
    turns_txt = "\n".join(
        f"- [{t.get('min', 0)} min] {t.get('how')} '{t.get('text', '')[:90]}' ({t.get('secs', '?')}s, {t.get('backspaces', '?')} backspaces) "
        f"-> coach: {'accept' if t.get('accept') else 'fix ' + str(t.get('focus'))}"
        + (f", outcome of previous ask: {t.get('outcome')}" if t.get("outcome") else "")
        for t in turns[-8:]
    ) or "(first writing turn today)"
    today = session.get("today_state") or {}
    behaviour = behaviour_facts(session, raw, signals)
    pushed, deferred = session.get("pushed", 0), session.get("deferred", 0)
    recent_days = "; ".join(f"{d.get('date')}: {d.get('energy')}/{d.get('willingness')}" for d in (model.get("day_states") or [])[-5:]) or "none"
    outcome = signals.get("outcome") or {}

    prompt = f"""LEARNER: {name}, Grade {rec.get('grade', 3)}. Parent notes:
{notes}

UNPROMPTED SKILL EVIDENCE (first drafts only):
{_skills_summary(model)}
Self-caught spelling fixes so far: {model.get('self_catches', 0)} | AI-caught: {model.get('ai_catches', 0)}

HYPOTHESES UNDER TEST (update with evidence when this turn tells you something):
{_hyp_summary(model)}

WHAT WORKS FOR HIM: {'; '.join(model.get('what_works') or []) or '(nothing recorded yet)'}
RECENT DAYS (energy/willingness): {recent_days}
CURSIVE ENABLED BY PARENT: {bool(rec.get('cursive_ready'))}

TODAY SO FAR (previous estimate: {today or 'none yet'}; asked {pushed} times, let {deferred} things go):
{turns_txt}

BEHAVIOUR FACTS (computed, trust these for today_state):
{behaviour}

WHERE HE IS IN THE BOOK: {context}
STORY SO FAR:
{story or '(just starting)'}

THIS TURN ({how}, {signals.get('minutes', 0)} min into session, took {signals.get('secs', '?')}s, {signals.get('backspaces', '?')} backspaces, used a starter chip: {signals.get('used_chip', False)}):
"{raw}"
Outcome of your previous request: {json.dumps(outcome) if outcome else 'n/a (no open request)'}

DIAGNOSTICS (from the checker; trust these for what is actually there):
{_diag_summary(chk)}"""

    system = COACH_SYSTEM.format(
        name=name,
        grade=rec.get("grade", 3),
        consecutive=session.get("consecutive_fixes", 0),
        max_fixes=MAX_CONSECUTIVE_FIXES,
    )
    t0 = time.time()
    try:
        out = _call(system, prompt, use_model)
    except Exception:
        out = None
    if not out and use_model and use_model != COACH_MODEL:
        try:
            out = _call(system, prompt, COACH_MODEL)
        except Exception:
            out = None
    if not out:
        return None
    decision = validate(out, raw, chk, session)
    if _has_school_vocab(decision):
        try:
            retry = _call(system, prompt + "\n\nYOUR LAST kid_words/input_prompt USED SCHOOL WORDS. Rewrite them in comic/story language, same decision.", use_model)
            if retry:
                d2 = validate(retry, raw, chk, session)
                if not _has_school_vocab(d2):
                    decision = d2
        except Exception:
            pass
        if _has_school_vocab(decision):
            for k in ("kid_words", "input_prompt"):
                decision[k] = _sanitize(decision.get(k, ""))
    decision["latency_s"] = round(time.time() - t0, 2)
    return decision


def _has_school_vocab(d: dict[str, Any]) -> bool:
    return bool(SCHOOL_VOCAB.search(d.get("kid_words") or "") or SCHOOL_VOCAB.search(d.get("input_prompt") or ""))


def _sanitize(s: str) -> str:
    for pat, rep in _SANITIZE:
        s = pat.sub(rep, s)
    return re.sub(r"\s{2,}", " ", s).strip()


def validate(out: dict[str, Any], raw: str, chk: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
    """Guardrails: code-enforced ceilings and checks on top of the LLM's decision."""
    d: dict[str, Any] = dict(out)
    d["accept"] = bool(d.get("accept", True))
    focus = str(d.get("focus") or "none").strip().lower()
    d["focus"] = focus if focus in FOCUS_TYPES else "none"
    sc = str(d.get("scaffold") or "none").strip().lower()
    d["scaffold"] = sc if sc in SCAFFOLDS else "none"
    ns = str(d.get("next_scaffold") or "starter_chips").strip().lower()
    d["next_scaffold"] = ns if ns in ("none", "starter_chips") else "starter_chips"
    d["chips"] = [x for x in (as_starter(c) for c in (d.get("chips") or [])) if x][:3]
    try:
        d["spell_rung"] = max(0, min(5, int(d.get("spell_rung") or 0)))
    except (TypeError, ValueError):
        d["spell_rung"] = 0
    d["kid_words"] = str(d.get("kid_words") or "").strip()
    d["input_prompt"] = str(d.get("input_prompt") or "").strip() or d["kid_words"][:90]
    d["prefill"] = str(d.get("prefill") or "").strip() or raw
    d["guardrail"] = ""

    sents = chk.get("sentences") or []
    ms = chk.get("misspellings") or []
    gf = chk.get("grammar_fixes") or []
    low = raw.lower()

    def force_accept(reason: str) -> None:
        d["accept"] = True
        d["guardrail"] = reason
        if d["focus"] != "none":
            d.setdefault("deferred", []).append(f"{d['focus']}: {d.get('focus_word') or ''}".strip(": "))
        d["focus"] = "none"

    if d["accept"]:
        d["focus"] = "none"
        # An accepted turn must not carry a hidden correction in its reaction line.
        if re.search(r"\b(fix|find|spot|check|mistakes?|typos?|spelling|capital|period|look again)\b", d["kid_words"], re.I):
            d["kid_words"] = ""
        return d

    # Streak ceiling: never more than MAX_CONSECUTIVE_FIXES asks in a row without drawing.
    if session.get("consecutive_fixes", 0) >= MAX_CONSECUTIVE_FIXES:
        force_accept("streak_ceiling")
        return d

    if d["focus"] == "none":
        force_accept("no_focus_given")
        return d

    # If LLM picked complete_sentence/run_on because a typo ('uoos'->'whose') looked like two clauses, pivot to spelling!
    if d["focus"] == "complete_sentence" and not any(s.get("issue") not in ("none", "run_on") for s in sents) and sents:
        if ms:
            d["focus"] = "spelling"
        else:
            force_accept("focus_not_present")
    elif d["focus"] == "run_on" and not any(s.get("issue") == "run_on" for s in sents):
        if ms:
            d["focus"] = "spelling"
        else:
            force_accept("focus_not_present")

    if d["focus"] == "capital" and not any(s.get("capital_ok") is False for s in sents):
        force_accept("focus_not_present")
    elif d["focus"] == "end_mark" and not any(s.get("end_ok") is False for s in sents):
        force_accept("focus_not_present")
    elif d["focus"] == "spelling":
        if not ms:
            force_accept("focus_not_present")
        else:
            fw = str(d.get("focus_word") or "").strip(".,!?;:\"' ")
            match = next((m for m in ms if m["wrote"].lower() == fw.lower()), None)
            if not match:
                match = ms[0]
            d["focus_word"], d["focus_correct"] = match["wrote"], match["meant"]
            d["misspelled"] = [m["wrote"] for m in ms]
            if d["spell_rung"] == 0:
                d["spell_rung"] = 3
            if d["spell_rung"] == 4:
                opts = [str(o).strip() for o in (d.get("spell_options") or []) if str(o).strip()]
                opts = list(dict.fromkeys(opts))
                if match["meant"] not in opts:
                    opts = [match["meant"]] + opts
                opts = opts[:3]
                if len(opts) < 2:
                    d["spell_rung"] = 3
                else:
                    random.shuffle(opts)
                    d["spell_options"] = opts
            if d["spell_rung"] >= 3 and match["wrote"].lower() not in d["kid_words"].lower():
                d["kid_words"] = (d["kid_words"] + f" Take another look at \"{match['wrote']}\".").strip()
            if d["spell_rung"] in (1, 2):
                # Don't give the word away on the find-it-yourself rungs.
                d["kid_words"] = re.sub(re.escape(match["wrote"]), "one word", d["kid_words"], flags=re.I)
                d["input_prompt"] = re.sub(re.escape(match["wrote"]), "one word", d["input_prompt"], flags=re.I)
    elif d["focus"] == "verb_ending":
        if not gf:
            force_accept("focus_not_present")
        else:
            fw = str(d.get("focus_word") or "").strip(".,!?;:\"' ")
            g = next((x for x in gf if x["wrote"].lower() == fw.lower()), gf[0])
            d["focus_word"] = g["wrote"]
            d["focus_correct"] = (g.get("options") or [""])[0]
            d["focus_options"] = g.get("options") or []
            if g["wrote"].lower() not in d["kid_words"].lower():
                d["kid_words"] = (d["kid_words"] + f" Check \"{g['wrote']}\".").strip()
    elif d["focus"] in ("word_choice",):
        fw = str(d.get("focus_word") or "")
        if fw and fw.lower() not in low:
            d["focus_word"] = ""
    return d


# ---------------------------------------------------------------- session bookkeeping


def new_session_state() -> dict[str, Any]:
    return {
        "started": time.time(),
        "turns": [],
        "today_state": {},
        "consecutive_fixes": 0,
        "pushed": 0,
        "deferred": 0,
        "last_request": None,
        "next_scaffold": "starter_chips",
        "offered_chips": [],
    }


def behaviour_facts(session: dict[str, Any], raw: str, signals: dict[str, Any]) -> str:
    turns = (session.get("turns") or []) + [{"text": raw, "secs": signals.get("secs"), "accept": None}]
    texts = [t.get("text") or "" for t in turns]
    wc = [len(re.findall(r"[A-Za-z']+", t)) for t in texts]
    lower = sum(1 for t in texts if t[:1].isalpha() and t[:1].islower())
    no_end = sum(1 for t in texts if t and not re.search(r'[.!?]["\')\]]*$', t.strip()))
    secs = [t.get("secs") for t in turns if isinstance(t.get("secs"), (int, float))]
    asks = [i for i, t in enumerate(turns[:-1]) if t.get("accept") is False]
    since_ask = (len(turns) - 1 - asks[-1] - 1) if asks else len(turns) - 1
    ignored = sum(1 for t in turns if "ignored" in str(t.get("outcome") or ""))
    complied = sum(1 for t in turns if "did it" in str(t.get("outcome") or ""))
    first, last = wc[: min(3, len(wc))], wc[-min(3, len(wc)):]
    trend = ""
    if len(wc) >= 4:
        a, b = sum(first) / len(first), sum(last) / len(last)
        trend = "shrinking" if b < a * 0.7 else ("growing" if b > a * 1.3 else "steady")

    # Measured effort signal (0-10). A measurement, not a decision: the coach may override with a stated reason.
    recent = texts[-4:]
    n = max(1, len(recent))
    score = 5.0
    avg_w = sum(wc[-4:]) / max(1, len(wc[-4:]))
    score += 1.5 if avg_w >= 14 else (0.5 if avg_w >= 9 else (-1.5 if avg_w < 6 else -0.5))
    score -= 2.0 * sum(1 for t in recent if t[:1].isalpha() and t[:1].islower()) / n
    score -= 1.0 * sum(1 for t in recent if t and not re.search(r'[.!?]["\')\]]*$', t.strip())) / n
    score -= 1.5 * sum(1 for t in recent if re.search(r"\b(idk+|dunno|whatever|boring)\b", t.lower())) / n
    score -= min(3.0, 1.5 * session.get("avoid_count", 0))
    score -= 1.0 * ignored
    score += 0.5 * complied
    if trend == "shrinking":
        score -= 1.0
    elif trend == "growing":
        score += 0.5
    if (signals.get("minutes") or 0) > 12:
        score -= 1.0
    score = max(0.0, min(10.0, score))
    label = "high" if score >= 6.5 else ("medium" if score >= 4.0 else "low")
    return "\n".join(
        [
            f"- MEASURED EFFORT SIGNAL: {score:.1f}/10 => {label}. Your today_state.energy should match this unless you name a specific reason in the note.",
            f"- writing turns today: {len(turns)}; words per turn: {wc[-6:]} (trend: {trend or 'too early'})",
            f"- lowercase starts: {lower}/{len(texts)}; missing end mark: {no_end}/{len(texts)}",
            f"- seconds per turn: {secs[-6:] or 'unknown'}",
            f"- avoidance/pushback messages today ('idk', 'boring', 'can we just draw'): {session.get('avoid_count', 0)}",
            f"- your asks today: {len(asks)}; he did it: {complied}; ignored or switched idea: {ignored}",
            f"- writing turns since your last ask: {since_ask}",
            f"- minutes into session: {signals.get('minutes', 0)}",
        ]
    )


def as_starter(chip: str) -> str:
    """Chips must be starters to finish, never whole sentences to copy."""
    c = re.sub(r"\s+", " ", str(chip or "")).strip().strip('"')
    c = re.sub(r"(…|\.\.\.)\s*$", "", c)
    words = c.split()
    if not words:
        return ""
    if re.search(r"[.!?]$", c) or len(words) > 7:
        words = [w.rstrip(".!?,") for w in words[: min(5, max(3, len(words) - 2))]]
    return " ".join(words).rstrip(",") + "…"


def chip_used(raw: str, offered: list[str]) -> bool:
    r = re.sub(r"[^a-z' ]", "", raw.lower()).strip()
    for c in offered or []:
        cc = re.sub(r"[^a-z' ]", "", c.lower().replace("…", "").replace("...", "")).strip()
        head = " ".join(cc.split()[:3])
        if head and r.startswith(head):
            return True
    return False


# ---------------------------------------------------------------- disengagement ("idk", "this is boring", one-word answers)

DISENGAGE_MOVES = ("draw_now", "quick_deal", "starters", "partial_frame", "twist", "switch_offer", "voice_offer", "wrap_offer")
SWITCH_OPTIONS = {
    "twist": "Surprise me with a twist",
    "game": "Make a mini-game instead",
    "comic": "Start a new comic",
    "voice": "Talk it out with the mic",
    "pause": "Pause for today",
}

DISENGAGE_SYSTEM = """You are the adaptive coach inside a comic-book and story app for {name}, a Grade {grade} boy with ADHD.
He just sent something that signals he's stuck, tired, bored, or pushing back (e.g. "idk", "this is boring", a single word, the same short thing again).
Decide the best next move FOR HIM, TODAY, from the evidence. Options:
- "draw_now": accept his PENDING DRAFT as-is and draw it right now (only possible when a pending draft exists). Weigh it like a teacher would: if he's asking to see his idea drawn, the draft is a real idea, and pressing the fix would cost more engagement than it teaches today, honor it (the issue is simply logged). If he has been dodging the same skill repeatedly and is otherwise fine, or the draft is too thin to draw, choose something else.
- "quick_deal": put his pending draft back in his box and offer a tiny deal ("add the period and it draws instantly"). His very next send draws, no further asks. Good middle ground when draw_now has already been used today.
ESCAPE LEARNING: if "can we just draw it" ALWAYS skips the fix, he learns that pushing back is the way out of writing. Count how often draw_now was already used this session (see moves tried). Honoring it occasionally is fine; repeatedly, prefer quick_deal or another move unless he is truly at the end of his rope.
- "starters": 2-3 tappable sentence STARTERS (3-6 words ending in "…", never whole sentences) from HIS story so he only has to finish an idea.
- "partial_frame": put half a sentence from his story in his box for him to finish.
- "twist": offer a wild, funny surprise event in his story to re-spark interest (he still writes what happens).
- "switch_offer": offer a different activity (mini-game, new comic) when this one has clearly gone stale.
- "voice_offer": suggest saying the idea out loud with the mic (good on low-energy days).
- "wrap_offer": offer to stop for today on a win when he's clearly done (many pushbacks, long session, low effort signal).
PRINCIPLES (evidence on ADHD, task avoidance and choice):
- Respect "no" immediately. Zero nagging, zero pep talks, zero guilt. One short line.
- Lower the demand and give him a choice; don't reward "idk" with free art, but make the next step tiny and fun.
- Don't repeat the move that just failed; escalate support or offer a switch/wrap as pushback repeats.
- Language: a sharp, funny comic collaborator. NEVER school words (complete sentence, punctuation, grammar, connector, clause, tier). You are an AI tutor, not his friend.
Return STRICT JSON:
{{"today_state":{{"energy":"high|medium|low","willingness":"high|medium|low","note":"short"}},
 "move":"draw_now|quick_deal|starters|partial_frame|twist|switch_offer|voice_offer|wrap_offer",
 "kid_words":"1-2 short sentences to say",
 "input_prompt":"very short line for the input bar",
 "chips":["starter…"],
 "prefill":"half sentence for partial_frame, else empty",
 "options":["twist|game|comic|voice|pause" keys to show as buttons, 1-3 of them],
 "rationale":"1-2 sentences for the parent",
 "hypothesis_updates":[{{"id":"H5","direction":"for|against","evidence":"short"}}]}}"""


def decide_disengaged(
    rec: dict[str, Any],
    session: dict[str, Any],
    raw: str,
    how: str,
    signals: dict[str, Any],
    context: str,
    story: str,
    has_project: bool,
    pending: str = "",
    last_focus: str = "",
) -> dict[str, Any] | None:
    model = ensure_model(rec)
    name = rec.get("name") or "the student"
    behaviour = behaviour_facts(session, raw, signals)
    recent_moves = ", ".join(session.get("disengage_moves") or []) or "none yet"
    prompt = f"""LEARNER: {name}, Grade {rec.get('grade', 3)}. Parent notes:
{chr(10).join('- ' + n.get('note', '') for n in (rec.get('parent_notes') or [])[:8]) or '(none)'}
WHAT WORKS FOR HIM: {'; '.join(model.get('what_works') or []) or '(nothing recorded yet)'}
HYPOTHESES: 
{_hyp_summary(model)}
BEHAVIOUR FACTS:
{behaviour}
Disengagement moves already tried this session (most recent last): {recent_moves}
PENDING DRAFT (his last real sentence, waiting on a fix you asked for): {pending or '(none; draw_now is NOT available)'}
What you last asked him to fix: {last_focus or '(nothing)'}
WHERE HE IS: {context} (has a saved book open: {has_project})
STORY SO FAR:
{story or '(just starting)'}
HE JUST SENT ({how}): "{raw}"
"""
    t0 = time.time()
    try:
        out = _call(DISENGAGE_SYSTEM.format(name=name, grade=rec.get("grade", 3)), prompt)
    except Exception:
        out = None
    if not out:
        return None
    d = dict(out)
    mv = str(d.get("move") or "starters").strip().lower()
    d["move"] = mv if mv in DISENGAGE_MOVES else "starters"
    if d["move"] in ("draw_now", "quick_deal") and not pending.strip():
        d["move"] = "starters"
    d["kid_words"] = _sanitize(str(d.get("kid_words") or "").strip())
    d["input_prompt"] = _sanitize(str(d.get("input_prompt") or "").strip()) or d["kid_words"][:90]
    d["chips"] = [x for x in (as_starter(c) for c in (d.get("chips") or [])) if x][:3]
    d["prefill"] = str(d.get("prefill") or "").strip()
    opts = [str(o).strip().lower() for o in (d.get("options") or []) if str(o).strip().lower() in SWITCH_OPTIONS]
    if d["move"] == "twist" and "twist" not in opts:
        opts = ["twist"] + opts
    if d["move"] == "voice_offer" and "voice" not in opts:
        opts = ["voice"] + opts
    if d["move"] == "wrap_offer" and "pause" not in opts:
        opts = opts + ["pause"]
    if d["move"] == "switch_offer" and not ({"game", "comic"} & set(opts)):
        opts = opts + ["game"]
    d["options"] = [SWITCH_OPTIONS[o] for o in dict.fromkeys(opts)][:3]
    if d["move"] == "partial_frame" and not d["prefill"]:
        d["move"] = "starters"
    if d["move"] == "starters" and not d["chips"] and not d["options"]:
        d["options"] = [SWITCH_OPTIONS["twist"], SWITCH_OPTIONS["voice"]]
    d["latency_s"] = round(time.time() - t0, 2)
    session["disengage_moves"] = (session.get("disengage_moves") or [])[-7:] + [d["move"]]
    apply_learning(model, {**d, "accept": False, "focus": "disengaged:" + d["move"], "scaffold": d["move"]}, raw)
    return d
