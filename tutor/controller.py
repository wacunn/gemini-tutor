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

import re
from typing import Any

from google import genai
from google.genai import types

from . import curriculum_tracker as ct
from . import projects, research_packs, spelling_srs, thinking
from .config import FALLBACK_MODEL, FAST_MODEL, genai_client
from .record import save_learner

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


DIRECTOR_SYSTEM = """You are a sharp, curious AI story & writing director working with a smart Grade 3–4 child with ADHD (NEVER babyish, NEVER cringe slang, NEVER robotic worksheet language).
Your job: generate the exact next prompt by reading THEIR actual characters, plot, or claim so far!

CRITICAL RULES:
1. ALWAYS REMIND + ASK SPECIFICALLY: Briefly remind them of the exact detail from their story/pitch so they don't have to hold it in working memory, then ask a curious, specific question ('where', 'why', 'how', 'what goes wrong first when...') that zooms into THIS exact beat!
   - BAD (generic static script): "Your story is all set, so let's zoom into Panel 1. Write one complete sentence describing the very first moment."
   - GOOD (specific AI story director): "At the start of your story, Bob gets a small, smelly cat! For Panel 1, where did Bob find that smelly cat, or why did he decide to bring it home? Tell me in one complete sentence!"
   - GOOD (Act II complication): "Okay, Bob has his tiny smelly cat! For the middle of your story, what big problem does that awful smell cause for Bob—write a complete sentence using 'because', 'when', or 'but'!"
2. Keep `spoken_prompt` to 1–2 crisp, natural sentences ending with the clear sentence/connector expectation.
3. Also output `kernel_1` and `kernel_2`: two short (5–8 word) optional spark sentences using THEIR exact characters/topic (never write the combined sentence for them).
Return strict JSON:
{"spoken_prompt":"1-2 natural sentences reminding them of their story + asking a specific question for this beat + naming the complete-sentence/connector goal.",
 "input_prompt":"Short 1-line specific question + complete-sentence cue for the input bar.",
 "kernel_1":"Short optional spark sentence 1 from their story.",
 "kernel_2":"Short optional spark sentence 2 from their story.",
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
    try:
        client = genai_client()
        for model in (PLANNER_MODEL, FALLBACK_MODEL):
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
                        "kernel_1": str(out.get("kernel_1") or "The door creaks open.").strip(),
                        "kernel_2": str(out.get("kernel_2") or "Something unexpected jumps out.").strip(),
                        "connectors": str(out.get("connectors") or connector_goal).strip(),
                    }
            except Exception:
                continue
    except Exception:
        pass
    return {
        "spoken_prompt": step_goal,
        "input_prompt": step_goal,
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


def _infer_book_title(beginning_sentence: str) -> str:
    words = re.findall(r"[A-Za-z0-9']+", beginning_sentence or "")
    stop = {"the", "a", "an", "in", "on", "at", "when", "once", "there", "was", "is", "were", "he", "she", "they", "his", "her", "deep", "gets", "got", "then"}
    picked = [w.capitalize() for w in words if w.lower() not in stop][:4]
    return " ".join(picked) if len(picked) >= 2 else "Original Graphic Novel"


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
    out = out.strip()
    if out and out[0].isalpha() and not out[0].isupper():
        out = out[0].upper() + out[1:]
    if out and not re.search(r'[.!?]["\')\]]*$', out):
        out += "."
    return out


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

    def spine_summary(self) -> str:
        if not self.project:
            return ""
        sp = self.project.get("spine") or {}
        bits = []
        if sp.get("beginning"):
            bits.append(f"Beginning (Kickoff): {sp['beginning']}")
        mbeats = projects.middle_beats_list(sp)
        for i, mb in enumerate(mbeats, 1):
            if mb.get("text"):
                bits.append(f"Middle Twist #{i}: {mb['text']}")
        if sp.get("end"):
            bits.append(f"Big Finale (End): {sp['end']}")
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
                return f"Plot Board: {step} · Tier {tier}"
            if kind == "epic_codex":
                labels = {0: "Reading Inference", 1: "Paragraph 1/3", 2: "Paragraph 2/3", 3: "Paragraph 3/3"}
                return f"Codex Entries: {pcount} · {labels.get(self.codex_step, 'Drafting')}"
            if kind == "medium_pitch":
                return f"Pitch Book (TREE): Page {min(4, self.tree_step + 1)}/4"
            ch_num = len(self.project.get("chapters") or [1])
            return f"Ch.{ch_num} · Book Panels: {pcount} (Today: {self.goal_done}/{self.session_panels_target}) · Tier {tier}"
        if self.phase == "WORD_STUDY" and self.word_target:
            return f"{self.goal_label}: {self.goal_done}/{self.goal_target} · Word Forge"
        streak = f" · Streak {self.first_try_streak}" if self.first_try_streak >= 2 else ""
        return f"{self.goal_label}: {self.goal_done}/{self.goal_target} · Tier {tier}{streak}"

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
            ask = f"Page 1: What bold idea or rule are you pitching to {self.parent_title}? (1 complete sentence)"
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
        beat = ai_direct_next_beat(self.rec, goal_desc, self.active_story, connector_goal=conns)
        ui.append({"type": "input", "mode": "type", "prompt": beat["input_prompt"], "prefill": ""})
        self.ui_locked_this_turn.update({"show_card", "ask_input"})
        return ui, f"Say this story-specific prompt naturally in 1–2 sentences: {beat['spoken_prompt']}"

    def _prompt_spine_step(self, ui: list[dict[str, Any]], resumed: bool = False) -> tuple[list[dict[str, Any]], str]:
        assert self.project is not None
        stage = self.project.get("stage", "spine_beginning")
        sp = self.project.get("spine") or {}
        mbeats = projects.middle_beats_list(sp)
        self.phase = "STORY_SPINE"

        if stage == "spine_beginning":
            ui.append({"type": "input", "mode": "type", "prompt": "Kickoff (Unlocks Cover Art): Who is your main character and what weird trouble starts the story?", "prefill": ""})
            self.ui_locked_this_turn.update({"show_card", "ask_input"})
            return ui, (
                f"{'Resuming' if resumed else 'Starting'} {self.name}'s Graphic Novel! "
                "In 1–2 plain sentences, tell them they can pick any comic art style on the right, and we'll map the Kickoff, the Big Finale, and then all the wild twists in the middle—ask who the main character is and what kicks off the trouble (unlocks Cover Art)."
            )

        if stage == "spine_end":
            beat = ai_direct_next_beat(
                self.rec,
                "We just locked the Beginning (Kickoff) and unlocked Cover Art! Before we pack the middle with twists, remind the student specifically of their Beginning, and ask a curious question jumping to the BIG FINALE at the very end of the book: how does this whole crazy story end up or pay off? Ask for 1–2 complete sentences using 'finally', 'so', or 'when' (unlocks Finale Art).",
                self.active_story,
                spine_context=self.spine_summary(),
                connector_goal="finally | so | when",
            )
            ui.append({"type": "input", "mode": "type", "prompt": beat["input_prompt"], "prefill": ""})
            self.ui_locked_this_turn.update({"show_card", "ask_input"})
            return ui, f"Cover Art is rendering! Deliver this specific Finale question in 1–2 plain sentences: {beat['spoken_prompt']}"

        # stage == "spine_middle": iterative middle twists bridging Beginning -> Big Finale!
        n_mid = len(mbeats)
        if n_mid == 0:
            beat = ai_direct_next_beat(
                self.rec,
                "We now know BOTH the Beginning AND the Big Finale! Remind the student specifically of where they start and where they have to end up, and ask what the FIRST big disaster, obstacle, or wild twist in the middle is that gets in their way. Ask for 1–2 complete sentences using 'because', 'when', or 'but' (unlocks Twist #1 Art).",
                self.active_story,
                spine_context=self.spine_summary(),
                connector_goal="because | when | but",
            )
            ui.append({"type": "input", "mode": "type", "prompt": beat["input_prompt"], "prefill": ""})
            self.ui_locked_this_turn.update({"show_card", "ask_input"})
            return ui, f"Finale Art is rendering! Now start building the middle twists in 1–2 plain sentences: {beat['spoken_prompt']}"

        if n_mid == 1:
            beat = ai_direct_next_beat(
                self.rec,
                "Middle Twist #1 is locked! Remind the student specifically of Twist #1 and the Big Finale still ahead, and ask: WHAT ELSE happens next in the middle to make things even wilder, funnier, or harder before they reach that ending? Ask for 1–2 complete sentences using 'when', 'because', 'but', or 'then' (unlocks Twist #2 Art).",
                self.active_story,
                spine_context=self.spine_summary(),
                connector_goal="when | because | but",
            )
            ui.append({"type": "input", "mode": "type", "prompt": beat["input_prompt"], "prefill": ""})
            self.ui_locked_this_turn.update({"show_card", "ask_input"})
            return ui, f"Twist #1 Art is rendering! Ask what ELSE happens next in the middle in 1–2 plain sentences: {beat['spoken_prompt']}"

        beat = ai_direct_next_beat(
            self.rec,
            f"Middle Twist #{n_mid} is locked! Briefly react to Twist #{n_mid} and ask a specific curious question about WHAT ELSE could go wrong or escalate in the middle before the finale—and mention they can either type another middle twist OR tap 'Start Chapter 1 panels' if their plot is ready.",
            self.active_story,
            spine_context=self.spine_summary(),
            connector_goal="when | because | but | so",
        )
        ui.append(
            {
                "type": "item",
                "item": {
                    "id": "spine_more_choices",
                    "kind": "choices",
                    "prompt": f"{n_mid} middle twists locked! Add another middle event, or start drawing Chapter 1?",
                    "options": ["Start Chapter 1 panels →", "Add another middle twist"],
                },
            }
        )
        ui.append({"type": "input", "mode": "type", "prompt": beat["input_prompt"], "prefill": ""})
        self.ui_locked_this_turn.update({"show_card", "show_choices", "ask_input"})
        return ui, f"Twist #{n_mid} Art is rendering! Ask what else happens in the middle (or invite starting Chapter 1 panels) in 1–2 plain sentences: {beat['spoken_prompt']}"

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

        if tier == 1:
            tier_req = "Ask for 1 complete sentence (Capital + Who/What + Action + Period)."
            conns = "when | so"
        elif tier == 2:
            tier_req = "Ask for 1 complete sentence using 'when', 'because', 'but', or 'so' to show cause or timing."
            conns = "when | because | but"
        elif tier == 3 and next_pnum % 2 == 0:
            tier_req = 'Ask them to include punctuated character speech in quotation marks (e.g. "Watch out!" yelled Bob.) so a real comic speech bubble appears on the panel!'
            conns = "when | because"
        elif tier >= 4:
            tier_req = "Ask them to open with a scene-setting where/when phrase + comma and use a vivid action verb."
            conns = "when | although | because"
        else:
            tier_req = "Ask for 1–2 complete sentences driving the scene forward."
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

        beat = ai_direct_next_beat(
            self.rec,
            zoom_goal,
            self.active_story,
            spine_context=self.spine_summary(),
            connector_goal=conns,
        )
        ui.append({"type": "input", "mode": "type", "prompt": beat["input_prompt"], "prefill": ""})
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
        raw = (text or "").strip()
        norm = _norm(raw)
        wlist = _words(raw)
        idx = self.turn_index
        self.turn_index += 1
        self.last_kid_text = raw

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

            if matched and len(wlist) >= 3 and not (chk or {}).get("misspellings") and not (chk or {}).get("grammar_fixes"):
                repaired = raw
                if repaired and repaired[0].isalpha() and not repaired[0].isupper():
                    repaired = repaired[0].upper() + repaired[1:]
                if repaired and not re.search(r'[.!?]["\')\]]*$', repaired):
                    repaired += "."
            else:
                repaired = self.pending_spell_sentence or raw
                for m in self.pending_spell_targets:
                    repaired = _splice_word_into_sentence(repaired, m["wrote"], m["meant"])

            self.phase = self.phase_before_inline_help or (
                "STORY_SPINE" if (self.project and self.project.get("stage", "").startswith("spine_")) else "BUILDING"
            )
            self.pending_spell_targets = []
            self.pending_spell_sentence = ""
            self.inline_word_help_tries = 0
            resolved_inline_word = target_word
            resolved_repaired_text = repaired
            raw = repaired
            norm = _norm(raw)
            wlist = _words(raw)
            self.last_kid_text = raw
            chk = thinking._post_verify_check(
                raw,
                {"sentences": [{"text": raw, "complete": True, "issue": "none", "capital_ok": True, "end_ok": True}], "misspellings": []},
            )

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

            if any(k in norm for k in ("continue ", "full comic book", "graphic novel", "codex", "field guide", "fact", "pitch", "why we should")):
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

        # ---------------- 7. GENUINE WRITING ATTEMPTS (Syntactic, Conventions & Mastery-Tier Verification) ----------------
        if self.phase == "OPENING":
            self.phase = "BUILDING"
        self.prev_norm_text = norm
        self.avoidance_streak = 0
        self.refusal_streak = 0

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
        if self.hint_step == 0 and not self.tier_nudged_this_item and not resolved_inline_word:
            self.first_try_streak += 1
        self.hint_step = 0
        self.tier_nudged_this_item = False
        self.engaged_draft = ""
        self.pending_spell_targets = []
        self.pending_spell_sentence = ""
        self.active_story.append(raw)

        def _finish(plan_dict: dict[str, Any]) -> dict[str, Any]:
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
                    self.project["title"] = _infer_book_title(raw)
                self.project["stage"] = "spine_end"
                projects.save_project(self.project, sandbox=self.test_mode)
                ui_actions.append({"type": "reward", "label": f"★ Cover & Kickoff Art Unlocked · “{self.project['title']}”"})
                ui_actions.append({"type": "item", "item": projects.project_ui_payload(self.project)})
                ui_actions.append({"type": "goal", "text": self.goal_badge()})
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
                ui_actions, directive = self._prompt_spine_step(ui_actions, resumed=False)
                return _finish({
                    "kind": self.last_kid_kind,
                    "spine_draw": {"beat": "end", "text": raw},
                    "ui": ui_actions,
                    "directive": directive,
                })

            # st == "spine_middle": append this twist to middle_beats and ask what ELSE happens in the middle!
            mbeats = list(projects.middle_beats_list(sp))
            beat_idx = len(mbeats)
            mbeats.append({"text": raw, "image": None, "src": None, "status": "drawing"})
            sp["middle_beats"] = mbeats
            sp["middle"] = " ".join(b.get("text", "") for b in mbeats)
            projects.save_project(self.project, sandbox=self.test_mode)
            ui_actions.append({"type": "reward", "label": f"★ Middle Twist #{beat_idx + 1} Art Unlocked!"})
            ui_actions.append({"type": "item", "item": projects.project_ui_payload(self.project)})
            ui_actions.append({"type": "goal", "text": self.goal_badge()})
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
