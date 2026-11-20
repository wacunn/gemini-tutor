"""Synchronous Pedagogical Controller, Multi-Scale Project Director & Hard Tool Gate.

Drives both:
- Quick 10-minute single-session sprints (3-panel strip, contraption compiler, live HTML5 game)
- Persistent multi-week Epic & Medium book projects (100-panel Graphic Novel starting with a
  causal Beginning -> Middle -> End Story Spine, Illustrated Monster/Invention Codex, and
  4-Page Persuasive Pitch Book, all auto-saved across sessions with live PDF book export).

Adapts expectations upward automatically across Tiers 1–5 using the learner's Ontario
Grade 3–4 Curriculum Report Card (`curriculum_tracker.py`).
"""

from __future__ import annotations

import re
from typing import Any

from google import genai
from google.genai import types

from . import curriculum_tracker as ct
from . import projects, thinking
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
    "?",
    "...",
}
REFUSAL_PATTERNS = (
    r"^(no|nope|nah|pass|stop|quit|skip)\b",
    r"\b(this is boring|boring|i dont want|i don't want|hate this|dumb|stupid|something else|different game|switch)\b",
)

HIGH_VALUE_PATTERNS = (
    r"(ed|ing|er|est|ly|ful|less|ness|able|tion|sion)$",
    r"^(un|re|dis|pre|mis|non|sub|over|under)",
    r"(tch|dge|ck|igh|eigh|ough|kn|wr|mb|ai|ay|oi|oy|ou|ow|ea)",
    r"because|friend|said|they|where|there|which|their|through|caught|thought",
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
Given the active story/book context (if any) and target connector/tier, output TWO short, concrete, action-packed simple sentences (5–8 words each) and 2–3 connectors that the student can combine into ONE strong sentence.
Rules:
- NEVER write the combined sentence for the student.
- If a Story Spine or active story exists, build BOTH kernels directly from THEIR story/chapter so the plot advances causally!
- If no premise exists yet, draw naturally from their interests/notes in LEARNER CONTEXT (or a crisp contraption/adventure moment if none listed).
- NEVER use babyish filler prompts ("what a bear eats", "what color a cow is", "a cat sleeps").
Return strict JSON:
{"kernel_1":"Complete short sentence 1.",
 "kernel_2":"Complete short sentence 2.",
 "connectors":"when | so",
 "ask_prompt":"Combine those two sentences into one sentence using 'when' or 'so' (or write your own complete sentence) to run the scene."}"""


def generate_combine_scaffold(
    rec: dict[str, Any],
    active_story: list[str],
    engaged_draft: str,
    rung: str,
    spine_context: str = "",
) -> dict[str, str]:
    story_txt = "\n".join(f"- {s}" for s in active_story[-5:]) or "(none yet)"
    notes_txt = "; ".join(n.get("note", "") for n in (rec.get("parent_notes") or [])[:6])
    interests_txt = ", ".join((rec.get("model") or {}).get("interests") or [])
    connector_goal = "when | because | if" if rung in ("B3.1_complex",) else "but | so | when"
    prompt = (
        f"LEARNER CONTEXT: Grade {rec.get('grade', 3)}. Notes: {notes_txt or '(none)'}. Interests: {interests_txt or '(open)'}.\n"
        + (f"BOOK STORY SPINE:\n{spine_context}\n" if spine_context else "")
        + f"Recent sentences:\n{story_txt}\n"
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
    return {
        "kernel_1": "The iron pressure plate clicks.",
        "kernel_2": "A hidden piston drops the floor over lava.",
        "connectors": "when | so",
        "ask_prompt": "Combine those two lines into one complete sentence using 'when' or 'so' (or write your own).",
    }


def _infer_book_title(beginning_sentence: str) -> str:
    words = re.findall(r"[A-Za-z0-9']+", beginning_sentence or "")
    stop = {"the", "a", "an", "in", "on", "at", "when", "once", "there", "was", "is", "were", "he", "she", "they", "his", "her"}
    picked = [w.capitalize() for w in words if w.lower() not in stop][:4]
    return " ".join(picked) if len(picked) >= 2 else "Original Graphic Novel"


class SessionController:
    """Deterministic pedagogical state machine + multi-scale book/project director + hard tool gate."""

    def __init__(self, rec: dict[str, Any], test_mode: bool = False):
        self.rec = rec
        self.test_mode = test_mode
        self.name = rec.get("name") or "the student"
        self.parent_title = rec.get("parent_title") or "your parent"
        self.rc = ct.ensure_report_card(rec)

        self.phase: str = "OPENING"  # OPENING -> STORY_SPINE -> BUILDING -> WORD_STUDY -> WRAP
        self.rung: str = "B3.1_simple"
        self.mastery_tier: int = ct.compute_mastery_tier(self.rc, 0)

        self.project: dict[str, Any] | None = None
        self.goal_label: str = "Sentences"
        self.goal_done: int = 0
        self.goal_target: int = 3
        self.session_panels_target: int = 4  # Manageable ~15-min daily slice of a 100-panel epic!
        self.first_try_streak: int = 0

        self.turn_index: int = 0
        self.hint_step: int = 0
        self.avoidance_streak: int = 0
        self.refusal_streak: int = 0
        self.had_revision: bool = False

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
        self.words_studied_count: int = 0

        self.draw_unlocked: bool = False
        self.ui_locked_this_turn: set[str] = set()

    def spine_summary(self) -> str:
        if not self.project:
            return ""
        sp = self.project.get("spine") or {}
        bits = []
        if sp.get("beginning"):
            bits.append(f"Beginning: {sp['beginning']}")
        if sp.get("middle"):
            bits.append(f"Middle: {sp['middle']}")
        if sp.get("end"):
            bits.append(f"End: {sp['end']}")
        return "\n".join(bits)

    def current_tier(self) -> int:
        pcount = projects.total_panels(self.project) if self.project else self.goal_done
        self.mastery_tier = ct.compute_mastery_tier(self.rc, pcount)
        return self.mastery_tier

    def goal_badge(self) -> str:
        tier = self.current_tier()
        if self.project:
            stage = self.project.get("stage", "")
            pcount = projects.total_panels(self.project)
            if stage.startswith("spine_"):
                step = {"spine_beginning": "1/3", "spine_middle": "2/3", "spine_end": "3/3"}.get(stage, "1/3")
                return f"Story Spine: {step} · Tier {tier}"
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
        opts.append("Illustrated Monster/Invention Codex (PDF)")
        ideas = opening_ideas or []
        quick_name = ideas[0]["name"] if ideas else "Quick 3-Panel Strip"
        if "comic" in quick_name.lower():
            quick_name = "Quick 3-Panel Strip (10 min)"
        opts.append(quick_name)
        opts.append("Build a Live Mini-Game (10 min)")
        return opts[:4]

    def start_or_resume_project(self, choice_label: str) -> tuple[list[dict[str, Any]], str]:
        """Initializes or loads a persistent multi-session project and returns (ui_actions, tutor_directive)."""
        ui: list[dict[str, Any]] = []
        low = choice_label.lower()

        # 1. Resume existing saved project
        if low.startswith("continue ") and not self.test_mode:
            saved = projects.list_projects()
            if saved:
                self.project = saved[0]
                for p in projects.all_panels(self.project)[-6:]:
                    if p.get("caption"):
                        self.active_story.append(p["caption"])
                ui.append({"type": "item", "item": projects.project_ui_payload(self.project)})
                ui.append({"type": "goal", "text": self.goal_badge()})
                st = self.project.get("stage", "drafting_panels")
                if st.startswith("spine_"):
                    return self._prompt_spine_step(ui, resumed=True)
                return self._prompt_next_book_panel(ui, resumed=True)

        # 2. New Full Graphic Novel (Beginning -> Middle -> End Story Spine -> Chapters -> 100-Panel PDF!)
        if "full comic book" in low or "graphic novel" in low:
            self.project = projects.create_project("epic_graphic_novel", self.name, self.parent_title, persist=not self.test_mode)
            self.phase = "STORY_SPINE"
            ui.append({"type": "item", "item": projects.project_ui_payload(self.project)})
            ui.append({"type": "goal", "text": self.goal_badge()})
            return self._prompt_spine_step(ui, resumed=False)

        # 3. New Illustrated Monster & Invention Codex (Expository Book -> PDF)
        if "codex" in low or "field guide" in low or "encyclopedia" in low:
            self.project = projects.create_project("epic_codex", self.name, self.parent_title, title=f"{self.name}'s Illustrated Codex", persist=not self.test_mode)
            self.phase = "BUILDING"
            ui.append({"type": "item", "item": projects.project_ui_payload(self.project)})
            ui.append({"type": "goal", "text": self.goal_badge()})
            card_txt = (
                "Codex Entry #1 — Every entry has 3 linked sentences (Appearance → How It Works → Weakness):\n"
                "  Start Sentence 1: Name your creature, boss, or contraption and describe what it looks like in one complete sentence."
            )
            ui.append({"type": "item", "item": {"id": "forge", "kind": "card", "title": "Illustrated Codex · Entry 1 (Saves to PDF Book)", "text": card_txt}})
            ui.append({"type": "input", "mode": "type", "prompt": "Write Sentence 1 naming your creature or invention and what it looks like (capital & period).", "prefill": ""})
            self.ui_locked_this_turn.update({"show_card", "ask_input"})
            return ui, (
                f"{self.name} started an ongoing Illustrated Codex (saves across sessions and exports as a real PDF book!). "
                "In 1–2 plain sentences, explain that each creature/invention gets an illustrated page built from complete sentences, "
                "and invite Sentence 1: who/what the first entry is and what it looks like."
            )

        # 4. New 4-Page Persuasive Pitch Book
        if "pitch" in low or "why we should" in low:
            self.project = projects.create_project("medium_pitch", self.name, self.parent_title, title="The Official Pitch", persist=not self.test_mode)
            self.phase = "BUILDING"
            self.session_panels_target = 4
            ui.append({"type": "item", "item": projects.project_ui_payload(self.project)})
            ui.append({"type": "goal", "text": self.goal_badge()})
            ui.append(
                {
                    "type": "item",
                    "item": {
                        "id": "forge",
                        "kind": "card",
                        "title": f"Page 1 of 4 · Bold Claim (for {self.parent_title})",
                        "text": f"Write one complete sentence stating what you are pitching to {self.parent_title} and why it matters (use 'because').",
                    },
                }
            )
            ui.append({"type": "input", "mode": "type", "prompt": "Write Page 1's claim as one complete sentence using 'because'.", "prefill": ""})
            self.ui_locked_this_turn.update({"show_card", "ask_input"})
            return ui, (
                f"{self.name} started a 4-Page Illustrated Pitch PDF for {self.parent_title}. "
                "Ask for Page 1's bold claim as one complete sentence using 'because'."
            )

        return ui, ""

    def _prompt_spine_step(self, ui: list[dict[str, Any]], resumed: bool = False) -> tuple[list[dict[str, Any]], str]:
        assert self.project is not None
        stage = self.project.get("stage", "spine_beginning")
        sp = self.project.get("spine", {})
        self.phase = "STORY_SPINE"

        if stage == "spine_beginning":
            card_txt = (
                "Great comic books map the whole story BEFORE Panel 1 so every chapter connects:\n"
                "  • ACT I — BEGINNING: Who is the main character, where are they, and what is their goal or normal world?\n"
                "  • ACT II — MIDDLE ('BUT / WHEN'): What goes horribly wrong or escalates?\n"
                "  • ACT III — END ('SO / FINALLY'): How does the final showdown resolve?\n\n"
                "Right now: Write 1–2 complete sentences for ACT I (THE BEGINNING). (You can talk it out with the mic first or type straight in.)"
            )
            ui.append({"type": "item", "item": {"id": "forge", "kind": "card", "title": "Graphic Novel Blueprint · Step 1 of 3: The Beginning", "text": card_txt}})
            ui.append({"type": "input", "mode": "type", "prompt": "Write 1–2 complete sentences for THE BEGINNING (who your hero is and their starting world/goal).", "prefill": ""})
            self.ui_locked_this_turn.update({"show_card", "ask_input"})
            return ui, (
                f"{'Resuming' if resumed else 'Starting'} {self.name}'s multi-chapter Graphic Novel (saves across weeks and exports to a printable PDF book!). "
                "In 1–2 plain sentences, explain that real graphic novelists map Beginning → Middle → End first before zooming into Panel 1, "
                "and ask for 1–2 complete sentences setting up THE BEGINNING (who the main character is and where they start)."
            )

        if stage == "spine_middle":
            card_txt = (
                f"ACT I (Locked): \"{sp.get('beginning','')}\"\n\n"
                "ACT II — THE MIDDLE (Causal Complication):\n"
                "  Real stories don't just say 'and then'—something happens BECAUSE of Act I, or a huge 'BUT / WHEN' problem hits!\n"
                "  Write 1–2 complete sentences starting with 'But', 'When', or 'Because' showing the big problem or escalation."
            )
            ui.append({"type": "item", "item": {"id": "forge", "kind": "card", "title": "Graphic Novel Blueprint · Step 2 of 3: The Middle ('But / When')", "text": card_txt}})
            ui.append({"type": "input", "mode": "type", "prompt": "Write 1–2 complete sentences for THE MIDDLE using 'but', 'when', or 'because' so it links causally to Act I.", "prefill": ""})
            self.ui_locked_this_turn.update({"show_card", "ask_input"})
            return ui, (
                f"Act I is locked ('{sp.get('beginning','')}'). Now ask for ACT II (THE MIDDLE) in 1–2 complete sentences: "
                "emphasize linking causally with 'but', 'when', or 'because' (not 'and then') to show the big problem that hits."
            )

        # spine_end
        card_txt = (
            f"ACT I: \"{sp.get('beginning','')}\"\n"
            f"ACT II: \"{sp.get('middle','')}\"\n\n"
            "ACT III — THE END (Climax & Resolution):\n"
            "  Because of Act II, how does the final showdown happen and how does it end?\n"
            "  Write 1–2 complete sentences using 'So', 'Finally', or 'When' to lock in the ending—then we zoom into Chapter 1, Panel 1!"
        )
        ui.append({"type": "item", "item": {"id": "forge", "kind": "card", "title": "Graphic Novel Blueprint · Step 3 of 3: The End ('So / Finally')", "text": card_txt}})
        ui.append({"type": "input", "mode": "type", "prompt": "Write 1–2 complete sentences for THE END using 'so', 'finally', or 'when'—then we zoom into Panel 1!", "prefill": ""})
        self.ui_locked_this_turn.update({"show_card", "ask_input"})
        return ui, (
            "Act II is locked! Ask for ACT III (THE END) in 1–2 complete sentences using 'so', 'finally', or 'when' to show the climax and resolution, "
            "letting them know that right after this we zoom into Chapter 1, Panel 1."
        )

    def _prompt_next_book_panel(self, ui: list[dict[str, Any]], resumed: bool = False) -> tuple[list[dict[str, Any]], str]:
        assert self.project is not None
        self.phase = "BUILDING"
        pcount = projects.total_panels(self.project)
        next_pnum = pcount + 1
        ch_num = len(self.project.get("chapters") or [1])
        tier = self.current_tier()
        tier_info = ct.TIER_DESCRIPTIONS.get(tier, ct.TIER_DESCRIPTIONS[1])
        sp = self.project.get("spine") or {}

        # Determine which Act we are currently zooming into
        act_focus = sp.get("beginning", "") if ch_num <= 2 else (sp.get("middle", "") if ch_num <= 10 else sp.get("end", ""))
        rung_for_scaf = "B3.1_complex" if tier >= 2 else "B3.1_simple"
        scaf = generate_combine_scaffold(self.rec, self.active_story, "", rung_for_scaf, spine_context=self.spine_summary())

        if tier == 1:
            req_line = "Write 1 complete sentence (Who + Does What + Capital & .) showing this exact moment—don't rush the whole plot in one panel!"
        elif tier == 2:
            req_line = f"Level-Up Challenge ({tier_info['name']}): Connect cause or timing with {_fmt_conns(scaf['connectors'])}!"
        elif tier == 3:
            req_line = (
                f"Level-Up Challenge ({tier_info['name']}): Include character speech! "
                'Put spoken words in quotation marks (e.g. "Watch out!" yelled Rex.) so a real speech bubble appears on the panel!'
            )
        else:
            req_line = (
                f"Level-Up Challenge ({tier_info['name']}): Open with WHERE or WHEN it happens (e.g. 'Inside the...', 'Seconds before...'), "
                "use a vivid verb, or include punctuated dialogue!"
            )

        card_txt = (
            (f"Zooming into Act Beat: \"{act_focus}\"\n\n" if act_focus else "")
            + f"{req_line}\n\n"
            f"Idea Sparks (combine these, or write your own Panel {next_pnum} beat):\n"
            f"  1. {scaf['kernel_1']}\n"
            f"  2. {scaf['kernel_2']}"
        )
        ui.append(
            {
                "type": "item",
                "item": {
                    "id": "forge",
                    "kind": "card",
                    "title": f"{self.project.get('title','Comic Book')} · Ch.{ch_num}, Panel {next_pnum}",
                    "text": card_txt,
                },
            }
        )
        ui.append(
            {
                "type": "input",
                "mode": "type",
                "prompt": f"Panel {next_pnum}: {tier_info['prompt_hint']}",
                "prefill": "",
            }
        )
        self.ui_locked_this_turn.update({"show_card", "ask_input"})
        directive = (
            f"{'Resumed' if resumed else 'Now zooming into'} {self.project.get('title')} — Chapter {ch_num}, Panel {next_pnum} "
            f"(Active Mastery Tier {tier}: {tier_info['rule']}). "
            "Remind them briefly to zoom in on just THIS single visual moment (so the story paces like a real graphic novel instead of rushing to the end), "
            f"and invite Panel {next_pnum} following Tier {tier}'s goal. (Note: PDF export updates live on the right after every panel!)"
        )
        return ui, directive

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
        """Deterministically classifies student input, advances project/sentence state, and returns UI actions + tutor directive."""
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
            typed_words = [w.lower() for w in wlist]
            matched = target_word.lower() in typed_words or norm == target_word.lower()
            self.word_study_tries += 1
            self.last_kid_kind = "SPELLING_ATTEMPT"
            self.prev_norm_text = norm
            if matched or self.word_study_tries >= 2:
                self.word_study_done = True
                self.words_studied_count += 1
                # Remove studied word from queue so a long session can study another later if needed
                self.misspellings = [m for m in self.misspellings if m["meant"].lower() != target_word.lower()]
                ui_actions.append({"type": "remove", "id": "word"})
                if self.project:
                    ui_actions.append({"type": "goal", "text": self.goal_badge()})
                    if self.goal_done >= self.session_panels_target:
                        self.phase = "WRAP"
                        ui_actions.append(
                            {
                                "type": "item",
                                "item": {
                                    "id": "done_choices",
                                    "kind": "choices",
                                    "prompt": f"Today's chapter goal reached ({projects.total_panels(self.project)} total panels saved in book)!",
                                    "options": ["Keep going — write next panel", "Wrap up & download PDF"],
                                },
                            }
                        )
                        self.ui_locked_this_turn.add("show_choices")
                        msg = (
                            f"Confirmed '{target_word}' ({self.word_target['parts']})! His book '{self.project.get('title')}' is auto-saved "
                            f"with {projects.total_panels(self.project)} panels and a live PDF ready on the right. Ask if he wants to keep adding panels or wrap for today."
                        )
                        return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": msg}
                    ui_actions, next_dir = self._prompt_next_book_panel(ui_actions, resumed=False)
                    return {
                        "kind": self.last_kid_kind,
                        "ui": ui_actions,
                        "directive": f"Confirmed '{target_word}' ({self.word_target['parts']}) in 1 short sentence! {next_dir}",
                    }

                self.phase = "WRAP" if self.goal_done >= self.goal_target else "BUILDING"
                ui_actions.append({"type": "goal", "text": self.goal_badge()})
                if matched:
                    directive = (
                        f"SPELLING LOCKED IN: {self.name} spelled '{target_word}' accurately from memory! "
                        f"Confirm specifically how they nailed the '{self.word_target['parts']}' pattern in one plain sentence. "
                        + (
                            f"Today's sentence goal is complete—call save_piece so {self.name} and {self.parent_title} can keep it, "
                            "and ask if they want to add a bonus sentence or wrap here."
                            if self.phase == "WRAP"
                            else f"Now return to sentence {self.goal_done + 1} of {self.goal_target}."
                        )
                    )
                else:
                    directive = (
                        f"Show the exact comparison once: '{target_word}' ({self.word_target['parts']}), without saying 'wrong'. "
                        "Move cleanly to saving the piece with save_piece or the next sentence."
                    )
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
                    f"({self.word_target['parts']}) in one short sentence and let them write '{target_word}' once more from memory."
                )
                return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": directive}

        # ---------------- 2. TAP INPUTS ----------------
        if how == "tap":
            self.prev_norm_text = norm
            if "keep going" in norm and self.project:
                self.session_panels_target += 3
                self.word_study_done = False
                ui_actions.append({"type": "goal", "text": self.goal_badge()})
                ui_actions, directive = self._prompt_next_book_panel(ui_actions, resumed=False)
                self.last_kid_kind = "PROJECT_PICK"
                return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": directive}

            if ("wrap" in norm or "pause" in norm) and self.project:
                self.phase = "WRAP"
                self.last_kid_kind = "PROJECT_PICK"
                return {
                    "kind": self.last_kid_kind,
                    "ui": ui_actions,
                    "directive": (
                        f"Book '{self.project.get('title')}' is saved ({projects.total_panels(self.project)} panels) and ready to download as a PDF "
                        "using the PDF button on the Comic pane! Give a crisp 1-sentence wrap-up noting what's queued for next session."
                    ),
                }

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
                return {
                    "kind": self.last_kid_kind,
                    "ui": ui_actions,
                    "directive": f"Word '{raw}' is added to the box. In ONE short sentence, ask them to finish the complete sentence and hit Enter.",
                }

            # Check if tapping an Epic / Medium / Saved Book Project!
            if any(k in norm for k in ("continue ", "full comic book", "graphic novel", "codex", "field guide", "pitch")):
                self.last_kid_kind = "PROJECT_PICK"
                self.avoidance_streak = 0
                self.refusal_streak = 0
                proj_ui, proj_dir = self.start_or_resume_project(raw)
                if proj_dir:
                    return {"kind": self.last_kid_kind, "ui": proj_ui, "directive": proj_dir}

            # Quick Activity / Mini-Game selection
            self.last_kid_kind = "PROJECT_PICK"
            self.phase = "BUILDING"
            self.active_mechanic = raw
            self.avoidance_streak = 0
            self.refusal_streak = 0
            ui_actions.append({"type": "goal", "text": self.goal_badge()})
            if "game" in norm or "mini-game" in norm:
                directive = (
                    f"{self.name} chose '{raw}'. Call build_activity NOW with a concrete spec where EVERY round requires "
                    "typing or repairing a complete sentence (never multiple-choice clicking), AND while it builds (~30s), put a "
                    "2-kernel Sentence Combining warm-up card on screen (show_card + ask_input) so Sentence 1 starts right now."
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
                    f"{self.name} picked '{raw}'. Start it immediately (call comic_new with 3 panels if it's a strip). "
                    "A starter card is already on screen. In ONE plain sentence, invite them to combine Option A or type their own complete first sentence."
                )
            return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": directive}

        # ---------------- 3. TURN-1 GREETING ----------------
        if idx == 0 and norm in GREETINGS:
            self.last_kid_kind = "GREETING"
            self.phase = "BUILDING"
            self.prev_norm_text = norm
            opts = self._opening_options(opening_ideas)
            scaf = generate_combine_scaffold(self.rec, [], "", self.rung)
            card_txt = (
                "Choose a project scale above:\n"
                "  • FULL COMIC BOOK / CODEX (Multi-Week · Saves Progress · Printable PDF Book)\n"
                "  • QUICK SPRINT / MINI-GAME (10 Minutes Today)\n\n"
                "Or jump straight in by combining these into 1 complete sentence with 'when' or 'so':\n"
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
                        "prompt": "Pick a long-term book project (saves & exports PDF) or a quick 10-minute build:",
                        "options": opts,
                    },
                }
            )
            ui_actions.append({"type": "item", "item": {"id": "forge", "kind": "card", "title": "Studio Menu · Epic PDF Books or Quick Sprints", "text": card_txt}})
            ui_actions.append(
                {
                    "type": "input",
                    "mode": "type",
                    "prompt": "Tap a project above (like 'Start a Full Comic Book'), or type one complete sentence right now to start.",
                }
            )
            self.ui_locked_this_turn.update({"show_choices", "show_card", "ask_input"})
            directive = (
                f"First turn! {self.name} said '{raw}'. Multi-scale project choices (including 'Start a Full Comic Book' with Beginning-Middle-End story arc & PDF export, "
                "plus quick 10-minute sprints) AND a quick-start sentence card are ALREADY on screen. "
                "Do NOT call draw and do NOT ask wh- interview questions. In at most TWO short, plain sentences: introduce yourself honestly as Gemini "
                "(an AI tutor made by Google) and tell them they can start/continue a multi-chapter PDF Comic Book or Codex, or jump straight in with one complete sentence."
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
                scaf = generate_combine_scaffold(self.rec, self.active_story, "", "B3.1_compound", spine_context=self.spine_summary())
                ui_actions.append({"type": "goal", "text": self.goal_badge()})
                ui_actions.append(
                    {
                        "type": "item",
                        "item": {
                            "id": "pivot_choices",
                            "kind": "choices",
                            "prompt": "Switch scale or format:",
                            "options": ["Start a Full Comic Book (PDF)", "Build a playable mini-game", "2-sentence quick sprint"],
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
                        "prompt": "Tap a different project above, or type 1 complete sentence to run the 2-sentence sprint.",
                    }
                )
                self.ui_locked_this_turn.update({"show_choices", "show_card", "ask_input"})
                directive = (
                    f"{self.name} pushed back ('{raw}'). Respect 'no' immediately—zero nagging, zero pep talks, zero babyish pivots. "
                    "Say ONE short plain line ('Fair enough, scrapping that.') and offer the options on screen: start a full saved Comic Book, "
                    "code a live mini-game, or knock out just two quick sentences."
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
                    "either code a quick custom game around any topic named in one sentence, or pause cleanly for today."
                )
            return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": directive}

        # ---------------- 5. TURN-1 TOPIC NAMING (e.g. "comic book" or "minecraft") ----------------
        if idx == 0 and ("comic" in norm or "graphic novel" in norm or "book" in norm) and len(wlist) <= 4:
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
            ui_actions.append(
                {
                    "type": "item",
                    "item": {
                        "id": "open_choices",
                        "kind": "choices",
                        "prompt": f"Want to make '{raw.title()}' a full multi-chapter PDF Comic Book or a quick 3-panel strip?",
                        "options": ["Start a Full Comic Book (Save & PDF)", "Quick 3-Panel Strip (10 min)"],
                    },
                }
            )
            ui_actions.append(
                {
                    "type": "item",
                    "item": {
                        "id": "forge",
                        "kind": "card",
                        "title": f"{raw.title()} · Sentence 1",
                        "text": f"Combine these two lines with {_fmt_conns(scaf['connectors'])}, OR write your own complete sentence about {raw}:\n  1. {scaf['kernel_1']}\n  2. {scaf['kernel_2']}",
                    },
                }
            )
            ui_actions.append(
                {
                    "type": "input",
                    "mode": "type",
                    "prompt": "Tap 'Start a Full Comic Book' for a full saved PDF book, or type Sentence 1 right now.",
                }
            )
            self.ui_locked_this_turn.update({"show_choices", "show_card", "ask_input"})
            directive = (
                f"{self.name} named '{raw}'. Do NOT ask conversational questions ('what do you like to build?'). "
                "In ONE plain sentence, tell them they can tap 'Start a Full Comic Book' to turn it into a multi-chapter PDF graphic novel, "
                "or type one complete sentence right now to render Scene 1."
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
            if self.phase == "OPENING":
                self.phase = "BUILDING"
            self.prev_norm_text = norm
            self.draw_unlocked = False

            scaf = generate_combine_scaffold(self.rec, self.active_story, self.engaged_draft, self.rung, spine_context=self.spine_summary())
            ui_actions.append({"type": "goal", "text": self.goal_badge()})

            if self.avoidance_streak == 1:
                card_title = (
                    f"Story Beat Helper — Combine into 1 Complete Sentence"
                    if (self.active_story or self.project)
                    else f"Sentence Forge ({self.goal_done + 1} of {self.goal_target}) — Full Sentences Only"
                )
                card_txt = (
                    f"Combine these two lines into ONE complete sentence using {_fmt_conns(scaf['connectors'])}\n"
                    f"(or write your own complete sentence with a Who + Does What):\n"
                    f"  1. {scaf['kernel_1']}\n"
                    f"  2. {scaf['kernel_2']}"
                )
                ui_actions.append({"type": "item", "item": {"id": "forge", "kind": "card", "title": card_title, "text": card_txt}})
                ui_actions.append({"type": "input", "mode": "type", "prompt": scaf["ask_prompt"], "prefill": ""})
                self.ui_locked_this_turn.update({"show_card", "ask_input"})
                directive = (
                    f"DISENGAGEMENT / MINIMAL INPUT ('{raw}'): HARD ESCAPE EXTINCTION + ANTECEDENT SCAFFOLD. "
                    "Do NOT draw anything, do NOT praise or joke about a 1-word answer, and NEVER invent babyish animal trivia. "
                    "A 2-kernel Sentence Combining card is ALREADY on screen. "
                    f"In ONE plain sentence, state that one-word/idk inputs don't advance the build, and invite combining the two lines on screen "
                    f"with {_fmt_conns(scaf['connectors'])} (or typing a full sentence)."
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
                        "item": {"id": "avoid_choices", "kind": "choices", "prompt": "Or switch format:", "options": ["Build a playable mini-game instead"]},
                    }
                )
                ui_actions.append({"type": "input", "mode": "type", "prompt": "Finish the pre-filled sentence in the box and end with a period.", "prefill": starter})
                self.ui_locked_this_turn.update({"show_card", "show_choices", "ask_input"})
                directive = (
                    f"SECOND CONSECUTIVE MINIMAL INPUT ('{raw}'). Zero nagging, zero animal trivia, zero drawing. "
                    f"'{starter}' is pre-filled in the typing box. In ONE calm sentence, invite finishing the sentence in the box or tapping to switch to a live game."
                )
            else:
                starter = scaf["kernel_1"].rstrip(".!?") + " so "
                ui_actions.append(
                    {
                        "type": "item",
                        "item": {"id": "avoid_choices", "kind": "choices", "prompt": "Pick one:", "options": ["Build a custom mini-game", "Pause here for today"]},
                    }
                )
                ui_actions.append({"type": "input", "mode": "type", "prompt": "Finish this 1 sentence to unlock the scene, or pick an option above.", "prefill": starter})
                self.ui_locked_this_turn.update({"show_choices", "ask_input"})
                directive = (
                    f"REPEATED AVOIDANCE ({self.avoidance_streak}x, '{raw}'). In ONE respectful sentence, offer finishing the one started sentence, "
                    "switching to a live game, or pausing cleanly for today."
                )
            return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": directive}

        # ---------------- 7. GENUINE WRITING ATTEMPTS (Syntactic Evaluation) ----------------
        if self.phase == "OPENING":
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
                        "text": (
                            f"Your draft:\n  \"{raw}\"\n\n"
                            "Fix: Replace 'and then' with a period + capital letter to make crisp separate sentences, "
                            "OR link cause-and-effect cleanly with 'when', 'because', or 'so'."
                        ),
                    },
                }
            )
            ui_actions.append(
                {
                    "type": "input",
                    "mode": "type",
                    "prompt": "Edit your draft right in the box: replace 'and then' with periods (or 'when'/'because'/'so').",
                    "prefill": fixed_prefill,
                }
            )
            self.ui_locked_this_turn.update({"show_card", "ask_input"})
            directive = (
                f"ENGAGED RUN-ON: {self.name} wrote a multi-event chain ('{raw}'). Keep 100% of their idea! "
                "Do NOT draw yet. Their exact text is pre-filled in the input box so they don't have to retype it. "
                "In 1–2 plain sentences, explain that chaining with 'and then' jams multiple moments together—ask them to split with a period + capital "
                "(or link with 'when'/'because') right in the box."
            )
            return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": directive}

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
                frame = f"{clean_d}, " if re.match(r"^(in|on|at|under|inside|when|after|before|if|because)\b", clean_d.lower()) else f"{clean_d} "
                verb_chips = ["launches", "explodes", "guards", "crashes"]

            if self.hint_step == 1:
                ui_actions.append({"type": "input", "mode": "type", "prompt": f"{gap_explain} (with a capital and period) to lock it in.", "prefill": frame if "________" not in frame else ""})
                self.ui_locked_this_turn.add("ask_input")
                directive = (
                    f"ENGAGED FRAGMENT (Hint Step 1/3): {self.name} wrote '{raw}' (draft: '{self.engaged_draft}'). "
                    "NEVER switch topics and NEVER dictate a finished sentence to copy. "
                    f"Their words are pre-filled in the box. In ONE plain sentence, say: {gap_explain} so it's a complete sentence."
                )
            elif self.hint_step == 2:
                ui_actions.append({"type": "item", "item": {"id": "forge", "kind": "card", "title": "Finish Your Sentence Frame", "text": f"Build on your exact words:\n  \"{frame}________.\""}})
                ui_actions.append({"type": "input", "mode": "type", "prompt": "Finish your pre-filled sentence in the box and end with a period.", "prefill": frame.replace("________ ", "")})
                self.ui_locked_this_turn.update({"show_card", "ask_input"})
                directive = "ENGAGED FRAGMENT (Hint Step 2/3): Point briefly to the sentence frame built from their words and ask for the missing action + period."
            else:
                ui_actions.append({"type": "item", "item": {"id": "forge", "kind": "card", "title": "Pick an Action Word & Finish the Sentence", "text": f"Your start:\n  \"{frame}________.\""}})
                ui_actions.append({"type": "item", "item": {"id": "verb_bank", "kind": "choices", "prompt": "Tap a word to drop into your box, then finish the sentence:", "options": verb_chips[:3]}})
                ui_actions.append({"type": "input", "mode": "type", "prompt": "Finish the complete sentence in the box (capital at start, period at end).", "prefill": frame.replace("________ ", "")})
                self.ui_locked_this_turn.update({"show_card", "show_choices", "ask_input"})
                directive = f"ENGAGED FRAGMENT (Hint Step 3/3): Word-bank chips ({', '.join(verb_chips[:3])}) are on screen. Invite tapping one or choosing their own to finish the complete sentence."
            return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": directive}

        # 7C. COMPLETE CLAUSE MISSING ONLY CAPITAL / END PUNCTUATION
        if missing_cap or missing_end:
            self.last_kid_kind = "CONVENTION_ONLY"
            self.draw_unlocked = False
            self.hint_step = min(3, self.hint_step + 1)
            self.had_revision = True
            needed = []
            if missing_cap:
                needed.append("a capital letter at the start")
            if missing_end:
                needed.append("end punctuation (. ! or ?)")
            need_str = " and ".join(needed)
            ui_actions.append({"type": "input", "mode": "type", "prompt": f"Complete thought! Add {need_str} right in the box and hit Enter to lock it in.", "prefill": raw})
            self.ui_locked_this_turn.add("ask_input")
            directive = (
                f"COMPLETE CLAUSE, CONVENTION EDIT NEEDED: '{raw}' has a full who + action, only missing {need_str}. "
                f"Exact draft is pre-filled in the box so fixing takes 1 second. Credit the complete thought and ask for {need_str}."
            )
            return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": directive}

        # ---------------- 7D. FULL, PUNCTUATED COMPLETE SENTENCE! ----------------
        if self.hint_step == 0:
            self.first_try_streak += 1
        self.hint_step = 0
        self.engaged_draft = ""
        self.active_story.append(raw)

        # CASE I: Advancing the Causal Story Spine of a Full Graphic Novel!
        if self.project and self.project.get("stage", "").startswith("spine_"):
            self.last_kid_kind = "SPINE_BEAT_COMPLETE"
            self.draw_unlocked = False  # Don't draw panels until Story Spine is mapped!
            st = self.project["stage"]
            sp = self.project.setdefault("spine", {})
            if st == "spine_beginning":
                sp["beginning"] = raw
                if self.project.get("title") in ("Untitled Graphic Novel", "Untitled Project", ""):
                    self.project["title"] = _infer_book_title(raw)
                self.project["stage"] = "spine_middle"
                if not self.test_mode:
                    projects.save_project(self.project)
                ui_actions.append({"type": "item", "item": projects.project_ui_payload(self.project)})
                ui_actions.append({"type": "goal", "text": self.goal_badge()})
                ui_actions, directive = self._prompt_spine_step(ui_actions, resumed=False)
                return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": directive}

            if st == "spine_middle":
                # Check causal link! Encourage 'but/when/because' if missing, or accept if causally clear
                sp["middle"] = raw
                self.project["stage"] = "spine_end"
                if not self.test_mode:
                    projects.save_project(self.project)
                ui_actions.append({"type": "item", "item": projects.project_ui_payload(self.project)})
                ui_actions.append({"type": "goal", "text": self.goal_badge()})
                ui_actions, directive = self._prompt_spine_step(ui_actions, resumed=False)
                return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": directive}

            # spine_end -> Story Spine is COMPLETE! Zoom into Chapter 1, Panel 1!
            sp["end"] = raw
            sp["complete"] = True
            self.project["stage"] = "drafting_panels"
            if not self.test_mode:
                projects.save_project(self.project)
            ui_actions.append({"type": "item", "item": projects.project_ui_payload(self.project)})
            ui_actions.append({"type": "goal", "text": self.goal_badge()})
            ui_actions, next_dir = self._prompt_next_book_panel(ui_actions, resumed=False)
            return {
                "kind": self.last_kid_kind,
                "ui": ui_actions,
                "directive": (
                    "FULL STORY SPINE LOCKED IN (Beginning → Middle → End)! Congratulate the causal story blueprint briefly in 1 plain sentence "
                    "(noting it's already saved in their book PDF on the right) and transition straight into zooming in on Chapter 1, Panel 1! "
                    + next_dir
                ),
            }

        # CASE II: Verified Complete Panel / Sentence!
        self.last_kid_kind = "COMPLETE_SENTENCE"
        self.draw_unlocked = True
        self.goal_done += 1

        if self.goal_done == 1 and self.rung == "B3.1_simple":
            self.rung = "B3.1_compound"
        elif self.goal_done >= 2 and self.rung in ("B3.1_simple", "B3.1_compound"):
            self.rung = "B3.1_complex"

        best_ms = self._pick_best_misspelling()
        target_for_today = self.session_panels_target if self.project else self.goal_target
        trigger_word_study = (
            not self.word_study_done
            and best_ms is not None
            and (self.goal_done >= target_for_today or self.goal_done >= 2)
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
                f"COMPLETE SENTENCE ({self.goal_done}/{target_for_today}): '{raw}'! "
                f"Transition into a quick 60-second Word Forge on '{ws['word']}' (they wrote '{ws['wrote']}'). "
                f"The Cover-Copy-Compare card ('{ws['parts']}' — {ws['note']}) is ALREADY on screen and auto-covers when they start typing/writing. "
                f"Give ONE plain sentence explaining why '{ws['word']}' is spelled '{ws['parts']}', and ask them to write '{ws['word']}' once from memory."
            )
            return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": directive}

        # Multi-session Book Project Panel Progression
        if self.project:
            ui_actions.append({"type": "goal", "text": self.goal_badge()})
            if self.goal_done >= self.session_panels_target:
                self.phase = "WRAP"
                total_p = projects.total_panels(self.project) + 1
                ui_actions.append(
                    {
                        "type": "item",
                        "item": {
                            "id": "done_choices",
                            "kind": "choices",
                            "prompt": f"Today's slice complete ({total_p} total panels saved in your book PDF)!",
                            "options": ["Keep going — add 3 more panels", f"Download PDF & save for {self.parent_title}"],
                        },
                    }
                )
                self.ui_locked_this_turn.add("show_choices")
                return {
                    "kind": self.last_kid_kind,
                    "ui": ui_actions,
                    "directive": (
                        f"Panel {total_p} is rendering and auto-saved into '{self.project.get('title')}'! "
                        "Give brief, specific process feedback on today's progress, mention they can click 'Download PDF' on the Comic pane anytime "
                        "for the latest issue, and let them choose whether to keep going for 3 more panels or save here for next time."
                    ),
                }
            ui_actions, next_dir = self._prompt_next_book_panel(ui_actions, resumed=False)
            return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": next_dir}

        # Quick Sprint Completion
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
                        "options": ["Turn this into a Full Multi-Chapter PDF Comic Book", f"Save & print for {self.parent_title}"],
                    },
                }
            )
            self.ui_locked_this_turn.add("show_choices")
            directive = (
                f"COMPLETE SENTENCE ({self.goal_done}/{self.goal_target} — GOAL HIT!): '{raw}'! "
                "Call save_piece so the finished work is saved! Give brief process feedback and let them choose whether to expand this into "
                "a full saved Graphic Novel PDF or wrap up."
            )
            return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": directive}

        scaf = generate_combine_scaffold(self.rec, self.active_story, "", self.rung)
        conn_label = "when, because, or if" if self.rung == "B3.1_complex" else "but, so, or when"
        card_txt = (
            f"Next beat — combine these two ideas with {conn_label}, OR write your own complete sentence for Step {self.goal_done + 1}:\n"
            f"  1. {scaf['kernel_1']}\n"
            f"  2. {scaf['kernel_2']}"
        )
        ui_actions.append({"type": "goal", "text": self.goal_badge()})
        ui_actions.append({"type": "item", "item": {"id": "forge", "kind": "card", "title": f"Step {self.goal_done + 1} of {self.goal_target} · Level Up with '{conn_label}'", "text": card_txt}})
        ui_actions.append({"type": "input", "mode": "type", "prompt": f"Type Sentence {self.goal_done + 1} using {conn_label} (combine the card lines, or write your own complete sentence).", "prefill": ""})
        self.ui_locked_this_turn.update({"show_card", "ask_input"})
        directive = (
            f"COMPLETE SENTENCE ({self.goal_done}/{self.goal_target}): '{raw}'! "
            f"Step {self.goal_done + 1} card is ALREADY on screen stretching syntax to Ontario B3.1 ({self.rung}: '{conn_label}'). "
            f"In 1–2 plain sentences, react specifically to what happened in the scene and invite Sentence {self.goal_done + 1} using {conn_label}."
        )
        return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": directive}

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
                    return {
                        "ok": True,
                        "status": "Handled automatically by the project/panel renderer. Do not repeat yourself.",
                    }
                return {
                    "blocked": True,
                    "reason": (
                        f"Drawing blocked by education gate: last student input class was {self.last_kid_kind!r}, not a complete punctuated panel sentence. "
                        "Tell them plainly what their sentence needs so the panel can render."
                    ),
                }
            self.draw_unlocked = False
            return None

        if name in ("write_on_page", "rewrite_page") and self.last_kid_kind != "COMPLETE_SENTENCE" and self.phase != "WRAP":
            return {
                "blocked": True,
                "reason": "Wait until the student finishes and punctuates the complete sentence before adding it to the writing page.",
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
                        "reason": f"Blocked choices {bad}: never offer multi-word phrases or complete sentences while constructing a sentence.",
                    }
            else:
                bad = [
                    o
                    for o in opts
                    if len(_words(o)) >= 7
                    and re.search(r"[.!?]$", o)
                    and not re.match(r"^(build|start|continue|make|try|switch|add|save|pause|wrap|turn|keep|download)\b", o.lower())
                ]
                if bad:
                    return {"blocked": True, "reason": f"Blocked choices {bad}: choices must be project formats or single words."}
            return None

        if name == "ask_input":
            p = (args.get("prompt") or "").strip()
            if re.search(r'(type|write|copy)[^"]*["\'][A-Z][^"\']{12,}[.!?]["\']', p, re.I):
                args["prompt"] = "Write your own complete sentence (Who + Does What + Capital & .)."
            if p.endswith("?") and "sentence" not in p.lower() and self.phase in ("BUILDING", "STORY_SPINE"):
                args["prompt"] = f"Write one complete sentence: {p}"
            return None

        return None
