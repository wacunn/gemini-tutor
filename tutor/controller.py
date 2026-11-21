"""Synchronous Pedagogical Controller, Multi-Genre SRSD Director, Spaced Word Forge & Hard Tool Gate.

Replacement-grade engine covering Ontario Grades 3–4 Language Strands B, C, and D:
  - Narrative Studio (`epic_graphic_novel`): Enforced causal Beginning -> Middle -> End Story Spine,
    chapter/panel zooming (up to 100+ panels), character dialogue bubbles, and enforced Mastery Tiers 1–5.
  - Reading-to-Write Research Codex (`epic_codex`): 3-Source Fact Packs (D1.3), Inference Check (C2.3/C3.2),
    and 3-sentence Informational Paragraph synthesis (Topic -> Causal Mechanism -> Contrast/Impact, D2.1).
  - Persuasive Studio (`medium_pitch`): SRSD POW+TREE 4-page illustrated case file (Claim -> Reason ->
    Counter-argument -> Ending, D1.1 + D2.1).
  - Voice-to-Draft Dictation-and-Edit (`ORAL_DRAFT`): MacArthur speech-to-text externalization paired with
    explicit syntactic & punctuation editing for low-energy ADHD days.
  - Guaranteed Spaced Orthography & Morphology (`spelling_srs.py`): Leitner spaced retrieval + 8-unit
    Ontario Continuum scope & sequence in every session.
"""

from __future__ import annotations

import difflib
import re
import threading
import time
from typing import Any

from google import genai
from google.genai import types

from . import curriculum_tracker as ct
from . import blackboard, coach, projects, research_packs, spelling_srs, thinking
from .config import FALLBACK_MODEL, FAST_MODEL, LITE_MODEL, genai_client
from .record import save_learner

PLANNER_MODEL = LITE_MODEL  # next story question + starters: small model is ~40% faster with equal quality

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
    "?",
    "...",
}
REFUSAL_PATTERNS = (
    r"^(no|nope|nah|pass|stop|quit|skip)\b",
    r"\b(this is boring|boring|i dont want|i don't want|hate this|dumb|stupid|something else|different game|switch)\b",
)
META_PATTERNS = (
    r"^(hello|hi|hey|yo|are you there|you there|is it working|did it freeze|it froze|testing|help|huh|what|wait)$",
    r"^(what do i do|what should i do|how does this work)$",
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


DIRECTOR_SYSTEM = """You are a calm, clear writing & story director working with a sharp, mature-curious 8-year-old child (Grade 3–4, ADHD) who listens to heavy metal, finds swearing funny, and is curious about death and grown-up topics.
CHILD AWARENESS WITHOUT BABYING OR "BLIPPI" CENSORSHIP:
- Keep genuine child-safety lines rock-solid (zero sexual/pornographic content, graphic gore, self-harm encouragement, real-world harm instructions, or secrecy from parents).
- NEVER baby him, NEVER scold/lecture swearing ("use nice words"), and NEVER sanitize dark/metal comic action, skeletons, graves, or character deaths into preschool fluff—treat his ideas completely matter-of-factly!
CRITICAL RULES:
1. ZERO PLOT SUGGESTING: NEVER invent story events, magic potions, rockets, monsters, or either/or plot choices ("Does he drink a potion or blast off?"). It is 100% THEIR story!
2. REMIND + ASK OPENLY: Briefly name what JUST happened in their own words so they know which panel/step they are on, then ask ONE short, open question ("What happens in Panel 2?", "What does Dylan do right after that?", "Why did that happen?").
3. TONE: Plain, normal, matter-of-fact adult voice. Zero hype ("Whoa!", "Super stinky!", "Comic gold!", "Epic!"), zero baby talk.
4. Leave `starters` as `[]`.
Return strict JSON:
{"spoken_prompt":"1-2 plain, open sentences referencing only what they already wrote + asking what happens in this panel/step.",
 "input_prompt":"Short 1-line open question for the input bar.",
 "starters":[],
 "kernel_1":"Short sentence 1 from their story.",
 "kernel_2":"Short sentence 2 from their story.",
 "connectors":"when | because | but"}"""


def ai_direct_next_beat(
    rec: dict[str, Any],
    step_goal: str,
    active_story: list[str],
    spine_context: str = "",
    connector_goal: str = "when | because | but",
) -> dict[str, str]:
    story_txt = "\n".join(f"- {s}" for s in active_story[-6:]) or "(none yet)"
    notes_txt = "; ".join(n.get("note", "") for n in (rec.get("parent_notes") or [])[:5])
    prompt = (
        f"LEARNER: Grade {rec.get('grade', 3)}. Notes: {notes_txt or '(none)'}.\n"
        f"STORY SPINE / BOOK CONTEXT SO FAR:\n{spine_context or '(starting now)'}\n"
        f"RECENT SENTENCES WRITTEN BY STUDENT:\n{story_txt}\n"
        f"CURRENT BEAT & SKILL GOAL:\n{step_goal}\n"
        f"TARGET CONNECTORS: {connector_goal}"
    )
    if blackboard.QUOTA.allow_background():
        try:
            client = genai_client(timeout_ms=3200)
            for model in (PLANNER_MODEL, FAST_MODEL):
                try:
                    resp = client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=DIRECTOR_SYSTEM,
                            temperature=0.4,
                            response_mime_type="application/json",
                            thinking_config=types.ThinkingConfig(thinking_budget=0),
                        ),
                    )
                    out = thinking._json(resp.text)
                    if isinstance(out, dict) and out.get("spoken_prompt") and out.get("input_prompt"):
                        return {
                            "spoken_prompt": str(out["spoken_prompt"]).strip(),
                            "input_prompt": str(out["input_prompt"]).strip(),
                            "starters": [coach.as_starter(s) for s in (out.get("starters") or []) if coach.as_starter(s)][:3],
                            "kernel_1": str(out.get("kernel_1") or "The door creaks open.").strip(),
                            "kernel_2": str(out.get("kernel_2") or "Something unexpected jumps out.").strip(),
                            "connectors": str(out.get("connectors") or connector_goal).strip(),
                        }
                except Exception as e:
                    blackboard.QUOTA.note_error("director", e)
                    if not blackboard.QUOTA.allow_background():
                        break
        except Exception:
            pass
    return {
        "spoken_prompt": step_goal,
        "input_prompt": step_goal,
        "starters": [],
        "kernel_1": "The iron pressure plate clicks.",
        "kernel_2": "A hidden piston drops the floor over lava.",
        "connectors": connector_goal,
    }


def generate_combine_scaffold(
    rec: dict[str, Any],
    active_story: list[str],
    engaged_draft: str,
    rung: str,
    spine_context: str = "",
) -> dict[str, str]:
    connector_goal = "when | because | if" if rung in ("B3.1_complex",) else "but | so | when"
    d = ai_direct_next_beat(
        rec,
        f"Help the student write the next complete sentence (latest fragment if any: {engaged_draft or 'none'}).",
        active_story,
        spine_context=spine_context,
        connector_goal=connector_goal,
    )
    return {
        "kernel_1": d["kernel_1"],
        "kernel_2": d["kernel_2"],
        "connectors": d["connectors"],
        "ask_prompt": d["input_prompt"],
    }


def _infer_book_title(beginning_sentence: str, suggested: str = "") -> str:
    src_words = {
        blackboard.COMMON_TYPOS.get(w.lower(), w.lower()).rstrip("s")
        for w in re.findall(r"[A-Za-z0-9']+", beginning_sentence or "")
    }
    sug = (suggested or "").strip().strip('"\'.!?')
    if sug and sug.lower() not in {"punchy comic title", "untitled", "untitled graphic novel"} and 2 <= len(sug.split()) <= 6:
        sug_content = [
            w.lower().rstrip("s")
            for w in re.findall(r"[A-Za-z0-9']+", sug)
            if w.lower() not in {"the", "a", "an", "and", "of", "in", "on", "to", "his", "her", "story", "adventure", "trouble"}
        ]
        # Only accept `suggested` if EVERY content word actually came from the child's sentence!
        if sug_content and all(any(sw.startswith(sc[:4]) or sc.startswith(sw[:4]) for sw in src_words if len(sw) >= 3) for sc in sug_content if len(sc) >= 4):
            return sug
    words = re.findall(r"[A-Za-z0-9']+", beginning_sentence or "")
    stop = {
        "the", "a", "an", "in", "on", "at", "when", "once", "there", "was", "is", "are", "were",
        "he", "she", "they", "his", "her", "my", "our", "main", "character", "hero", "story",
        "about", "named", "called", "whose", "who", "that", "with", "gets", "got", "has", "have",
        "then", "but", "and", "because", "uoos", "hoos",
    }
    cleaned = []
    for w in words:
        wl = w.lower()
        fixed = blackboard.COMMON_TYPOS.get(wl, w)
        if fixed.lower() in stop or wl in stop:
            continue
        cleaned.append(fixed.capitalize())
    picked = cleaned[:4]
    return " ".join(picked) if len(picked) >= 2 else (picked[0] + "'s Adventure" if picked else "Original Graphic Novel")


def _phrase_around_word(sentence: str, word: str) -> str:
    tokens = sentence.split()
    wlow = word.lower().strip(".,!?;:\"'()[]")
    for i, tok in enumerate(tokens):
        if tok.lower().strip(".,!?;:\"'()[]") == wlow:
            lo = max(0, i - 1)
            hi = min(len(tokens), i + 2)
            return " ".join(tokens[lo:hi])
    return word


def _specific_spelling_pointer(sentence: str, wrote: str, meant: str, tier: int) -> str:
    """Names the exact misspelled word (never vague 'fix spelling') and gives an age-appropriate clue at early tiers."""
    w_low, m_low = wrote.lower(), meant.lower()
    if " " in meant.strip():
        n_words = len(meant.strip().split())
        snip = _phrase_around_word(sentence, wrote)
        return f'"{wrote}" in "{snip}" (hint: split into {n_words} separate words)'
    if len(wrote) <= 3 and len(meant) <= 4:
        snip = _phrase_around_word(sentence, wrote)
        if m_low.endswith("th") and not w_low.endswith("th"):
            return f'"{wrote}" in "{snip}" (hint: ends with "-th")'
        return f'"{wrote}" in "{snip}" (check the exact spelling of this short word)' if tier <= 3 else f'"{wrote}" in "{snip}"'
    if tier > 3:
        return f'the spelling of "{wrote}"'
    if m_low.endswith("ed") and not w_low.endswith("ed"):
        return f'"{wrote}" (hint: base word + "-ed" past-tense ending)'
    if m_low.endswith(("ed", "ing", "er", "est", "able")) and abs(len(meant) - len(wrote)) == 1:
        return f'"{wrote}" (hint: check whether a letter doubles or silent-e drops before the ending)'
    return f'"{wrote}" (hint: {len(meant)} letters, starts "{meant[:2]}…")'


def _splice_word_into_sentence(sentence: str, wrote: str, replacement: str) -> str:
    if not sentence:
        return replacement
    pat = re.compile(rf"\b{re.escape(wrote)}\b", re.IGNORECASE)

    def _repl(m: re.Match[str]) -> str:
        orig = m.group(0)
        if orig[:1].isupper() and replacement[:1].isalpha():
            return replacement[:1].upper() + replacement[1:]
        return replacement

    out, count = pat.subn(_repl, sentence, count=1)
    if count == 0:
        out = sentence.replace(wrote, replacement, 1)
    return out.strip()


class SessionController:
    """Deterministic pedagogical state machine + multi-genre SRSD director + Leitner spelling + hard tool gate."""

    def __init__(self, rec: dict[str, Any], test_mode: bool = False):
        self.rec = rec
        self.test_mode = test_mode
        self.name = rec.get("name") or "the student"
        self.parent_title = rec.get("parent_title") or "your parent"
        self.rc = ct.ensure_report_card(rec)
        spelling_srs.ensure_deck(rec)

        self.phase: str = "OPENING"  # OPENING -> STORY_SPINE -> BUILDING -> WORD_STUDY -> WRAP
        self.rung: str = "B3.1_simple"
        self.mastery_tier: int = ct.compute_mastery_tier(self.rc, 0)

        self.project: dict[str, Any] | None = None
        self.research_pack: dict[str, Any] | None = None
        self.awaiting_codex_topic: bool = False
        self.codex_step: int = 0  # 0=inference, 1=topic_s1, 2=mech_s2, 3=impact_s3
        self.codex_buf: list[str] = []
        self.tree_step: int = 0  # 0=Claim, 1=Reason(because), 2=Counter(although), 3=Ending

        self.goal_label: str = "Sentences"
        self.goal_done: int = 0
        self.goal_target: int = 3
        self.session_panels_target: int = 4
        self.first_try_streak: int = 0

        self.turn_index: int = 0
        self.hint_step: int = 0
        self.tier_nudged_this_item: bool = False
        self.avoidance_streak: int = 0
        self.refusal_streak: int = 0
        self.had_revision: bool = False
        self.had_inference: bool = False
        self.had_synthesis: bool = False

        self.last_kid_kind: str = "NONE"
        self.last_kid_text: str = ""
        self.prev_norm_text: str = ""

        self.engaged_draft: str = ""
        self.active_story: list[str] = []
        self.active_mechanic: str = ""

        self.misspellings: list[dict[str, str]] = []
        self.pending_spell_sentence: str = ""
        self.pending_spell_targets: list[dict[str, str]] = []
        self.phase_before_inline_help: str = "BUILDING"
        self.inline_word_help_tries: int = 0
        self.word_target: dict[str, Any] | None = None
        self.word_study_done: bool = False
        self.word_study_tries: int = 0
        self.studied_words_today: set[str] = set()
        self.handwriting_fix_tries: int = 0

        self.draw_unlocked: bool = False
        self.ui_locked_this_turn: set[str] = set()

        # Shared Working-Memory Blackboard + Fast Front-Line Talker + Art Approval Gate
        coach.ensure_model(rec)
        self.blackboard = blackboard.WorkingMemoryBlackboard(rec)
        self.coach_enabled: bool = True
        self._coach_lock = threading.RLock()
        self.coach_session: dict[str, Any] = coach.new_session_state()
        self.turn_signals: dict[str, Any] = {}
        self.spell_pick: dict[str, Any] | None = None
        self.last_coach: dict[str, Any] | None = None
        self._cached_beat: dict[str, Any] | None = None
        self._suggested_title: str = ""
        self.pending_art_target: str = ""
        self.phase_after_art_check: str = "BUILDING"
        self.pause_for_art_check: bool = not test_mode
        self.active_mic_request: dict[str, Any] | None = None
        self.asked_aloud_words: set[str] = set()

    def spine_summary(self) -> str:
        if not self.project:
            return ""
        sp = self.project.get("spine") or {}
        bits = []
        if sp.get("beginning"):
            bits.append(f"1. Beginning (START): {sp['beginning']}")
        mbeats = projects.middle_beats_list(sp)
        for i, mb in enumerate(mbeats, 1):
            if mb.get("text"):
                bits.append(f"2.{i} Middle Twist #{i} (CURRENT SCENE / LOCATION RIGHT NOW): {mb['text']}")
        if sp.get("end"):
            bits.append(
                f"3. FUTURE Big Finale Goal at VERY END of Book (NOT HAPPENED YET — characters are still in the current scene above working toward this!): {sp['end']}"
            )
        return "\n".join(bits)

    def current_tier(self) -> int:
        pcount = projects.total_panels(self.project) if self.project else self.goal_done
        self.mastery_tier = ct.compute_mastery_tier(self.rc, pcount)
        return self.mastery_tier

    def goal_badge(self) -> str:
        tier = self.current_tier()
        if self.project:
            kind = self.project.get("kind", "")
            stage = self.project.get("stage", "")
            pcount = projects.total_panels(self.project)
            if stage.startswith("spine_"):
                sp = self.project.get("spine") or {}
                n_mid = len(projects.middle_beats_list(sp))
                step = {
                    "spine_beginning": "Kickoff",
                    "spine_end": "Big Finale",
                    "spine_middle": f"Middle Twist #{n_mid + 1}",
                }.get(stage, "Plotting")
                return f"Plot Board: {step}"
            if kind == "epic_codex":
                labels = {0: "Reading Inference", 1: "Paragraph 1/3", 2: "Paragraph 2/3", 3: "Paragraph 3/3"}
                return f"Codex Entries: {pcount} · {labels.get(self.codex_step, 'Drafting')}"
            if kind == "medium_pitch":
                return f"Pitch Book (TREE): Page {min(4, self.tree_step + 1)}/4"
            ch_num = len(self.project.get("chapters") or [1])
            return f"Ch.{ch_num} · {pcount} panel{'s' if pcount != 1 else ''} · today {self.goal_done}/{self.session_panels_target}"
        if self.phase == "WORD_STUDY" and self.word_target:
            return f"{self.goal_label}: {self.goal_done}/{self.goal_target} · Word Forge"
        streak = f" · Streak {self.first_try_streak}" if self.first_try_streak >= 2 else ""
        return f"{self.goal_label}: {self.goal_done}/{self.goal_target}{streak}"

    def _opening_options(self, opening_ideas: list[dict[str, Any]] | None) -> list[str]:
        opts: list[str] = []
        if not self.test_mode:
            saved = projects.list_projects()
            if saved:
                top = saved[0]
                opts.append(f"Continue '{top.get('title','Book')}' ({top.get('panel_count',0)} panels)")
        opts.append("Start a Full Comic Book (Save & PDF)")
        opts.append("3-Source Fact & Invention Codex (PDF)")
        opts.append("4-Page Persuasive Pitch ('Why We Should…')")
        opts.append("Build a Live Mini-Game (10 min)")
        return opts[:4]

    # ---------------- GENRE STUDIO LAUNCHERS & PROMPTS ----------------

    def _save_current_if_needed(self) -> None:
        if self.project and projects.is_project_nonempty(self.project):
            projects.save_project(self.project, sandbox=self.test_mode)

    def _reset_item_buffers(self) -> None:
        self.engaged_draft = ""
        self.hint_step = 0
        self.tier_nudged_this_item = False
        self.pending_spell_sentence = ""
        self.pending_spell_targets = []
        self.inline_word_help_tries = 0
        self.awaiting_codex_topic = False
        self.pending_art_target = ""
        self._cached_beat = None
        self._suggested_title = ""
        self.active_mic_request = None
        self.asked_aloud_words.clear()

    def resume_loaded_project(self, proj: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
        """Saves any active project first, then resumes the selected saved project."""
        if self.project and self.project.get("id") != proj.get("id"):
            self._save_current_if_needed()
        self._reset_item_buffers()
        self.project = proj
        self.goal_done = 0
        self.active_story = [p["caption"] for p in projects.all_panels(proj)[-6:] if p.get("caption")]
        ui: list[dict[str, Any]] = [
            {"type": "item", "item": projects.project_ui_payload(proj)},
            {"type": "goal", "text": self.goal_badge()},
        ]
        pkind = proj.get("kind", "epic_graphic_novel")
        if pkind == "epic_codex":
            self.phase = "BUILDING"
            return self._prompt_codex_step(ui, new_entry=True)
        if pkind == "medium_pitch":
            self.phase = "BUILDING"
            self.session_panels_target = 4
            self.tree_step = min(3, projects.total_panels(proj))
            return self._prompt_pitch_step(ui)
        if proj.get("stage", "").startswith("spine_"):
            return self._prompt_spine_step(ui, resumed=True)
        self.session_panels_target = 3 if pkind == "quick_strip" else 4
        return self._prompt_next_book_panel(ui, resumed=True)

    def create_or_switch_project(self, kind: str, title: str = "") -> tuple[list[dict[str, Any]], str]:
        """Saves any active book cleanly and starts a brand-new book/strip/game without overwriting previous ones."""
        self._save_current_if_needed()
        self._reset_item_buffers()
        self.goal_done = 0
        self.codex_step = 0
        self.codex_buf = []
        self.tree_step = 0
        self.research_pack = None
        ui: list[dict[str, Any]] = []
        clean_t = (title or "").strip()

        if kind == "quick_game":
            self.project = None
            self.phase = "BUILDING"
            self.active_mechanic = clean_t or "Live Mini-Game"
            ui.append({"type": "goal", "text": self.goal_badge()})
            return ui, (
                f"Start a brand-new live HTML5 mini-game{f' titled {clean_t!r}' if clean_t else ''}. "
                "Call build_activity NOW with a concrete spec where EVERY round requires typing or repairing a complete sentence, "
                "and put a 2-kernel Sentence Combining warm-up card on screen while it builds."
            )

        self.project = projects.create_project(
            kind,
            self.name,
            self.parent_title,
            title=clean_t,
            persist=bool(clean_t),
            sandbox=self.test_mode,
        )
        ui.append({"type": "item", "item": projects.project_ui_payload(self.project)})
        ui.append({"type": "goal", "text": self.goal_badge()})

        if kind == "epic_graphic_novel":
            self.phase = "STORY_SPINE"
            self.session_panels_target = 2
            return self._prompt_spine_step(ui, resumed=False)
        if kind == "epic_codex":
            self.phase = "BUILDING"
            return self._prompt_codex_step(ui, new_entry=True)
        if kind == "medium_pitch":
            self.phase = "BUILDING"
            self.session_panels_target = 4
            return self._prompt_pitch_step(ui)
        # quick_strip (3-panel saved comic strip -> PDF!)
        self.phase = "BUILDING"
        self.session_panels_target = 3
        return self._prompt_next_book_panel(ui, resumed=False)

    def start_or_resume_project(self, choice_label: str) -> tuple[list[dict[str, Any]], str]:
        low = choice_label.lower()

        if low.startswith("continue "):
            saved = projects.list_projects(sandbox=self.test_mode)
            if saved:
                return self.resume_loaded_project(saved[0])

        if "full comic book" in low or "graphic novel" in low or "another comic" in low or "new comic" in low:
            return self.create_or_switch_project("epic_graphic_novel")

        if "codex" in low or "field guide" in low or "fact" in low:
            return self.create_or_switch_project("epic_codex")

        if "pitch" in low or "why we should" in low or "persuasive" in low:
            return self.create_or_switch_project("medium_pitch")

        if "3-panel" in low or "quick strip" in low:
            return self.create_or_switch_project("quick_strip")

        if "mini-game" in low or "live game" in low:
            return self.create_or_switch_project("quick_game")

        return [], ""

    def _prompt_codex_step(self, ui: list[dict[str, Any]], new_entry: bool = False, custom_topic: str = "") -> tuple[list[dict[str, Any]], str]:
        """Drives Strand C Reading Comprehension + D1.3 3-Source Synthesis + D2.1 Informational Paragraph Building."""
        assert self.project is not None
        if new_entry or not self.research_pack or custom_topic.strip():
            used_ids = self.project.setdefault("used_packs", [])
            self.research_pack = research_packs.pick_pack(used_ids, custom_topic=custom_topic)
            if self.research_pack.get("id") and self.research_pack["id"] != "custom" and self.research_pack["id"] not in used_ids:
                used_ids.append(self.research_pack["id"])
            self.codex_step = 0
            self.codex_buf = []

        pack = self.research_pack
        sources_txt = "\n".join(f"  • {s}" for s in pack.get("sources", []))
        ui.append({"type": "goal", "text": self.goal_badge()})

        if self.codex_step == 0:
            card_txt = f"Read these 3 real sources:\n{sources_txt}\n\n{pack['inference_prompt']}"
            ui.append({"type": "item", "item": {"id": "forge", "kind": "card", "title": f"Codex Dossier · {pack['title']} (Reading + Inference)", "text": card_txt}})
            ui.append({"type": "item", "item": {"id": "codex_topic_opt", "kind": "choices", "prompt": "Or pick any real-world science/engineering/music topic:", "options": ["Research my own Codex topic"]}})
            ui.append({"type": "input", "mode": "type", "prompt": pack["inference_prompt"], "prefill": ""})
            self.ui_locked_this_turn.update({"show_card", "show_choices", "ask_input"})
            return ui, (
                f"Started 3-Source Codex Dossier '{pack['title']}' (Ontario Strand C Comprehension + D1.3 Research). "
                "The 3 mini-sources are on screen. Give him a moment to read them and ask the 1-sentence Inference Check on the card."
            )

        psteps = pack.get("paragraph_steps") or [
            "Sentence 1 (Topic): Introduce the topic and main idea.",
            "Sentence 2 (Mechanism): Explain how or why it works using 'when' or 'because'.",
            "Sentence 3 (Contrast/Impact): Explain the result or contrast using 'although', 'unlike', or 'so'.",
        ]
        step_instr = psteps[min(self.codex_step - 1, len(psteps) - 1)]
        so_far = " ".join(self.codex_buf)
        card_txt = (
            f"Sources ({pack['title']}):\n{sources_txt}\n\n"
            + (f"Paragraph Draft So Far:\n  \"{so_far}\"\n\n" if so_far else "")
            + f"Now Build Paragraph Part {self.codex_step} of 3:\n  → {step_instr}"
        )
        ui.append({"type": "item", "item": {"id": "forge", "kind": "card", "title": f"Codex Entry Paragraph · Sentence {self.codex_step} of 3", "text": card_txt}})
        ui.append({"type": "input", "mode": "type", "prompt": step_instr, "prefill": ""})
        self.ui_locked_this_turn.update({"show_card", "ask_input"})
        return ui, (
            f"Building cohesive 3-sentence informational paragraph for '{pack['title']}' (Part {self.codex_step}/3). "
            f"Ask concisely for {step_instr}"
        )

    def _prompt_pitch_step(self, ui: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
        """Drives SRSD POW+TREE 4-Page Persuasive Book using live AI follow-up questions—zero clutter boxes."""
        assert self.project is not None
        ui.append({"type": "goal", "text": self.goal_badge()})
        if self.tree_step == 0:
            ask = f"Page 1: What bold idea or rule are you pitching to {self.parent_title}?"
            ui.append({"type": "input", "mode": "type", "prompt": ask, "prefill": ""})
            self.ui_locked_this_turn.update({"show_card", "ask_input"})
            return ui, f"Starting a 4-Page Illustrated Pitch Book for {self.parent_title}. Ask in 1–2 natural sentences what bold idea they want to pitch on Page 1."

        step_specs = {
            1: (
                f"Remind them of their Page 1 pitch, ask a specific WHY/HOW question proving why it will work, and require 1–2 complete sentences using 'because' or 'since'.",
                "because | since",
            ),
            2: (
                f"Remind them of their pitch, guess the exact practical thing {self.parent_title} will worry about, and ask how they solve it starting with 'Although' or 'Even though'.",
                "although | even though",
            ),
            3: (
                f"Remind them of their pitch and solution, and ask what concrete first test or deal they propose to {self.parent_title} using 'if' or 'so' to finish the Pitch PDF.",
                "if | so",
            ),
        }
        goal_desc, conns = step_specs[min(self.tree_step, 3)]
        beat = self._pop_or_direct_beat(goal_desc, conns)
        self._beat_input(ui, beat)
        self.ui_locked_this_turn.update({"show_card", "ask_input"})
        return ui, f"Say this story-specific prompt naturally in 1–2 sentences: {beat['spoken_prompt']}"

    def _pop_or_direct_beat(self, goal_desc: str, conns: str = "when | because | but") -> dict[str, Any]:
        if self._cached_beat and self._cached_beat.get("spoken_prompt"):
            b = self._cached_beat
            self._cached_beat = None
            return b
        return ai_direct_next_beat(self.rec, goal_desc, self.active_story, spine_context=self.spine_summary(), connector_goal=conns)

    def _next_goal_preview(self) -> str:
        if not self.project:
            return "Ask what happens next in the story."
        kind = self.project.get("kind")
        st = self.project.get("stage", "")
        if kind == "epic_graphic_novel":
            if st == "spine_beginning":
                return "Jump to the Big Finale: how does this whole crazy story finally end up?"
            if st == "spine_end":
                return "Start the middle twists right after the Kickoff (NOT at the finale yet!): what is the FIRST big disaster or twist in the middle?"
            if st == "spine_middle":
                return "Stay in the CURRENT middle scene/location (do NOT jump to the finale setting yet!) and ask what happens or escalates next right where they are."
            pnum = projects.total_panels(self.project) + 2
            speech_cue = ' (Invite adding what a character yells in "quote marks" for a speech bubble!)' if pnum >= 2 else ""
            return f"Zoom into Panel {pnum}: ask a specific where/why/what-happens-right-after question.{speech_cue}"
        if kind == "medium_pitch":
            return f"Ask for Page {min(4, self.tree_step + 2)} of the persuasive pitch."
        return "Ask a specific question for the next panel."

    def _enter_art_check_gate(self, ui_actions: list[dict[str, Any]], target: str, after_phase: str, label: str) -> dict[str, Any]:
        """Holds off asking the next story beat until the picture renders and the child confirms it matches their story!"""
        self.pending_art_target = target
        self.phase_after_art_check = after_phase
        self.phase = "AWAITING_ART_CHECK"
        ui_actions.append({"type": "remove", "id": "starters"})
        ui_actions.append(
            {
                "type": "input",
                "mode": "type",
                "prompt": "Drawing your picture right now—check it on the right in a moment to make sure I got your scene right!",
            }
        )
        self.ui_locked_this_turn.update({"show_choices", "ask_input"})
        rx = ((self.last_coach or {}).get("story_reaction") or (self.last_coach or {}).get("kid_words") or "").strip()
        lead = f"{rx} " if rx else ""
        spoken = f"{lead}Drawing {label} now—check the picture on the right when it appears to make sure it matches your story."
        return {
            "kind": self.last_kid_kind,
            "art_check_target": target,
            "spoken_fallback": spoken,
            "ui": ui_actions,
            "directive": f'React briefly to their story idea and tell them you are drawing {label} now so they can check if the picture matches their story before moving on: "{spoken}"',
        }

    def prompt_after_art_rendered(self, target: str) -> tuple[list[dict[str, Any]], str, str]:
        """Called as soon as a Spine or Panel image finishes drawing so the child checks the picture BEFORE moving on!"""
        self.pending_art_target = target
        self.phase = "AWAITING_ART_CHECK"
        ui: list[dict[str, Any]] = [
            {
                "type": "item",
                "item": {
                    "id": "art_check_choices",
                    "kind": "choices",
                    "prompt": "Does this picture & step match your story?",
                    "options": [
                        "✓ Looks right — next part!",
                        "↻ Not quite — fix picture",
                        "↶ Undo / change this sentence",
                    ],
                },
            },
            {
                "type": "input",
                "mode": "type",
                "prompt": "Tap 'Looks right', 'Fix picture', or 'Undo / change this sentence':",
            },
        ]
        spoken = "Check your picture—does it match your story, or should we fix or undo it?"
        return ui, f'Say plainly in 1 short sentence: "{spoken}"', spoken

    def start_fix_art_prompt(self, target: str) -> dict[str, Any]:
        """Enters friendly-blame clarification mode and turns ON the Center Green Mic so he can just say what the picture should show!"""
        self.pending_art_target = target
        if self.phase not in ("AWAITING_ART_CHECK", "REDRAW_CLARIFY"):
            self.phase_after_art_check = self.phase
        self.phase = "REDRAW_CLARIFY"
        self.last_kid_kind = "REDRAW_PROMPT"
        orig_scene = projects.get_art_text(self.project, target) if self.project else ""
        self.active_mic_request = {"purpose": "picture", "target": target, "sentence": orig_scene}
        spoken = (
            "My bad—sometimes it takes an extra detail for me to picture what's in your head! "
            "Tell me into the green mic what this picture should show, and I'll redraw it right now."
        )
        return {
            "epoch": self.blackboard.bump_epoch(),
            "kind": self.last_kid_kind,
            "spoken_fallback": spoken,
            "ui": [
                {"type": "remove", "id": "art_check_choices"},
                {"type": "remove", "id": "starters"},
                {
                    "type": "tutor_mic",
                    "action": "on",
                    "purpose": "picture",
                    "target_word": "",
                    "sentence": orig_scene,
                    "prompt": "Tell me out loud what this picture should show",
                },
                {"type": "input", "mode": "type", "prompt": "Say what the picture should show into the green mic (or type it here):"},
            ],
            "directive": f'Take friendly blame in 1-2 short sentences and invite speaking into the green mic: "{spoken}"',
        }

    def _continue_after_art_approved(self, ui_actions: list[dict[str, Any]]) -> dict[str, Any]:
        if self.project and self.pending_art_target:
            projects.mark_art_verified(self.project, self.pending_art_target, sandbox=self.test_mode)
            ui_actions.append({"type": "item", "item": projects.project_ui_payload(self.project)})
        self.pending_art_target = ""
        ui_actions.append({"type": "remove", "id": "art_check_choices"})
        self.phase = self.phase_after_art_check or "BUILDING"
        if self.project:
            pkind = self.project.get("kind", "")
            if self.project.get("stage", "").startswith("spine_"):
                ui_actions, directive = self._prompt_spine_step(ui_actions, resumed=False)
                return {"kind": "ART_APPROVED", "ui": ui_actions, "directive": directive}
            if pkind == "epic_codex":
                ui_actions, directive = self._prompt_codex_step(ui_actions, new_entry=False)
                return {"kind": "ART_APPROVED", "ui": ui_actions, "directive": directive}
            if pkind == "medium_pitch":
                if self.tree_step >= 4:
                    self.phase = "WRAP"
                    ui_actions.append({"type": "item", "item": {"id": "done_choices", "kind": "choices", "prompt": "All 4 Pitch Pages Complete!", "options": [f"Download Pitch PDF for {self.parent_title}"]}})
                    return {"kind": "ART_APPROVED", "ui": ui_actions, "directive": "All 4 pages are drawn and approved—invite downloading the PDF!"}
                ui_actions, directive = self._prompt_pitch_step(ui_actions)
                return {"kind": "ART_APPROVED", "ui": ui_actions, "directive": directive}
            ui_actions, directive = self._prompt_next_book_panel(ui_actions, resumed=False)
            return {"kind": "ART_APPROVED", "ui": ui_actions, "directive": directive}
        return {"kind": "ART_APPROVED", "ui": ui_actions, "directive": "Great—ask what happens next in their story!"}

    @staticmethod
    def _is_director_correction(raw: str) -> bool:
        """Detects when the child/parent is correcting the AI about a wrong picture or misunderstood setting ('why are you having the spaceship stuck on the moon and not earth>') so we NEVER append their complaint as a story beat!"""
        t = (raw or "").strip()
        if not t or '"' in t or "“" in t:
            return False
        low = t.lower()
        if re.search(
            r"\b(why are you|why did you|why do you|why is (?:it|the|he|she|there|dylan)|you (?:put|made|drew|got|have|had|said)|"
            r"not on the|instead of|supposed to be|they(?:'re| are) on .+ not|it(?:'s| is) on .+ not|should be (?:on|in|at)|"
            r"wrong picture|bad picture|fix the picture|fix that picture|redraw|change the picture|that'?s wrong|you messed up|you misunderstood)\b",
            low,
        ):
            return True
        if re.match(r"^(?:no[,\s]+|wait[,\s]+|hey[,\s]+)(?:they|it|he|she|dylan|the\s+)", low) and any(
            k in low for k in ("not ", "still ", "earth", "picture", "wrong", "supposed")
        ):
            return True
        return False

    @staticmethod
    def _is_wrong_slot_or_undo(raw: str) -> tuple[bool, bool]:
        """Returns (matched, move_end_to_middle). Catches 'that wasn't the end, you asked what happened next' or 'undo / change this sentence'!"""
        t = (raw or "").strip()
        if not t or '"' in t or "“" in t:
            return False, False
        low = t.lower()
        if re.search(
            r"\b(wasn'?t the end|not the end|not the ending|not the finale|wasn'?t the finale|asked what happened next|"
            r"that'?s what happens next|that was the middle|meant the middle|not how it ends)\b",
            low,
        ):
            return True, True
        if re.search(
            r"\b(undo / change this sentence|undo this|take that back|go back a step|wrong step|delete that sentence|change this sentence)\b",
            low,
        ) or low in {"undo", "go back"}:
            return True, False
        return False, False

    def _handle_wrong_slot_or_undo(self, epoch: int, move_end_to_middle: bool) -> dict[str, Any]:
        assert self.project is not None
        target = self.pending_art_target or projects.latest_art_target(self.project)
        self.pending_art_target = ""
        sp = self.project.get("spine") or {}
        do_move = bool(move_end_to_middle and sp.get("end"))
        old_txt, action = projects.undo_or_move_beat(self.project, target, move_end_to_middle=do_move, sandbox=self.test_mode)
        ui_u: list[dict[str, Any]] = [
            {"type": "remove", "id": "art_check_choices"},
            {"type": "remove", "id": "starters"},
            {"type": "item", "item": projects.project_ui_payload(self.project)},
            {"type": "goal", "text": self.goal_badge()},
        ]
        if action == "moved_to_middle":
            self.phase = "STORY_SPINE"
            self.last_kid_kind = "STEP_MOVED"
            ui_u.append(
                {
                    "type": "input",
                    "mode": "type",
                    "prompt": "Plot Board Step 2 — The Ending (very end of the whole book): How does the story finally end?",
                    "prefill": "",
                }
            )
            self.ui_locked_this_turn.update({"ask_input", "show_choices"})
            spoken = (
                f'My bad—I moved "{old_txt}" to Middle Event #1 right after the beginning, and cleared The Ending. '
                "Now jump all the way to the very end of the whole book: how does the story finally end?"
            )
            return {
                "epoch": epoch,
                "kind": self.last_kid_kind,
                "spoken_fallback": spoken,
                "ui": ui_u,
                "directive": f'Say ONLY this exact clarification calmly: "{spoken}"',
            }

        self.phase = "STORY_SPINE" if self.project.get("stage", "").startswith("spine_") else "BUILDING"
        self.last_kid_kind = "STEP_UNDONE"
        ui_u.append(
            {
                "type": "input",
                "mode": "type",
                "prompt": "Edit or replace your sentence below and hit Enter:",
                "prefill": old_txt,
            }
        )
        self.ui_locked_this_turn.update({"ask_input", "show_choices"})
        spoken = "Undid that step and put your sentence back in the box so you can change or replace it."
        return {
            "epoch": epoch,
            "kind": self.last_kid_kind,
            "spoken_fallback": spoken,
            "ui": ui_u,
            "directive": f'Say ONLY this exact sentence calmly: "{spoken}"',
        }

    def _beat_input(self, ui: list[dict[str, Any]], beat: dict[str, Any]) -> None:
        """Next story question — never dumps unsolicited plot-suggesting starter chips onto open story beats."""
        ui.append({"type": "input", "mode": "type", "prompt": beat["input_prompt"], "prefill": "", "hint_pen": bool(self.coach_session.get("suggest_pen"))})
        if beat.get("force_starters") and beat.get("starters"):
            self.coach_session["offered_chips"] = beat["starters"]
            ui.append({"type": "item", "item": {"id": "starters", "kind": "starters", "options": beat["starters"]}})
        else:
            self.coach_session["offered_chips"] = []
            ui.append({"type": "remove", "id": "starters"})

    def _prompt_spine_step(self, ui: list[dict[str, Any]], resumed: bool = False) -> tuple[list[dict[str, Any]], str]:
        """Deterministic, crystal-clear Plot Board prompts—NEVER drops which structural step we are on and NEVER suggests plot ideas!"""
        assert self.project is not None
        stage = self.project.get("stage", "spine_beginning")
        sp = self.project.get("spine") or {}
        mbeats = projects.middle_beats_list(sp)
        self.phase = "STORY_SPINE"
        self._cached_beat = None  # Never let an LLM paraphrase drop the structural Plot Board step!
        ui.append({"type": "remove", "id": "starters"})

        if stage == "spine_beginning":
            spoken = (
                f"{'Welcome back to' if resumed else 'Starting'} your Graphic Novel. "
                "Step 1 on the Plot Board is the Beginning: who is the main character, and what problem starts the story?"
            )
            ui.append(
                {
                    "type": "input",
                    "mode": "type",
                    "prompt": "Plot Board Step 1 — The Beginning: Who is the main character, and what starts the story?",
                    "prefill": "",
                }
            )
            self.ui_locked_this_turn.update({"show_card", "ask_input"})
            return ui, f'Say ONLY this exact prompt calmly and plainly: "{spoken}"'

        if stage == "spine_end":
            # Note: if `middle_beats` already has a moved beat (e.g. from "that wasn't the end"), acknowledge it cleanly!
            spoken = (
                "Step 2 on your Plot Board is the Ending. Before we fill in the middle, jump all the way to the very end of the whole book: "
                "how does this story finally end?"
            )
            ui.append(
                {
                    "type": "input",
                    "mode": "type",
                    "prompt": "Plot Board Step 2 — The Ending (very end of the whole book): How does the story finally end?",
                    "prefill": "",
                }
            )
            self.ui_locked_this_turn.update({"show_card", "ask_input"})
            return ui, f'Say ONLY this exact prompt calmly and plainly (do NOT add any plot suggestions!): "{spoken}"'

        # stage == "spine_middle": iterative middle events bridging Beginning -> Ending!
        n_mid = len(mbeats)
        beg_short = (sp.get("beginning") or "")[:90].rstrip(". ")
        end_short = (sp.get("end") or "")[:90].rstrip(". ")
        if n_mid == 0:
            spoken = (
                f'Now we have the Beginning ("{beg_short}") and the Ending ("{end_short}"). '
                "Going back to right after the beginning, what happens first in the middle?"
            )
            ui.append(
                {
                    "type": "input",
                    "mode": "type",
                    "prompt": "Plot Board Step 3 — Middle Event #1 (right after the beginning): What happens first in the middle?",
                    "prefill": "",
                }
            )
            self.ui_locked_this_turn.update({"show_card", "ask_input"})
            return ui, f'Say ONLY this exact prompt calmly and plainly (do NOT suggest plot events!): "{spoken}"'

        last_mid = (mbeats[-1].get("text") or "")[:90].rstrip(". ")
        ui.append(
            {
                "type": "item",
                "item": {
                    "id": "spine_more_choices",
                    "kind": "choices",
                    "prompt": f"{n_mid} middle event{'s' if n_mid != 1 else ''} on the Plot Board. Add another middle event, or start Chapter 1 panels?",
                    "options": ["Start Chapter 1 panels →", "Add another middle twist"],
                },
            }
        )
        spoken = (
            f'Right after "{last_mid}", what happens next in the middle before the ending? '
            "(Or tap Start Chapter 1 panels if your outline is ready.)"
        )
        ui.append(
            {
                "type": "input",
                "mode": "type",
                "prompt": f"Middle Event #{n_mid + 1}: What happens next in the middle? (Or tap 'Start Chapter 1 panels')",
                "prefill": "",
            }
        )
        self.ui_locked_this_turn.update({"show_card", "show_choices", "ask_input"})
        return ui, f'Say ONLY this exact prompt calmly and plainly (do NOT suggest plot events!): "{spoken}"'

    def _prompt_next_book_panel(self, ui: list[dict[str, Any]], resumed: bool = False) -> tuple[list[dict[str, Any]], str]:
        assert self.project is not None
        self.phase = "BUILDING"
        self.tier_nudged_this_item = False
        pcount = projects.total_panels(self.project)
        next_pnum = pcount + 1
        ch_num = len(self.project.get("chapters") or [1])
        tier = self.current_tier()
        sp = self.project.get("spine") or {}
        mbeats = projects.middle_beats_list(sp)

        if ch_num == 1:
            act_name = "Chapter 1 (The Kickoff)"
            act_focus = sp.get("beginning", "")
        elif ch_num - 1 <= len(mbeats):
            t_idx = ch_num - 1
            act_name = f"Chapter {ch_num} (Middle Twist #{t_idx})"
            act_focus = mbeats[t_idx - 1].get("text", "")
        else:
            act_name = f"Chapter {ch_num} (The Big Finale)"
            act_focus = sp.get("end", "")

        if next_pnum >= 2 and next_pnum % 2 == 0:
            tier_req = 'Invite them to include what a character shouts or says in "quotation marks" (like "Get off!" yelled Dylan.) if they want a real comic speech bubble on the panel!'
            conns = "when | because | but"
        elif tier >= 4:
            tier_req = "Invite starting with where or when the moment happens."
            conns = "when | although | because"
        else:
            tier_req = "Ask a specific story question driving the scene forward."
            conns = "when | because | so"

        if next_pnum == 1 and act_focus:
            zoom_goal = (
                f"We are zooming into Chapter 1, Panel 1 of {act_name}: \"{act_focus}\". "
                "DO NOT ask a generic prompt like 'describe the first moment'! Instead, remind them of what happens in Act I "
                "and ask a specific, curious zoom-in question (e.g. WHERE they got/found X, WHY they went there, or HOW the very first scene starts) "
                f"that hasn't been explained yet! {tier_req}"
            )
        elif act_focus:
            zoom_goal = (
                f"We are on Chapter {ch_num}, Panel {next_pnum} (currently inside {act_name}: \"{act_focus}\"). "
                "Remind them briefly of what JUST happened in the last panel, and ask a specific, curious story question ('why', 'where', 'how', 'what happens right after...') "
                f"that zooms into the very next beat toward {act_name}! {tier_req}"
            )
        else:
            zoom_goal = f"We are on Panel {next_pnum} of a 3-panel comic strip. Ask a specific, curious question for Panel {next_pnum}. {tier_req}"

        beat = self._pop_or_direct_beat(zoom_goal, conns)
        self._beat_input(ui, beat)
        self.ui_locked_this_turn.update({"show_card", "ask_input"})
        return ui, f"Deliver this specific, story-aware prompt for Panel {next_pnum} in 1–2 natural sentences: {beat['spoken_prompt']}"

    def _merge_fragments(self, prev: str, cur: str) -> str:
        if not prev:
            return cur.strip()
        p_low, c_low = prev.lower(), cur.lower()
        if p_low in c_low:
            return cur.strip()
        if c_low in p_low:
            return prev.strip()
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
        if not self.test_mode and chk.get("misspellings"):
            spelling_srs.ingest_misspellings(self.rec, self.misspellings)

    def _launch_word_forge(
        self,
        ui_actions: list[dict[str, Any]],
        raw_sentence: str,
        full_paragraph: str | None = None,
    ) -> dict[str, Any]:
        card = spelling_srs.select_word_for_session(self.rec, self.misspellings, self.studied_words_today)
        self.phase = "WORD_STUDY"
        self.word_target = card
        self.word_study_tries = 0
        ui_actions.append({"type": "goal", "text": self.goal_badge()})
        ui_actions.append(
            {
                "type": "item",
                "item": {
                    "id": "word",
                    "kind": "word",
                    "word": card["word"],
                    "parts": [p.strip() for p in card["parts"].split("+")],
                    "note": card["note"],
                },
            }
        )
        ui_actions.append(
            {
                "type": "input",
                "mode": "type",
                "prompt": f"Word Forge ({card.get('unit','Morphology & Spelling')}): study '{card['parts']}' above (covers when you type), then spell '{card['word']}' from memory (keyboard or pen).",
                "prefill": "",
            }
        )
        self.ui_locked_this_turn.update({"show_word", "ask_input"})
        origin = f"from '{card['wrote']}' earlier" if card.get("wrote") else f"({card.get('unit','Ontario pattern')})"
        directive = (
            f"COMPLETE SENTENCE LOCKED: '{raw_sentence}'! "
            f"Now run a quick 60-second Word Forge on '{card['word']}' {origin}. "
            f"The Cover-Copy-Compare card ('{card['parts']}' — {card['note']}) is ALREADY on screen and auto-covers on typing/pen. "
            f"Explain why '{card['word']}' is built as '{card['parts']}' in ONE plain sentence, and ask them to write '{card['word']}' from memory."
        )
        res: dict[str, Any] = {"kind": "COMPLETE_SENTENCE", "ui": ui_actions, "directive": directive}
        if full_paragraph:
            res["full_paragraph"] = full_paragraph
        return res

    # ---------------- ADAPTIVE AI COACH ----------------

    def _coach_context(self) -> str:
        if not self.project:
            return f"Free writing ({self.active_mechanic or 'quick comic strip'})."
        kind = self.project.get("kind")
        stage = self.project.get("stage", "")
        if kind == "epic_graphic_novel":
            n_mid = len(projects.middle_beats_list(self.project.get("spine") or {}))
            if stage == "spine_beginning":
                return "Graphic novel plot board: the KICKOFF (who is the hero + what trouble starts it). This sentence unlocks the cover art."
            if stage == "spine_end":
                return "Graphic novel plot board: the BIG FINALE (how the whole story ends up). Unlocks finale art."
            if stage == "spine_middle":
                return f"Graphic novel plot board: MIDDLE TWIST #{n_mid + 1} (what else goes wrong / escalates). Good spot for because/when/but."
            ch = len(self.project.get("chapters") or [1])
            return f"Graphic novel, chapter {ch}, panel {projects.total_panels(self.project) + 1}. Dialogue in quotes becomes a speech bubble."
        if kind == "epic_codex":
            return f"Fact codex step {self.codex_step} (0 = inference about the 3 sources; 1-3 = building a 3-sentence encyclopedia paragraph)."
        if kind == "medium_pitch":
            steps = {0: "the big idea he is pitching", 1: "a reason it will work (because/since)", 2: "answering the parent's worry (although/even though)", 3: "the deal (if/so)"}
            return f"Persuasive pitch page {self.tree_step + 1}: {steps.get(min(self.tree_step, 3))}."
        return "Quick 3-panel comic strip."

    def _launch_inline_word_help(
        self,
        ui: list[dict[str, Any]],
        sentence: str,
        wrote: str,
        meant: str,
        alt_words: list[str] | None = None,
        extra_targets: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Full word help: shows actual spelling + morpheme/sound parts, highlights word in prefill, AND offers 1-tap mic if meant word was misunderstood."""
        if " " in meant.strip():
            ws_card: dict[str, Any] = {"word": meant, "wrote": wrote, "parts": " + ".join(meant.split()), "note": f"'{meant}' is written as separate words."}
        elif len(meant) <= 2:
            ws_card = {"word": meant, "wrote": wrote, "parts": meant, "note": f"In '{_phrase_around_word(sentence, wrote)}', it's '{meant}'."}
        else:
            ws_card = dict(thinking.analyze_word_study(wrote, meant))
        if alt_words:
            ws_card["alt_words"] = alt_words
        self.phase_before_inline_help = self.phase if self.phase != "INLINE_WORD_HELP" else self.phase_before_inline_help
        self.phase = "INLINE_WORD_HELP"
        self.word_target = ws_card
        self.inline_word_help_tries = 0
        self.pending_spell_sentence = sentence
        targets = [{"wrote": wrote, "meant": meant}]
        for et in extra_targets or []:
            if et.get("wrote") and et.get("meant") and et["wrote"].lower() != wrote.lower():
                targets.append({"wrote": et["wrote"], "meant": et["meant"]})
        self.pending_spell_targets = targets
        ui.append({"type": "item", "item": {"id": "word", "kind": "word", "word": ws_card["word"], "parts": [x.strip() for x in ws_card["parts"].split("+")], "note": ws_card["note"]}})
        ui.append(
            {
                "type": "item",
                "item": {
                    "id": "say_word_help",
                    "kind": "choices",
                    "prompt": f"Meant a different word than “{ws_card['word']}”?",
                    "options": ["🎤 Say the word out loud so I can help"],
                },
            }
        )
        ui.append({"type": "input", "mode": "type", "prompt": f"Here's how '{ws_card['word']}' is spelled ({ws_card['parts']})—type '{ws_card['word']}' right over '{wrote}'!", "prefill": sentence, "select_word": wrote})
        self.ui_locked_this_turn.update({"show_word", "show_choices", "ask_input"})
        return ws_card

    @staticmethod
    def _should_ask_word_aloud(wrote: str, meant: str, llm_ask_aloud: bool = False) -> bool:
        """Decides when turning on the Center Green Mic ('Maybe say what this word is?') will genuinely help."""
        w = (wrote or "").strip().lower()
        m = (meant or "").strip().lower()
        if not w or not m:
            return False
        if llm_ask_aloud:
            return True
        if w[0] != m[0]:
            return True
        ratio = difflib.SequenceMatcher(None, w, m).ratio()
        return ratio < 0.68

    def _launch_tutor_mic_word_plan(
        self,
        sentence: str,
        wrote: str,
        meant_guess: str,
        story_rx: str = "",
        extra_ms: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Summons the Tutor-Controlled Center Green Mic asking him to say what `wrote` is supposed to be."""
        self.last_kid_kind = "TUTOR_MIC_WORD"
        self.draw_unlocked = False
        self.had_revision = True
        self.asked_aloud_words.add(wrote.lower())
        rest = [m for m in (extra_ms or []) if m.get("wrote") and m.get("meant") and m["wrote"].lower() != wrote.lower()]
        self.active_mic_request = {
            "purpose": "word",
            "wrote": wrote,
            "meant_guess": meant_guess,
            "sentence": sentence,
            "extra_ms": rest,
        }
        self.coach_session["last_request"] = {
            "focus": "spelling",
            "focus_word": wrote,
            "focus_correct": meant_guess,
            "focus_options": [meant_guess] if meant_guess else [],
            "spell_rung": 3,
            "misspelled": [wrote],
            "sentence": sentence,
            "chk": None,
        }
        rx_p = f"{story_rx.strip()} " if story_rx and story_rx.strip() else ""
        spoken = f"{rx_p}Maybe say out loud what word '{wrote}' is supposed to be so I can help spell it?"
        ui_mic = [
            {
                "type": "tutor_mic",
                "action": "on",
                "purpose": "word",
                "target_word": wrote,
                "sentence": sentence,
                "prompt": f"Say out loud what word “{wrote}” is",
            },
            {
                "type": "input",
                "mode": "type",
                "prompt": f"Say what “{wrote}” is into the green mic (or type the fix right here):",
                "prefill": sentence,
                "select_word": wrote,
            },
        ]
        self.ui_locked_this_turn.update({"ask_input", "show_choices"})
        mic_dec = {
            "accept": False,
            "focus": "spelling",
            "focus_word": wrote,
            "focus_correct": meant_guess,
            "spell_rung": 3,
            "scaffold": "tutor_mic_word",
            "kid_words": spoken,
            "rationale": f"Turned on Center Green Mic for '{wrote}' so he can say the word aloud and help clarify/sound it out.",
            "guardrail": "tutor_mic_word",
            "latency_s": 0.0,
        }
        self.last_coach = mic_dec
        return {
            "epoch": self.blackboard.bump_epoch(),
            "kind": self.last_kid_kind,
            "ui": ui_mic,
            "spoken_fallback": spoken,
            "directive": f'Ask warmly in 1-2 short sentences (the green mic in the center will turn on automatically right after you ask): "{spoken}"',
            "coach": mic_dec,
        }

    def handle_voice_clip_result(self, transcript: str, intended_word: str, purpose: str) -> dict[str, Any]:
        """Processes the short audio clip captured by the Tutor-Controlled Center Green Mic and turns the mic OFF."""
        epoch = self.blackboard.bump_epoch()
        req = self.active_mic_request or {}
        self.active_mic_request = None
        eff_purpose = purpose or req.get("purpose") or "story"

        if eff_purpose == "word":
            base_sent = str(req.get("sentence") or self.pending_spell_sentence or ((self.coach_session.get("last_request") or {}).get("sentence") or "")).strip()
            old_wrote = str(req.get("wrote") or (self.word_target or {}).get("wrote") or ((self.coach_session.get("last_request") or {}).get("focus_word") or "")).strip()
            extra_ms = req.get("extra_ms") or []
            word_clean = (intended_word or "").strip().lower()
            if not word_clean and transcript:
                toks = _words(transcript)
                word_clean = toks[-1].lower() if toks else ""
            if not word_clean:
                word_clean = str(req.get("meant_guess") or "").strip().lower()
            if base_sent and old_wrote and word_clean:
                ui_sp: list[dict[str, Any]] = [
                    {"type": "tutor_mic", "action": "off"},
                    {"type": "remove", "id": "say_word_help"},
                ]
                card = self._launch_inline_word_help(ui_sp, base_sent, old_wrote, word_clean, extra_targets=extra_ms)
                # Remove redundant mic button since he JUST spoke the word into the green mic!
                ui_sp = [u for u in ui_sp if not (u.get("type") == "item" and u.get("item", {}).get("id") == "say_word_help")]
                sp_line = f"Got it—'{card['word']}'! Here's how '{card['word']}' works: {card['parts']} ({card['note']}). Type '{card['word']}' right over '{old_wrote}' in your box!"
                return {
                    "epoch": epoch,
                    "kind": "SPOKEN_WORD_HELP",
                    "spoken_fallback": sp_line,
                    "ui": ui_sp,
                    "directive": f'Confirm the word they just said warmly and explain its spelling parts in 1-2 short sentences: "{sp_line}"',
                }

        if eff_purpose == "picture" and transcript:
            if req.get("target"):
                self.pending_art_target = req["target"]
            self.phase = "REDRAW_CLARIFY"
            res = self.classify_and_advance(transcript, "spoken")
            res["ui"] = [{"type": "tutor_mic", "action": "off"}] + res.get("ui", [])
            return res

        # Default ("story"): turn spoken idea into pre-filled draft in his box!
        res = self.classify_and_advance(transcript, "spoken")
        res["ui"] = [{"type": "tutor_mic", "action": "off"}] + res.get("ui", [])
        return res

    @staticmethod
    def _make_spell_choices(wrote: str, meant: str) -> list[str]:
        """Builds 3 plausible multiple-choice spellings (always including `meant` + `wrote` + 1 orthographic distractor)."""
        w_clean = wrote.strip()
        m_clean = meant.strip()
        # Preserve capitalization if wrote was capitalized at start of sentence
        if w_clean[:1].isupper() and m_clean[:1].islower():
            m_disp = m_clean[:1].upper() + m_clean[1:]
        else:
            m_disp = m_clean
        special_distractors = {
            "whose": ["who's", "whoose"],
            "face": ["fasse", "faice"],
            "because": ["becuase", "becuse"],
            "flying": ["flieing", "flyin"],
            "friend": ["freind", "frend"],
            "people": ["peple", "poeple"],
            "finally": ["finaly", "finelly"],
            "smelly": ["smely", "smelee"],
            "their": ["there", "they're"],
            "there": ["their", "they're"],
        }
        cands = [m_disp]
        if w_clean.lower() != m_disp.lower():
            cands.append(w_clean)
        for d_opt in special_distractors.get(m_clean.lower(), []):
            d_disp = d_opt[:1].upper() + d_opt[1:] if m_disp[:1].isupper() else d_opt
            if d_disp.lower() not in {c.lower() for c in cands}:
                cands.append(d_disp)
        # Generic phonetic/orthographic distractors if still < 3
        fallbacks = [
            m_disp + "e" if not m_disp.endswith("e") else m_disp[:-1],
            re.sub(r"([aeiou])", r"\1\1", m_disp, count=1),
            m_disp.replace("c", "s", 1) if "c" in m_disp.lower() else m_disp + "s",
        ]
        for fb in fallbacks:
            if len(cands) >= 3:
                break
            if fb and len(fb) >= 2 and fb.lower() not in {c.lower() for c in cands}:
                cands.append(fb)
        cands = cands[:3]
        # Deterministic shuffle seeded by sentence/word so choices don't always have correct first
        shift = sum(ord(ch) for ch in (w_clean + m_disp)) % len(cands)
        return cands[shift:] + cands[:shift]

    def _launch_quick_spell_mc_plan(
        self,
        sentence: str,
        wrote: str,
        meant: str,
        extra_ms: list[dict[str, str]] | None = None,
        rationale: str = "",
    ) -> dict[str, Any]:
        """Homework-grade Multiple-Choice + 'Why' explanation whenever we don't make the child retype a spelling error cold."""
        if " " in meant.strip():
            ws = {"word": meant, "parts": " + ".join(meant.split()), "note": f"'{meant}' is written as separate words."}
        elif len(meant) <= 2:
            ws = {"word": meant, "parts": meant, "note": f"In '{_phrase_around_word(sentence, wrote)}', use '{meant}'."}
        else:
            ws = dict(thinking.analyze_word_study(wrote, meant))
        why_note = ws.get("note") or f"Notice how '{meant}' is built: {ws.get('parts', meant)}."
        parts_str = ws.get("parts") or meant
        opts = self._make_spell_choices(wrote, meant)
        correct_disp = next((o for o in opts if o.lower() == meant.strip().lower()), meant.strip())

        self.last_kid_kind = "QUICK_SPELL_CHOICE"
        self.draw_unlocked = False
        self.had_revision = True
        self.spell_pick = {
            "wrote": wrote,
            "correct": correct_disp,
            "options": opts,
            "sentence": sentence,
            "why": why_note,
            "parts": parts_str,
            "extra_ms": [m for m in (extra_ms or []) if m.get("wrote") and m.get("meant") and m["wrote"].lower() != wrote.lower()],
        }
        ui_mc: list[dict[str, Any]] = [
            {"type": "remove", "id": "word"},
            {"type": "remove", "id": "say_word_help"},
            {
                "type": "item",
                "item": {
                    "id": "spell_why",
                    "kind": "card",
                    "title": f"Quick Spelling Check · “{wrote}”",
                    "text": f"Why it works: {why_note} ({parts_str})",
                },
            },
            {
                "type": "item",
                "item": {
                    "id": "spell_pick",
                    "kind": "choices",
                    "prompt": f"Pick the right spelling for “{wrote}”:",
                    "options": [*opts, "🎤 Say the word out loud so I can help"],
                },
            },
            {
                "type": "input",
                "mode": "type",
                "prompt": f"Tap the right spelling above (or type it right over “{wrote}” in your sentence):",
                "prefill": sentence,
                "select_word": wrote,
            },
        ]
        self.ui_locked_this_turn.update({"show_card", "show_choices", "ask_input"})
        spoken = f"Quick check on '{wrote}'! {why_note} Tap the right spelling on screen (or fix it in the box)!"
        mc_dec = {
            "accept": False,
            "focus": "spelling",
            "focus_word": wrote,
            "focus_correct": correct_disp,
            "spell_rung": 4,
            "scaffold": "multiple_choice_why",
            "kid_words": spoken,
            "rationale": rationale or f"Never skip spelling: showing 1-tap multiple choice + why rule ({parts_str}) for '{wrote}' -> '{correct_disp}'.",
            "guardrail": "never_skip_spelling_mc",
            "latency_s": 0.0,
        }
        self.last_coach = mc_dec
        return {
            "kind": self.last_kid_kind,
            "ui": ui_mc,
            "spoken_fallback": spoken,
            "directive": f'Explain briefly in 1-2 short plain sentences (do NOT say wrong): "{spoken}"',
            "coach": mc_dec,
        }

    def _is_frustrated(self, sig: dict[str, Any], decision: dict[str, Any]) -> bool:
        """Returns True ONLY when genuine frustration/overload is present—otherwise we gently fix every issue in the sentence!"""
        cs = self.coach_session
        if cs.get("consecutive_fixes", 0) >= coach.MAX_CONSECUTIVE_FIXES:
            return True
        if (sig.get("backspaces") or 0) >= 20:
            return True
        if cs.get("avoid_count", 0) >= 1 and cs.get("consecutive_fixes", 0) >= 2:
            return True
        return False

    def _launch_quick_grammar_mc_plan(
        self,
        sentence: str,
        wrote: str,
        options: list[str],
        rule: str,
        story_rx: str = "",
    ) -> dict[str, Any]:
        """Gentle 1-tap + highlighted-box check for verb endings/agreement ('get' -> 'gets'/'got') and missing articles ('a stinky cat')."""
        clean_opts = []
        for o in options or []:
            o_str = str(o).strip()
            if o_str and o_str.lower() not in {x.lower() for x in clean_opts}:
                clean_opts.append(o_str)
        if not clean_opts:
            clean_opts = [wrote]
        why_txt = (rule or f"In this sentence, change '{wrote}' to {' or '.join(repr(x) for x in clean_opts[:2])}.").strip()

        self.last_kid_kind = "QUICK_GRAMMAR_CHOICE"
        self.draw_unlocked = False
        self.had_revision = True
        self.spell_pick = {
            "pick_kind": "grammar",
            "wrote": wrote,
            "correct": clean_opts[0],
            "valid_options": [o.lower() for o in clean_opts],
            "options": clean_opts[:3],
            "sentence": sentence,
            "why": why_txt,
            "parts": " / ".join(clean_opts[:3]),
            "extra_ms": [],
        }
        self.coach_session["last_request"] = {
            "focus": "verb_ending",
            "focus_word": wrote,
            "focus_correct": clean_opts[0],
            "focus_options": clean_opts[:3],
            "spell_rung": 4,
            "misspelled": [],
            "sentence": sentence,
            "chk": None,
        }
        ui_gf: list[dict[str, Any]] = [
            {"type": "remove", "id": "word"},
            {"type": "remove", "id": "say_word_help"},
            {
                "type": "item",
                "item": {
                    "id": "spell_why",
                    "kind": "card",
                    "title": f"Quick Wording Check · “{wrote}”",
                    "text": f"Why it works: {why_txt}",
                },
            },
            {
                "type": "item",
                "item": {
                    "id": "spell_pick",
                    "kind": "choices",
                    "prompt": f"Pick the wording that fits your story for “{wrote}”:",
                    "options": clean_opts[:3],
                },
            },
            {
                "type": "input",
                "mode": "type",
                "prompt": f"Tap {' or '.join('“' + x + '”' for x in clean_opts[:2])} above (or edit “{wrote}” right in your box):",
                "prefill": sentence,
                "select_word": wrote,
            },
        ]
        self.ui_locked_this_turn.update({"show_card", "show_choices", "ask_input"})
        rx_p = f"{story_rx.strip()} " if story_rx and story_rx.strip() else ""
        opts_spoken = " or ".join(f"'{x}'" for x in clean_opts[:2])
        spoken = f"{rx_p}Quick check on '{wrote}'—{why_txt} Tap {opts_spoken} on screen (or fix it in the box)!"
        gf_dec = {
            "accept": False,
            "focus": "verb_ending",
            "focus_word": wrote,
            "focus_correct": clean_opts[0],
            "focus_options": clean_opts[:3],
            "scaffold": "grammar_choice_why",
            "kid_words": spoken,
            "rationale": f"No frustration detected: gently fixing grammar/wording '{wrote}' -> {clean_opts[:2]} ({why_txt}).",
            "guardrail": "fix_all_unless_frustrated",
            "latency_s": 0.0,
        }
        self.last_coach = gf_dec
        return {
            "kind": self.last_kid_kind,
            "ui": ui_gf,
            "spoken_fallback": spoken,
            "directive": f'Explain kindly in 1-2 short plain sentences (do NOT say wrong): "{spoken}"',
            "coach": gf_dec,
        }

    @staticmethod
    def _is_clean(chk: dict[str, Any] | None) -> bool:
        if not chk:
            return False
        sents = chk.get("sentences") or []
        return (
            bool(sents)
            and all(s.get("issue") == "none" and s.get("capital_ok") and s.get("end_ok") for s in sents)
            and not chk.get("misspellings")
            and not chk.get("grammar_fixes")
            and (chk.get("features") or {}).get("dialogue_punct_ok", True) is not False
        )

    def _coach_turn(self, raw: str, how: str, chk: dict[str, Any] | None) -> tuple[str | None, Any, dict[str, Any]]:
        cs = self.coach_session
        deal = cs.get("deal_pending")
        if deal:
            cs["deal_pending"] = None
            prev_w = set(re.findall(r"[a-z']+", deal.lower()))
            now_w = set(re.findall(r"[a-z']+", raw.lower()))
            if prev_w and len(prev_w & now_w) / max(1, len(prev_w)) >= 0.5:
                self._force_accept = {
                    "accept": True, "focus": "none", "scaffold": "none",
                    "next_scaffold": cs.get("next_scaffold", "starter_chips"), "kid_words": "",
                    "rationale": "Kept the deal: he sent his draft back after the quick-deal offer, so it draws with no further asks.",
                    "guardrail": "quick_deal_kept", "latency_s": 0.0,
                }
        if getattr(self, "_force_accept", None):
            forced = self._force_accept
            self._force_accept = None
            cs["consecutive_fixes"] = 0
            cs["last_request"] = None
            self.spell_pick = None
            self.last_coach = forced
            return "accept", forced, chk or blackboard.local_check_writing(raw)

        sig = dict(self.turn_signals or {})
        self.turn_signals = {}
        sig["minutes"] = round((time.time() - cs["started"]) / 60, 1)
        sig["used_chip"] = coach.chip_used(raw, cs.get("offered_chips") or [])
        last = cs.get("last_request")
        story = self.spine_summary() or "\n".join(self.active_story[-6:])
        next_goal = self._next_goal_preview()

        # Single fast small-model reflex call (~0.8s, 3.2s cap, 0ms local fallback)—NO serial multi-LLM chain!
        reflex_chk, decision, beat = blackboard.fast_reflex_turn(
            self.rec, self.blackboard, cs, raw, how, story, next_goal
        )
        effective_chk = chk if (chk and (chk.get("sentences") or chk.get("misspellings") or chk.get("grammar_fixes"))) else reflex_chk
        if chk is not None and chk is effective_chk:
            decision = coach.validate(decision, raw, effective_chk, cs)

        model = coach.ensure_model(self.rec)
        outcome = coach.outcome_of_last_request(last, effective_chk, raw) if last else {}
        sig["outcome"] = outcome
        if outcome.get("self_caught_words"):
            model["self_catches"] = model.get("self_catches", 0) + len(outcome["self_caught_words"])
        elif last and last.get("focus") == "spelling" and outcome.get("complied") and (last.get("spell_rung") or 0) >= 3:
            model["ai_catches"] = model.get("ai_catches", 0) + 1
        if effective_chk and (not last or not outcome.get("kept_same_idea")):
            coach.record_first_draft_stats(model, effective_chk)

        # IRONCLAD RETRY ESCALATION LAW:
        # If we asked him to fix a word ('fase' -> 'face') and he tried on the same sentence ('fasse')
        # OR if he edited a word in the same sentence ('fase' -> 'fasse') that is still misspelled,
        # NEVER silently let 'fasse' slide untaught! Show the Word Card ('f + ace') + highlight 'fasse'!
        old_toks_retry = _words(last.get("sentence") or "") if last else []
        old_set_retry = {w.lower() for w in old_toks_retry}
        edited_still_ms = next(
            (m for m in (effective_chk.get("misspellings") or []) if old_set_retry and m["wrote"].lower() not in old_set_retry),
            None,
        )
        if last and outcome.get("kept_same_idea") and (
            (last.get("focus") in ("spelling", "verb_ending") and outcome.get("complied") is False)
            or edited_still_ms is not None
        ):
            meant_prev = str((edited_still_ms or {}).get("meant") or last.get("focus_correct") or "").strip()
            alt_opts = list(last.get("focus_options") or ([meant_prev] if meant_prev else []))
            ms_list = effective_chk.get("misspellings") or []
            gf_list = effective_chk.get("grammar_fixes") or []
            matched_ms = edited_still_ms or next((m for m in ms_list if meant_prev and m["meant"].lower() == meant_prev.lower()), None)
            if not matched_ms and ms_list:
                matched_ms = ms_list[0]
            wrote_now = ""
            target_meant = meant_prev
            if matched_ms:
                wrote_now = matched_ms["wrote"]
                target_meant = matched_ms["meant"]
            elif gf_list:
                wrote_now = gf_list[0]["wrote"]
                target_meant = (gf_list[0].get("options") or [meant_prev])[0]
                alt_opts = gf_list[0].get("options") or alt_opts
            else:
                old_toks = _words(last.get("sentence") or "")
                old_set = {w.lower() for w in old_toks}
                diff_toks = [w for w in _words(raw) if w.lower() not in old_set]
                if diff_toks and meant_prev:
                    wrote_now = diff_toks[-1]
            if wrote_now and target_meant and wrote_now.lower() != target_meant.lower():
                cs["last_request"] = None
                cs["consecutive_fixes"] = 0
                ui_help: list[dict[str, Any]] = []
                self.last_kid_kind = "INLINE_WORD_HELP"
                self.draw_unlocked = False
                self.had_revision = True
                card = self._launch_inline_word_help(ui_help, raw, wrote_now, target_meant, alt_words=alt_opts, extra_targets=ms_list)
                spoken = f"Good try! Here's how '{card['word']}' is spelled: {card['parts']}. Type '{card['word']}' right over '{wrote_now}' (or tap the mic button if you meant a different word)!"
                esc_decision = {
                    "accept": False,
                    "focus": "spelling",
                    "focus_word": wrote_now,
                    "focus_correct": card["word"],
                    "spell_rung": 5,
                    "scaffold": "full_word_help",
                    "kid_words": spoken,
                    "rationale": f"He tried fixing '{last.get('focus_word')}' -> '{wrote_now}'; showing exact spelling '{card['word']}' ({card['parts']}) so he learns it instead of letting '{wrote_now}' slide.",
                    "guardrail": "retry_show_spelling",
                    "latency_s": decision.get("latency_s", 0.0),
                }
                self.last_coach = esc_decision
                snapshot = {**cs, "turns": list(cs.get("turns") or [])}
                threading.Thread(
                    target=blackboard.background_coach_update,
                    args=(self.rec, self.blackboard, snapshot, raw, how, effective_chk, sig, esc_decision, self.test_mode),
                    daemon=True,
                ).start()
                return (
                    "fix",
                    {
                        "kind": "INLINE_WORD_HELP",
                        "ui": ui_help,
                        "spoken_fallback": spoken,
                        "directive": f'Say warmly in 1-2 short sentences (do NOT say wrong): "{spoken}"',
                        "coach": esc_decision,
                    },
                    effective_chk,
                )

        self._cached_beat = beat
        if beat.get("book_title"):
            self._suggested_title = beat["book_title"]

        cs["today_state"] = decision.get("today_state") or cs.get("today_state") or {}
        cs["next_scaffold"] = "starter_chips" if self.blackboard.get_policy().get("use_starters", True) else "none"
        cs["suggest_pen"] = bool(self.blackboard.get_policy().get("suggest_pen", False))
        oc_txt = ""
        if outcome:
            oc_txt = f"{outcome.get('last_focus')}: {'did it' if outcome.get('complied') else ('ignored/changed idea' if outcome.get('complied') is False else 'n/a')}"
            if outcome.get("self_caught_words"):
                oc_txt += f", self-caught {outcome['self_caught_words']}"
        cs["turns"] = (cs.get("turns") or [])[-29:] + [
            {
                "min": sig["minutes"],
                "how": how,
                "text": raw,
                "secs": sig.get("secs"),
                "backspaces": sig.get("backspaces"),
                "accept": decision["accept"],
                "focus": decision["focus"],
                "outcome": oc_txt,
            }
        ]
        self.last_coach = decision

        # Asynchronous Background Specialist updates Blackboard policy & hypotheses for turn t+1!
        snapshot = {**cs, "turns": list(cs.get("turns") or [])}
        threading.Thread(
            target=blackboard.background_coach_update,
            args=(self.rec, self.blackboard, snapshot, raw, how, effective_chk, sig, decision, self.test_mode),
            daemon=True,
        ).start()

        ms_rem = effective_chk.get("misspellings") or []
        gf_rem = effective_chk.get("grammar_fixes") or []
        sents_rem = effective_chk.get("sentences") or []
        miss_cap = any(s.get("capital_ok") is False for s in sents_rem) or (bool(raw) and raw[0].isalpha() and not raw[0].isupper())
        miss_end = any(s.get("end_ok") is False for s in sents_rem) or (bool(raw) and not re.search(r'[.!?]["\')\]]*$', raw))

        frustrated = self._is_frustrated(sig, decision)

        # HOMEWORK RULE 1: Fix EVERY spelling error (unless genuinely frustrated)!
        if ms_rem and not frustrated and (decision["accept"] or (decision["focus"] != "spelling" and decision["focus"] not in ("complete_sentence", "run_on"))):
            m0 = sorted(ms_rem, key=lambda x: len(x.get("meant", "")), reverse=True)[0]
            rest_ms = [m for m in ms_rem if m["wrote"].lower() != m0["wrote"].lower()]
            cs["consecutive_fixes"] = cs.get("consecutive_fixes", 0) + 1
            cs["pushed"] = cs.get("pushed", 0) + 1
            if m0["wrote"].lower() not in self.asked_aloud_words and self._should_ask_word_aloud(m0["wrote"], m0["meant"], bool(decision.get("ask_aloud"))):
                return (
                    "fix",
                    self._launch_tutor_mic_word_plan(raw, m0["wrote"], m0["meant"], story_rx=decision.get("story_reaction", ""), extra_ms=rest_ms),
                    effective_chk,
                )
            return (
                "fix",
                self._launch_quick_spell_mc_plan(
                    raw,
                    m0["wrote"],
                    m0["meant"],
                    extra_ms=rest_ms,
                    rationale=f"No frustration: gently fixing spelling '{m0['wrote']}' -> '{m0['meant']}' with Multiple-Choice + Why.",
                ),
                effective_chk,
            )

        # HOMEWORK RULE 2: Fix EVERY verb-ending, agreement, or missing-article error ('Dylan get' -> 'gets'/'got', 'a stinky cat') unless frustrated!
        if gf_rem and not ms_rem and not frustrated and (decision["accept"] or decision["focus"] == "verb_ending"):
            g0 = gf_rem[0]
            cs["consecutive_fixes"] = cs.get("consecutive_fixes", 0) + 1
            cs["pushed"] = cs.get("pushed", 0) + 1
            return (
                "fix",
                self._launch_quick_grammar_mc_plan(
                    raw,
                    g0["wrote"],
                    g0.get("options") or [],
                    g0.get("rule") or "",
                    story_rx=decision.get("story_reaction", ""),
                ),
                effective_chk,
            )

        # HOMEWORK RULE 3: Every sentence MUST start with a Capital AND end with . ! or ? before moving on!
        if decision["accept"] and (miss_cap or miss_end):
            rx = (decision.get("story_reaction") or "").strip()
            rx_p = f"{rx} " if rx else ""
            if miss_cap and miss_end:
                kw = f"{rx_p}Capitalize the first letter at the start and add a period at the end."
                ip = "Capitalize the first letter + add a period at the end, then hit Enter"
                cpos = 0
                srange = [0, 1]
            elif miss_cap:
                kw = f"{rx_p}Capitalize the first letter at the start of your sentence."
                ip = "Capitalize the first letter at the start and hit Enter"
                cpos = 0
                srange = [0, 1]
            else:
                kw = f"{rx_p}Add a period (or ! or ?) at the end of your sentence."
                ip = "Add a period, !, or ? at the end and hit Enter"
                cpos = len(raw)
                srange = None
            decision = {
                **decision,
                "accept": False,
                "focus": "capital" if miss_cap else "end_mark",
                "cursor_pos": cpos,
                "select_range": srange,
                "kid_words": kw,
                "input_prompt": ip,
                "rationale": "Homework standard: starting capital and end mark (. ! ?) required before moving on.",
                "guardrail": "homework_cap_period_required",
            }
        elif not decision["accept"] and decision.get("focus") == "capital":
            decision["select_range"] = [0, 1]

        # Bonus efficiency: if asking to fix a spelling word AND missing capital/period, mention both in the prompt so he can fix both in 1 shot!
        if not decision["accept"] and decision["focus"] == "spelling" and (miss_cap or miss_end):
            extra_bits = []
            if miss_cap:
                extra_bits.append("start with a capital")
            if miss_end:
                extra_bits.append("end with a . or !")
            decision["input_prompt"] = f"{decision['input_prompt'].rstrip('.!')} (and {' + '.join(extra_bits)})"

        if decision["accept"]:
            cs["consecutive_fixes"] = 0
            cs["last_request"] = None
            cs["deferred"] = cs.get("deferred", 0) + len(decision.get("deferred") or [])
            self.spell_pick = None
            return "accept", decision, effective_chk

        # TUTOR-CONTROLLED MIC FOR UNCLEAR / PHONETIC MISSPELLINGS ("Maybe say what this word is?"):
        if (
            decision["focus"] == "spelling"
            and decision.get("focus_word")
            and decision["focus_word"].lower() not in self.asked_aloud_words
            and self._should_ask_word_aloud(
                decision["focus_word"],
                decision.get("focus_correct", ""),
                bool(decision.get("ask_aloud")),
            )
        ):
            cs["consecutive_fixes"] = cs.get("consecutive_fixes", 0) + 1
            cs["pushed"] = cs.get("pushed", 0) + 1
            return (
                "fix",
                self._launch_tutor_mic_word_plan(
                    raw,
                    decision["focus_word"],
                    decision.get("focus_correct", ""),
                    story_rx=decision.get("story_reaction", ""),
                    extra_ms=ms_rem,
                ),
                effective_chk,
            )

        cs["consecutive_fixes"] = cs.get("consecutive_fixes", 0) + 1
        cs["pushed"] = cs.get("pushed", 0) + 1
        cs["last_request"] = {
            "focus": decision["focus"],
            "focus_word": decision.get("focus_word", ""),
            "focus_correct": decision.get("focus_correct", ""),
            "focus_options": decision.get("focus_options") or [],
            "spell_rung": decision.get("spell_rung", 0),
            "misspelled": decision.get("misspelled") or [],
            "sentence": raw,
            "chk": effective_chk,
        }
        return "fix", self._coach_fix_plan(raw, decision, effective_chk), effective_chk

    def _coach_fix_plan(self, raw: str, d: dict[str, Any], chk: dict[str, Any]) -> dict[str, Any]:
        ui: list[dict[str, Any]] = []
        self.last_kid_kind = "COACH_FIX"
        self.draw_unlocked = False
        self.had_revision = True
        self.engaged_draft = raw
        inp: dict[str, Any] = {
            "type": "input",
            "mode": "type",
            "prompt": d["input_prompt"],
            "prefill": d.get("prefill") or raw,
            "hint_pen": bool(d.get("suggest_pen")),
        }
        focus = d["focus"]
        if focus == "spelling":
            rung = d.get("spell_rung", 3)
            self.pending_spell_sentence = raw
            self.pending_spell_targets = [{"wrote": m["wrote"], "meant": m["meant"]} for m in (chk.get("misspellings") or [])]
            inp["prefill"] = raw
            if rung == 5:
                self._launch_inline_word_help(ui, raw, d["focus_word"], d["focus_correct"])
                inp = {}
            elif rung == 4:
                extra_ms = [m for m in (chk.get("misspellings") or []) if m["wrote"].lower() != d["focus_word"].lower()]
                return self._launch_quick_spell_mc_plan(raw, d["focus_word"], d["focus_correct"], extra_ms=extra_ms, rationale=d.get("rationale", ""))
            elif rung == 3:
                inp["select_word"] = d["focus_word"]
        elif focus in ("verb_ending", "word_choice") and d.get("focus_word"):
            inp["prefill"] = raw
            inp["select_word"] = d["focus_word"]
        if d.get("scaffold") == "starter_chips" and d.get("chips"):
            self.coach_session["offered_chips"] = d["chips"]
            ui.append({"type": "item", "item": {"id": "starters", "kind": "starters", "options": d["chips"]}})
        if inp:
            if isinstance(d.get("select_range"), list) and len(d["select_range"]) == 2:
                inp["select_range"] = d["select_range"]
            elif isinstance(d.get("cursor_pos"), int):
                inp["cursor_pos"] = d["cursor_pos"]
            ui.append(inp)
        self.ui_locked_this_turn.update({"ask_input", "show_choices", "show_card", "show_word"})
        return {
            "kind": self.last_kid_kind,
            "ui": ui,
            "spoken_fallback": d.get("kid_words") or d.get("input_prompt") or "",
            "directive": f'Deliver this in 1-2 short natural sentences (warm story reaction is great; NEVER use cutesy grammar metaphors like "little dot" or "big like a superhero"—say "capital" and "period" directly): "{d["kid_words"]}"',
            "coach": {k: d.get(k) for k in ("accept", "focus", "focus_word", "spell_rung", "scaffold", "rationale", "guardrail", "today_state", "latency_s")},
        }

    # ---------------- MAIN SYNCHRONOUS TURN CLASSIFIER & STATE MACHINE ----------------

    def classify_and_advance(
        self,
        text: str,
        how: str,
        chk: dict[str, Any] | None = None,
        opening_ideas: list[dict[str, Any]] | None = None,
        handwriting_issue: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.ui_locked_this_turn.clear()
        self.last_coach = None
        epoch = self.blackboard.bump_epoch()
        had_mic_req = self.active_mic_request is not None
        if how in ("typed", "tap", "handwritten"):
            self.active_mic_request = None
        raw = (text or "").strip()
        norm = _norm(raw)
        wlist = _words(raw)
        idx = self.turn_index
        self.turn_index += 1
        self.last_kid_text = raw

        # ---------------- 00-PRE. WRONG STORY SLOT / UNDO STEP ("that wasn't the end. you asked what happened next.") ----------------
        if self.project and self.phase not in ("INLINE_WORD_HELP", "WORD_STUDY"):
            is_undo, move_end = self._is_wrong_slot_or_undo(raw)
            if is_undo:
                return self._handle_wrong_slot_or_undo(epoch, move_end)

        # ---------------- 00. PICTURE APPROVAL & COLLABORATIVE REDRAW ("Did I draw your scene right?") ----------------
        if self.phase == "AWAITING_ART_CHECK" and self.pending_art_target:
            if any(k in norm for k in ("looks right", "looks good", "next part", "keep going", "nailed it", "matches my story")) or norm in {"yes", "yep", "yeah", "good", "ok", "okay", "next", "right"}:
                res_plan = self._continue_after_art_approved([])
                res_plan["epoch"] = epoch
                return res_plan
            if "not quite" in norm or "fix picture" in norm or "fix the picture" in norm or norm in {"no", "nope", "wrong", "bad", "fix", "fix it", "redo"}:
                res_plan = self.start_fix_art_prompt(self.pending_art_target)
                res_plan["epoch"] = epoch
                return res_plan
            if len(wlist) >= 3 and how in ("typed", "spoken", "handwritten"):
                # He jumped straight into explaining what the picture should look like!
                self.phase = "REDRAW_CLARIFY"

        if self.phase == "REDRAW_CLARIFY" and self.pending_art_target and self.project and raw:
            if any(k in norm for k in ("looks right", "keep going", "skip", "never mind")):
                res_plan = self._continue_after_art_approved([])
                res_plan["epoch"] = epoch
                return res_plan
            rd = projects.prepare_art_redraw(self.project, self.pending_art_target, raw, sandbox=self.test_mode)
            self.phase = "AWAITING_ART_CHECK"
            self.last_kid_kind = "REDRAW_SUBMITTED"
            spoken = "Got it—that extra detail helps a ton! Redrawing your picture right now."
            ui_rd = [
                {"type": "remove", "id": "art_check_choices"},
                {"type": "reward", "label": "★ Redrawing with your new details…"},
                {"type": "item", "item": projects.project_ui_payload(self.project)},
                {"type": "input", "mode": "type", "prompt": "Redrawing your scene now—one moment…"},
            ]
            return {
                "epoch": epoch,
                "kind": self.last_kid_kind,
                "redraw_art": rd,
                "spoken_fallback": spoken,
                "ui": ui_rd,
                "directive": f'Say in 1 short sentence: "{spoken}"',
            }

        # ---------------- 00A. DIRECTOR META-CORRECTION GUARD ("why are you having the spaceship stuck on the moon and not earth>") ----------------
        if (
            self.project
            and how in ("typed", "spoken", "handwritten")
            and self.phase not in ("INLINE_WORD_HELP", "WORD_STUDY")
            and self._is_director_correction(raw)
        ):
            target_fix = self.pending_art_target or projects.latest_art_target(self.project)
            if target_fix:
                if self.phase not in ("AWAITING_ART_CHECK", "REDRAW_CLARIFY"):
                    self.phase_after_art_check = self.phase
                self.pending_art_target = target_fix
                self.phase = "AWAITING_ART_CHECK"
                self.last_kid_kind = "REDRAW_SUBMITTED"
                rd = projects.prepare_art_redraw(
                    self.project,
                    target_fix,
                    f"DIRECTOR SETTING/STORY CORRECTION — FOLLOW STRICTLY: {raw}",
                    sandbox=self.test_mode,
                )
                spoken = "My bad—you are totally right! Let me fix that and redraw the scene right now so it matches your story."
                ui_fix = [
                    {"type": "remove", "id": "art_check_choices"},
                    {"type": "reward", "label": "★ Fixing & redrawing scene to match your story…"},
                    {"type": "item", "item": projects.project_ui_payload(self.project)},
                    {"type": "input", "mode": "type", "prompt": "Redrawing your corrected scene now—one moment…"},
                ]
                return {
                    "epoch": epoch,
                    "kind": self.last_kid_kind,
                    "redraw_art": rd,
                    "spoken_fallback": spoken,
                    "ui": ui_fix,
                    "directive": (
                        f'The student just corrected a mistake you made about their story/picture ("{raw}"). '
                        "Apologize warmly in 1 short sentence ('My bad—you are totally right!'), confirm their EXACT correction accurately (do NOT flip Earth vs moon backwards!), "
                        "and tell them you are redrawing that scene right now without adding a fake story beat."
                    ),
                }

        # ---------------- 00B. SPOKEN SINGLE-WORD HELP ("Why don't you tell me what the word is so I can help?") ----------------
        if how == "spoken" and 1 <= len(wlist) <= 3 and (self.phase == "INLINE_WORD_HELP" or (self.coach_session.get("last_request") or {}).get("focus") == "spelling"):
            spoken_word = wlist[-1].lower()
            base_sent = self.pending_spell_sentence or ((self.coach_session.get("last_request") or {}).get("sentence") or "")
            old_wrote = (self.word_target or {}).get("wrote") or ((self.coach_session.get("last_request") or {}).get("focus_word") or "")
            if base_sent and old_wrote and len(spoken_word) >= 2:
                card = self._launch_inline_word_help([], base_sent, old_wrote, spoken_word)
                ui_sp = [
                    {"type": "remove", "id": "say_word_help"},
                    {"type": "item", "item": {"id": "word", "kind": "word", "word": card["word"], "parts": [x.strip() for x in card["parts"].split("+")], "note": card["note"]}},
                    {"type": "input", "mode": "type", "prompt": f"Aha, “{card['word']}”! Study {card['parts']}, then type “{card['word']}” over “{old_wrote}” in your sentence!", "prefill": base_sent, "select_word": old_wrote},
                ]
                sp_line = f"Aha, you meant '{card['word']}'! Here's how it's spelled: {card['parts']}. Type '{card['word']}' right over '{old_wrote}' in your sentence!"
                return {
                    "epoch": epoch,
                    "kind": "SPOKEN_WORD_HELP",
                    "spoken_fallback": sp_line,
                    "ui": ui_sp,
                    "directive": f'Say warmly in 1-2 short sentences: "{sp_line}"',
                }

        # ---------------- 0A. PLAYFULLY CONFUSED SINGLE-LETTER HANDWRITING TOUCH-UP ----------------
        if how == "handwritten":
            if isinstance(handwriting_issue, dict) and handwriting_issue.get("letter_intended") and self.handwriting_fix_tries == 0:
                self.handwriting_fix_tries = 1
                self.last_kid_kind = "HANDWRITING_LETTER_FIX"
                self.draw_unlocked = False
                w_int = str(handwriting_issue.get("word_intended") or "")
                w_wri = str(handwriting_issue.get("word_written") or raw)
                l_int = str(handwriting_issue.get("letter_intended") or "")
                l_lks = str(handwriting_issue.get("looks_like") or "?")
                tip = str(handwriting_issue.get("line_tip") or "Check the Sky, Fence, Grass, and Worm lines.")
                prompt_msg = (
                    f"Hold on—in \"{w_int or w_wri}\", that letter looks like '{l_lks}'! "
                    f"Tap Erase and fix just that one '{l_int}' ({tip})"
                )
                return {
                    "kind": self.last_kid_kind,
                    "ui": [
                        {
                            "type": "input",
                            "mode": "pen",
                            "keep_strokes": True,
                            "spot": {
                                "x": handwriting_issue.get("x_frac"),
                                "y": handwriting_issue.get("y_frac"),
                                "label": f"'{l_lks}' → '{l_int}'",
                            },
                            "prompt": prompt_msg,
                        }
                    ],
                    "directive": (
                        f"Act friendly and playfully confused about JUST ONE letter in {self.name}'s handwriting: "
                        f"in '{w_int or w_wri}', one letter looked like '{l_lks}' ('{w_wri}') instead of '{l_int}'. "
                        f"Tell them their writing is still right on the lined pad—tap Erase and fix JUST that one letter ({tip}), then tap Done!"
                    ),
                }
            self.handwriting_fix_tries = 0

        if chk:
            self.record_misspellings(chk)
        if how in ("typed", "spoken", "handwritten") and (
            norm in AVOIDANCE_WORDS or any(re.search(pat, norm) for pat in REFUSAL_PATTERNS) or re.search(r"\b(can we just|just draw|its fine|it's fine)\b", norm)
        ):
            self.coach_session["avoid_count"] = self.coach_session.get("avoid_count", 0) + 1

        ui_actions: list[dict[str, Any]] = []
        resolved_inline_word: str = ""
        resolved_repaired_text: str = ""

        # ---------------- 0. VOICE-TO-DRAFT DICTATION EXTERNALIZATION (MacArthur + Barkley) ----------------
        if how == "spoken" and len(wlist) >= 3 and not any(re.search(p, norm) for p in REFUSAL_PATTERNS) and norm not in AVOIDANCE_WORDS:
            self.last_kid_kind = "ORAL_DRAFT"
            self.draw_unlocked = False
            self.engaged_draft = raw
            ui_actions.append(
                {
                    "type": "item",
                    "item": {
                        "id": "forge",
                        "kind": "card",
                        "title": "Voice Draft Captured — Check, Upgrade & Send",
                        "text": f"You spoke:\n  \"{raw}\"\n\nCheck & Fix in the box below: capital at start, clean sentence boundaries (no 'and then' chains), and period at the end—then hit Enter!",
                    },
                }
            )
            ui_actions.append(
                {
                    "type": "input",
                    "mode": "type",
                    "prompt": "Check and edit your spoken sentence right in the box (capital, connector, punctuation), then hit Enter!",
                    "prefill": raw[:1].upper() + raw[1:],
                }
            )
            self.ui_locked_this_turn.update({"show_card", "ask_input"})
            return {
                "kind": self.last_kid_kind,
                "ui": ui_actions,
                "directive": (
                    f"{self.name} dictated an idea aloud ('{raw}'). It is now captured in their typing box! "
                    "In ONE short sentence, tell them their spoken draft is in the box—check the capital, connectors, and end punctuation and hit Enter to lock it in."
                ),
            }

        # ---------------- 0B. INLINE WORD HELP RETRIEVAL ("Start All the Help" on Retry) ----------------
        if self.phase == "INLINE_WORD_HELP" and self.word_target and how in ("typed", "handwritten"):
            target_word = self.word_target["word"]
            alt_words = [target_word] + [w for w in (self.word_target.get("alt_words") or []) if w and w.lower() != target_word.lower()]
            wrote_orig = self.word_target.get("wrote", "")
            alt_pats = [re.compile(rf"\b{re.escape(w.lower())}\b") for w in alt_words]
            w_pat = re.compile(rf"\b{re.escape(wrote_orig.lower())}\b") if wrote_orig else None
            matched_word = next(
                (
                    w
                    for w, pat in zip(alt_words, alt_pats)
                    if norm == w.lower()
                    or (len(wlist) <= 3 and bool(pat.search(norm)))
                    or (len(wlist) >= 3 and bool(pat.search(norm)) and not (w_pat and w_pat.search(norm)))
                ),
                "",
            )
            matched = bool(matched_word)
            if not matched and self.inline_word_help_tries == 0:
                self.inline_word_help_tries = 1
                self.last_kid_kind = "INLINE_WORD_HELP"
                self.draw_unlocked = False
                letter_guide = " - ".join(list(target_word))
                note_plus = f"{self.word_target['note']} (Letters: {letter_guide})"
                ui_actions.append(
                    {
                        "type": "item",
                        "item": {
                            "id": "word",
                            "kind": "word",
                            "word": target_word,
                            "parts": [p.strip() for p in self.word_target["parts"].split("+")],
                            "note": note_plus,
                        },
                    }
                )
                chk_ms = [m for m in (chk or {}).get("misspellings", []) if m.get("wrote")]
                if len(wlist) >= 3:
                    retry_prefill = raw
                    if chk_ms:
                        self.pending_spell_sentence = raw
                        self.pending_spell_targets = chk_ms
                else:
                    retry_prefill = self.pending_spell_sentence or raw
                if wrote_orig and wrote_orig.lower() in retry_prefill.lower():
                    retry_sel = wrote_orig
                elif chk_ms and chk_ms[0]["wrote"].lower() in retry_prefill.lower():
                    retry_sel = chk_ms[0]["wrote"]
                else:
                    retry_sel = raw if len(wlist) <= 2 else ""
                ui_actions.append(
                    {
                        "type": "input",
                        "mode": "type",
                        "prompt": f"Look closely at '{self.word_target['parts']}' ({letter_guide}), then fix it right in your sentence below and hit Enter.",
                        "prefill": retry_prefill,
                        "select_word": retry_sel,
                    }
                )
                self.ui_locked_this_turn.update({"show_word", "ask_input"})
                return {
                    "kind": self.last_kid_kind,
                    "ui": ui_actions,
                    "directive": (
                        f"Give full gentle support on '{target_word}' (they wrote '{raw}'). Do NOT say 'wrong'. "
                        f"Walk through the parts '{self.word_target['parts']}' in 1 short sentence and invite fixing it right in their pre-filled sentence."
                    ),
                }

            # Resolved! Record SRS, splice fixed word(s) into their sentence, remove word card, and advance immediately!
            final_word = matched_word or target_word
            self.studied_words_today.add(final_word.lower())
            if len(final_word) >= 3:
                self.word_study_done = True
            if not self.test_mode and len(final_word) >= 2:
                spelling_srs.record_retrieval_result(self.rec, final_word, correct_first_try=(matched and self.inline_word_help_tries == 0))
                save_learner(self.rec)
            ui_actions.append({"type": "remove", "id": "word"})
            ui_actions.append({"type": "remove", "id": "say_word_help"})
            ui_actions.append({"type": "remove", "id": "spell_why"})
            ui_actions.append({"type": "remove", "id": "spell_pick"})
            self.spell_pick = None

            if matched and len(wlist) >= 3:
                repaired = raw
            else:
                repaired = _splice_word_into_sentence(self.pending_spell_sentence or raw, wrote_orig or final_word, final_word)

            remaining_targets = [
                m for m in self.pending_spell_targets
                if m.get("wrote") and m.get("meant") and re.search(rf"\b{re.escape(m['wrote'])}\b", repaired, re.I)
            ]
            if remaining_targets:
                nxt = remaining_targets[0]
                self.phase = self.phase_before_inline_help or (
                    "STORY_SPINE" if (self.project and self.project.get("stage", "").startswith("spine_")) else "BUILDING"
                )
                self.pending_spell_targets = []
                self.pending_spell_sentence = ""
                self.inline_word_help_tries = 0
                mc_plan = self._launch_quick_spell_mc_plan(repaired, nxt["wrote"], nxt["meant"], extra_ms=remaining_targets[1:])
                mc_plan["ui"] = ui_actions + mc_plan["ui"]
                mc_plan["epoch"] = epoch
                return mc_plan

            # Enforce Capital + End Punctuation on `repaired` before advancing!
            miss_c = bool(repaired) and repaired[0].isalpha() and not repaired[0].isupper()
            miss_e = bool(repaired) and not re.search(r'[.!?]["\')\]]*$', repaired)
            if miss_c or miss_e:
                self.phase = self.phase_before_inline_help or (
                    "STORY_SPINE" if (self.project and self.project.get("stage", "").startswith("spine_")) else "BUILDING"
                )
                self.pending_spell_targets = []
                self.pending_spell_sentence = ""
                self.inline_word_help_tries = 0
                self.last_kid_kind = "COACH_FIX"
                prompt_ce = (
                    "Nice spelling fix! Now capitalize the first letter and add a . or ! at the end to unlock the art:"
                    if (miss_c and miss_e)
                    else ("Nice spelling fix! Capitalize the first letter at the start and hit Enter:" if miss_c else "Nice spelling fix! Add a . ! or ? at the end and hit Enter:")
                )
                ui_actions.append({"type": "input", "mode": "type", "prompt": prompt_ce, "prefill": repaired, "cursor_pos": 0 if miss_c else len(repaired)})
                self.ui_locked_this_turn.add("ask_input")
                return {
                    "epoch": epoch,
                    "kind": self.last_kid_kind,
                    "spoken_fallback": prompt_ce,
                    "ui": ui_actions,
                    "directive": f'Say warmly in 1 short sentence: "{prompt_ce}"',
                }

            self.phase = self.phase_before_inline_help or (
                "STORY_SPINE" if (self.project and self.project.get("stage", "").startswith("spine_")) else "BUILDING"
            )
            self.pending_spell_targets = []
            self.pending_spell_sentence = ""
            self.inline_word_help_tries = 0
            self.coach_session["last_request"] = None
            resolved_inline_word = target_word
            resolved_repaired_text = repaired
            raw = repaired
            norm = _norm(raw)
            wlist = _words(raw)
            self.last_kid_text = raw
            chk = None  # Re-verify full sentence so any remaining verb/article/capital/period issue ('Dylan get stinky cat.') is caught!

        # ---------------- 1. WORD STUDY RETRIEVAL PHASE (Leitner Spaced Deck) ----------------
        if self.phase == "WORD_STUDY" and self.word_target:
            target_word = self.word_target["word"]
            typed_words = [w.lower() for w in wlist]
            matched = target_word.lower() in typed_words or norm == target_word.lower()
            self.word_study_tries += 1
            self.last_kid_kind = "SPELLING_ATTEMPT"
            self.prev_norm_text = norm
            if matched or self.word_study_tries >= 2:
                self.word_study_done = True
                self.studied_words_today.add(target_word.lower())
                if not self.test_mode:
                    spelling_srs.record_retrieval_result(self.rec, target_word, correct_first_try=(matched and self.word_study_tries == 1))
                    save_learner(self.rec)
                ui_actions.append({"type": "remove", "id": "word"})

                if self.project:
                    ui_actions.append({"type": "goal", "text": self.goal_badge()})
                    pkind = self.project.get("kind", "")
                    if pkind == "epic_codex" and self.codex_step <= 3:
                        ui_actions, next_dir = self._prompt_codex_step(ui_actions, new_entry=(self.codex_step == 0))
                    elif pkind == "medium_pitch" and self.tree_step < 4:
                        ui_actions, next_dir = self._prompt_pitch_step(ui_actions)
                    elif self.goal_done >= self.session_panels_target:
                        self.phase = "WRAP"
                        ui_actions.append(
                            {
                                "type": "item",
                                "item": {
                                    "id": "done_choices",
                                    "kind": "choices",
                                    "prompt": f"Today's slice complete ({projects.total_panels(self.project)} total pages/panels saved in PDF)!",
                                    "options": ["Keep going — next page/panel", "Wrap up & download PDF"],
                                },
                            }
                        )
                        self.ui_locked_this_turn.add("show_choices")
                        next_dir = f"Book '{self.project.get('title')}' is auto-saved with a live PDF ready on the right. Ask if they want to keep going or wrap here."
                    else:
                        ui_actions, next_dir = self._prompt_next_book_panel(ui_actions, resumed=False)
                    ack = (
                        f"Locked '{target_word}' ({self.word_target['parts']}) into your spaced word deck! "
                        if matched
                        else f"Compare once: '{target_word}' ({self.word_target['parts']})—it will come back in a couple days for review. "
                    )
                    return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": ack + next_dir}

                self.phase = "WRAP" if self.goal_done >= self.goal_target else "BUILDING"
                ui_actions.append({"type": "goal", "text": self.goal_badge()})
                if matched:
                    directive = (
                        f"SPELLING LOCKED IN: {self.name} spelled '{target_word}' accurately from memory! "
                        f"Confirm how they nailed '{self.word_target['parts']}' in one plain sentence. "
                        + (
                            f"Today's goal is complete—call save_piece so {self.name} and {self.parent_title} can keep it, or offer turning it into a Full PDF Comic Book."
                            if self.phase == "WRAP"
                            else f"Now return to sentence {self.goal_done + 1} of {self.goal_target}."
                        )
                    )
                else:
                    directive = f"Show the exact comparison once: '{target_word}' ({self.word_target['parts']}), without saying 'wrong', and move cleanly forward."
                return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": directive}
            else:
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
                ui_actions.append({"type": "input", "mode": "type", "prompt": f"Look at '{self.word_target['parts']}', then type '{target_word}' from memory.", "prefill": ""})
                self.ui_locked_this_turn.update({"show_word", "ask_input"})
                return {
                    "kind": self.last_kid_kind,
                    "ui": ui_actions,
                    "directive": f"{self.name} wrote '{raw}' for '{target_word}'. Do NOT say 'wrong'. Point out '{self.word_target['parts']}' in 1 short sentence and invite 1 retry from memory.",
                }

        # ---------------- 1B. FINISHING ITERATIVE MIDDLE TWISTS -> START CHAPTER 1 PANELS ----------------
        if (
            self.project
            and self.project.get("stage") == "spine_middle"
            and len(projects.middle_beats_list(self.project.get("spine") or {})) >= 1
            and re.search(r"\b(start chapter|start panel|ready for panel|no more twist|done with middle|start drawing)\b", norm)
        ):
            sp = self.project.setdefault("spine", {})
            sp["complete"] = True
            self.project["stage"] = "drafting_panels"
            projects.save_project(self.project, sandbox=self.test_mode)
            self.last_kid_kind = "PROJECT_PICK"
            ui_actions.append({"type": "remove", "id": "spine_more_choices"})
            ui_actions.append({"type": "reward", "label": "★ Plot Board Complete · Starting Chapter 1!"})
            ui_actions.append({"type": "item", "item": projects.project_ui_payload(self.project)})
            ui_actions.append({"type": "goal", "text": self.goal_badge()})
            ui_actions, next_dir = self._prompt_next_book_panel(ui_actions, resumed=False)
            return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": next_dir}

        # ---------------- 2. TAP INPUTS ----------------
        if how == "tap":
            self.prev_norm_text = norm
            if self.spell_pick and raw.strip().lower() in [o.lower() for o in self.spell_pick.get("options", [])]:
                sp = self.spell_pick
                self.spell_pick = None
                self.last_kid_kind = "SPELL_PICK"
                ui_actions.append({"type": "remove", "id": "spell_pick"})
                ui_actions.append({"type": "remove", "id": "spell_why"})
                valid_set = set(sp.get("valid_options") or [sp["correct"].lower()])
                picked_clean = raw.strip()
                if picked_clean.lower() in valid_set:
                    if sp.get("pick_kind") != "grammar" and not self.test_mode and len(picked_clean) >= 3:
                        spelling_srs.record_retrieval_result(self.rec, picked_clean, correct_first_try=True)
                        save_learner(self.rec)
                    repaired_sp = _splice_word_into_sentence(sp["sentence"], sp["wrote"], picked_clean)
                    extra_list = [
                        m for m in (sp.get("extra_ms") or [])
                        if m.get("wrote") and re.search(rf"\b{re.escape(m['wrote'])}\b", repaired_sp, re.I)
                    ]
                    if extra_list:
                        nxt = extra_list[0]
                        mc_next = self._launch_quick_spell_mc_plan(repaired_sp, nxt["wrote"], nxt["meant"], extra_ms=extra_list[1:])
                        mc_next["ui"] = ui_actions + mc_next["ui"]
                        mc_next["epoch"] = epoch
                        return mc_next
                    # Re-check `repaired_sp` genuinely (chk=None) so any remaining verb/article/capital/period issue ('Dylan get stinky cat.') is caught gently!
                    self.coach_session["last_request"] = None
                    adv = self.classify_and_advance(repaired_sp, "typed", chk=None, opening_ideas=opening_ideas)
                    adv["ui"] = ui_actions + adv["ui"]
                    adv.setdefault("repaired_text", repaired_sp)
                    return adv
                # Picked a distractor -> explain WHY the correct spelling works and show full Word Card!
                card = self._launch_inline_word_help(ui_actions, sp["sentence"], sp["wrote"], sp["correct"], extra_targets=sp.get("extra_ms"))
                sp_why = f"Close! It's '{sp['correct']}' ({card['parts']})—{card['note']} Type '{sp['correct']}' over '{sp['wrote']}' in the box!"
                return {
                    "epoch": epoch,
                    "kind": self.last_kid_kind,
                    "spoken_fallback": sp_why,
                    "ui": ui_actions,
                    "directive": f'Without saying wrong, explain why in 1 short sentence: "{sp_why}"',
                }
            if norm == _norm(coach.SWITCH_OPTIONS["twist"]):
                self.last_kid_kind = "TWIST_CARD"
                beat = ai_direct_next_beat(
                    self.rec,
                    "He was stuck. Invent ONE wild, funny surprise event that crashes into HIS story right now (gross or absurd is great), "
                    "say it in one punchy line, then ask what his hero does about it.",
                    self.active_story,
                    spine_context=self.spine_summary(),
                    connector_goal="when | because | but | so",
                )
                ui_actions.append({"type": "remove", "id": "unstick"})
                self._beat_input(ui_actions, beat)
                self.ui_locked_this_turn.update({"ask_input", "show_choices"})
                return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": f"Deliver this surprise twist with energy in 1–2 short sentences: {beat['spoken_prompt']}"}

            if "say the word out loud" in norm:
                self.last_kid_kind = "VOICE_WORD_PROMPT"
                wt_wrote = (self.word_target or {}).get("wrote") or (self.spell_pick or {}).get("wrote") or ""
                wt_sent = self.pending_spell_sentence or (self.spell_pick or {}).get("sentence") or ""
                wt_guess = (self.word_target or {}).get("word") or (self.spell_pick or {}).get("correct") or ""
                self.active_mic_request = {"purpose": "word", "wrote": wt_wrote, "meant_guess": wt_guess, "sentence": wt_sent, "extra_ms": []}
                ui_actions.append({"type": "remove", "id": "say_word_help"})
                ui_actions.append({"type": "tutor_mic", "action": "on", "purpose": "word", "target_word": wt_wrote, "sentence": wt_sent, "prompt": f"Say out loud what word “{wt_wrote or 'that'}” is"})
                ui_actions.append({"type": "input", "mode": "type", "prompt": "Green mic is ON—say the word out loud so I can help spell it!"})
                self.ui_locked_this_turn.add("ask_input")
                sp_line = "I turned on the green mic—say just that word out loud so I know the exact word you want!"
                return {"epoch": epoch, "kind": self.last_kid_kind, "spoken_fallback": sp_line, "ui": ui_actions, "directive": f'Say in 1 short sentence: "{sp_line}"'}

            if norm == _norm(coach.SWITCH_OPTIONS["voice"]):
                self.last_kid_kind = "VOICE_OFFER"
                self.active_mic_request = {"purpose": "story", "sentence": ""}
                ui_actions.append({"type": "remove", "id": "unstick"})
                ui_actions.append({"type": "tutor_mic", "action": "on", "purpose": "story", "target_word": "", "sentence": "", "prompt": "Tell me out loud what happens next"})
                ui_actions.append({"type": "input", "mode": "type", "prompt": "Green mic is ON—say what happens next out loud!"})
                self.ui_locked_this_turn.add("ask_input")
                sp_line = "I turned on the green mic—just say what happens next out loud, and I'll put your words in the box!"
                return {"epoch": epoch, "kind": self.last_kid_kind, "spoken_fallback": sp_line, "ui": ui_actions, "directive": f'Say in 1 short sentence: "{sp_line}"'}

            if norm == _norm(coach.SWITCH_OPTIONS["pause"]):
                self.phase = "WRAP"
                self.last_kid_kind = "PROJECT_PICK"
                ui_actions.append({"type": "remove", "id": "unstick"})
                saved = f" '{self.project.get('title')}' is saved, and the PDF button on the right has everything so far." if self.project else ""
                return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": f"He wants to stop for today. In ONE short, warm line, wrap up on a win.{saved} No pressure, no guilt."}

            if "add another middle twist" in norm and self.project and self.project.get("stage") == "spine_middle":
                self.last_kid_kind = "PROJECT_PICK"
                ui_actions.append({"type": "remove", "id": "spine_more_choices"})
                n_mid = len(projects.middle_beats_list(self.project.get("spine") or {}))
                ui_actions.append({"type": "input", "mode": "type", "prompt": f"Middle Twist #{n_mid + 1}: What else goes wrong or escalates next before your ending?", "prefill": ""})
                self.ui_locked_this_turn.add("ask_input")
                return {
                    "kind": self.last_kid_kind,
                    "ui": ui_actions,
                    "directive": f"Invite writing Middle Twist #{n_mid + 1} in 1 short sentence—ask specifically what else happens in the middle before their finale.",
                }

            if "research my own" in norm and self.project and self.project.get("kind") == "epic_codex":
                self.awaiting_codex_topic = True
                self.last_kid_kind = "PROJECT_PICK"
                ui_actions.append({"type": "input", "mode": "type", "prompt": "Name any real science, creature, machine, history, or music topic for your 3-Source Codex Dossier:", "prefill": ""})
                self.ui_locked_this_turn.add("ask_input")
                return {
                    "kind": self.last_kid_kind,
                    "ui": ui_actions,
                    "directive": "Invite naming any real-world topic (science, engineering, creatures, medieval weapons, heavy metal acoustics) and you'll pull 3 factual sources on it.",
                }

            if "keep going" in norm and self.project:
                self.session_panels_target += 3
                self.word_study_done = False
                pkind = self.project.get("kind", "")
                if pkind == "epic_codex":
                    ui_actions, directive = self._prompt_codex_step(ui_actions, new_entry=True)
                else:
                    ui_actions, directive = self._prompt_next_book_panel(ui_actions, resumed=False)
                self.last_kid_kind = "PROJECT_PICK"
                return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": directive}

            if ("wrap" in norm or "pause" in norm or "download pdf" in norm) and self.project:
                self.phase = "WRAP"
                self.last_kid_kind = "PROJECT_PICK"
                return {
                    "kind": self.last_kid_kind,
                    "ui": ui_actions,
                    "directive": f"Book '{self.project.get('title')}' is saved and ready via the Download PDF button on the right! Give a crisp 1-sentence wrap-up.",
                }

            if len(wlist) <= 2 and self.engaged_draft:
                self.last_kid_kind = "SCAFFOLD_CHIP"
                merged = f"{self.engaged_draft.rstrip('.!?, ')} {raw} "
                ui_actions.append({"type": "input", "mode": "type", "prompt": f"Finish and send the complete sentence using '{raw}'.", "prefill": merged[:1].upper() + merged[1:]})
                self.ui_locked_this_turn.add("ask_input")
                return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": f"Word '{raw}' added to box—ask in 1 short sentence to finish the complete sentence."}

            if any(k in norm for k in ("continue ", "full comic book", "graphic novel", "new comic", "codex", "field guide", "fact", "pitch", "why we should")):
                self.last_kid_kind = "PROJECT_PICK"
                self.avoidance_streak = 0
                self.refusal_streak = 0
                proj_ui, proj_dir = self.start_or_resume_project(raw)
                if proj_dir:
                    return {"kind": self.last_kid_kind, "ui": proj_ui, "directive": proj_dir}

            self.last_kid_kind = "PROJECT_PICK"
            self.phase = "BUILDING"
            self.active_mechanic = raw
            self.avoidance_streak = 0
            self.refusal_streak = 0
            ui_actions.append({"type": "goal", "text": self.goal_badge()})
            if "game" in norm or "mini-game" in norm:
                directive = (
                    f"{self.name} chose '{raw}'. Call build_activity NOW with a concrete spec where EVERY round requires "
                    "typing or repairing a complete sentence, AND put a 2-kernel Sentence Combining warm-up card on screen while it builds."
                )
            else:
                scaf = generate_combine_scaffold(self.rec, self.active_story, "", self.rung)
                card_txt = (
                    f"Option A — Combine these two lines with {_fmt_conns(scaf['connectors'])}:\n"
                    f"  1. {scaf['kernel_1']}\n  2. {scaf['kernel_2']}\n\n"
                    "Option B — Write your own complete sentence (Who + Does What + Capital & .)"
                )
                ui_actions.append({"type": "item", "item": {"id": "forge", "kind": "card", "title": f"{raw} · Step 1 of {self.goal_target}", "text": card_txt}})
                ui_actions.append({"type": "input", "mode": "type", "prompt": "Type Sentence 1 (combine Option A, or write your own complete sentence)."})
                self.ui_locked_this_turn.update({"show_card", "ask_input"})
                directive = f"{self.name} picked '{raw}'. Call comic_new(panels='3') and invite combining Option A or writing their own complete first sentence."
            return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": directive}

        # ---------------- 2B. CUSTOM CODEX TOPIC SUBMISSION ----------------
        if self.awaiting_codex_topic and self.project and self.project.get("kind") == "epic_codex" and raw:
            self.awaiting_codex_topic = False
            self.last_kid_kind = "PROJECT_PICK"
            self.draw_unlocked = False
            ui_actions, directive = self._prompt_codex_step(ui_actions, new_entry=True, custom_topic=raw)
            return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": directive}

        # ---------------- 3. TURN-1 GREETING ----------------
        if idx == 0 and norm in GREETINGS:
            self.last_kid_kind = "GREETING"
            self.phase = "BUILDING"
            self.prev_norm_text = norm
            opts = self._opening_options(opening_ideas)
            ui_actions.append({"type": "goal", "text": self.goal_badge()})
            ui_actions.append({"type": "item", "item": {"id": "open_choices", "kind": "choices", "prompt": "", "options": opts}})
            ui_actions.append({"type": "input", "mode": "type", "prompt": "Pick one above, or type one complete sentence to jump in."})
            self.ui_locked_this_turn.update({"show_choices", "show_card", "ask_input"})
            directive = (
                f"First turn! {self.name} said '{raw}'. Clean project pills are on screen. Do NOT call draw or show_card. "
                "In at most TWO short, plain sentences: introduce yourself honestly as Gemini (an AI tutor made by Google) and invite picking a project or typing one complete sentence."
            )
            return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": directive}

        # ---------------- 3B. MID-SESSION META / STATUS CHECK ("hello?", "are you there?", "help") ----------------
        if idx > 0 and any(re.search(p, norm) for p in META_PATTERNS):
            self.last_kid_kind = "META_CHECK"
            self.draw_unlocked = False
            ui_actions.append({"type": "goal", "text": self.goal_badge()})
            ui_actions.append(
                {
                    "type": "input",
                    "mode": "type",
                    "prompt": "Right here! Finish your complete sentence in the box (or tap a choice above) and hit Enter.",
                    "prefill": self.engaged_draft,
                }
            )
            self.ui_locked_this_turn.add("ask_input")
            return {
                "kind": self.last_kid_kind,
                "ui": ui_actions,
                "directive": (
                    f"{self.name} sent a quick check-in ('{raw}'). Do NOT treat '{raw}' as part of their story and do NOT merge it into their sentence! "
                    "In ONE short plain sentence, confirm you're right here and invite finishing the current step on screen."
                ),
            }

        # ---------------- 3B-FIX. SINGLE-WORD / PHRASE / PUNCTUATION FIX RECOVERY (e.g. typing "stinky", "got", "a stinky cat", or "He") ----------------
        sp_active = self.spell_pick
        last_req_fix = self.coach_session.get("last_request") or {}
        prev_sent_fix = str((sp_active or {}).get("sentence") or last_req_fix.get("sentence") or "").strip()
        if prev_sent_fix and how in ("typed", "handwritten") and self.phase not in ("INLINE_WORD_HELP", "WORD_STUDY"):
            lfoc = "verb_ending" if (sp_active and sp_active.get("pick_kind") == "grammar") else ("spelling" if sp_active else last_req_fix.get("focus"))
            fword_fix = str((sp_active or {}).get("wrote") or last_req_fix.get("focus_word") or "").strip()
            prev_words_fix = _words(prev_sent_fix)
            if lfoc == "capital" and len(wlist) == 1 and raw[:1].isupper() and prev_words_fix and wlist[0].lower() == prev_words_fix[0].lower():
                raw = re.sub(rf"^\s*{re.escape(prev_words_fix[0])}\b", wlist[0], prev_sent_fix, count=1, flags=re.I)
                norm = _norm(raw)
                wlist = _words(raw)
                self.last_kid_text = raw
                self.coach_session["last_request"] = None
            elif lfoc == "end_mark" and raw in {".", "!", "?"}:
                raw = prev_sent_fix.rstrip(".!? ") + raw
                norm = _norm(raw)
                wlist = _words(raw)
                self.last_kid_text = raw
                self.coach_session["last_request"] = None
            elif lfoc in ("spelling", "verb_ending") and 1 <= len(wlist) <= 3 and fword_fix and norm not in AVOIDANCE_WORDS and len(wlist) < len(prev_words_fix):
                raw = _splice_word_into_sentence(prev_sent_fix, fword_fix, raw)
                norm = _norm(raw)
                wlist = _words(raw)
                self.last_kid_text = raw
                # Only clear last_request if the word actually changed to a valid/clean form; if he typed a wrong retry ('fasse'), keep last_request so retry escalation fires!
                valid_l = set((sp_active or {}).get("valid_options") or ([str(last_req_fix.get("focus_correct") or "").lower()] if last_req_fix.get("focus_correct") else []))
                if not valid_l or raw != prev_sent_fix and any(v and v in norm for v in valid_l):
                    self.coach_session["last_request"] = None

        # ---------------- 3C. DISENGAGEMENT -> ADAPTIVE COACH (falls back to the legacy rules below) ----------------
        is_refusal = any(re.search(p, norm) for p in REFUSAL_PATTERNS)
        is_avoid = (
            norm in AVOIDANCE_WORDS
            or bool(norm and norm == self.prev_norm_text and len(wlist) <= 2)
            or (len(wlist) <= 1 and (norm in AVOIDANCE_WORDS or not chk or all(s.get("issue") != "none" for s in (chk.get("sentences") or []))))
            or bool(re.search(r"\b(can we just|just draw|its fine|it's fine)\b", norm))
        )
        first_turn_single_word = idx == 0 and len(wlist) == 1 and norm not in AVOIDANCE_WORDS and not is_refusal
        if self.coach_enabled and (is_refusal or is_avoid) and not first_turn_single_word and how in ("typed", "handwritten", "spoken"):
            sig = dict(self.turn_signals or {})
            self.turn_signals = {}
            sig["minutes"] = round((time.time() - self.coach_session["started"]) / 60, 1)
            last_req = self.coach_session.get("last_request") or {}
            pending = (last_req.get("sentence") or self.engaged_draft or "").strip()
            with self._coach_lock:
                d = coach.decide_disengaged(
                    self.rec,
                    self.coach_session,
                    raw,
                    how,
                    sig,
                    self._coach_context(),
                    self.spine_summary() or "\n".join(self.active_story[-6:]),
                    bool(self.project),
                    pending=pending,
                    last_focus=str(last_req.get("focus") or ""),
                )
                if d and not self.test_mode:
                    save_learner(self.rec)
            if d and d["move"] == "draw_now" and pending:
                # The coach chose to honor "just draw it": accept his pending draft as-is and run the normal accept flow.
                pending_chk = last_req.get("chk") or thinking.check_writing(pending)
                if self.phase == "INLINE_WORD_HELP":
                    self.phase = self.phase_before_inline_help or "BUILDING"
                    self.word_target = None
                self.engaged_draft = ""
                self._force_accept = {
                    "accept": True,
                    "focus": "none",
                    "scaffold": "none",
                    "next_scaffold": self.coach_session.get("next_scaffold", "starter_chips"),
                    "kid_words": d.get("kid_words", ""),
                    "rationale": d.get("rationale", ""),
                    "guardrail": "kid_asked_to_draw",
                    "today_state": d.get("today_state"),
                    "latency_s": d.get("latency_s"),
                }
                self.prev_norm_text = ""
                plan = self.classify_and_advance(pending, "typed", pending_chk)
                plan.setdefault("repaired_text", pending)
                self.last_coach = {**d, "accept": True, "focus": "disengaged", "scaffold": "draw_now"}
                return plan
            if d and d["move"] == "quick_deal" and pending:
                self.coach_session["deal_pending"] = pending
                self.last_coach = {**d, "accept": False, "focus": "disengaged", "scaffold": "quick_deal"}
                self.last_kid_kind = "DISENGAGED"
                self.prev_norm_text = norm
                ui_actions.append({"type": "input", "mode": "type", "prompt": d["input_prompt"], "prefill": pending})
                self.ui_locked_this_turn.add("ask_input")
                return {
                    "kind": self.last_kid_kind,
                    "ui": ui_actions,
                    "directive": f'He asked to just draw it. Offer the deal in your own voice (1 short sentence, no nagging): "{d["kid_words"]}"',
                }
            if d:
                self.last_coach = {**d, "accept": False, "focus": "disengaged", "scaffold": d["move"]}
                self.last_kid_kind = "DISENGAGED"
                self.prev_norm_text = norm
                self.draw_unlocked = False
                if self.phase == "OPENING":
                    self.phase = "BUILDING"
                ui_actions.append({"type": "goal", "text": self.goal_badge()})
                if d["chips"] and d["move"] in ("starters", "twist", "voice_offer", "switch_offer", "wrap_offer"):
                    self.coach_session["offered_chips"] = d["chips"]
                    ui_actions.append({"type": "item", "item": {"id": "starters", "kind": "starters", "options": d["chips"]}})
                if d["options"]:
                    ui_actions.append({"type": "item", "item": {"id": "unstick", "kind": "choices", "prompt": "", "options": d["options"]}})
                if d["move"] == "voice_offer":
                    self.active_mic_request = {"purpose": "story", "sentence": ""}
                    ui_actions.append({"type": "tutor_mic", "action": "on", "purpose": "story", "target_word": "", "sentence": "", "prompt": "Tell me out loud what happens next"})
                inp: dict[str, Any] = {"type": "input", "mode": "type", "prompt": d["input_prompt"]}
                if d["move"] == "partial_frame":
                    inp["prefill"] = d["prefill"].rstrip() + " "
                    self.engaged_draft = d["prefill"]
                ui_actions.append(inp)
                self.ui_locked_this_turn.update({"ask_input", "show_choices", "show_card"})
                return {
                    "kind": self.last_kid_kind,
                    "ui": ui_actions,
                    "directive": (
                        f'{self.name} sent "{raw}". Say this in your own natural voice (1–2 short sentences, same meaning, no nagging, '
                        f'no school words, no drawing): "{d["kid_words"]}"'
                    ),
                }

        # ---------------- 4. EXPLICIT REFUSAL ----------------
        if any(re.search(p, norm) for p in REFUSAL_PATTERNS):
            self.last_kid_kind = "REFUSAL"
            self.refusal_streak += 1
            self.avoidance_streak = 0
            self.prev_norm_text = norm
            self.draw_unlocked = False
            if self.refusal_streak == 1:
                self.goal_target = 2
                scaf = generate_combine_scaffold(self.rec, self.active_story, "", "B3.1_compound", spine_context=self.spine_summary())
                ui_actions.append({"type": "goal", "text": self.goal_badge()})
                ui_actions.append(
                    {
                        "type": "item",
                        "item": {
                            "id": "pivot_choices",
                            "kind": "choices",
                            "prompt": "Switch format or energy mode:",
                            "options": ["Start a Full Comic Book (PDF)", "Build a playable mini-game", "Voice-First 2-Sentence Sprint"],
                        },
                    }
                )
                ui_actions.append(
                    {
                        "type": "item",
                        "item": {
                            "id": "forge",
                            "kind": "card",
                            "title": "Low-Friction 2-Sentence Option (Type or Tap Mic to Speak)",
                            "text": f"Combine into 1 sentence using 'but' or 'when' (or speak your own idea with the Mic):\n  1. {scaf['kernel_1']}\n  2. {scaf['kernel_2']}",
                        },
                    }
                )
                ui_actions.append({"type": "input", "mode": "type", "prompt": "Tap a different format, tap the Mic to speak a draft, or type 1 complete sentence."})
                self.ui_locked_this_turn.update({"show_choices", "show_card", "ask_input"})
                return {
                    "kind": self.last_kid_kind,
                    "ui": ui_actions,
                    "directive": (
                        f"{self.name} pushed back ('{raw}'). Respect 'no' immediately—zero nagging or pep talks. "
                        "Say ONE short plain line ('Fair enough, scrapping that.') and offer starting a PDF Comic Book, coding a live mini-game, or speaking a quick 2-sentence draft via the mic."
                    ),
                }
            ui_actions.append({"type": "item", "item": {"id": "wrap_choices", "kind": "choices", "prompt": "Your call:", "options": ["Build a custom mini-game", "Pause here for today"]}})
            self.ui_locked_this_turn.add("show_choices")
            return {
                "kind": self.last_kid_kind,
                "ui": ui_actions,
                "directive": f"Second refusal ('{raw}'). In ONE plain, respectful sentence, offer coding a custom game around any topic named in one sentence, or pausing cleanly for today.",
            }

        # ---------------- 5. TURN-1 TOPIC NAMING ----------------
        if idx == 0 and ("comic" in norm or "graphic novel" in norm) and len(wlist) <= 4:
            self.last_kid_kind = "PROJECT_PICK"
            proj_ui, proj_dir = self.start_or_resume_project("Start a Full Comic Book (Save & PDF)")
            return {"kind": self.last_kid_kind, "ui": proj_ui, "directive": proj_dir}

        if idx == 0 and len(wlist) == 1 and norm not in AVOIDANCE_WORDS and raw.lower() not in {"cow", "cat", "dog", "bear"}:
            self.last_kid_kind = "PROJECT_PICK"
            self.phase = "BUILDING"
            self.prev_norm_text = norm
            self.engaged_draft = raw
            scaf = generate_combine_scaffold(self.rec, [], raw, self.rung)
            ui_actions.append({"type": "goal", "text": self.goal_badge()})
            ui_actions.append({"type": "item", "item": {"id": "open_choices", "kind": "choices", "prompt": f"Scale for '{raw.title()}':", "options": ["Start a Full Comic Book (Save & PDF)", "Quick 3-Panel Strip (10 min)"]}})
            ui_actions.append({"type": "item", "item": {"id": "forge", "kind": "card", "title": f"{raw.title()} · Sentence 1", "text": f"Combine with {_fmt_conns(scaf['connectors'])}, OR write your own complete sentence about {raw}:\n  1. {scaf['kernel_1']}\n  2. {scaf['kernel_2']}"}})
            ui_actions.append({"type": "input", "mode": "type", "prompt": "Tap 'Start a Full Comic Book' for a saved PDF book, or type Sentence 1 right now."})
            self.ui_locked_this_turn.update({"show_choices", "show_card", "ask_input"})
            return {
                "kind": self.last_kid_kind,
                "ui": ui_actions,
                "directive": f"{self.name} named '{raw}'. Do NOT ask wh- interview questions. Invite tapping 'Start a Full Comic Book' or typing one complete sentence right now.",
            }

        # ---------------- 6. TASK AVOIDANCE / ESCAPE ----------------
        is_repeated_short = bool(norm and norm == self.prev_norm_text and len(wlist) <= 2)
        is_bare_one_word = len(wlist) <= 1 and (
            norm in AVOIDANCE_WORDS or not chk or all(s.get("issue") != "none" for s in (chk.get("sentences") or []))
        )
        if norm in AVOIDANCE_WORDS or is_repeated_short or is_bare_one_word:
            self.last_kid_kind = "AVOIDANCE_ESCAPE"
            self.avoidance_streak += 1
            if self.phase == "OPENING":
                self.phase = "BUILDING"
            self.prev_norm_text = norm
            self.draw_unlocked = False

            scaf = generate_combine_scaffold(self.rec, self.active_story, self.engaged_draft, self.rung, spine_context=self.spine_summary())
            ui_actions.append({"type": "goal", "text": self.goal_badge()})

            if self.avoidance_streak == 1:
                card_title = "Story Beat Helper — Combine into 1 Complete Sentence" if (self.active_story or self.project) else f"Sentence Forge ({self.goal_done + 1} of {self.goal_target}) — Full Sentences Only"
                card_txt = (
                    f"Combine these two lines into ONE complete sentence using {_fmt_conns(scaf['connectors'])}\n"
                    f"(or write/speak your own complete sentence):\n"
                    f"  1. {scaf['kernel_1']}\n  2. {scaf['kernel_2']}"
                )
                ui_actions.append({"type": "item", "item": {"id": "forge", "kind": "card", "title": card_title, "text": card_txt}})
                ui_actions.append({"type": "input", "mode": "type", "prompt": scaf["ask_prompt"], "prefill": ""})
                self.ui_locked_this_turn.update({"show_card", "ask_input"})
                return {
                    "kind": self.last_kid_kind,
                    "ui": ui_actions,
                    "directive": (
                        f"DISENGAGEMENT / MINIMAL INPUT ('{raw}'): HARD ESCAPE EXTINCTION. "
                        "Do NOT draw anything, do NOT praise a 1-word answer, and NEVER invent babyish animal trivia. "
                        f"In ONE plain sentence, state that one-word/idk inputs don't run the scene, and invite combining the two lines on screen with {_fmt_conns(scaf['connectors'])}."
                    ),
                }
            if self.avoidance_streak == 2:
                self.goal_target = max(self.goal_done + 1, 2)
                starter = scaf["kernel_1"].rstrip(".!?") + " when "
                ui_actions.append({"type": "item", "item": {"id": "forge", "kind": "card", "title": "Half-Built Clause — Finish & Punctuate It", "text": f"Finish in the box (or tap Mic to dictate):\n  \"{starter}________.\"\n  (Idea: {scaf['kernel_2']})"}})
                ui_actions.append({"type": "item", "item": {"id": "avoid_choices", "kind": "choices", "prompt": "Or switch format:", "options": ["Build a playable mini-game instead"]}})
                ui_actions.append({"type": "input", "mode": "type", "prompt": "Finish the pre-filled sentence in the box and end with a period.", "prefill": starter})
                self.ui_locked_this_turn.update({"show_card", "show_choices", "ask_input"})
                return {
                    "kind": self.last_kid_kind,
                    "ui": ui_actions,
                    "directive": f"SECOND MINIMAL INPUT ('{raw}'). '{starter}' is pre-filled in the box. Invite finishing those 3–5 words + period or tapping to switch to a live game.",
                }
            starter = scaf["kernel_1"].rstrip(".!?") + " so "
            ui_actions.append({"type": "item", "item": {"id": "avoid_choices", "kind": "choices", "prompt": "Pick one:", "options": ["Build a custom mini-game", "Pause here for today"]}})
            ui_actions.append({"type": "input", "mode": "type", "prompt": "Finish this 1 sentence to unlock the scene, or pick an option above.", "prefill": starter})
            self.ui_locked_this_turn.update({"show_choices", "ask_input"})
            return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": f"REPEATED AVOIDANCE ('{raw}'). Offer finishing the 1 started sentence, coding a custom game, or pausing cleanly."}

        # Clean up any active spell_pick card if the student edited the sentence directly in the box
        if self.spell_pick:
            self.spell_pick = None
            ui_actions.append({"type": "remove", "id": "spell_pick"})
            ui_actions.append({"type": "remove", "id": "spell_why"})

        # ---------------- 7. GENUINE WRITING ATTEMPTS (Syntactic, Conventions & Mastery-Tier Verification) ----------------
        if self.phase == "OPENING":
            self.phase = "BUILDING"
        self.prev_norm_text = norm
        self.avoidance_streak = 0
        self.refusal_streak = 0

        # ---- ADAPTIVE AI COACH decides accept vs. one focused fix (falls back to the legacy rules if unavailable)
        coach_accepted = False
        coach_info: dict[str, Any] | None = None
        if self.coach_enabled and how in ("typed", "handwritten"):
            verdict, payload, chk = self._coach_turn(raw, how, chk)
            if verdict == "fix":
                payload["epoch"] = epoch
                return payload
            if verdict == "accept":
                coach_accepted = True
                coach_info = {k: payload.get(k) for k in ("accept", "focus", "scaffold", "rationale", "guardrail", "today_state", "latency_s", "deferred")}
                # Record any spelling words he fixed after an earlier request; leave the rest for the editing pass.
                if self.pending_spell_targets and not self.test_mode:
                    for t in self.pending_spell_targets:
                        if len(t.get("meant", "")) >= 3 and not re.search(rf"\b{re.escape(t['wrote'].lower())}\b", raw.lower()):
                            spelling_srs.record_retrieval_result(self.rec, t["meant"], correct_first_try=False)
                    save_learner(self.rec)
                self.pending_spell_targets = []
                self.pending_spell_sentence = ""
                base_sents = (chk or {}).get("sentences") or [{"text": raw}]
                chk = {
                    **(chk or {}),
                    "sentences": [{**s, "issue": "none", "complete": True, "capital_ok": True, "end_ok": True} for s in base_sents],
                    "misspellings": [],
                    "grammar_fixes": [],
                    "features": {**((chk or {}).get("features") or {}), "dialogue_punct_ok": True},
                }
                self.tier_nudged_this_item = True  # Coach owns upgrade asks; skip legacy tier gates

        sents = (chk or {}).get("sentences") or []
        feats = (chk or {}).get("features") or {}
        has_run_on = any(s.get("issue") == "run_on" for s in sents)
        has_fragment = any(s.get("issue") in ("missing_subject", "missing_verb", "incomplete_thought", "not_a_sentence_attempt") for s in sents) or not sents
        missing_cap = any(s.get("capital_ok") is False for s in sents)
        missing_end = any(s.get("end_ok") is False for s in sents)

        # 7A. ENGAGED RUN-ON
        if has_run_on:
            self.last_kid_kind = "ENGAGED_RUN_ON"
            self.draw_unlocked = False
            self.hint_step = min(3, self.hint_step + 1)
            self.had_revision = True
            self.engaged_draft = raw
            fixed_prefill = raw[:1].upper() + raw[1:] if raw else ""
            ui_actions.append(
                {
                    "type": "item",
                    "item": {
                        "id": "forge",
                        "kind": "card",
                        "title": "Boundary Overload — Split or Link Causally",
                        "text": f"Your draft:\n  \"{raw}\"\n\nFix: Replace 'and then' with a period + capital letter to make crisp separate sentences, OR link cause-and-effect cleanly with 'when', 'because', or 'so'.",
                    },
                }
            )
            ui_actions.append({"type": "input", "mode": "type", "prompt": "Edit your draft right in the box: replace 'and then' with periods (or 'when'/'because'/'so').", "prefill": fixed_prefill})
            self.ui_locked_this_turn.update({"show_card", "ask_input"})
            return {
                "kind": self.last_kid_kind,
                "ui": ui_actions,
                "directive": f"ENGAGED RUN-ON ('{raw}'). Keep 100% of their idea! Draft is pre-filled in the box—ask in 1–2 plain sentences to split 'and then' with a period + capital or use 'when'/'because'.",
            }

        # 7B. ENGAGED FRAGMENT
        if has_fragment:
            self.last_kid_kind = "ENGAGED_FRAGMENT"
            self.draw_unlocked = False
            self.hint_step = min(3, self.hint_step + 1)
            self.had_revision = True
            self.engaged_draft = self._merge_fragments(self.engaged_draft, raw)
            issues = [s.get("issue") for s in sents]

            if "missing_verb" in issues:
                gap_explain = f"You have the 'who/what' ({self.engaged_draft}), now add what it DOES"
                frame = f"{self.engaged_draft[:1].upper() + self.engaged_draft[1:].rstrip('.!?, ')} "
                verb_chips = ["stomps", "ambushes", "blasts", "shatters"]
            elif "missing_subject" in issues:
                gap_explain = f"You have the action ({raw}), now add WHO or WHAT is doing it at the front"
                frame = f"The ________ {raw.lstrip().rstrip('.!?')}."
                verb_chips = ["The hero", "The iron golem", "A giant boss"]
            else:
                gap_explain = f"You set up '{self.engaged_draft}', now finish what happens (who does what)"
                clean_d = self.engaged_draft[:1].upper() + self.engaged_draft[1:].rstrip(".!?, ")
                frame = f"{clean_d}, " if re.match(r"^(in|on|at|under|inside|when|after|before|if|because|although|unlike)\b", clean_d.lower()) else f"{clean_d} "
                verb_chips = ["launches", "explodes", "guards", "crashes"]

            if self.hint_step == 1:
                if "________" in frame:
                    ui_actions.append({"type": "input", "mode": "type", "prompt": f"{gap_explain} (with a capital and period) to lock it in.", "prefill": " " + raw.lstrip(), "cursor_pos": 0})
                else:
                    ui_actions.append({"type": "input", "mode": "type", "prompt": f"{gap_explain} (with a capital and period) to lock it in.", "prefill": frame})
                self.ui_locked_this_turn.add("ask_input")
                return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": f"ENGAGED FRAGMENT (Hint 1/3): '{raw}'. Keep their idea! Words are pre-filled in box. Say plainly: {gap_explain} so it's a complete sentence."}
            if self.hint_step == 2:
                ui_actions.append({"type": "item", "item": {"id": "forge", "kind": "card", "title": "Finish Your Sentence Frame", "text": f"Build on your exact words:\n  \"{frame}________.\""}})
                ui_actions.append({"type": "input", "mode": "type", "prompt": "Finish your pre-filled sentence in the box and end with a period.", "prefill": frame.replace("________ ", "")})
                self.ui_locked_this_turn.update({"show_card", "ask_input"})
                return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": "ENGAGED FRAGMENT (Hint 2/3): Point briefly to the frame built from their words and ask for the missing action + period."}
            ui_actions.append({"type": "item", "item": {"id": "forge", "kind": "card", "title": "Pick an Action Word & Finish", "text": f"Your start:\n  \"{frame}________.\""}})
            ui_actions.append({"type": "item", "item": {"id": "verb_bank", "kind": "choices", "prompt": "Tap a word to drop into your box, then finish the sentence:", "options": verb_chips[:3]}})
            ui_actions.append({"type": "input", "mode": "type", "prompt": "Finish the complete sentence in the box (capital at start, period at end).", "prefill": frame.replace("________ ", "")})
            self.ui_locked_this_turn.update({"show_card", "show_choices", "ask_input"})
            return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": f"ENGAGED FRAGMENT (Hint 3/3): Word chips ({', '.join(verb_chips[:3])}) on screen—invite finishing the complete sentence."}

        # 7C. CONVENTION, GRAMMAR INFLECTION (B3.2), & 2-STAGE INLINE SPELLING CHECK
        #   - Attempt 1: Name the EXACT word (+ morphological/verb-ending clue; prefill sentence with that word highlighted)!
        #   - Attempt 2 (still misspelled or uninflected on retry): START ALL THE HELP (Word Card + prefill + word highlighted)!
        dialogue_punct_bad = bool(feats.get("has_dialogue") and feats.get("dialogue_punct_ok") is False)
        ms = (chk or {}).get("misspellings") or []
        gf = (chk or {}).get("grammar_fixes") or []
        word_issues: list[dict[str, Any]] = list(ms) + [
            {
                "wrote": g["wrote"],
                "meant": (g.get("options") or [""])[0],
                "alt_words": g.get("options") or [],
                "rule": g.get("rule") or "",
                "is_grammar": True,
            }
            for g in gf
            if g.get("wrote") and g.get("options")
        ]

        if not word_issues and self.pending_spell_targets:
            if not self.test_mode:
                for fixed_m in self.pending_spell_targets:
                    if len(fixed_m.get("meant", "")) >= 3:
                        spelling_srs.record_retrieval_result(self.rec, fixed_m["meant"], correct_first_try=True)
                save_learner(self.rec)
            self.pending_spell_targets = []
            self.pending_spell_sentence = ""

        if word_issues:
            prev_w = {w.lower() for w in _words(self.pending_spell_sentence)}
            cur_w = {w.lower() for w in wlist}
            same_draft = bool(
                self.pending_spell_targets
                and prev_w
                and cur_w
                and len(prev_w & cur_w) / max(1, min(len(prev_w), len(cur_w))) >= 0.5
            )
            if same_draft:
                # Attempt 2 still had a spelling or verb-ending issue -> START ALL THE HELP right now!
                ms_sorted = sorted(word_issues, key=lambda x: (len(x.get("meant", "").replace(" ", "")) >= 4, len(x.get("meant", ""))), reverse=True)
                m0 = ms_sorted[0]
                wrote, meant = m0["wrote"], m0["meant"]
                alt_opts = m0.get("alt_words") or [meant]
                tidy_raw = raw[:1].upper() + raw[1:] if (raw and raw[0].isalpha()) else raw
                if tidy_raw and not re.search(r'[.!?]["\')\]]*$', tidy_raw):
                    tidy_raw += "."
                self.pending_spell_sentence = tidy_raw
                self.pending_spell_targets = word_issues
                if " " in meant.strip():
                    ws_card: dict[str, Any] = {
                        "word": meant,
                        "alt_words": alt_opts,
                        "wrote": wrote,
                        "parts": " + ".join(meant.strip().split()),
                        "note": m0.get("rule") or f"'{meant}' is written as two separate words ('{meant}').",
                    }
                elif len(meant) <= 2:
                    ws_card = {
                        "word": meant,
                        "alt_words": alt_opts,
                        "wrote": wrote,
                        "parts": meant,
                        "note": m0.get("rule") or f"In '{_phrase_around_word(raw, wrote)}', use '{meant}' rather than '{wrote}'.",
                    }
                else:
                    ws_card = dict(thinking.analyze_word_study(wrote, meant))
                    ws_card["alt_words"] = alt_opts
                    if m0.get("rule"):
                        ws_card["note"] = m0["rule"]
                self.phase_before_inline_help = self.phase
                self.phase = "INLINE_WORD_HELP"
                self.word_target = ws_card
                self.inline_word_help_tries = 0
                self.had_revision = True
                self.last_kid_kind = "INLINE_WORD_HELP"
                self.draw_unlocked = False
                ui_actions.append(
                    {
                        "type": "item",
                        "item": {
                            "id": "word",
                            "kind": "word",
                            "word": ws_card["word"],
                            "parts": [p.strip() for p in ws_card["parts"].split("+")],
                            "note": ws_card["note"],
                        },
                    }
                )
                ui_actions.append(
                    {
                        "type": "input",
                        "mode": "type",
                        "prompt": f"Study '{ws_card['parts']}' above (covers when you type), then fix '{wrote}' right in your sentence below and hit Enter!",
                        "prefill": tidy_raw,
                        "select_word": wrote,
                    }
                )
                self.ui_locked_this_turn.update({"show_word", "show_card", "ask_input"})
                return {
                    "kind": self.last_kid_kind,
                    "ui": ui_actions,
                    "directive": (
                        f"They tried fixing '{wrote}' and still needed help, so the Word Card ('{ws_card['parts']}' — {ws_card['note']}) is on screen and their sentence is pre-filled in the box with '{wrote}' highlighted. "
                        f"Do NOT say 'still wrong'. Explain '{ws_card['parts']}' in ONE warm, plain sentence and invite replacing '{wrote}' in their box and hitting Enter."
                    ),
                }

        if missing_cap or missing_end or dialogue_punct_bad or ms or gf:
            self.last_kid_kind = "CONVENTION_ONLY"
            self.draw_unlocked = False
            self.hint_step = min(3, self.hint_step + 1)
            self.had_revision = True
            tier = self.current_tier()
            needed = []
            if missing_cap:
                needed.append("add a capital letter at the start")
            if missing_end:
                needed.append("add end punctuation (. ! or ?)")
            if dialogue_punct_bad:
                needed.append("fix dialogue punctuation (quotes, capital inside quote, and comma/!/? inside closing quote)")
            if word_issues:
                self.pending_spell_sentence = raw
                self.pending_spell_targets = word_issues
            if ms:
                spell_ptrs = [_specific_spelling_pointer(raw, m["wrote"], m["meant"], tier) for m in ms[:4]]
                needed.append("check " + (", ".join(spell_ptrs[:-1]) + f", and {spell_ptrs[-1]}" if len(spell_ptrs) > 1 else spell_ptrs[0]))
            if gf:
                gf_ptrs = []
                for g in gf[:2]:
                    opts_s = " or ".join(f"'{o}'" for o in (g.get("options") or [])[:2])
                    gf_ptrs.append(f"'{g['wrote']}' (change to {opts_s} so the verb/noun form fits)")
                needed.append("update " + (" and ".join(gf_ptrs)))
            need_str = ", and ".join(needed) if len(needed) <= 2 else (", ".join(needed[:-1]) + f", and {needed[-1]}")
            sel_word = word_issues[0]["wrote"] if (word_issues and not missing_end and not missing_cap) else ""
            ui_actions.append(
                {
                    "type": "input",
                    "mode": "type",
                    "prompt": f"Almost unlocks the art! {need_str[:1].upper() + need_str[1:]} right in the box and hit Enter.",
                    "prefill": raw,
                    "select_word": sel_word,
                }
            )
            self.ui_locked_this_turn.update({"show_card", "ask_input"})
            named_words = ", ".join(f"'{w['wrote']}'" for w in word_issues[:4])
            spell_rule_for_llm = (
                f" You MUST name the exact word(s) {named_words} aloud—NEVER silently fix {named_words} yourself or say vague 'fix the error' without naming {named_words}!"
                if word_issues
                else ""
            )
            return {
                "kind": self.last_kid_kind,
                "ui": ui_actions,
                "directive": f"CONVENTION / GRAMMAR / SPELLING POLISH on '{raw}': briefly react to their story idea, then ask concisely to {need_str} in the pre-filled box and hit Enter.{spell_rule_for_llm}",
            }

        # ---------------- 7D. ENFORCED GENRE & MASTERY-TIER GATES (Max 1 Power-Up Pass Per Item!) ----------------
        has_conn = bool(feats.get("has_connector"))
        has_dial = bool(feats.get("has_dialogue"))
        weak_words = feats.get("weak_words") or []

        # Gate 1: Graphic Novel Story Spine Causality Check (Act II & Act III must link causally!)
        if self.project and self.project.get("stage") in ("spine_middle", "spine_end") and not has_conn and not self.tier_nudged_this_item:
            self.tier_nudged_this_item = True
            self.had_revision = True
            self.last_kid_kind = "TIER_UPGRADE"
            self.draw_unlocked = False
            st = self.project["stage"]
            req_c = "'But', 'When', or 'Because'" if st == "spine_middle" else "'So', 'Therefore', or 'Finally'"
            pref = ("When " if st == "spine_middle" else "So ") + raw[:1].lower() + raw[1:]
            ui_actions.append({"type": "input", "mode": "type", "prompt": f"Connect this Act causally using {req_c} right in the box, then hit Enter!", "prefill": pref})
            self.ui_locked_this_turn.add("ask_input")
            return {
                "kind": self.last_kid_kind,
                "ui": ui_actions,
                "directive": f"Good event ('{raw}'), now enforce the Story Spine causal rule: ask them to link it to the previous Act using {req_c} (pre-filled in box).",
            }

        # Gate 2: Persuasive Pitch TREE Causal/Counter-Argument Checks (Page 2 = because/since; Page 3 = although/even though)
        if self.project and self.project.get("kind") == "medium_pitch" and not self.tier_nudged_this_item:
            if self.tree_step == 1 and not re.search(r"\b(because|since|so)\b", raw, re.I):
                self.tier_nudged_this_item = True
                self.had_revision = True
                self.last_kid_kind = "TIER_UPGRADE"
                self.draw_unlocked = False
                ui_actions.append({"type": "input", "mode": "type", "prompt": "Power up Page 2: add 'because' + your concrete proof right at the end!", "prefill": raw.rstrip(".!?") + " because "})
                self.ui_locked_this_turn.add("ask_input")
                return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": "Solid start for Page 2—ask them to add 'because' + concrete proof in the pre-filled box."}
            if self.tree_step == 2 and not re.search(r"\b(although|even though|though|while)\b", raw, re.I):
                self.tier_nudged_this_item = True
                self.had_revision = True
                self.last_kid_kind = "TIER_UPGRADE"
                self.draw_unlocked = False
                ui_actions.append({"type": "input", "mode": "type", "prompt": f"Start Page 3 with 'Although {self.parent_title} might worry...' to beat the objection!", "prefill": f"Although {raw[:1].lower() + raw[1:]}"})
                self.ui_locked_this_turn.add("ask_input")
                return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": "Ask them to frame Page 3 with 'Although' or 'Even though' (pre-filled in box) to answer the counter-argument."}

        # Gate 3: Mastery Tier Escalation Gates on Graphic Novel Panels (Tier 2 causal, Tier 3 dialogue, Tier 4 vivid verb revision)
        if self.project and self.project.get("kind") == "epic_graphic_novel" and self.project.get("stage") == "drafting_panels" and not self.tier_nudged_this_item:
            next_pnum = projects.total_panels(self.project) + 1
            tier = self.current_tier()
            if tier >= 3 and next_pnum % 2 == 0 and not has_dial:
                self.tier_nudged_this_item = True
                self.had_revision = True
                self.last_kid_kind = "TIER_UPGRADE"
                self.draw_unlocked = False
                ui_actions.append(
                    {
                        "type": "input",
                        "mode": "type",
                        "prompt": 'Tier 3 Power-Up: Add what a character shouts in quotation marks (e.g. "Watch out!" yelled Max.) to unlock a speech bubble!',
                        "prefill": raw + ' "',
                    }
                )
                self.ui_locked_this_turn.add("ask_input")
                return {
                    "kind": self.last_kid_kind,
                    "ui": ui_actions,
                    "directive": f"Base action works ('{raw}')! For Tier 3 Dialogue Mastery, invite adding a quoted line of speech right in the pre-filled box so a comic speech bubble renders.",
                }
            if tier == 2 and next_pnum % 2 == 0 and not has_conn:
                self.tier_nudged_this_item = True
                self.had_revision = True
                self.last_kid_kind = "TIER_UPGRADE"
                self.draw_unlocked = False
                ui_actions.append({"type": "input", "mode": "type", "prompt": "Tier 2 Power-Up: Expand your sentence with 'because', 'when', or 'but' to show cause and effect!", "prefill": raw.rstrip(".!?") + " because "})
                self.ui_locked_this_turn.add("ask_input")
                return {
                    "kind": self.last_kid_kind,
                    "ui": ui_actions,
                    "directive": f"Base clause is solid ('{raw}')! Invite adding 'because', 'when', or 'but' in the pre-filled box to hit Tier 2 causal flow before rendering.",
                }
            if tier >= 4 and weak_words and not self.tier_nudged_this_item:
                self.tier_nudged_this_item = True
                self.had_revision = True
                self.last_kid_kind = "TIER_UPGRADE"
                self.draw_unlocked = False
                w0 = weak_words[0]
                ui_actions.append({"type": "input", "mode": "type", "prompt": f"Author's Craft Pass (D2.5): Swap '{w0}' in your box for a sharper, more vivid word, then hit Enter!", "prefill": raw})
                self.ui_locked_this_turn.add("ask_input")
                return {
                    "kind": self.last_kid_kind,
                    "ui": ui_actions,
                    "directive": f"Great structure ('{raw}')—run a quick Tier 4 Author's Revision pass: ask them to swap '{w0}' in the pre-filled box for a more vivid, specific word.",
                }

        # ---------------- 8. VERIFIED COMPLETE STEP! ----------------
        if self.hint_step == 0 and (coach_accepted or not self.tier_nudged_this_item) and not resolved_inline_word:
            self.first_try_streak += 1
        self.hint_step = 0
        self.tier_nudged_this_item = False
        self.engaged_draft = ""
        self.pending_spell_targets = []
        self.pending_spell_sentence = ""
        self.active_story.append(raw)

        def _finish(plan_dict: dict[str, Any]) -> dict[str, Any]:
            plan_dict["epoch"] = epoch
            if coach_info:
                plan_dict["coach"] = coach_info
                reaction = (self.last_coach or {}).get("kid_words") or ""
                if reaction:
                    plan_dict["directive"] = f'Open with a quick story reaction in this spirit (a few words, your own voice): "{reaction[:160]}". Then: ' + plan_dict["directive"]
            if resolved_repaired_text:
                plan_dict["repaired_text"] = resolved_repaired_text
                plan_dict["directive"] = f"Locked '{resolved_inline_word}' into your sentence ('{resolved_repaired_text}')! " + plan_dict["directive"]
            return plan_dict

        # CASE A: Advancing Graphic Novel Plot Board (Kickoff -> Big Finale -> Iterative Middle Twists!)
        if self.project and self.project.get("stage", "").startswith("spine_"):
            self.last_kid_kind = "SPINE_BEAT_COMPLETE"
            self.draw_unlocked = False
            st = self.project["stage"]
            sp = self.project.setdefault("spine", {})
            ui_actions.append({"type": "remove", "id": "spine_more_choices"})
            if st == "spine_beginning":
                sp["beginning"] = raw
                sp["beginning_status"] = "drawing"
                if self.project.get("title") in ("Untitled Graphic Novel", "Untitled Project", "") and not self.project.get("custom_titled"):
                    self.project["title"] = _infer_book_title(raw, self._suggested_title)
                    self._suggested_title = ""
                self.project["stage"] = "spine_end"
                projects.save_project(self.project, sandbox=self.test_mode)
                ui_actions.append({"type": "reward", "label": f"★ Cover & Kickoff Art Unlocked · “{self.project['title']}”"})
                ui_actions.append({"type": "item", "item": projects.project_ui_payload(self.project)})
                ui_actions.append({"type": "goal", "text": self.goal_badge()})
                if self.pause_for_art_check:
                    gate = self._enter_art_check_gate(ui_actions, "spine:beginning", "STORY_SPINE", "your Cover & Kickoff picture")
                    gate["spine_draw"] = {"beat": "beginning", "text": raw}
                    return _finish(gate)
                ui_actions, directive = self._prompt_spine_step(ui_actions, resumed=False)
                return _finish({
                    "kind": self.last_kid_kind,
                    "spine_draw": {"beat": "beginning", "text": raw},
                    "ui": ui_actions,
                    "directive": directive,
                })

            if st == "spine_end":
                sp["end"] = raw
                sp["end_status"] = "drawing"
                self.project["stage"] = "spine_middle"
                projects.save_project(self.project, sandbox=self.test_mode)
                ui_actions.append({"type": "reward", "label": "★ Big Finale Art Unlocked!"})
                ui_actions.append({"type": "item", "item": projects.project_ui_payload(self.project)})
                ui_actions.append({"type": "goal", "text": self.goal_badge()})
                if self.pause_for_art_check:
                    gate = self._enter_art_check_gate(ui_actions, "spine:end", "STORY_SPINE", "your Big Finale picture")
                    gate["spine_draw"] = {"beat": "end", "text": raw}
                    return _finish(gate)
                ui_actions, directive = self._prompt_spine_step(ui_actions, resumed=False)
                return _finish({
                    "kind": self.last_kid_kind,
                    "spine_draw": {"beat": "end", "text": raw},
                    "ui": ui_actions,
                    "directive": directive,
                })

            # st == "spine_middle": append this twist to middle_beats!
            mbeats = list(projects.middle_beats_list(sp))
            beat_idx = len(mbeats)
            mbeats.append({"text": raw, "image": None, "src": None, "status": "drawing"})
            sp["middle_beats"] = mbeats
            sp["middle"] = " ".join(b.get("text", "") for b in mbeats)
            projects.save_project(self.project, sandbox=self.test_mode)
            ui_actions.append({"type": "reward", "label": f"★ Middle Twist #{beat_idx + 1} Art Unlocked!"})
            ui_actions.append({"type": "item", "item": projects.project_ui_payload(self.project)})
            ui_actions.append({"type": "goal", "text": self.goal_badge()})
            if self.pause_for_art_check:
                gate = self._enter_art_check_gate(ui_actions, f"spine:middle_{beat_idx}", "STORY_SPINE", f"Middle Twist #{beat_idx + 1}")
                gate["spine_draw"] = {"beat": f"middle_{beat_idx}", "text": raw}
                return _finish(gate)
            ui_actions, directive = self._prompt_spine_step(ui_actions, resumed=False)
            return _finish({
                "kind": self.last_kid_kind,
                "spine_draw": {"beat": f"middle_{beat_idx}", "text": raw},
                "ui": ui_actions,
                "directive": directive,
            })

        # CASE B: Advancing 3-Source Reading-to-Write Codex (`epic_codex`) — Unlocks Field Sketch on Step 0 + Live Draft Progress!
        if self.project and self.project.get("kind") == "epic_codex":
            if self.codex_step == 0:
                self.had_inference = True
                self.last_kid_kind = "SPINE_BEAT_COMPLETE"
                self.draw_unlocked = False
                self.codex_step = 1
                self.project["codex_sketch_status"] = "drawing"
                self.project["codex_sketch_caption"] = raw
                self.project["codex_draft_sentences"] = []
                projects.save_project(self.project, sandbox=self.test_mode)
                ui_actions.append({"type": "reward", "label": "★ Specimen Blueprint Sketch Unlocked!"})
                ui_actions.append({"type": "item", "item": projects.project_ui_payload(self.project)})
                ui_actions, directive = self._prompt_codex_step(ui_actions, new_entry=False)
                return _finish({
                    "kind": self.last_kid_kind,
                    "codex_sketch": f"{(self.research_pack or {}).get('title','')}: {raw}",
                    "ui": ui_actions,
                    "directive": f"Sharp inference—that just unlocked the Specimen Blueprint Sketch on the right! Now ask for Sentence 1 (Topic Sentence). " + directive,
                })
            if self.codex_step in (1, 2):
                self.codex_buf.append(raw)
                self.project["codex_draft_sentences"] = list(self.codex_buf)
                projects.save_project(self.project, sandbox=self.test_mode)
                self.last_kid_kind = "SPINE_BEAT_COMPLETE"
                self.draw_unlocked = False
                self.codex_step += 1
                ui_actions.append({"type": "reward", "label": f"★ Codex Paragraph {len(self.codex_buf)}/3 Locked In"})
                ui_actions.append({"type": "item", "item": projects.project_ui_payload(self.project)})
                ui_actions, directive = self._prompt_codex_step(ui_actions, new_entry=False)
                return _finish({"kind": self.last_kid_kind, "ui": ui_actions, "directive": f"Sentence {self.codex_step - 1} added to the live Codex page! " + directive})

            self.codex_buf.append(raw)
            full_paragraph = " ".join(self.codex_buf)
            self.codex_buf = []
            self.project["codex_draft_sentences"] = []
            self.codex_step = 0
            self.had_synthesis = True
            self.last_kid_kind = "COMPLETE_SENTENCE"
            self.draw_unlocked = True
            self.goal_done += 1
            self.last_kid_text = full_paragraph
            if not self.word_study_done:
                return _finish(self._launch_word_forge(ui_actions, full_paragraph, full_paragraph=full_paragraph))
            ui_actions.append({"type": "goal", "text": self.goal_badge()})
            ui_actions.append(
                {
                    "type": "item",
                    "item": {
                        "id": "done_choices",
                        "kind": "choices",
                        "prompt": "Full 3-Sentence Codex Entry & Illustration Saved to PDF!",
                        "options": ["Keep going — next 3-Source Codex Dossier", f"Download Codex PDF for {self.parent_title}"],
                    },
                }
            )
            self.ui_locked_this_turn.add("show_choices")
            return _finish({
                "kind": self.last_kid_kind,
                "ui": ui_actions,
                "full_paragraph": full_paragraph,
                "directive": "Full 3-sentence informational paragraph synthesized from all 3 sources and rendering into the Codex PDF! Acknowledge the complete paragraph concisely and offer starting the next dossier or downloading the PDF.",
            })

        # CASE C: Advancing SRSD POW+TREE 4-Page Persuasive Pitch (`medium_pitch`)!
        if self.project and self.project.get("kind") == "medium_pitch":
            self.last_kid_kind = "COMPLETE_SENTENCE"
            self.draw_unlocked = True
            self.goal_done += 1
            self.tree_step += 1
            if self.tree_step >= 4:
                if not self.word_study_done:
                    return _finish(self._launch_word_forge(ui_actions, raw))
                self.phase = "WRAP"
                ui_actions.append({"type": "goal", "text": self.goal_badge()})
                ui_actions.append({"type": "item", "item": {"id": "done_choices", "kind": "choices", "prompt": "All 4 Persuasive Pitch Pages Complete!", "options": [f"Download Pitch PDF for {self.parent_title}"]}})
                self.ui_locked_this_turn.add("show_choices")
                return _finish({
                    "kind": self.last_kid_kind,
                    "ui": ui_actions,
                    "directive": f"All 4 pages of the SRSD TREE Persuasive Pitch (Claim, Reason, Counter-Argument, Deal) are complete and ready to download as an illustrated PDF for {self.parent_title}!",
                })
            ui_actions, next_dir = self._prompt_pitch_step(ui_actions)
            return _finish({"kind": self.last_kid_kind, "ui": ui_actions, "directive": f"Page {self.tree_step} locked and rendering! " + next_dir})

        # CASE D: Graphic Novel Panel, 3-Panel Strip, or Quick Sprint Sentence!
        self.last_kid_kind = "COMPLETE_SENTENCE"
        self.draw_unlocked = True
        self.goal_done += 1

        if self.goal_done == 1 and self.rung == "B3.1_simple":
            self.rung = "B3.1_compound"
        elif self.goal_done >= 2 and self.rung in ("B3.1_simple", "B3.1_compound"):
            self.rung = "B3.1_complex"

        target_for_today = self.session_panels_target if self.project else self.goal_target
        trigger_word_study = not self.word_study_done and (
            (self.misspellings and self.goal_done >= 2) or self.goal_done >= target_for_today
        )

        if trigger_word_study:
            return _finish(self._launch_word_forge(ui_actions, raw))

        if self.project:
            ui_actions.append({"type": "goal", "text": self.goal_badge()})
            if self.goal_done >= self.session_panels_target:
                self.phase = "WRAP"
                total_p = projects.total_panels(self.project) + 1
                ui_actions.append({"type": "item", "item": {"id": "done_choices", "kind": "choices", "prompt": f"Today's slice complete ({total_p} total panels in your PDF book)!", "options": ["Keep going — add 3 more panels", f"Download PDF & save for {self.parent_title}"]}})
                self.ui_locked_this_turn.add("show_choices")
                return _finish({
                    "kind": self.last_kid_kind,
                    "ui": ui_actions,
                    "directive": f"Panel {total_p} is rendering into '{self.project.get('title')}'! Mention the live Download PDF button on the right and let them choose whether to add 3 more panels or save here.",
                })
            if self.pause_for_art_check:
                next_pnum = projects.total_panels(self.project) + 1
                gate = self._enter_art_check_gate(ui_actions, f"panel:{next_pnum}", "BUILDING", f"Panel {next_pnum}")
                return _finish(gate)
            ui_actions, next_dir = self._prompt_next_book_panel(ui_actions, resumed=False)
            return _finish({"kind": self.last_kid_kind, "ui": ui_actions, "directive": next_dir})

        if self.goal_done >= self.goal_target:
            self.phase = "WRAP"
            ui_actions.append({"type": "goal", "text": self.goal_badge()})
            ui_actions.append({"type": "item", "item": {"id": "done_choices", "kind": "choices", "prompt": "Goal complete! Want to:", "options": ["Turn this into a Full Multi-Chapter PDF Comic Book", f"Save & print for {self.parent_title}"]}})
            self.ui_locked_this_turn.add("show_choices")
            return _finish({
                "kind": self.last_kid_kind,
                "ui": ui_actions,
                "directive": f"COMPLETE SENTENCE ({self.goal_done}/{self.goal_target} — GOAL HIT!): '{raw}'! Call save_piece and offer turning this into a Full PDF Comic Book or wrapping up.",
            })

        scaf = generate_combine_scaffold(self.rec, self.active_story, "", self.rung)
        conn_label = "when, because, or if" if self.rung == "B3.1_complex" else "but, so, or when"
        card_txt = f"Next beat — combine these two ideas with {conn_label}, OR write your own complete sentence for Step {self.goal_done + 1}:\n  1. {scaf['kernel_1']}\n  2. {scaf['kernel_2']}"
        ui_actions.append({"type": "goal", "text": self.goal_badge()})
        ui_actions.append({"type": "item", "item": {"id": "forge", "kind": "card", "title": f"Step {self.goal_done + 1} of {self.goal_target} · Level Up with '{conn_label}'", "text": card_txt}})
        ui_actions.append({"type": "input", "mode": "type", "prompt": f"Type Sentence {self.goal_done + 1} using {conn_label} (combine the card lines, or write your own complete sentence).", "prefill": ""})
        self.ui_locked_this_turn.update({"show_card", "ask_input"})
        return _finish({
            "kind": self.last_kid_kind,
            "ui": ui_actions,
            "directive": f"COMPLETE SENTENCE ({self.goal_done}/{self.goal_target}): '{raw}'! React briefly to the scene and invite Sentence {self.goal_done + 1} using {conn_label}.",
        })

    # ---------------- HARD PYTHON TOOL GATE ----------------

    def gate_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any] | None:
        if name == "comic_new":
            if self.project:
                return {"ok": True, "note": "Book project canvas is already open and managed automatically."}
            try:
                n = max(2, min(6, int(str(args.get("panels", "3")).strip())))
            except ValueError:
                n = 3
            self.goal_label = "Panels"
            self.goal_target = n
            return None

        if name in ("draw", "comic_panel"):
            if not self.draw_unlocked:
                if self.last_kid_kind in ("COMPLETE_SENTENCE", "SPINE_BEAT_COMPLETE"):
                    return {"ok": True, "status": "Handled automatically by the project/panel renderer. Do not repeat yourself."}
                return {
                    "blocked": True,
                    "reason": f"Drawing blocked by education gate: last student input class was {self.last_kid_kind!r}. Wait until the complete sentence / power-up edit is submitted.",
                }
            self.draw_unlocked = False
            return None

        if name == "save_piece":
            if self.project is not None:
                return {
                    "ok": True,
                    "note": "This book project auto-saves every beat automatically. NEVER wrap up or say 'next session' unless the student explicitly asked to stop!",
                }
            if self.phase != "WRAP" and self.last_kid_kind != "STOP":
                return {"blocked": True, "reason": "Do NOT call save_piece or wrap up the session mid-story!"}

        if name in ("write_on_page", "rewrite_page") and self.last_kid_kind != "COMPLETE_SENTENCE" and self.phase != "WRAP":
            return {"blocked": True, "reason": "Wait until the complete sentence is finalized before adding to the page."}

        if name in ("show_card", "show_choices", "ask_input", "show_word") and name in self.ui_locked_this_turn:
            return {"ok": True, "note": f"{name} is already on screen. Do NOT repeat anything you already said aloud."}

        if name == "show_choices":
            opts = [o.strip() for o in (args.get("options") or "").split("|") if o.strip()]
            allow_activity = self.last_kid_kind in ("NONE", "GREETING", "REFUSAL") or self.avoidance_streak >= 2 or self.phase == "WRAP"
            if not allow_activity:
                bad = [o for o in opts if len(_words(o)) > 3 or re.search(r"[.!?]$", o)]
                if bad:
                    return {"blocked": True, "reason": f"Blocked choices {bad}: only offer 1-2 word verbs/connectors during sentence writing."}
            else:
                bad = [
                    o
                    for o in opts
                    if len(_words(o)) >= 8
                    and re.search(r"[.!?]$", o)
                    and not re.match(r"^(build|start|continue|make|try|switch|add|save|pause|wrap|turn|keep|download|voice)\b", o.lower())
                ]
                if bad:
                    return {"blocked": True, "reason": f"Blocked choices {bad}: choices must be project formats, never story sentences."}
            return None

        if name == "ask_input":
            p = (args.get("prompt") or "").strip()
            if re.search(r'(type|write|copy)[^"]*["\'][A-Z][^"\']{12,}[.!?]["\']', p, re.I):
                args["prompt"] = "Write your own complete sentence (Who + Does What + Capital & .)."
            if p.endswith("?") and "sentence" not in p.lower() and self.phase in ("BUILDING", "STORY_SPINE"):
                args["prompt"] = f"Write one complete sentence: {p}"
            return None

        return None
