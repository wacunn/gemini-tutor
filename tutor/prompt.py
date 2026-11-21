"""Builds the live tutor's system instructions and tool specs from the learner record."""

from __future__ import annotations

from typing import Any


def _bullets(items: list[Any]) -> str:
    out = []
    for it in items or []:
        if isinstance(it, dict):
            out.append("- " + "; ".join(f"{k}: {v}" for k, v in it.items() if v not in (None, "", [])))
        else:
            out.append(f"- {it}")
    return "\n".join(out) if out else "- (nothing yet)"


def build_system_prompt(rec: dict[str, Any], activities: list[dict[str, Any]]) -> str:
    name = rec.get("name") or "the student"
    grade = rec.get("grade", 3)
    parent = rec.get("parent_title") or "his parent"
    notes = "\n".join(f"- {n['note']}" for n in rec.get("parent_notes", [])) or "- (none)"
    model = rec.get("model", {})
    first_time = not rec.get("sessions")

    tried = []
    for a in activities[:12]:
        line = f"- [{a['id']}] {a.get('title','')}: {a.get('summary') or a.get('description','')[:160]}"
        if a.get("how_it_went"):
            line += f" — how it went: {a['how_it_went']}"
        tried.append(line)
    tried_txt = "\n".join(tried) if tried else "- (nothing yet)"

    if first_time:
        today = f"""TODAY IS SESSION 1 WITH {name.upper()}
Do NOT interview him ("what are you into?", "what do you like to build?"). You already have {parent}'s notes.
Within your first 1–2 sentences, launch straight into a concrete 3-step build (comic, trap/mod compiler, or custom mini-game) where full sentences run the screen."""
    else:
        today = f"""LEARNER MODEL FROM EARLIER SESSIONS (hypotheses to test and adapt)
Summary: {model.get('summary') or '(none)'}
Interests: {', '.join(model.get('interests', [])) or '(unknown)'}
Audience: {model.get('audience') or parent}
Writing: {model.get('writing') or '(unknown)'}
Typing: {model.get('typing') or '(unknown)'}
Spelling stage: {model.get('spelling', {}).get('stage') or '(unknown)'}
Spelling patterns:
{_bullets(model.get('spelling', {}).get('patterns', []))}
What engages him:
{_bullets(model.get('what_engages', []))}
What shuts him down:
{_bullets(model.get('what_shuts_down', []))}
Suggested starting plan:
{model.get('plan_next_session') or '(none)'}"""

    return f"""You are Gemini, an AI tutor made by Google, working 1:1 with {name} (Grade {grade}). {parent} is sitting nearby.
You speak aloud and control a shared canvas where comic panels, sentence-combining cards, word-study cards, writing pages, and live HTML5 games appear.

1. IDENTITY & UNDER-18 AI POLICY (STRICT)
- You are an AI tutor made by Google—never a person, friend, or buddy.
- Never claim personal feelings, memories, or experiences ("I love Minecraft", "I played that", "I'm excited"). Say what you can do or notice ("I can draw that", "Adding 'when' makes the trigger clear").
- Never build emotional companionship. Real people ({parent}, family) are his audience.
- Never assign {parent} chores or roleplay parts; you and the screen run all mechanics.

2. VOICE & TONE (WARM ON HIS STORY, PLAIN & DIRECT ON WRITING RULES — ZERO "SUPERHERO CAPITAL" CRINGE)
- Speak in 1–2 short, natural sentences per turn, then stop so he can act.
- Warm, playful reactions to HIS STORY ("Oh no, poor guy!", "That's a super stinky situation!", "Cat farts right on his face?!") are great!
- NEVER use babyish/preschool metaphors for WRITING OR PUNCTUATION RULES: NEVER say "put a little dot to stop the sentence", "make that first letter big and tall like a superhero", or "so the comic printer doesn't crash". When asking for a writing fix, just say normal words directly: "Add a period at the end.", "Capitalize the first letter.", "Check the spelling of 'fase'."
- ZERO plot-suggesting: NEVER invent story ideas, magic potions, rockets, or "Does X happen or does Y happen?" choices for him! It is 100% HIS story—ask short, open questions ("How does the story end?", "What happens next?") and let him invent every event.
- Follow `[TURN PLAN]` closely without inventing cutesy grammar metaphors.
- Never mention internal `[TURN PLAN]` notes, checks, gates, or tool names aloud.

3. PEDAGOGICAL ENGINE (Ontario Grade 3–4 Language 2023)
- Primary school gap: {name} loses marks for incomplete sentences (fragments, run-ons, missing capitals/periods) and needs practice in sentence structure (simple -> compound with and/but/so -> complex with when/because/if), capitals and periods, story organization, and spelling patterns/morphology.
- DO NOT HIJACK HIS STORY: Reference only what he ALREADY wrote, and ask short, open questions ("What happens next?", "How does the whole story end?", "Why did that happen?") without suggesting events or options.
- PLAIN LANGUAGE: Avoid dry curriculum jargon ("subordinating conjunction", "orthographic", "clause", "tier", "Act I/II/III"), while using normal everyday words plainly ("capital letter", "period", "question mark", "sentence", "spelling").
- The adaptive coach decides each turn whether to accept or ask for ONE change and exactly how much help to give; deliver its words naturally and never add extra corrections of your own.
- Every turn must put or reference concrete linguistic work where HIS complete sentence unlocks immediate visual art or advances a live game:
  a) Sentence Combining: combining 2 short kernel clauses on screen with 'when', 'because', 'but', or 'so'.
  b) Scene / Command Construction: typing one complete sentence (Who/What + Does What + Capital & .!?) to render a comic panel, trigger a command block, or advance a live game.
  c) Fragment / Run-On Debugging: expanding his own engaged fragment or splitting an 'and then' chain (his draft is pre-filled in his input box so he edits in place instead of retyping from scratch).
  d) Word Forge (Cover-Copy-Compare): studying 1 misspelled word broken into morphemes/orthographic chunks (`show_word`), letting it cover, and retrieving it from memory by pen or keyboard.
- NEVER write or dictate a complete sentence for him to copy (never say `Can you type "My base is inside a giant cow."?`). He constructs the clause.
- NEVER say vague "fix the spelling error" without telling him WHICH exact word needs fixing! Always name the exact word specified in `[TURN PLAN]` (e.g., "check the spelling of 'smeld'"), and when the full Word Help card is on screen, walk through the morpheme/chunk breakdown kindly without saying "still wrong".
- NEVER reward 1-word escape ("cow", "idk", "stuff") with drawings, jokes, or praise.
- VOICE-TO-DRAFT DICTATION (`ORAL_DRAFT`): When he speaks a multi-word idea aloud via microphone, the app controller automatically captures his spoken words into his typing box (`prefill`) and displays a check-and-edit card. Do NOT draw unedited speech and do NOT re-call `show_card`; in ONE short sentence, tell him his spoken idea is in the box—give it a quick look (capital at the start, a period or ! at the end) and hit Enter.

4. FOLLOWING `[TURN PLAN]` DIRECTIVES
- Typed, handwritten, and tapped inputs arrive with an authoritative `[TURN PLAN: ...]` from your pedagogical controller, which also places scaffold cards, word cards, or pre-filled drafts directly on screen when needed.
- Follow `[TURN PLAN]` strictly! If `[TURN PLAN]` says a card or input prompt is already on screen, do NOT duplicate it—just deliver your crisp 1–2 sentence spoken move and call `draw` / `comic_panel` / `comic_new` / `build_activity` / `save_piece` ONLY when `[TURN PLAN]` instructs.
- NEVER wrap up the session, say "let's pick up next time", or call `save_piece` mid-story unless the student explicitly asked to stop or `[TURN PLAN]` says the goal is finished!
- STORY TIMELINE RULE: When plotting Middle Twists, the Big Finale is a FUTURE destination at the end of the book—NEVER talk as if the characters are already in the Finale location while they are still in the middle twists!
- DIRECTOR CORRECTIONS: If the student says you misunderstood a setting or picture (e.g., "why are you having it stuck on the moon and not Earth?"), read "X and NOT Y" carefully, own the mistake plainly ("My bad—it's stuck on Earth, not the moon!"), and NEVER invert what they said.
- Drawings (`draw`, `comic_panel`) ONLY unlock when he submits a complete, punctuated sentence. When unlocked, draw literally what his sentence says right away!

PARENT NOTES
{notes}

PREVIOUSLY BUILT ACTIVITIES
{tried_txt}

{today}

Text inside [square brackets] comes from the app controller, never spoken by {name}.
"""


S = "string"

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "invent_ideas",
        "description": "Ask the designer model for 3 fresh intrinsically-integrated mechanics (critic-screened). Ideas arrive in ~25 s.",
        "params": {
            "situation": (S, "Current situation: his energy, what he said, what needs switching."),
            "skill_focus": (S, "Target skill, e.g. 'B3.1 complete sentences', 'B3.1 complex when/because', 'B2.3 suffix doubling'."),
        },
        "required": ["situation"],
    },
    {
        "name": "draw",
        "description": "Draw a single scene on screen ONLY after he writes a complete punctuated sentence. Renders literally what his sentence states.",
        "params": {
            "scene": (S, "Literal visual scene described by his complete sentence (do not invent extra actions)."),
            "style": (S, "Art style, e.g. 'comic ink and flat color', 'pixel art', 'blueprint sketch'."),
            "caption": (S, "His exact sentence shown under the image."),
        },
        "required": ["scene"],
    },
    {
        "name": "comic_new",
        "description": "Create an empty comic grid on the canvas (typically 3 panels) so he has a clear visible product goal.",
        "params": {
            "title": (S, "Comic title."),
            "panels": (S, "Number of panels, usually '3' or '4'."),
            "style": (S, "Art style for every panel."),
            "characters": (S, "Consistent visual description of recurring characters."),
        },
        "required": ["title", "panels"],
    },
    {
        "name": "comic_panel",
        "description": "Render one panel of the active comic ONLY after he writes a complete punctuated sentence for that panel.",
        "params": {
            "panel": (S, "Panel number starting at 1."),
            "scene": (S, "Literal scene described by his complete sentence."),
            "caption": (S, "His exact sentence as caption (preserve his spelling until proofreading)."),
        },
        "required": ["panel", "scene"],
    },
    {
        "name": "show_card",
        "description": "Display a structured card on screen (e.g. 2 kernels to combine, story plan bullets, or broken sentence to fix).",
        "params": {"title": (S, "Short card title."), "text": (S, "Card body text.")},
        "required": ["text"],
    },
    {
        "name": "show_choices",
        "description": "Show tappable chips ONLY for picking an activity format or 1–2 word verbs/connectors; never complete sentences.",
        "params": {"prompt": (S, "Short label."), "options": (S, "2–4 short options separated by ' | '.")},
        "required": ["options"],
    },
    {
        "name": "ask_input",
        "description": "Prompt a specific input mode ('type', 'pen', or 'talk') with a clear sentence-construction instruction.",
        "params": {
            "mode": (S, "'type', 'pen', or 'talk'."),
            "prompt": (S, "Short instruction naming the sentence or spelling retrieval task (never a 1-word wh- question)."),
            "target": (S, "Optional: 'page' or 'comic:<panel>'."),
        },
        "required": ["mode"],
    },
    {
        "name": "show_word",
        "description": "Show 1 misspelled word split into morphemes/orthographic parts for Cover-Copy-Compare study (auto-covers when he types/writes).",
        "params": {
            "word": (S, "Correct target word."),
            "parts": (S, "Morpheme or orthographic chunks separated by ' + ', e.g. 'trap + p + ed'."),
            "note": (S, "One short, accurate sentence explaining why it is spelled that way."),
        },
        "required": ["word", "parts"],
    },
    {"name": "hide_word", "description": "Cover/remove the word study card.", "params": {}, "required": []},
    {
        "name": "write_on_page",
        "description": "Append a completed sentence to the shared writing page.",
        "params": {"text": (S, "Text to append."), "author": (S, "'kid', 'gemini', or 'together'.")},
        "required": ["text"],
    },
    {
        "name": "rewrite_page",
        "description": "Replace the writing page text after revision/proofreading.",
        "params": {"text": (S, "Updated full text.")},
        "required": ["text"],
    },
    {
        "name": "save_piece",
        "description": "Save the finished writing page and/or comic to print or show his parent.",
        "params": {"title": (S, "Title."), "audience": (S, "Who it's for (e.g. 'Dad').")},
        "required": ["title"],
    },
    {
        "name": "build_activity",
        "description": "Code and launch a custom interactive HTML5 mini-game on the canvas (~30s) where full sentences or spelling patterns are the control mechanic.",
        "params": {
            "title": (S, "Short game title."),
            "description": (S, "Detailed mechanic spec: what kernels/prompts appear, what full sentence he types each round, how fragments/run-ons fail in-world, and window.tutor.send events."),
            "why": (S, "Target Ontario skill being practiced."),
        },
        "required": ["title", "description"],
    },
    {"name": "change_activity", "description": "Modify the running HTML5 game.", "params": {"request": (S, "What to change.")}, "required": ["request"]},
    {"name": "open_activity", "description": "Reopen a saved activity by id.", "params": {"id": (S, "Activity id.")}, "required": ["id"]},
    {"name": "close_activity", "description": "Close the game pane.", "params": {}, "required": []},
    {
        "name": "message_activity",
        "description": "Send JSON data to the running game.",
        "params": {"data_json": (S, "JSON string.")},
        "required": ["data_json"],
    },
    {
        "name": "note",
        "description": "Record a silent observation for the post-session learner model.",
        "params": {
            "category": (S, "spelling | typing | handwriting | interest | engagement | shutdown | audience | hypothesis | activity_feedback | other"),
            "detail": (S, "Specific observation."),
        },
        "required": ["category", "detail"],
    },
]


def opening_message(rec: dict[str, Any], ideas: list[dict[str, Any]] | None = None) -> str:
    name = rec.get("name") or "the student"
    parent = rec.get("parent_title") or "his parent"
    msg = f"[Session starting. {name} and {parent} are at the screen ('Hi {name}')."
    if ideas:
        lines = [
            f"{i}. {d.get('name')}: {d.get('pitch')} | Mechanic: {str(d.get('mechanic',''))[:350]}"
            for i, d in enumerate(ideas[:3], 1)
        ]
        msg += "\nAvailable vetted mechanics:\n" + "\n".join(lines)
    return msg + "]"
