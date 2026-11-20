"""Observers watching every session alongside the live tutor.

- Critic: guards educational value across the session window and vets every new game spec
  and every invented activity idea before it reaches the child.
- Turn Auditor: scores every single tutor turn against our empirical rubric (with full
  learner context and controller state) for the live parent view and voice-turn drift checks.
- Tracker: models engagement (level, trend, risk) and gathers quote-based evidence per skill.
- WritingStats: deterministic counters from check_writing().
"""

from __future__ import annotations

import json
import re
from typing import Any

from google import genai
from google.genai import types

from .config import FALLBACK_MODEL, FAST_MODEL, HYDROGEN_MODEL, ROOT, api_key

OBSERVER_MODEL = HYDROGEN_MODEL  # gemini-4-hydrogen for child modeling, critic, and turn auditing
TARGETS_FILE = ROOT / "curriculum" / "targets.md"


def targets_text() -> str:
    try:
        return TARGETS_FILE.read_text(encoding="utf-8")
    except OSError:
        return ""


def _client() -> genai.Client:
    key = api_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set")
    return genai.Client(api_key=key)


def _json(text: str) -> Any:
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", t)
        return json.loads(m.group(0)) if m else {}


def _call(system: str, prompt: str, temperature: float = 0.2) -> dict[str, Any]:
    client = _client()
    for model in (OBSERVER_MODEL, FAST_MODEL, FALLBACK_MODEL):
        try:
            resp = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system, temperature=temperature, response_mime_type="application/json"
                ),
            )
            out = _json(resp.text)
            if isinstance(out, dict):
                return out
        except Exception:
            continue
    return {}


# ---------------------------------------------------------------- session critic

CRITIC_SYSTEM = """You are the education critic sitting silently beside a live AI tutor and a Grade 3 child (ADHD, strong reader, loses marks on complete sentences, hates babyish content and worksheets).
You are an experienced literacy specialist (SRSD, Saddler & Graham sentence combining, structured literacy, Ontario Language Curriculum 2023).

Flag as drifting or off_track if ANY of these happen:
- Conversational wh- traps: asking questions naturally answered with 1 word or a fragment ("Where is your base?", "What surrounds it?", "What's inside?") instead of setting up concrete sentence construction/combining/repair.
- Escape reinforcement: rewarding, drawing, praising, or playing along with minimal/avoidant answers ("cow", "cow", "idk", "stuff").
- Babyish or arbitrary school-drill filler: "write a sentence about what a bear eats / what color a cow is / what a cat does".
- Doing the cognitive work for him: dictating a complete sentence verbatim for him to copy, or offering complete sentences as tappable choices.
- Ignoring an engaged fragment/idea: switching away from his creative premise when he gave a vivid multi-word fragment that only needed a verb or boundary fix.
- Persona drift: claiming human feelings/experiences or acting like a buddy/friend instead of an honest AI tutor made by Google.

Return strict JSON:
{"verdict":"on_track|drifting|off_track","learning_per_minute":1-5,"skill_required":true|false,
 "who_is_doing_the_work":"kid|tutor|mixed","issue":"short, specific, or empty",
 "advice":"ONE concrete age-respectful, in-world move; empty if on_track","pivot":true|false}"""


def critique(window: str, mechanic: str, stats: dict[str, Any], tracker: dict[str, Any]) -> dict[str, Any]:
    prompt = (
        f"SKILL TARGETS (sourced):\n{targets_text()}\n\n"
        f"WHAT'S ON SCREEN / CURRENT MECHANIC:\n{mechanic or '(just conversation)'}\n\n"
        f"WRITING STATS SO FAR (computed):\n{json.dumps(stats)}\n\n"
        f"TRACKER'S READ ON ENGAGEMENT:\n{json.dumps(tracker.get('engagement', {}))}\n\n"
        f"LAST FEW MINUTES:\n{window}"
    )
    return _call(CRITIC_SYSTEM, prompt)


VET_SPEC_SYSTEM = """You are the education critic reviewing an HTML5 game/activity spec BEFORE it is coded for an intelligent Grade 3 child with ADHD.
Approve ONLY if:
1. Intrinsic integration (Habgood & Ainsworth 2011): constructing, combining, expanding, or repairing FULL SENTENCES (or retrieving spelling patterns from memory) is the actual control input—NOT multiple-choice clicking or 1-word typing.
2. Not a worksheet in disguise, not babyish (zero cartoon animals/confetti/baby talk), and zero cringe slang.
3. Every typed submission reports via window.tutor.send({kind:'submission', typed: ...}).
If it fails any check, rewrite the spec cleanly so it passes while keeping the fun game loop.
Return JSON: {"approve":true|false,"problems":["..."],"revised_description":"full revised spec, or empty if approved"}"""


def vet_spec(title: str, description: str) -> dict[str, Any]:
    prompt = f"SKILL TARGETS:\n{targets_text()}\n\nSPEC TITLE: {title}\nSPEC:\n{description}"
    return _call(VET_SPEC_SYSTEM, prompt)


VET_IDEAS_SYSTEM = """You are the education critic screening invented activity ideas BEFORE the tutor offers them to an intelligent Grade 3 child (ADHD, hates babyish material and cringe slang, loses marks on complete sentences).
Score each idea 1–5:
- Score 1–2 (REJECT) if it allows 1-word answers, uses multiple-choice sentence selection, uses insults ("idiot", "stupid"), uses babyish themes, or forces cringe slang.
- Score 4–5 if complete sentence construction/combining/debugging is genuinely inseparable from the mechanic and `first_move` gives concrete raw material on screen.
IMPORTANT: Only provide `fixed_mechanic` if you are writing a COMPLETE replacement 4–6 sentence step-by-step mechanic; otherwise leave `fixed_mechanic` as ""! Never put a 1-line comment in `fixed_mechanic`.
Also clean `pitch` into `fixed_pitch` if `pitch` has any insult, hype, or awkward phrasing (otherwise "").
Return JSON: {"ideas":[{"name":"...","score":1-5,"critic_note":"...","fixed_pitch":"","fixed_mechanic":""}]}"""


def vet_ideas(ideas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not ideas:
        return []
    out = _call(VET_IDEAS_SYSTEM, f"SKILL TARGETS:\n{targets_text()}\n\nIDEAS:\n{json.dumps(ideas, ensure_ascii=False)}")
    scored = {i.get("name"): i for i in out.get("ideas", []) if isinstance(i, dict)}
    result = []
    for idea in ideas:
        s = scored.get(idea.get("name"), {})
        idea = dict(idea)
        idea["critic_score"] = s.get("score", 4)
        idea["critic_note"] = s.get("critic_note", "")
        fp = (s.get("fixed_pitch") or "").strip()
        if len(fp) >= 20:
            idea["pitch"] = fp
        fm = (s.get("fixed_mechanic") or "").strip()
        # Guard against overwriting a full mechanic with a short editorial comment
        if len(fm) >= 140:
            idea["mechanic"] = fm
        result.append(idea)
    result.sort(key=lambda i: -(i.get("critic_score") or 0))
    return [i for i in result if (i.get("critic_score") or 3) >= 3] or result[:2]


# ---------------------------------------------------------------- per-turn auditor

TURN_AUDIT_SYSTEM = """You are the per-turn pedagogical auditor evaluating the AI tutor's MOST RECENT response to a Grade 3 student (see LEARNER PROFILE below).

A tutor turn PASSES (last_turn_ok = true) ONLY if ALL of these hold:
1. Educational task demand: It sets up, scaffolds, or responds to genuine language production—complete sentence construction, sentence combining (when/because/but/so/although), causal Story Spine planning, 3-Source Reading Inference & Informational Paragraph synthesis (Strand C / D1.3), SRSD TREE Persuasive drafting, Voice-to-Draft editing, fragment/run-on/punctuation repair, or Cover-Copy-Compare word retrieval—OR is a crisp <=2-sentence launch/wrap with concrete on-screen options/tasks.
2. Zero 1-word wh- traps: It does NOT ask a conversational question naturally answered by a single word or noun phrase ("Where is your base?", "What surrounds it?").
3. Zero escape reinforcement: If the student gave a minimal/avoidant input ("cow", "idk", "stuff"), the tutor did NOT praise it, play along with it, or draw it.
4. Zero babyish / arbitrary filler: No 1st-grade prompts ("what a bear eats", "what color a cow is", "what a cat does").
5. Student does the cognitive work: Tutor did NOT dictate a finished sentence verbatim for him to copy and did NOT offer complete sentences as choices.
6. AI transparency & tone: Plain, brief, respectful AI tutor tone (no fake human feelings/friendship, no "awesome!/fellow-kids" hype, no narrating internal tools/coaches).

If last_turn_ok is false, provide ONE concrete age-respectful corrective instruction in `next_move` (never baby animals, never wh- chat).
Return strict JSON:
{"last_turn_ok":true|false,"why":"concise reason","next_move":"empty if ok, else 1 concrete instruction","skill":"Ontario target e.g. B3.1 simple/compound/complex or B2.3 morphology"}"""


def turn_coach(recent: str, mechanic: str, last_check: str, learner_notes: str = "", controller_summary: str = "") -> dict[str, Any]:
    prompt = (
        f"LEARNER PROFILE:\n{learner_notes or 'Grade 3, ADHD, hates babyish content, working on complete/compound/complex sentences & spelling.'}\n\n"
        f"CONTROLLER STATE:\n{controller_summary or '(active)'}\n\n"
        f"ON SCREEN:\n{mechanic or '(canvas initializing)'}\n\n"
        f"LATEST WRITING CHECK:\n{last_check or '(none)'}\n\n"
        f"RECENT EXCHANGE (evaluate the final Tutor turn):\n{recent}"
    )
    return _call(TURN_AUDIT_SYSTEM, prompt, temperature=0.1)


# ---------------------------------------------------------------- tracker

TRACKER_SYSTEM = """You track a Grade 3 child's engagement and Ontario Language 2023 skills during a live tutoring session.
Engagement signals: complete sentences, multi-word creative ideas, revising fragments, combining clauses, fast responses, asking for more.
Disengagement signals: single-word escape ("cow", "cow"), "idk", "stuff", explicit refusal ("boring", "no").
Skills: quote exact evidence from the session only.

Return JSON:
{"engagement":{"level":1-5,"trend":"rising|steady|falling","evidence":"short quote-based"},
 "risk":"none|boredom|frustration|shutdown",
 "skills":[{"target":"e.g. B3.1 complete sentences","status":"not_seen|emerging|inconsistent|solid","evidence":"..."}],
 "interests_noticed":["..."],
 "headline":"one plain line for the parent"}"""


def track(window: str, stats: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    prompt = (
        f"SKILL TARGETS:\n{targets_text()}\n\n"
        f"WRITING STATS SO FAR:\n{json.dumps(stats)}\n\n"
        f"PREVIOUS READ:\n{json.dumps(previous)}\n\n"
        f"LAST FEW MINUTES:\n{window}"
    )
    return _call(TRACKER_SYSTEM, prompt)


# ---------------------------------------------------------------- computed stats

class WritingStats:
    """Deterministic counters from check_writing()."""

    def __init__(self) -> None:
        self.entries = 0
        self.sentence_attempts = 0
        self.complete_first_try = 0
        self.complete_total = 0
        self.issues: dict[str, int] = {}
        self.capital_missing = 0
        self.end_punct_missing = 0
        self.misspellings: list[dict[str, str]] = []
        self.typed_chars = 0
        self.typed_seconds = 0.0
        self.handwritten = 0

    def add(self, text: str, check: dict[str, Any], how: str, seconds: float = 0.0, first_try: bool = True) -> None:
        self.entries += 1
        if how == "typed":
            self.typed_chars += len(text)
            self.typed_seconds += seconds or 0
        else:
            self.handwritten += 1
        for s in check.get("sentences", []) or []:
            issue = s.get("issue", "none")
            if issue == "not_a_sentence_attempt":
                continue
            self.sentence_attempts += 1
            fully_ok = (
                issue == "none"
                and bool(s.get("complete"))
                and s.get("capital_ok") is not False
                and s.get("end_ok") is not False
            )
            if fully_ok:
                self.complete_total += 1
                if first_try:
                    self.complete_first_try += 1
            if issue != "none":
                self.issues[issue] = self.issues.get(issue, 0) + 1
            if s.get("capital_ok") is False:
                self.capital_missing += 1
            if s.get("end_ok") is False:
                self.end_punct_missing += 1
        for m in check.get("misspellings", []) or []:
            self.misspellings.append({"wrote": m.get("wrote", ""), "meant": m.get("meant", "")})

    def as_dict(self) -> dict[str, Any]:
        return {
            "entries": self.entries,
            "sentence_attempts": self.sentence_attempts,
            "complete_sentences": self.complete_total,
            "complete_on_first_try": self.complete_first_try,
            "complete_first_try_rate": round(self.complete_first_try / self.sentence_attempts, 2) if self.sentence_attempts else None,
            "issues": self.issues,
            "missing_capital": self.capital_missing,
            "missing_end_punctuation": self.end_punct_missing,
            "misspellings": self.misspellings[-20:],
            "typed_chars": self.typed_chars,
            "typing_chars_per_min": round(self.typed_chars / (self.typed_seconds / 60), 1) if self.typed_seconds > 0 else None,
            "handwritten_entries": self.handwritten,
        }
