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
from .config import FALLBACK_MODEL, FAST_MODEL, api_key
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
        + (f"BOOK CONTEXT:\n{spine_context}\n" if spine_context else "")
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
    stop = {"the", "a", "an", "in", "on", "at", "when", "once", "there", "was", "is", "were", "he", "she", "they", "his", "her", "deep"}
    picked = [w.capitalize() for w in words if w.lower() not in stop][:4]
    return " ".join(picked) if len(picked) >= 2 else "Original Graphic Novel"


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
        self.word_target: dict[str, Any] | None = None
        self.word_study_done: bool = False
        self.word_study_tries: int = 0
        self.studied_words_today: set[str] = set()

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
            kind = self.project.get("kind", "")
            stage = self.project.get("stage", "")
            pcount = projects.total_panels(self.project)
            if stage.startswith("spine_"):
                step = {"spine_beginning": "1/3", "spine_middle": "2/3", "spine_end": "3/3"}.get(stage, "1/3")
                return f"Story Spine: {step} · Tier {tier}"
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

    def resume_loaded_project(self, proj: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
        """Genre-aware resume for any saved project (Graphic Novel, Research Codex, or Persuasive Pitch)."""
        self.project = proj
        for p in projects.all_panels(proj)[-6:]:
            if p.get("caption"):
                self.active_story.append(p["caption"])
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
        self.session_panels_target = 4
        return self._prompt_next_book_panel(ui, resumed=True)

    def start_or_resume_project(self, choice_label: str) -> tuple[list[dict[str, Any]], str]:
        ui: list[dict[str, Any]] = []
        low = choice_label.lower()

        if low.startswith("continue ") and not self.test_mode:
            saved = projects.list_projects()
            if saved:
                return self.resume_loaded_project(saved[0])

        if "full comic book" in low or "graphic novel" in low:
            self.project = projects.create_project("epic_graphic_novel", self.name, self.parent_title, persist=not self.test_mode)
            self.phase = "STORY_SPINE"
            # Session 1 maps the 3-Act Spine + first 2 illustrated panels + Word Forge (~12-15 min)
            self.session_panels_target = 2
            ui.append({"type": "item", "item": projects.project_ui_payload(self.project)})
            ui.append({"type": "goal", "text": self.goal_badge()})
            return self._prompt_spine_step(ui, resumed=False)

        if "codex" in low or "field guide" in low or "fact" in low:
            self.project = projects.create_project(
                "epic_codex", self.name, self.parent_title, title=f"{self.name}'s Research & Invention Codex", persist=not self.test_mode
            )
            self.phase = "BUILDING"
            ui.append({"type": "item", "item": projects.project_ui_payload(self.project)})
            return self._prompt_codex_step(ui, new_entry=True)

        if "pitch" in low or "why we should" in low or "persuasive" in low:
            self.project = projects.create_project(
                "medium_pitch", self.name, self.parent_title, title=f"Official Case File for {self.parent_title}", persist=not self.test_mode
            )
            self.phase = "BUILDING"
            self.tree_step = 0
            self.session_panels_target = 4
            ui.append({"type": "item", "item": projects.project_ui_payload(self.project)})
            return self._prompt_pitch_step(ui)

        return ui, ""

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
        """Drives SRSD POW+TREE 4-Page Persuasive Book (Topic/Claim -> Reason -> Counter-Argument -> Ending)."""
        assert self.project is not None
        ui.append({"type": "goal", "text": self.goal_badge()})
        steps = [
            (
                f"Page 1 of 4 · T = Topic & Bold Claim (for {self.parent_title})",
                f"Pick something real or hilariously ambitious to pitch to {self.parent_title} (e.g. a backyard contraption, a new game rule, a late-night build).\n"
                "Write Page 1's clear Claim in 1 complete sentence (e.g. 'We need to build ...' or 'Our house should have ...').",
                f"Write Page 1: your bold claim for {self.parent_title} in one complete sentence.",
            ),
            (
                "Page 2 of 4 · R = Strongest Reason & Evidence ('because / since')",
                "A real pitch proves WHY it works.\nWrite 1–2 complete sentences using 'because' or 'since' giving your strongest concrete reason.",
                "Write Page 2 using 'because' or 'since' to prove why your idea works.",
            ),
            (
                f"Page 3 of 4 · E = Beat {self.parent_title}'s Biggest Objection ('although / even though')",
                f"Smart persuaders answer the objection BEFORE {self.parent_title} says it!\n"
                f"Start with 'Although' or 'Even though' to name what {self.parent_title} might worry about, and explain how you solve it.",
                "Start Page 3 with 'Although' or 'Even though' to answer the biggest objection.",
            ),
            (
                "Page 4 of 4 · E = Ending & Final Deal ('so / if')",
                "Close the case! Write 1 strong final sentence using 'if' or 'so' proposing the exact deal or first test.",
                "Write Page 4's closing deal sentence using 'if' or 'so' to finish the Pitch PDF!",
            ),
        ]
        title, body, ask = steps[min(self.tree_step, 3)]
        ui.append({"type": "item", "item": {"id": "forge", "kind": "card", "title": title, "text": body}})
        ui.append({"type": "input", "mode": "type", "prompt": ask, "prefill": ""})
        self.ui_locked_this_turn.update({"show_card", "ask_input"})
        return ui, f"Persuasive Pitch Book (SRSD TREE) step {self.tree_step + 1}/4: {ask}"

    def _prompt_spine_step(self, ui: list[dict[str, Any]], resumed: bool = False) -> tuple[list[dict[str, Any]], str]:
        assert self.project is not None
        stage = self.project.get("stage", "spine_beginning")
        sp = self.project.get("spine", {})
        self.phase = "STORY_SPINE"

        if stage == "spine_beginning":
            card_txt = (
                "Great comic books map the whole causal story BEFORE Panel 1 (SRSD Story Blueprint):\n"
                "  • ACT I — BEGINNING (Who + Where + Goal): Who is the hero, where are they, and what do they want?\n"
                "  • ACT II — MIDDLE ('BUT / WHEN / BECAUSE'): What goes wrong because of Act I?\n"
                "  • ACT III — END ('SO / FINALLY'): How does the final showdown resolve?\n\n"
                "Step 1: Write 1–2 complete sentences for ACT I (or tap the Mic to speak it first, then edit in the box)."
            )
            ui.append({"type": "item", "item": {"id": "forge", "kind": "card", "title": "Graphic Novel Blueprint · Step 1 of 3: The Beginning", "text": card_txt}})
            ui.append({"type": "input", "mode": "type", "prompt": "Write 1–2 complete sentences for THE BEGINNING (who your hero is, where they are, and their goal).", "prefill": ""})
            self.ui_locked_this_turn.update({"show_card", "ask_input"})
            return ui, (
                f"{'Resuming' if resumed else 'Starting'} {self.name}'s multi-chapter Graphic Novel (saves across weeks & exports to PDF!). "
                "Explain in 1–2 plain sentences that mapping Beginning → Middle → End first makes every chapter connect, and ask for ACT I (The Beginning)."
            )

        if stage == "spine_middle":
            card_txt = (
                f"ACT I (Locked): \"{sp.get('beginning','')}\"\n\n"
                "ACT II — THE MIDDLE (Causal Complication — Required Connector: 'But', 'When', or 'Because'):\n"
                "  Strong stories link by CAUSE, never 'and then'.\n"
                "  Write 1–2 complete sentences using 'But', 'When', 'Until', or 'Because' showing how everything goes sideways!"
            )
            ui.append({"type": "item", "item": {"id": "forge", "kind": "card", "title": "Graphic Novel Blueprint · Step 2 of 3: The Middle ('But / When')", "text": card_txt}})
            ui.append({"type": "input", "mode": "type", "prompt": "Write ACT II using 'but', 'when', 'until', or 'because' so it links causally to Act I.", "prefill": ""})
            self.ui_locked_this_turn.update({"show_card", "ask_input"})
            return ui, f"Act I locked. Ask for ACT II (THE MIDDLE) linked causally with 'but', 'when', or 'because'."

        card_txt = (
            f"ACT I: \"{sp.get('beginning','')}\"\n"
            f"ACT II: \"{sp.get('middle','')}\"\n\n"
            "ACT III — THE END (Causal Climax & Resolution — Required Connector: 'So', 'Therefore', 'Finally', or 'When'):\n"
            "  Write 1–2 complete sentences showing how the climax resolves Act II—then we zoom into Chapter 1, Panel 1!"
        )
        ui.append({"type": "item", "item": {"id": "forge", "kind": "card", "title": "Graphic Novel Blueprint · Step 3 of 3: The End ('So / Finally')", "text": card_txt}})
        ui.append({"type": "input", "mode": "type", "prompt": "Write ACT III using 'so', 'finally', or 'when'—then we zoom into Chapter 1, Panel 1!", "prefill": ""})
        self.ui_locked_this_turn.update({"show_card", "ask_input"})
        return ui, "Act II locked. Ask for ACT III (THE END) using 'so', 'finally', or 'when', then we zoom into Panel 1."

    def _prompt_next_book_panel(self, ui: list[dict[str, Any]], resumed: bool = False) -> tuple[list[dict[str, Any]], str]:
        assert self.project is not None
        self.phase = "BUILDING"
        self.tier_nudged_this_item = False
        pcount = projects.total_panels(self.project)
        next_pnum = pcount + 1
        ch_num = len(self.project.get("chapters") or [1])
        tier = self.current_tier()
        tier_info = ct.TIER_DESCRIPTIONS.get(tier, ct.TIER_DESCRIPTIONS[1])
        sp = self.project.get("spine") or {}

        act_focus = sp.get("beginning", "") if ch_num <= 2 else (sp.get("middle", "") if ch_num <= 10 else sp.get("end", ""))
        rung_for_scaf = "B3.1_complex" if tier >= 2 else "B3.1_simple"
        scaf = generate_combine_scaffold(self.rec, self.active_story, "", rung_for_scaf, spine_context=self.spine_summary())

        if tier == 1:
            req_line = "Panel Goal: 1 complete sentence (Who + Does What + Capital & .) zooming into JUST this single moment."
        elif tier == 2:
            req_line = f"Panel Goal ({tier_info['name']}): Include {_fmt_conns(scaf['connectors'])} to show cause or timing!"
        elif tier == 3 and next_pnum % 2 == 0:
            req_line = (
                f"Panel Goal ({tier_info['name']}): Include punctuated character dialogue in quotes "
                '(e.g. "Watch the floor!" shouted Max.) so a real speech bubble renders on the panel!'
            )
        elif tier >= 4:
            req_line = (
                f"Panel Goal ({tier_info['name']}): Open with a scene-setting phrase + comma (e.g. 'Beneath the bridge, ...'), "
                "use a vivid action verb, and include causal flow or dialogue!"
            )
        else:
            req_line = f"Panel Goal ({tier_info['name']}): {tier_info['prompt_hint']}"

        card_txt = (
            (f"Current Act Arc: \"{act_focus}\"\n\n" if act_focus else "")
            + f"{req_line}\n\n"
            f"Idea Sparks (combine these, or write/speak your own Panel {next_pnum} beat):\n"
            f"  1. {scaf['kernel_1']}\n"
            f"  2. {scaf['kernel_2']}"
        )
        ui.append({"type": "item", "item": {"id": "forge", "kind": "card", "title": f"{self.project.get('title','Comic Book')} · Ch.{ch_num}, Panel {next_pnum}", "text": card_txt}})
        ui.append({"type": "input", "mode": "type", "prompt": f"Panel {next_pnum}: {tier_info['prompt_hint']}", "prefill": ""})
        self.ui_locked_this_turn.update({"show_card", "ask_input"})
        return ui, (
            f"{'Resumed' if resumed else 'Zoomed into'} {self.project.get('title')} — Ch.{ch_num}, Panel {next_pnum} (Mastery Tier {tier}). "
            f"Invite Panel {next_pnum} concisely: {req_line}"
        )

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
    ) -> dict[str, Any]:
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

        # ---------------- 2. TAP INPUTS ----------------
        if how == "tap":
            self.prev_norm_text = norm
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
            scaf = generate_combine_scaffold(self.rec, [], "", self.rung)
            card_txt = (
                "Pick a project above:\n"
                "  • FULL COMIC BOOK (Beginning → Middle → End Story Arc · Up to 100 Panels · PDF Book)\n"
                "  • 3-SOURCE FACT & INVENTION CODEX (Reading + Science/World Facts → Illustrated PDF)\n"
                "  • 4-PAGE PERSUASIVE PITCH (Build an Illustrated Case File)\n\n"
                "Or jump straight in by combining these into 1 complete sentence with 'when' or 'so':\n"
                f"  1. {scaf['kernel_1']}\n  2. {scaf['kernel_2']}"
            )
            ui_actions.append({"type": "goal", "text": self.goal_badge()})
            ui_actions.append({"type": "item", "item": {"id": "open_choices", "kind": "choices", "prompt": "Choose a multi-session PDF book or a quick build:", "options": opts}})
            ui_actions.append({"type": "item", "item": {"id": "forge", "kind": "card", "title": "Studio Menu · Narrative, Research Codex, Persuasive Pitch, or Game", "text": card_txt}})
            ui_actions.append({"type": "input", "mode": "type", "prompt": "Tap a project above, or type/speak one complete sentence right now to start."})
            self.ui_locked_this_turn.update({"show_choices", "show_card", "ask_input"})
            directive = (
                f"First turn! {self.name} said '{raw}'. Project choices (Full PDF Comic Book, 3-Source Fact Codex, 4-Page Pitch, Live Mini-Game) "
                "and a quick-start card are ALREADY on screen. Do NOT call draw and do NOT ask wh- interview questions. "
                "In at most TWO short, plain sentences: introduce yourself honestly as Gemini (an AI tutor made by Google) and invite picking a book/game or typing one complete sentence."
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
                ui_actions.append({"type": "input", "mode": "type", "prompt": f"{gap_explain} (with a capital and period) to lock it in.", "prefill": frame if "________" not in frame else ""})
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

        # 7C. CONVENTION CHECK (Start Capital, End Punctuation, AND B3.3 Dialogue Quotation Punctuation!)
        dialogue_punct_bad = bool(feats.get("has_dialogue") and feats.get("dialogue_punct_ok") is False)
        if missing_cap or missing_end or dialogue_punct_bad:
            self.last_kid_kind = "CONVENTION_ONLY"
            self.draw_unlocked = False
            self.hint_step = min(3, self.hint_step + 1)
            self.had_revision = True
            needed = []
            if missing_cap:
                needed.append("a capital letter at the start")
            if missing_end:
                needed.append("end punctuation (. ! or ?)")
            if dialogue_punct_bad:
                needed.append('dialogue punctuation (opening & closing quotes, capital at the start of the quote, and a comma/!/? inside the closing quote)')
            need_str = " and ".join(needed)
            ui_actions.append({"type": "input", "mode": "type", "prompt": f"Complete thought! Fix {need_str} right in the box and hit Enter.", "prefill": raw})
            self.ui_locked_this_turn.add("ask_input")
            return {
                "kind": self.last_kid_kind,
                "ui": ui_actions,
                "directive": f"CONVENTION EDIT NEEDED on '{raw}': ask concisely to add/fix {need_str} in the pre-filled box and hit Enter.",
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
        if self.hint_step == 0 and not self.tier_nudged_this_item:
            self.first_try_streak += 1
        self.hint_step = 0
        self.tier_nudged_this_item = False
        self.engaged_draft = ""
        self.active_story.append(raw)

        # CASE A: Advancing Graphic Novel Story Spine!
        if self.project and self.project.get("stage", "").startswith("spine_"):
            self.last_kid_kind = "SPINE_BEAT_COMPLETE"
            self.draw_unlocked = False
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
                sp["middle"] = raw
                self.project["stage"] = "spine_end"
                if not self.test_mode:
                    projects.save_project(self.project)
                ui_actions.append({"type": "item", "item": projects.project_ui_payload(self.project)})
                ui_actions.append({"type": "goal", "text": self.goal_badge()})
                ui_actions, directive = self._prompt_spine_step(ui_actions, resumed=False)
                return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": directive}

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
                "directive": "FULL CAUSAL STORY SPINE LOCKED IN! Acknowledge the 3-Act arc in 1 short sentence and zoom into Chapter 1, Panel 1! " + next_dir,
            }

        # CASE B: Advancing 3-Source Reading-to-Write Codex (`epic_codex`)!
        if self.project and self.project.get("kind") == "epic_codex":
            if self.codex_step == 0:
                # Completed Reading Inference Check (C2.3 / C3.2) -> Advance to Paragraph Sentence 1!
                self.had_inference = True
                self.last_kid_kind = "SPINE_BEAT_COMPLETE"
                self.draw_unlocked = False
                self.codex_step = 1
                ui_actions, directive = self._prompt_codex_step(ui_actions, new_entry=False)
                return {
                    "kind": self.last_kid_kind,
                    "ui": ui_actions,
                    "directive": f"Sharp inference ('{raw}')! Now transition to drafting the 3-sentence Codex Entry Paragraph (Sentence 1: Topic Sentence). " + directive,
                }
            if self.codex_step in (1, 2):
                self.codex_buf.append(raw)
                self.last_kid_kind = "SPINE_BEAT_COMPLETE"
                self.draw_unlocked = False
                self.codex_step += 1
                ui_actions, directive = self._prompt_codex_step(ui_actions, new_entry=False)
                return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": f"Sentence {self.codex_step - 1} locked into the paragraph! " + directive}

            # codex_step == 3 -> Assemble full 3-sentence expository paragraph & render Codex illustration!
            self.codex_buf.append(raw)
            full_paragraph = " ".join(self.codex_buf)
            self.codex_buf = []
            self.codex_step = 0
            self.had_synthesis = True
            self.last_kid_kind = "COMPLETE_SENTENCE"
            self.draw_unlocked = True
            self.goal_done += 1
            # Store full paragraph so auto_render_sentence saves the entire cohesive paragraph onto the Codex page!
            self.last_kid_text = full_paragraph
            if not self.word_study_done:
                return self._launch_word_forge(ui_actions, full_paragraph, full_paragraph=full_paragraph)
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
            return {
                "kind": self.last_kid_kind,
                "ui": ui_actions,
                "full_paragraph": full_paragraph,
                "directive": "Full 3-sentence informational paragraph synthesized from all 3 sources and rendering into the Codex PDF! Acknowledge the complete paragraph concisely and offer starting the next dossier or downloading the PDF.",
            }

        # CASE C: Advancing SRSD POW+TREE 4-Page Persuasive Pitch (`medium_pitch`)!
        if self.project and self.project.get("kind") == "medium_pitch":
            self.last_kid_kind = "COMPLETE_SENTENCE"
            self.draw_unlocked = True
            self.goal_done += 1
            self.tree_step += 1
            if self.tree_step >= 4:
                if not self.word_study_done:
                    return self._launch_word_forge(ui_actions, raw)
                self.phase = "WRAP"
                ui_actions.append({"type": "goal", "text": self.goal_badge()})
                ui_actions.append({"type": "item", "item": {"id": "done_choices", "kind": "choices", "prompt": "All 4 Persuasive Pitch Pages Complete!", "options": [f"Download Pitch PDF for {self.parent_title}"]}})
                self.ui_locked_this_turn.add("show_choices")
                return {
                    "kind": self.last_kid_kind,
                    "ui": ui_actions,
                    "directive": f"All 4 pages of the SRSD TREE Persuasive Pitch (Claim, Reason, Counter-Argument, Deal) are complete and ready to download as an illustrated PDF for {self.parent_title}!",
                }
            ui_actions, next_dir = self._prompt_pitch_step(ui_actions)
            return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": f"Page {self.tree_step} locked and rendering! " + next_dir}

        # CASE D: Graphic Novel Panel or Quick Sprint Sentence!
        self.last_kid_kind = "COMPLETE_SENTENCE"
        self.draw_unlocked = True
        self.goal_done += 1

        if self.goal_done == 1 and self.rung == "B3.1_simple":
            self.rung = "B3.1_compound"
        elif self.goal_done >= 2 and self.rung in ("B3.1_simple", "B3.1_compound"):
            self.rung = "B3.1_complex"

        target_for_today = self.session_panels_target if self.project else self.goal_target
        # Guaranteed Spaced Word Forge in EVERY session once >=2 sentences/panels are completed (or on error)!
        trigger_word_study = not self.word_study_done and (
            (self.misspellings and self.goal_done >= 2) or self.goal_done >= target_for_today
        )

        if trigger_word_study:
            return self._launch_word_forge(ui_actions, raw)

        if self.project:
            ui_actions.append({"type": "goal", "text": self.goal_badge()})
            if self.goal_done >= self.session_panels_target:
                self.phase = "WRAP"
                total_p = projects.total_panels(self.project) + 1
                ui_actions.append({"type": "item", "item": {"id": "done_choices", "kind": "choices", "prompt": f"Today's slice complete ({total_p} total panels in your PDF book)!", "options": ["Keep going — add 3 more panels", f"Download PDF & save for {self.parent_title}"]}})
                self.ui_locked_this_turn.add("show_choices")
                return {
                    "kind": self.last_kid_kind,
                    "ui": ui_actions,
                    "directive": f"Panel {total_p} is rendering into '{self.project.get('title')}'! Mention the live Download PDF button on the right and let them choose whether to add 3 more panels or save here.",
                }
            ui_actions, next_dir = self._prompt_next_book_panel(ui_actions, resumed=False)
            return {"kind": self.last_kid_kind, "ui": ui_actions, "directive": next_dir}

        if self.goal_done >= self.goal_target:
            self.phase = "WRAP"
            ui_actions.append({"type": "goal", "text": self.goal_badge()})
            ui_actions.append({"type": "item", "item": {"id": "done_choices", "kind": "choices", "prompt": "Goal complete! Want to:", "options": ["Turn this into a Full Multi-Chapter PDF Comic Book", f"Save & print for {self.parent_title}"]}})
            self.ui_locked_this_turn.add("show_choices")
            return {
                "kind": self.last_kid_kind,
                "ui": ui_actions,
                "directive": f"COMPLETE SENTENCE ({self.goal_done}/{self.goal_target} — GOAL HIT!): '{raw}'! Call save_piece and offer turning this into a Full PDF Comic Book or wrapping up.",
            }

        scaf = generate_combine_scaffold(self.rec, self.active_story, "", self.rung)
        conn_label = "when, because, or if" if self.rung == "B3.1_complex" else "but, so, or when"
        card_txt = f"Next beat — combine these two ideas with {conn_label}, OR write your own complete sentence for Step {self.goal_done + 1}:\n  1. {scaf['kernel_1']}\n  2. {scaf['kernel_2']}"
        ui_actions.append({"type": "goal", "text": self.goal_badge()})
        ui_actions.append({"type": "item", "item": {"id": "forge", "kind": "card", "title": f"Step {self.goal_done + 1} of {self.goal_target} · Level Up with '{conn_label}'", "text": card_txt}})
        ui_actions.append({"type": "input", "mode": "type", "prompt": f"Type Sentence {self.goal_done + 1} using {conn_label} (combine the card lines, or write your own complete sentence).", "prefill": ""})
        self.ui_locked_this_turn.update({"show_card", "ask_input"})
        return {
            "kind": self.last_kid_kind,
            "ui": ui_actions,
            "directive": f"COMPLETE SENTENCE ({self.goal_done}/{self.goal_target}): '{raw}'! React briefly to the scene and invite Sentence {self.goal_done + 1} using {conn_label}.",
        }

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
