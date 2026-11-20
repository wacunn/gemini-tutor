"""Synchronous Pedagogical Controller & Hard Tool Gate.

Sits between student inputs / tool calls and gemini-3.8-live so that EVERY turn is:
1. Strictly educational (aligned with Ontario Grade 3–4 Language B3.1, B3.3, B2.1–B2.3, D1–D2).
2. Grounded in empirical writing & ADHD science:
   - Explicit product goals & self-monitoring (Graham et al. 2012, ES=0.76; Reid & Lienemann 2006)
   - Sentence combining & kernel expansion (Saddler & Graham 2005, d=0.81; Graham & Perin 2007, d=0.50)
   - Graduated step-based hints without giving away the answer (VanLehn 2011, d=0.76; Bastani et al. 2024)
   - Hard escape extinction + antecedent load reduction on avoidance (Dunlap et al. 1994)
   - Formal pattern/morphological spelling via Cover-Copy-Compare on his own errors (Graham & Santangelo 2014, transfer ES=0.94; Bowers et al. 2010)
3. Respectful of an intelligent 8–9 year old (zero babyish animal trivia, zero 'fellow kids' slang, zero chat/wh- traps).
"""

from __future__ import annotations

import json
import re
from typing import Any

from google import genai
from google.genai import types

from . import thinking
from .config import FALLBACK_MODEL, FAST_MODEL, api_key

PLANNER_MODEL = FAST_MODEL

GREETINGS = {"hi", "hey", "hello", "yo", "sup", "hiya", "start", "ready", "ok", "okay"}
AVOIDANCE_WORDS = {
    "idk",
    "i dont know",
    "i don't know",
    "dunno",
    "stuff",
    "nothing",
    "whatever",
    "meh",
    "fine",
    "k",
    "kk",
    "asdf",
    "idk.",
    "?",
    "...",
}
REFUSAL_PATTERNS = (
    r"^(no|nope|nah|pass|stop|quit|skip)\b",
    r"\b(this is boring|boring|i dont want|i don't want|hate this|dumb|stupid|something else|different game|switch)\b",
)

# Priority order for selecting 1 high-value spelling word from his own writing (Ontario Gr. 3 B2.2–B2.3)
HIGH_VALUE_PATTERNS = (
    r"(ed|ing|er|est|ly|ful|less|ness|able|tion|sion)$",  # suffix / doubling / drop-e / y->i
    r"^(un|re|dis|pre|mis|non|sub|over|under)",  # prefixes
    r"(tch|dge|ck|igh|eigh|ough|kn|wr|mb|ai|ay|oi|oy|ou|ow|ea)",  # orthographic / positional
    r"because|friend|said|they|where|there|which|their|through|caught|thought",  # high-frequency irregulars
)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s']", "", (s or "").lower())).strip()


def _words(s: str) -> list[str]:
    return re.findall(r"[A-Za-z']+", s or "")


def _fmt_conns(conns: str) -> str:
    parts = [f"'{c.strip()}'" for c in (conns or "when | so").split("|") if c.strip()]
    if len(parts) <= 1:
        return parts[0] if parts else "'when'"
    return ", ".join(parts[:-1]) + f", or {parts[-1]}" if len(parts) > 2 else f"{parts[0]} or {parts[1]}"


KERNEL_SYSTEM = """You generate a 2-kernel Sentence Combining scaffold for an intelligent child (see LEARNER CONTEXT below; NEVER use babyish 1st-grade farm/zoo/pet trivia and NEVER use cringe slang).
Given the active story/context (if any) and target connector set, output TWO short, concrete, action-packed simple sentences (5–8 words each) and 2 connectors (e.g. "when | because" or "but | so") that the student can combine into ONE strong compound or complex sentence.
Rules:
- NEVER write the combined sentence for the student.
- If the student already introduced a subject/premise, build BOTH kernels directly from THEIR premise so their story continues!
- If no premise exists yet, draw naturally from their interests/notes in LEARNER CONTEXT (or a crisp, imaginative contraption/adventure moment if no interests are listed yet).
- NEVER use babyish filler prompts (no "what a bear eats", "what color a cow is", "a cat sleeps").
Return strict JSON:
{"kernel_1":"Complete short sentence 1.",
 "kernel_2":"Complete short sentence 2.",
 "connectors":"when | so",
 "ask_prompt":"Combine those two sentences into one sentence using 'when' or 'so' (or write your own complete sentence) to run the scene."}"""


def generate_combine_scaffold(rec: dict[str, Any], active_story: list[str], engaged_draft: str, rung: str) -> dict[str, str]:
    """Fast (~0.4s) context-aware 2-kernel generator so 'idk'/minimal answers drop initiation load without dropping sentence rigor."""
    story_txt = "\n".join(f"- {s}" for s in active_story[-4:]) or "(none yet)"
    notes_txt = "; ".join(n.get("note", "") for n in (rec.get("parent_notes") or [])[:6])
    interests_txt = ", ".join((rec.get("model") or {}).get("interests") or [])
    connector_goal = (
        "when | because | if" if rung in ("B3.1_complex",) else "but | so | when"
    )
    prompt = (
        f"LEARNER CONTEXT: Grade {rec.get('grade', 3)}. Notes: {notes_txt or '(none)'}. Interests: {interests_txt or '(open)'}.\n"
        f"Active story sentences so far:\n{story_txt}\n"
        f"Latest fragment/idea if any: {engaged_draft or '(none)'}\n"
        f"Preferred connectors: {connector_goal}"
    )
    try:
        client = genai.Client(api_key=api_key())
        for model in (PLANNER_MODEL, FALLBACK_MODEL):
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=KERNEL_SYSTEM,
                        temperature=0.4,
                        response_mime_type="application/json",
                    ),
                )
                out = thinking._json(resp.text)
                if isinstance(out, dict) and out.get("kernel_1") and out.get("kernel_2"):
                    return {
                        "kernel_1": str(out["kernel_1"]).strip(),
                        "kernel_2": str(out["kernel_2"]).strip(),
                        "connectors": str(out.get("connectors") or "when | so").strip(),
                        "ask_prompt": str(
                            out.get("ask_prompt")
                            or "Combine the two lines on the card into one complete sentence."
                        ).strip(),
                    }
            except Exception:
                continue
    except Exception:
        pass
    # Deterministic fallback (never babyish)
    return {
        "kernel_1": "The iron pressure plate clicks.",
        "kernel_2": "A hidden piston drops the floor over lava.",
        "connectors": "when | so",
        "ask_prompt": "Combine those two lines into one complete sentence using 'when' or 'so' (or write your own).",
    }


class SessionController:
    """Deterministic pedagogical state machine + synchronous turn director."""

    def __init__(self, rec: dict[str, Any]):
        self.rec = rec
        self.name = rec.get("name") or "the student"
        self.parent_title = rec.get("parent_title") or "your parent"
        self.phase: str = "OPENING"  # OPENING -> BUILDING -> WORD_STUDY -> WRAP
        self.rung: str = "B3.1_simple"  # B3.1_simple -> B3.1_compound -> B3.1_complex
        self.goal_label: str = "Sentences"
        self.goal_done: int = 0
        self.goal_target: int = 3
        self.first_try_streak: int = 0

        self.turn_index: int = 0
        self.hint_step: int = 0
        self.avoidance_streak: int = 0
        self.refusal_streak: int = 0

        self.last_kid_kind: str = "NONE"
        self.last_kid_text: str = ""
        self.prev_norm_text: str = ""

        self.engaged_draft: str = ""
        self.active_story: list[str] = []
        self.active_mechanic: str = ""

        self.misspellings: list[dict[str, str]] = []
        self.word_target: dict[str, str] | None = None
        self.word_study_done: bool = False
        self.word_study_tries: int = 0

        self.draw_unlocked: bool = False
        self.ui_locked_this_turn: set[str] = set()

    def goal_badge(self) -> str:
        if self.phase == "WORD_STUDY" and self.word_target:
            return f"{self.goal_label}: {self.goal_done}/{self.goal_target} · Word Forge: 1 word"
        streak = f" · First-try streak: {self.first_try_streak}" if self.first_try_streak >= 2 else ""
        return f"{self.goal_label}: {self.goal_done}/{self.goal_target}{streak}"

    def _pick_best_misspelling(self) -> dict[str, str] | None:
        if not self.misspellings:
            return None
        scored = []
        for idx, m in enumerate(self.misspellings):
            meant = m.get("meant", "").lower()
            score = 0
            for rank, pat in enumerate(HIGH_VALUE_PATTERNS):
                if re.search(pat, meant):
                    score = 10 - rank
                    break
            if len(meant) >= 5:
                score += 1
            scored.append((score, idx, m))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return scored[0][2]

    def _merge_fragments(self, prev: str, cur: str) -> str:
        if not prev:
            return cur.strip()
        p_low, c_low = prev.lower(), cur.lower()
        if p_low in c_low:
            return cur.strip()
        if c_low in p_low:
            return prev.strip()
        # e.g. "in the nether fortress" + "a wither skeleton with a bow"
        p_clean = prev.strip().rstrip(".!?,")
        c_clean = cur.strip()
        if re.match(r"^(in|on|at|under|inside|near|behind|above|during|after|before|when|while)\b", p_low):
            return f"{p_clean}, {c_clean}"
        return f"{p_clean} {c_clean}"

    def record_misspellings(self, chk: dict[str, Any]) -> None:
        existing = {(m["wrote"].lower(), m["meant"].lower()) for m in self.misspellings}
        for m in chk.get("misspellings") or []:
            w, mt = (m.get("wrote") or "").strip(), (m.get("meant") or "").strip()
            if w and mt and w.lower() != mt.lower() and (w.lower(), mt.lower()) not in existing:
                self.misspellings.append({"wrote": w, "meant": mt})
                existing.add((w.lower(), mt.lower()))

    def classify_and_advance(
        self,
        text: str,
        how: str,
        chk: dict[str, Any] | None = None,
        opening_ideas: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Deterministically classifies student input, advances state, and returns UI actions + tutor directive."""
        self.ui_locked_this_turn.clear()
        raw = (text or "").strip()
        norm = _norm(raw)
        wlist = _words(raw)
        idx = self.turn_index
        self.turn_index += 1
        self.last_kid_text = raw

        if chk:
            self.record_misspellings(chk)

        ui_actions: list[dict[str, Any]] = []

        # ---------------- 1. WORD STUDY RETRIEVAL PHASE ----------------
        if self.phase == "WORD_STUDY" and self.word_target:
            target_word = self.word_target["word"]
            # Look for target word in what he typed/handwrote
            typed_words = [w.lower() for w in wlist]
            matched = target_word.lower() in typed_words or norm == target_word.lower()
            self.word_study_tries += 1
            self.last_kid_kind = "SPELLING_ATTEMPT"
            self.prev_norm_text = norm
            if matched or self.word_study_tries >= 2:
                self.word_study_done = True
                self.phase = "WRAP" if self.goal_done >= self.goal_target else "BUILDING"
                ui_actions.append({"type": "remove", "id": "word"})
                ui_actions.append({"type": "goal", "text": self.goal_badge()})
                if matched:
                    directive = (
                        f"SPELLING LOCKED IN: {self.name} spelled '{target_word}' accurately from memory! "
                        f"Confirm specifically how he nailed the '{self.word_target['parts']}' pattern in one plain sentence. "
                        + (
                            f"He has hit today's sentence goal—call save_piece with a fitting title so {self.name} and {self.parent_title} can keep it, "
                            "and ask if he wants to add one bonus panel/sentence or wrap here."
                            if self.phase == "WRAP"
                            else f"Now return to sentence {self.goal_done + 1} of {self.goal_target}."
                        )
                    )
                else:
                    directive = (
                        f"Show the exact comparison once: '{target_word}' ({self.word_target['parts']}), without saying 'wrong'. "
                        "Move cleanly to saving his piece with save_piece or the next sentence—never drill one word past two tries."
                    )
                return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": directive}
            else:
                # 1 retry: flash parts again briefly, auto-cover when typing
                ui_actions.append(
                    {
                        "type": "item",
                        "item": {
                            "id": "word",
                            "kind": "word",
                            "word": target_word,
                            "parts": [p.strip() for p in self.word_target["parts"].split("+")],
                            "note": self.word_target["note"],
                        },
                    }
                )
                ui_actions.append(
                    {
                        "type": "input",
                        "mode": "type",
                        "prompt": f"Look at the parts ({self.word_target['parts']}), then type '{target_word}' from memory.",
                        "prefill": "",
                    }
                )
                self.ui_locked_this_turn.update({"show_word", "ask_input"})
                directive = (
                    f"{self.name} wrote '{raw}' for '{target_word}'. Do NOT say 'wrong'. Point out the exact tricky part "
                    f"({self.word_target['parts']}) in one short sentence and let him write '{target_word}' once more from memory."
                )
                return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": directive}

        # ---------------- 2. TAP INPUTS ----------------
        if how == "tap":
            self.prev_norm_text = norm
            # Is it a single-word verb/connector scaffold chip?
            if len(wlist) <= 2 and self.engaged_draft:
                self.last_kid_kind = "SCAFFOLD_CHIP"
                merged = f"{self.engaged_draft.rstrip('.!?, ')} {raw} "
                ui_actions.append(
                    {
                        "type": "input",
                        "mode": "type",
                        "prompt": f"Finish and send the complete sentence using '{raw}' (start with a capital, end with . ! or ?).",
                        "prefill": merged[:1].upper() + merged[1:] if merged else raw,
                    }
                )
                self.ui_locked_this_turn.add("ask_input")
                directive = (
                    f"He picked the word '{raw}'. His draft is pre-filled in his typing box. "
                    "In ONE short sentence, tell him to finish the full sentence in the box and hit Enter so you can draw/run it."
                )
                return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": directive}

            # Activity / Mechanic selection
            self.last_kid_kind = "PROJECT_PICK"
            self.phase = "BUILDING"
            self.active_mechanic = raw
            self.avoidance_streak = 0
            self.refusal_streak = 0
            ui_actions.append({"type": "goal", "text": self.goal_badge()})
            if "game" in raw.lower() or "mini-game" in raw.lower():
                directive = (
                    f"{self.name} chose '{raw}'. Call build_activity NOW with a tight, concrete spec where EVERY round requires "
                    "typing or repairing a complete sentence (never multiple-choice clicking), AND while it builds (~30s), put a "
                    "2-kernel Sentence Combining warm-up card on screen (show_card + ask_input) so he writes Sentence 1 right now."
                )
            else:
                scaf = generate_combine_scaffold(self.rec, self.active_story, "", self.rung)
                card_txt = (
                    f"Option A — Combine these two lines with {_fmt_conns(scaf['connectors'])}:\n"
                    f"  1. {scaf['kernel_1']}\n"
                    f"  2. {scaf['kernel_2']}\n\n"
                    f"Option B — Write your own complete sentence (Who + Does What + Capital & .)"
                )
                ui_actions.append(
                    {"type": "item", "item": {"id": "forge", "kind": "card", "title": f"{raw} · Step 1 of {self.goal_target}", "text": card_txt}}
                )
                ui_actions.append({"type": "input", "mode": "type", "prompt": "Type Sentence 1 (combine Option A, or write your own complete sentence)."})
                self.ui_locked_this_turn.update({"show_card", "ask_input"})
                directive = (
                    f"{self.name} picked '{raw}'. Start it immediately (e.g. call comic_new with 3 panels if it's a comic). "
                    "A starter card is already on screen so he has zero blank-page friction. In ONE plain sentence, tell him to "
                    "either combine the two lines on screen or type his own complete first sentence to render Step 1. No wh- chat questions."
                )
            return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": directive}

        # ---------------- 3. TURN-1 GREETING ----------------
        if idx == 0 and norm in GREETINGS:
            self.last_kid_kind = "GREETING"
            self.phase = "BUILDING"
            self.prev_norm_text = norm
            ideas = opening_ideas or []
            opt1 = ideas[0]["name"] if len(ideas) >= 1 else "3-Panel Trap Comic"
            opt2 = ideas[1]["name"] if len(ideas) >= 2 else "Cursed Command Compiler"
            scaf = generate_combine_scaffold(self.rec, [], "", self.rung)
            card_txt = (
                f"Quick start — combine these into 1 sentence with 'when' or 'so', OR type your own complete sentence:\n"
                f"  1. {scaf['kernel_1']}\n"
                f"  2. {scaf['kernel_2']}"
            )
            ui_actions.append({"type": "goal", "text": self.goal_badge()})
            ui_actions.append(
                {
                    "type": "item",
                    "item": {
                        "id": "open_choices",
                        "kind": "choices",
                        "prompt": "Pick a format, or jump straight in below:",
                        "options": [opt1, opt2, "Build a Live Mini-Game"],
                    },
                }
            )
            ui_actions.append({"type": "item", "item": {"id": "forge", "kind": "card", "title": "Sentence 1 of 3 (draws only from full sentences)", "text": card_txt}})
            ui_actions.append(
                {
                    "type": "input",
                    "mode": "type",
                    "prompt": "Type one complete sentence (combine the two lines above, or write your own idea) to draw Scene 1.",
                }
            )
            self.ui_locked_this_turn.update({"show_choices", "show_card", "ask_input"})
            directive = (
                f"First turn! {self.name} said '{raw}'. Choice chips AND a ready-to-go Sentence 1 card are ALREADY on screen. "
                "Do NOT call draw, do NOT ask 'what are you into?', and do NOT ask any wh- question. "
                "Say at most TWO short, plain sentences: introduce yourself honestly as Gemini (an AI tutor made by Google) and "
                "tell him he can tap a format on screen or type one complete sentence right now (combining the two trap lines or pitching his own scene) and you'll draw/build it."
            )
            return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": directive}

        # ---------------- 4. EXPLICIT REFUSAL ----------------
        if any(re.search(p, norm) for p in REFUSAL_PATTERNS):
            self.last_kid_kind = "REFUSAL"
            self.refusal_streak += 1
            self.avoidance_streak = 0
            self.prev_norm_text = norm
            self.draw_unlocked = False
            if self.refusal_streak == 1:
                self.goal_target = 2
                scaf = generate_combine_scaffold(self.rec, self.active_story, "", "B3.1_compound")
                ui_actions.append({"type": "goal", "text": self.goal_badge()})
                ui_actions.append(
                    {
                        "type": "item",
                        "item": {
                            "id": "pivot_choices",
                            "kind": "choices",
                            "prompt": "Switch how we do it:",
                            "options": ["Build a playable mini-game", "2-sentence absurd comic sprint"],
                        },
                    }
                )
                ui_actions.append(
                    {
                        "type": "item",
                        "item": {
                            "id": "forge",
                            "kind": "card",
                            "title": "Fast 2-Sentence Option (zero blank page)",
                            "text": f"Combine into 1 sentence using 'but' or 'when' (or write your own):\n  1. {scaf['kernel_1']}\n  2. {scaf['kernel_2']}",
                        },
                    }
                )
                ui_actions.append(
                    {
                        "type": "input",
                        "mode": "type",
                        "prompt": "Tap to build a live game, or type 1 complete sentence to run the 2-sentence sprint.",
                    }
                )
                self.ui_locked_this_turn.update({"show_choices", "show_card", "ask_input"})
                directive = (
                    f"{self.name} pushed back ('{raw}'). Respect 'no' immediately—zero nagging, zero pep talks, zero babyish pivots. "
                    "Say ONE short plain line ('Fair enough, scrapping that.') and tell him he can either tap to have you code a live playable "
                    "mini-game on the spot, or knock out just two quick sentences starting with the card on screen."
                )
            else:
                ui_actions.append(
                    {
                        "type": "item",
                        "item": {
                            "id": "wrap_choices",
                            "kind": "choices",
                            "prompt": "Your call:",
                            "options": ["Build a custom mini-game", "Pause here for today"],
                        },
                    }
                )
                self.ui_locked_this_turn.add("show_choices")
                directive = (
                    f"Second refusal ('{raw}'). Keep total respect and zero pressure. In ONE plain sentence, offer the choice on screen: "
                    "either code a quick custom game around any topic he names in one sentence, or pause cleanly for today."
                )
            return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": directive}

        # ---------------- 5. TURN-1 TOPIC NAMING (e.g. "minecraft") ----------------
        if idx == 0 and len(wlist) == 1 and norm not in AVOIDANCE_WORDS and raw.lower() not in {"cow", "cat", "dog", "bear"}:
            self.last_kid_kind = "PROJECT_PICK"
            self.phase = "BUILDING"
            self.prev_norm_text = norm
            self.engaged_draft = raw
            scaf = generate_combine_scaffold(self.rec, [], raw, self.rung)
            ui_actions.append({"type": "goal", "text": self.goal_badge()})
            ui_actions.append(
                {
                    "type": "item",
                    "item": {
                        "id": "forge",
                        "kind": "card",
                        "title": f"{raw.title()} · Sentence 1 of {self.goal_target}",
                        "text": f"Combine these two lines with {_fmt_conns(scaf['connectors'])}, OR write your own complete sentence about {raw}:\n  1. {scaf['kernel_1']}\n  2. {scaf['kernel_2']}",
                    },
                }
            )
            ui_actions.append(
                {
                    "type": "input",
                    "mode": "type",
                    "prompt": f"Type one complete sentence (Who + Does What + Capital & .) to launch Scene 1.",
                }
            )
            self.ui_locked_this_turn.update({"show_card", "ask_input"})
            directive = (
                f"{self.name} named '{raw}'. Do NOT ask conversational questions ('what do you like to build?'). "
                "Start a 3-panel comic (comic_new) or blueprint right away and tell him in ONE plain sentence to type one complete "
                "sentence (either combining the two lines on the card or writing his own) to draw Panel 1."
            )
            return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": directive}

        # ---------------- 6. TASK AVOIDANCE / ESCAPE ("cow", "cow", "idk", "stuff") ----------------
        is_repeated_short = bool(norm and norm == self.prev_norm_text and len(wlist) <= 2)
        is_bare_one_word = len(wlist) <= 1 and (
            norm in AVOIDANCE_WORDS
            or not chk
            or all(s.get("issue") != "none" for s in (chk.get("sentences") or []))
        )
        if norm in AVOIDANCE_WORDS or is_repeated_short or is_bare_one_word:
            self.last_kid_kind = "AVOIDANCE_ESCAPE"
            self.avoidance_streak += 1
            self.phase = "BUILDING"
            self.prev_norm_text = norm
            self.draw_unlocked = False

            scaf = generate_combine_scaffold(self.rec, self.active_story, self.engaged_draft, self.rung)
            ui_actions.append({"type": "goal", "text": self.goal_badge()})

            if self.avoidance_streak == 1:
                card_title = (
                    f"Continue Scene {self.goal_done + 1} of {self.goal_target} — Combine into 1 Sentence"
                    if self.active_story
                    else f"Sentence Forge ({self.goal_done + 1} of {self.goal_target}) — Full Sentences Only"
                )
                card_txt = (
                    f"Combine these two lines into ONE complete sentence using {_fmt_conns(scaf['connectors'])}\n"
                    f"(or write your own complete sentence with a Who + Does What):\n"
                    f"  1. {scaf['kernel_1']}\n"
                    f"  2. {scaf['kernel_2']}"
                )
                ui_actions.append({"type": "item", "item": {"id": "forge", "kind": "card", "title": card_title, "text": card_txt}})
                ui_actions.append(
                    {
                        "type": "input",
                        "mode": "type",
                        "prompt": scaf["ask_prompt"],
                        "prefill": "",
                    }
                )
                self.ui_locked_this_turn.update({"show_card", "ask_input"})
                directive = (
                    f"DISENGAGEMENT / MINIMAL INPUT ('{raw}'): HARD ESCAPE EXTINCTION + ANTECEDENT SCAFFOLD. "
                    "Do NOT draw anything, do NOT praise or joke about a 1-word answer ('interesting!', 'a cow base?'), "
                    "and NEVER switch to babyish animal trivia ('what does a bear eat / what color is a cow / what does a cat do'). "
                    "A 2-kernel Sentence Combining card is ALREADY on screen so he doesn't have to invent an idea from a blank page. "
                    f"In ONE plain, matter-of-fact sentence, state that one-word/idk inputs don't run the scene, and invite him to "
                    f"combine the two lines on screen with {_fmt_conns(scaf['connectors'])} (or type his own full sentence) to draw it."
                )
            elif self.avoidance_streak == 2:
                self.goal_target = max(self.goal_done + 1, 2)
                starter = scaf["kernel_1"].rstrip(".!?") + " when "
                ui_actions.append(
                    {
                        "type": "item",
                        "item": {
                            "id": "forge",
                            "kind": "card",
                            "title": "Half-Built Clause — Finish & Punctuate It",
                            "text": f"Finish this sentence in the box below (or tap to switch to a live game):\n  \"{starter}________.\"\n  (Idea from line 2: {scaf['kernel_2']})",
                        },
                    }
                )
                ui_actions.append(
                    {
                        "type": "item",
                        "item": {
                            "id": "avoid_choices",
                            "kind": "choices",
                            "prompt": "Or switch format:",
                            "options": ["Build a playable mini-game instead"],
                        },
                    }
                )
                ui_actions.append(
                    {
                        "type": "input",
                        "mode": "type",
                        "prompt": "Finish the pre-filled sentence in the box and end with a period.",
                        "prefill": starter,
                    }
                )
                self.ui_locked_this_turn.update({"show_card", "show_choices", "ask_input"})
                directive = (
                    f"SECOND CONSECUTIVE MINIMAL INPUT ('{raw}'). Zero nagging, zero animal trivia, zero drawing. "
                    f"The start of a complex sentence ('{starter}') is now pre-filled right in his typing box so typing effort is tiny, "
                    "plus a chip to switch to a live mini-game. In ONE short, calm sentence, tell him to finish the sentence in his box "
                    "(just 3–5 words + period) or tap to switch to a live game."
                )
            else:
                starter = scaf["kernel_1"].rstrip(".!?") + " so "
                ui_actions.append(
                    {
                        "type": "item",
                        "item": {
                            "id": "avoid_choices",
                            "kind": "choices",
                            "prompt": "Pick one:",
                            "options": ["Build a custom mini-game", "Wrap up for today"],
                        },
                    }
                )
                ui_actions.append(
                    {
                        "type": "input",
                        "mode": "type",
                        "prompt": "Finish this 1 sentence to unlock the drawing, or pick an option above.",
                        "prefill": starter,
                    }
                )
                self.ui_locked_this_turn.update({"show_choices", "ask_input"})
                directive = (
                    f"REPEATED AVOIDANCE ({self.avoidance_streak}x, '{raw}'). Do NOT nag, lecture, or invent baby questions. "
                    "In ONE plain, respectful sentence, give him a clean choice: finish the one started sentence in the box, "
                    "tap to build a live game, or wrap up cleanly for today."
                )
            return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": directive}

        # ---------------- 7. GENUINE WRITING ATTEMPTS (Syntactic Evaluation) ----------------
        self.phase = "BUILDING"
        self.prev_norm_text = norm
        self.avoidance_streak = 0
        self.refusal_streak = 0

        sents = (chk or {}).get("sentences") or []
        has_run_on = any(s.get("issue") == "run_on" for s in sents)
        has_fragment = any(s.get("issue") in ("missing_subject", "missing_verb", "incomplete_thought", "not_a_sentence_attempt") for s in sents) or not sents
        missing_cap = any(s.get("capital_ok") is False for s in sents)
        missing_end = any(s.get("end_ok") is False for s in sents)

        # 7A. ENGAGED RUN-ON
        if has_run_on:
            self.last_kid_kind = "ENGAGED_RUN_ON"
            self.draw_unlocked = False
            self.hint_step = min(3, self.hint_step + 1)
            self.engaged_draft = raw
            fixed_prefill = raw[:1].upper() + raw[1:] if raw else ""
            ui_actions.append(
                {
                    "type": "item",
                    "item": {
                        "id": "forge",
                        "kind": "card",
                        "title": "Boundary Overload — Split or Join Cleanly",
                        "text": (
                            f"Your draft:\n  \"{raw}\"\n\n"
                            "Fix: Replace 'and then' with a period + capital letter to make 2 sharp sentences, "
                            "OR join two actions cleanly with 'when' or 'so'."
                        ),
                    },
                }
            )
            ui_actions.append(
                {
                    "type": "input",
                    "mode": "type",
                    "prompt": "Edit your draft right in the box: replace 'and then' with periods (or 'when'/'so') so each sentence is clean.",
                    "prefill": fixed_prefill,
                }
            )
            self.ui_locked_this_turn.update({"show_card", "ask_input"})
            directive = (
                f"ENGAGED RUN-ON: {self.name} wrote a rich multi-event chain ('{raw}'). Keep 100% of his cool idea! "
                "Do NOT draw yet and do NOT switch topics. His exact text is pre-filled in his input box so he does NOT have to retype it. "
                "In 1–2 plain sentences, tell him the scene jammed because several actions are chained with 'and then'—have him split them "
                "with a period + capital (or use 'when') right in the box so you can render it."
            )
            return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": directive}

        # 7B. ENGAGED FRAGMENT (missing subject, missing verb, or dependent/prepositional phrase)
        if has_fragment:
            self.last_kid_kind = "ENGAGED_FRAGMENT"
            self.draw_unlocked = False
            self.hint_step = min(3, self.hint_step + 1)
            self.engaged_draft = self._merge_fragments(self.engaged_draft, raw)
            issues = [s.get("issue") for s in sents]

            if "missing_verb" in issues:
                gap_explain = f"You have the 'who/what' ({self.engaged_draft}), now add what it DOES"
                frame = f"{self.engaged_draft[:1].upper() + self.engaged_draft[1:].rstrip('.!?, ')} "
                verb_chips = ["stomps", "ambushes", "blasts", "shatters"]
            elif "missing_subject" in issues:
                gap_explain = f"You have the action ({raw}), now add WHO or WHAT is doing it at the front"
                frame = f"The ________ {raw.lstrip().rstrip('.!?')}."
                verb_chips = ["The iron golem", "The creeper", "A giant boss"]
            else:
                gap_explain = f"You set up '{self.engaged_draft}', now finish what happens (who does what)"
                clean_d = self.engaged_draft[:1].upper() + self.engaged_draft[1:].rstrip(".!?, ")
                frame = f"{clean_d}, " if re.match(r"^(in|on|at|under|inside|when|after|before|if|because)\b", clean_d.lower()) else f"{clean_d} "
                verb_chips = ["launches", "explodes", "guards", "crashes"]

            if self.hint_step == 1:
                ui_actions.append(
                    {
                        "type": "input",
                        "mode": "type",
                        "prompt": f"{gap_explain} (with a capital and period) to draw it.",
                        "prefill": frame if "________" not in frame else "",
                    }
                )
                self.ui_locked_this_turn.add("ask_input")
                directive = (
                    f"ENGAGED FRAGMENT (Hint Step 1/3): {self.name} wrote '{raw}' (combined draft: '{self.engaged_draft}'). "
                    "He IS engaged—NEVER switch topics and NEVER draw an incomplete fragment! "
                    "Do NOT use grammar jargon ('predicate', 'fragment') and NEVER dictate a finished sentence for him to copy. "
                    f"His words are pre-filled in his typing box. In ONE plain sentence, tell him: {gap_explain} so it's a complete sentence and you'll draw/run it."
                )
            elif self.hint_step == 2:
                ui_actions.append(
                    {
                        "type": "item",
                        "item": {
                            "id": "forge",
                            "kind": "card",
                            "title": "Finish Your Sentence Frame",
                            "text": f"Build on your exact words:\n  \"{frame}________.\"",
                        },
                    }
                )
                ui_actions.append(
                    {
                        "type": "input",
                        "mode": "type",
                        "prompt": "Finish your pre-filled sentence in the box and end with a period.",
                        "prefill": frame.replace("________ ", ""),
                    }
                )
                self.ui_locked_this_turn.update({"show_card", "ask_input"})
                directive = (
                    f"ENGAGED FRAGMENT (Hint Step 2/3): Still missing a complete clause ('{self.engaged_draft}'). "
                    "A sentence frame built from HIS exact words is now on screen and pre-filled in his box. "
                    "In ONE short sentence, point to the frame on screen and ask him to add the missing action/part and a period."
                )
            else:
                ui_actions.append(
                    {
                        "type": "item",
                        "item": {
                            "id": "forge",
                            "kind": "card",
                            "title": "Pick an Action Word (or Use Your Own) & Finish the Sentence",
                            "text": f"Your start:\n  \"{frame}________.\"",
                        },
                    }
                )
                ui_actions.append(
                    {
                        "type": "item",
                        "item": {
                            "id": "verb_bank",
                            "kind": "choices",
                            "prompt": "Tap a word to drop into your box, then finish the sentence:",
                            "options": verb_chips[:3],
                        },
                    }
                )
                ui_actions.append(
                    {
                        "type": "input",
                        "mode": "type",
                        "prompt": "Finish the complete sentence in the box (capital at start, period at end).",
                        "prefill": frame.replace("________ ", ""),
                    }
                )
                self.ui_locked_this_turn.update({"show_card", "show_choices", "ask_input"})
                directive = (
                    f"ENGAGED FRAGMENT (Hint Step 3/3): Word-bank chips ({', '.join(verb_chips[:3])}) and his frame are on screen. "
                    "Tell him in ONE short sentence to tap one of those words (or pick his own) and finish the full sentence in the box."
                )
            return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": directive}

        # 7C. COMPLETE CLAUSE MISSING ONLY CAPITAL AND/OR END PUNCTUATION (B3.3 Conventions)
        if missing_cap or missing_end:
            self.last_kid_kind = "CONVENTION_ONLY"
            self.draw_unlocked = False
            self.hint_step = min(3, self.hint_step + 1)
            needed = []
            if missing_cap:
                needed.append("a capital letter at the start")
            if missing_end:
                needed.append("end punctuation (. ! or ?)")
            need_str = " and ".join(needed)
            ui_actions.append(
                {
                    "type": "input",
                    "mode": "type",
                    "prompt": f"Complete thought! Add {need_str} right in the box and hit Enter to run it.",
                    "prefill": raw,
                }
            )
            self.ui_locked_this_turn.add("ask_input")
            directive = (
                f"COMPLETE CLAUSE, CONVENTION EDIT NEEDED: '{raw}' has a full who + action, only missing {need_str}. "
                "His exact sentence is pre-filled in his box so fixing it takes 2 seconds. "
                f"Credit that it's a complete thought, ask him to add {need_str} and hit Enter so the drawing/step fires."
            )
            return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": directive}

        # 7D. FULL, PUNCTUATED COMPLETE SENTENCE!
        self.last_kid_kind = "COMPLETE_SENTENCE"
        self.draw_unlocked = True
        if self.hint_step == 0:
            self.first_try_streak += 1
        self.hint_step = 0
        self.engaged_draft = ""
        self.active_story.append(raw)
        self.goal_done += 1

        # Step up Ontario B3.1 rung after success
        if self.goal_done == 1 and self.rung == "B3.1_simple":
            self.rung = "B3.1_compound"
        elif self.goal_done >= 2 and self.rung in ("B3.1_simple", "B3.1_compound"):
            self.rung = "B3.1_complex"

        # Should we trigger Beat 3 (90s Cover-Copy-Compare Word Forge)?
        # Trigger once goal_done >= goal_target (or goal_done >= 2 when a real misspelling is captured!)
        best_ms = self._pick_best_misspelling()
        trigger_word_study = (
            not self.word_study_done
            and best_ms is not None
            and (self.goal_done >= self.goal_target or self.goal_done >= 2)
        )

        if trigger_word_study and best_ms is not None:
            self.phase = "WORD_STUDY"
            ws = thinking.analyze_word_study(best_ms["wrote"], best_ms["meant"])
            self.word_target = ws
            self.word_study_tries = 0
            ui_actions.append({"type": "goal", "text": self.goal_badge()})
            ui_actions.append(
                {
                    "type": "item",
                    "item": {
                        "id": "word",
                        "kind": "word",
                        "word": ws["word"],
                        "parts": [p.strip() for p in ws["parts"].split("+")],
                        "note": ws["note"],
                    },
                }
            )
            ui_actions.append(
                {
                    "type": "input",
                    "mode": "type",
                    "prompt": f"Quick Word Forge: study '{ws['parts']}' above (it covers when you type), then spell '{ws['word']}' from memory (keyboard or pen).",
                    "prefill": "",
                }
            )
            self.ui_locked_this_turn.update({"show_word", "ask_input"})
            directive = (
                f"COMPLETE SENTENCE ({self.goal_done}/{self.goal_target}): '{raw}'! "
                "1) Call draw or comic_panel RIGHT NOW to render his exact sentence! "
                f"2) Transition into a quick 60-second Word Forge on '{ws['word']}' (he wrote '{ws['wrote']}' earlier). "
                f"The Cover-Copy-Compare card ('{ws['parts']}' — {ws['note']}) is ALREADY on screen and auto-covers when he starts typing/writing. "
                f"Give ONE plain sentence explaining why '{ws['word']}' is spelled '{ws['parts']}', and ask him to write '{ws['word']}' once from memory (pen or keyboard)."
            )
            return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": directive}

        if self.goal_done >= self.goal_target:
            self.phase = "WRAP"
            ui_actions.append({"type": "goal", "text": self.goal_badge()})
            ui_actions.append(
                {
                    "type": "item",
                    "item": {
                        "id": "done_choices",
                        "kind": "choices",
                        "prompt": "Goal complete! Want to:",
                        "options": ["Add a bonus complex sentence ('when' / 'because')", f"Save & print for {self.parent_title}"],
                    },
                }
            )
            self.ui_locked_this_turn.add("show_choices")
            directive = (
                f"COMPLETE SENTENCE ({self.goal_done}/{self.goal_target} — GOAL HIT!): '{raw}'! "
                "1) Call draw or comic_panel RIGHT NOW to render his exact sentence, AND call write_on_page / save_piece so his finished work is saved! "
                f"2) Give brief, specific process feedback (e.g. '{self.goal_done} complete sentences locked in')—never generic hype—and let him pick whether to add a bonus 'when/because' twist or wrap up."
            )
            return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": directive}

        # Advance to next sentence in the artifact, stretching syntax up to B3.1 compound/complex!
        scaf = generate_combine_scaffold(self.rec, self.active_story, "", self.rung)
        conn_label = "when, because, or if" if self.rung == "B3.1_complex" else "but, so, or when"
        card_txt = (
            f"Next beat — combine these two ideas with {conn_label}, OR write your own complete sentence for Step {self.goal_done + 1}:\n"
            f"  1. {scaf['kernel_1']}\n"
            f"  2. {scaf['kernel_2']}"
        )
        ui_actions.append({"type": "goal", "text": self.goal_badge()})
        ui_actions.append(
            {
                "type": "item",
                "item": {
                    "id": "forge",
                    "kind": "card",
                    "title": f"Step {self.goal_done + 1} of {self.goal_target} · Level Up with '{conn_label}'",
                    "text": card_txt,
                },
            }
        )
        ui_actions.append(
            {
                "type": "input",
                "mode": "type",
                "prompt": f"Type Sentence {self.goal_done + 1} using {conn_label} (combine the card lines, or write your own complete sentence).",
                "prefill": "",
            }
        )
        self.ui_locked_this_turn.update({"show_card", "ask_input"})
        directive = (
            f"COMPLETE SENTENCE ({self.goal_done}/{self.goal_target}): '{raw}'! "
            "1) Call draw or comic_panel IMMEDIATELY to render exactly what his sentence says (keep his spelling in any caption). "
            f"2) Step {self.goal_done + 1} card is ALREADY on screen stretching him to Ontario B3.1 ({self.rung}: '{conn_label}'). "
            f"In 1–2 plain sentences, react specifically to what happened in his scene and invite him to write Sentence {self.goal_done + 1} "
            f"using {conn_label} (combining the two lines on screen or writing his own complete sentence). NEVER ask a 1-word wh- question."
        )
        return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": directive}

    # ---------------- HARD PYTHON TOOL GATE ----------------

    def gate_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any] | None:
        """Returns None if tool is allowed (mutating args in place if needed), or a dict response blocking/redirecting it."""
        if name == "comic_new":
            try:
                n = max(2, min(6, int(str(args.get("panels", "3")).strip())))
            except ValueError:
                n = 3
            self.goal_label = "Panels"
            self.goal_target = n
            return None

        if name in ("draw", "comic_panel"):
            # Allow caption-only update only if complete sentence, and block ALL image generation unless draw_unlocked!
            if not self.draw_unlocked:
                return {
                    "blocked": True,
                    "reason": (
                        f"Drawing blocked by education gate: last student input class was {self.last_kid_kind!r}, not a complete punctuated sentence. "
                        "Never draw a 1-word answer, greeting, refusal, or incomplete fragment. Tell him plainly what his sentence needs so you can draw it."
                    ),
                }
            # Consume draw_unlocked after one draw/panel render so the model cannot draw twice without a new sentence
            self.draw_unlocked = False
            return None

        if name in ("write_on_page", "rewrite_page") and self.last_kid_kind != "COMPLETE_SENTENCE" and self.phase != "WRAP":
            return {
                "blocked": True,
                "reason": "Wait until he finishes and punctuates the complete sentence himself before adding it to the writing page.",
            }

        if name in ("show_card", "show_choices", "ask_input", "show_word") and name in self.ui_locked_this_turn:
            return {
                "ok": True,
                "note": f"{name} is already on screen. Do NOT repeat anything you already said aloud; finish silently if you already gave your prompt.",
            }

        if name == "show_choices":
            opts = [o.strip() for o in (args.get("options") or "").split("|") if o.strip()]
            allow_activity = self.last_kid_kind in ("NONE", "GREETING", "REFUSAL") or self.avoidance_streak >= 2 or self.phase == "WRAP"
            if not allow_activity:
                bad = [o for o in opts if len(_words(o)) > 3 or re.search(r"[.!?]$", o)]
                if bad:
                    return {
                        "blocked": True,
                        "reason": (
                            f"Blocked choices {bad}: never offer multi-word phrases or complete sentences as tappable options while he is constructing a sentence. "
                            "Offer at most 1-2 word verbs/connectors, or let him type the sentence himself."
                        ),
                    }
            else:
                # Even when offering activity choices, never offer narrative story sentences to copy/tap
                bad = [
                    o
                    for o in opts
                    if len(_words(o)) >= 6
                    and re.search(r"[.!?]$", o)
                    and not re.match(r"^(build|start|make|try|switch|add|save|pause|wrap)\b", o.lower())
                ]
                if bad:
                    return {
                        "blocked": True,
                        "reason": f"Blocked choices {bad}: choices must be activity formats or single words, never finished story sentences.",
                    }
            return None

        if name == "ask_input":
            p = (args.get("prompt") or "").strip()
            # Strip verbatim copy-dictation like: Type: "My base is inside a giant cow."
            if re.search(r'(type|write|copy)[^"]*["\'][A-Z][^"\']{12,}[.!?]["\']', p, re.I):
                args["prompt"] = "Write your own complete sentence (Who + Does What + Capital & .)."
            # Upgrade bare wh- questions that fail to ask for a full sentence
            if p.endswith("?") and "sentence" not in p.lower() and self.phase == "BUILDING":
                args["prompt"] = f"Write one complete sentence: {p}"
            return None

        return None
