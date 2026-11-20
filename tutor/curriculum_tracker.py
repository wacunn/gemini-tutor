"""Ontario Grade 3 & Grade 4 Language Curriculum (2023) Report Card & Mastery Escalator.

Tracks longitudinal mastery across 14 sourced expectations spanning:
- Strand B3: Syntax, Sentence Structure, Grammar & Conventions (including Dialogue)
- Strand B2: Phonics, Orthography, Morphology & Vocabulary
- Strand D: Causal Story/Idea Architecture, Multi-Genre Drafting, Voice, Revision & Keyboarding

Levels follow Ontario's 4-level achievement scale:
  0 = Not yet assessed
  1 = Emerging (needs heavy scaffolding)
  2 = Approaching (succeeds with light prompts)
  3 = Solid — Grade 3 Expectation Met (applies independently on first try)
  4 = Extending — Grade 4 Expectation (sustained, complex application)
"""

from __future__ import annotations

import re
from typing import Any

from .record import now_iso

ONTARIO_EXPECTATIONS: list[dict[str, str]] = [
    # Strand B3: Sentence Structure, Grammar & Conventions
    {
        "id": "B3.1_simple",
        "code": "Gr.3 B3.1",
        "strand": "Sentences & Conventions (B3)",
        "name": "Complete Simple Sentences",
        "desc": "Writes complete thoughts with an explicit subject and finite verb (zero fragments).",
    },
    {
        "id": "B3.1_boundaries",
        "code": "Gr.3 B3.1",
        "strand": "Sentences & Conventions (B3)",
        "name": "Sentence Boundary Control",
        "desc": "Separates distinct events cleanly instead of chaining run-ons with 'and then'.",
    },
    {
        "id": "B3.1_compound",
        "code": "Gr.3–4 B3.1",
        "strand": "Sentences & Conventions (B3)",
        "name": "Compound Sentences (and / but / so)",
        "desc": "Joins independent clauses with coordinating conjunctions showing contrast or result.",
    },
    {
        "id": "B3.1_complex",
        "code": "Gr.3–4 B3.1",
        "strand": "Sentences & Conventions (B3)",
        "name": "Complex Sentences & Adverbial Clauses",
        "desc": "Constructs causal/temporal/conditional clauses using when, because, if, before, after, while, although.",
    },
    {
        "id": "B3.2_grammar",
        "code": "Gr.3–4 B3.2",
        "strand": "Sentences & Conventions (B3)",
        "name": "Grammar & Prepositional Elaboration",
        "desc": "Uses tense consistency, possessives, and prepositional phrases (Gr. 4 B3.1/B3.2) to add precision.",
    },
    {
        "id": "B3.3_mechanics",
        "code": "Gr.3 B3.3",
        "strand": "Sentences & Conventions (B3)",
        "name": "Capitals, End Punctuation & Apostrophes",
        "desc": "Applies sentence-initial capitals, title capitals, . ! ? end marks, and contraction apostrophes.",
    },
    {
        "id": "B3.3_dialogue",
        "code": "Gr.3–4 B3.3",
        "strand": "Sentences & Conventions (B3)",
        "name": "Direct Speech & Dialogue Punctuation",
        "desc": "Writes character dialogue and punctuates direct speech with quotation marks, commas, and capitals.",
    },
    # Strand B2: Spelling & Vocabulary
    {
        "id": "B2.1_2_orthography",
        "code": "Gr.3 B2.1–B2.2",
        "strand": "Spelling, Morphology & Vocabulary (B2)",
        "name": "Phonics & Positional Orthography",
        "desc": "Applies phonemic segmentation and position rules (-ck, -tch, -dge, vowel teams).",
    },
    {
        "id": "B2.3_morphology",
        "code": "Gr.3 B2.3 / Gr.4 B2.1",
        "strand": "Spelling, Morphology & Vocabulary (B2)",
        "name": "Morphological Spelling (Bases & Affixes)",
        "desc": "Applies prefixes, suffixes, 1-1-1 consonant doubling, drop-e, and y-to-i rules.",
    },
    {
        "id": "B2.4_vocabulary",
        "code": "Gr.3 B2.4 / Gr.4 B2.2",
        "strand": "Spelling, Morphology & Vocabulary (B2)",
        "name": "Precise Vocabulary & Vivid Verbs",
        "desc": "Selects specific verbs, nouns, and modifiers to convey exact meaning and tone.",
    },
    # Strand D: Composition, Story Architecture & Keyboarding
    {
        "id": "D1.2_4_architecture",
        "code": "Gr.3–4 D1.1–D1.4",
        "strand": "Story Architecture & Composition (D1–D3)",
        "name": "Causal Story & Idea Architecture",
        "desc": "Plans Beginning–Middle–End arcs linked causally ('but / therefore') and sequences chapters/sections.",
    },
    {
        "id": "D2.1_3_drafting",
        "code": "Gr.3–4 D2.1, D2.3, D2.4",
        "strand": "Story Architecture & Composition (D1–D3)",
        "name": "Sustained Drafting, Voice & Genre",
        "desc": "Drafts extended narrative, informational, or persuasive pieces with distinct voice and point of view.",
    },
    {
        "id": "D2.5_6_revision",
        "code": "Gr.3–4 D2.5–D2.6",
        "strand": "Story Architecture & Composition (D1–D3)",
        "name": "Revision, Expansion & Self-Editing",
        "desc": "Revises drafts to strengthen causal detail/word choice and edits own mechanics and spelling.",
    },
    {
        "id": "D2.2_keyboarding",
        "code": "Gr.4 D2.2",
        "strand": "Story Architecture & Composition (D1–D3)",
        "name": "Keyboarding Fluency",
        "desc": "Develops comfortable, increasingly fluent keyboarding during authentic composition.",
    },
]

LEVEL_LABELS = {
    0: "Not yet assessed",
    1: "Level 1 · Emerging",
    2: "Level 2 · Approaching",
    3: "Level 3 · Grade 3 Solid",
    4: "Level 4 · Extending (Gr. 4+)",
}


def default_report_card() -> dict[str, Any]:
    skills = {}
    for exp in ONTARIO_EXPECTATIONS:
        skills[exp["id"]] = {
            "level": 0,
            "trend": "new",
            "attempts": 0,
            "evidence": "",
            "updated": "",
            "history": [],
        }
    return {"skills": skills, "mastery_tier": 1, "updated": ""}


def ensure_report_card(rec: dict[str, Any]) -> dict[str, Any]:
    rc = rec.get("report_card")
    if not isinstance(rc, dict) or "skills" not in rc:
        rc = default_report_card()
        rec["report_card"] = rc
    for exp in ONTARIO_EXPECTATIONS:
        rc["skills"].setdefault(
            exp["id"],
            {"level": 0, "trend": "new", "attempts": 0, "evidence": "", "updated": "", "history": []},
        )
    rc.setdefault("mastery_tier", compute_mastery_tier(rc))
    return rc


def compute_mastery_tier(rc: dict[str, Any], panel_count: int = 0) -> int:
    """Determines the active pedagogical challenge tier (1..5) from skill mastery + project depth."""
    sk = (rc or {}).get("skills") or {}
    l_simple = sk.get("B3.1_simple", {}).get("level", 0)
    l_bound = sk.get("B3.1_boundaries", {}).get("level", 0)
    l_comp = max(sk.get("B3.1_compound", {}).get("level", 0), sk.get("B3.1_complex", {}).get("level", 0))
    l_dial = sk.get("B3.3_dialogue", {}).get("level", 0)
    l_elab = max(sk.get("B3.2_grammar", {}).get("level", 0), sk.get("B2.4_vocabulary", {}).get("level", 0))

    # Also allow gradual escalation inside a long comic book as panels accumulate
    tier = 1
    if l_simple >= 3 or panel_count >= 5:
        tier = 2  # Compound & Complex causal links (but / so / when / because / if)
    if (l_simple >= 3 and l_comp >= 3) or panel_count >= 12:
        tier = 3  # Direct Speech Bubbles & Dialogue Punctuation ("...", yelled X.)
    if (tier >= 3 and l_dial >= 3 and l_bound >= 3) or panel_count >= 25:
        tier = 4  # Prepositional scene-openers, vivid verb revision & 2-sentence captions (Gr. 4 B3.1/D2.3)
    if (tier >= 4 and l_elab >= 3) or panel_count >= 45:
        tier = 5  # Multi-sentence paragraphs, parallel subplots ("Meanwhile..."), and independent proofreading
    return tier


TIER_DESCRIPTIONS: dict[int, dict[str, str]] = {
    1: {
        "name": "Tier 1 · Crisp Complete Clauses (Gr. 3 B3.1 / B3.3)",
        "rule": "Every panel/step requires 1 complete sentence (Who/What + Does What + Capital & .!?).",
        "prompt_hint": "Write one complete sentence (Who + Does What) with a capital and period.",
    },
    2: {
        "name": "Tier 2 · Causal & Temporal Sentences (Gr. 3 B3.1 Compound/Complex)",
        "rule": "Connect cause, contrast, or timing using 'when', 'because', 'but', 'so', 'before', or 'while'.",
        "prompt_hint": "Write a complete sentence using 'when', 'because', 'but', or 'so' to show cause and effect.",
    },
    3: {
        "name": "Tier 3 · Action + Direct Speech / Dialogue (Gr. 3 B3.3 Dialogue)",
        "rule": "Combine scene action with character speech—either a comic dialogue line or punctuated quotation marks (\"...\", shouted X.).",
        "prompt_hint": "Include both what happens AND what a character says (using quotation marks or Speaker: line).",
    },
    4: {
        "name": "Tier 4 · Vivid Detail & Prepositional Openers (Gr. 4 B3.1 / B3.2 / D2.3)",
        "rule": "Open with where/when (prepositional or adverbial phrase) and use specific, vivid action verbs—or write a 2-sentence beat.",
        "prompt_hint": "Start with where/when it happens (e.g. 'Beneath the...', 'Seconds before...') and use a vivid action verb.",
    },
    5: {
        "name": "Tier 5 · Graphic Novelist Mastery (Gr. 4 D1.4 / D2.5 / D2.6)",
        "rule": "Write 2–3 cohesive sentences weaving action, internal reaction/subplot, and punctuated dialogue, self-edited for conventions.",
        "prompt_hint": "Write 2 cohesive sentences combining action and punctuated dialogue to drive the chapter forward.",
    },
}


def update_from_session_deterministic(
    rc: dict[str, Any],
    writing_checks: list[dict[str, Any]],
    stats: dict[str, Any],
    had_spine: bool = False,
    had_revision: bool = False,
) -> None:
    """Applies conservative deterministic floor updates from objective session checks before specialist review."""
    ts = now_iso()[:10]
    sk = rc["skills"]

    attempts = stats.get("sentence_attempts") or 0
    rate = stats.get("complete_first_try_rate")
    if attempts >= 2 and rate is not None:
        cur = sk["B3.1_simple"]["level"]
        est = 3 if (rate >= 0.75 and attempts >= 3) else (2 if rate >= 0.45 else 1)
        if cur == 0 or est > cur:
            sk["B3.1_simple"]["level"] = est
            sk["B3.1_simple"]["updated"] = ts

        cap_miss = stats.get("missing_capital") or 0
        end_miss = stats.get("missing_end_punctuation") or 0
        mech_rate = max(0.0, 1.0 - (cap_miss + end_miss) / max(1, attempts * 2))
        m_est = 3 if (mech_rate >= 0.85 and attempts >= 3) else (2 if mech_rate >= 0.55 else 1)
        if sk["B3.3_mechanics"]["level"] == 0 or m_est > sk["B3.3_mechanics"]["level"]:
            sk["B3.3_mechanics"]["level"] = m_est
            sk["B3.3_mechanics"]["updated"] = ts

    # Inspect verified sentences for compound, complex, and dialogue punctuation
    complex_examples = []
    compound_examples = []
    dialogue_examples = []
    for wc in writing_checks:
        txt = wc.get("text") or ""
        chk = wc.get("check") or {}
        for s in chk.get("sentences") or []:
            if s.get("complete") and s.get("issue") == "none" and s.get("capital_ok") and s.get("end_ok"):
                ct = s.get("clause_type")
                st = s.get("text") or txt
                if ct == "complex" or re.search(r"\b(when|because|if|before|after|while|although|unless|since)\b", st, re.I):
                    complex_examples.append(st)
                elif ct == "compound" or re.search(r",\s*(but|so|and|or)\b|\b(but|so)\b", st, re.I):
                    compound_examples.append(st)
                if '"' in st and re.search(r'"[^"]+[,.!?]"', st):
                    dialogue_examples.append(st)

    if compound_examples and sk["B3.1_compound"]["level"] < 2:
        sk["B3.1_compound"]["level"] = 3 if len(compound_examples) >= 3 else 2
        sk["B3.1_compound"]["evidence"] = compound_examples[-1][:140]
        sk["B3.1_compound"]["updated"] = ts

    if complex_examples and sk["B3.1_complex"]["level"] < 2:
        sk["B3.1_complex"]["level"] = 3 if len(complex_examples) >= 3 else 2
        sk["B3.1_complex"]["evidence"] = complex_examples[-1][:140]
        sk["B3.1_complex"]["updated"] = ts

    if dialogue_examples and sk["B3.3_dialogue"]["level"] < 2:
        sk["B3.3_dialogue"]["level"] = 3 if len(dialogue_examples) >= 2 else 2
        sk["B3.3_dialogue"]["evidence"] = dialogue_examples[-1][:140]
        sk["B3.3_dialogue"]["updated"] = ts

    if had_spine and sk["D1.2_4_architecture"]["level"] < 2:
        sk["D1.2_4_architecture"]["level"] = 2
        sk["D1.2_4_architecture"]["updated"] = ts

    if had_revision and sk["D2.5_6_revision"]["level"] < 2:
        sk["D2.5_6_revision"]["level"] = 2
        sk["D2.5_6_revision"]["updated"] = ts

    cpm = stats.get("typing_chars_per_min")
    if cpm and (stats.get("typed_chars") or 0) >= 60:
        k_est = 4 if cpm >= 140 else (3 if cpm >= 95 else (2 if cpm >= 55 else 1))
        if sk["D2.2_keyboarding"]["level"] == 0 or k_est > sk["D2.2_keyboarding"]["level"]:
            sk["D2.2_keyboarding"]["level"] = k_est
            sk["D2.2_keyboarding"]["evidence"] = f"{cpm} chars/min during composition"
            sk["D2.2_keyboarding"]["updated"] = ts

    rc["mastery_tier"] = compute_mastery_tier(rc)
    rc["updated"] = now_iso()


def merge_specialist_ratings(rc: dict[str, Any], ratings: list[dict[str, Any]], session_id: str) -> None:
    """Merges post-session specialist (gemini-4-carbon) ratings & quoted evidence into the longitudinal report card."""
    ts = now_iso()[:10]
    sk = rc["skills"]
    for item in ratings or []:
        if not isinstance(item, dict):
            continue
        sid = item.get("id")
        if sid not in sk:
            continue
        new_lvl = item.get("level")
        if not isinstance(new_lvl, int) or not (1 <= new_lvl <= 4):
            continue
        entry = sk[sid]
        old_lvl = entry.get("level", 0)
        entry["trend"] = "rising" if new_lvl > old_lvl else ("falling" if (old_lvl > 0 and new_lvl < old_lvl) else "steady")
        entry["level"] = new_lvl
        entry["attempts"] = entry.get("attempts", 0) + 1
        if item.get("evidence"):
            entry["evidence"] = str(item["evidence"])[:200]
        entry["updated"] = ts
        hist = entry.setdefault("history", [])
        hist.append({"date": ts, "session": session_id, "level": new_lvl})
        entry["history"] = hist[-20:]
    rc["mastery_tier"] = compute_mastery_tier(rc)
    rc["updated"] = now_iso()


def format_report_for_ui(rc: dict[str, Any]) -> dict[str, Any]:
    ensure_dict = rc if isinstance(rc, dict) and "skills" in rc else default_report_card()
    sk = ensure_dict["skills"]
    rows = []
    assessed = 0
    solid_or_above = 0
    for exp in ONTARIO_EXPECTATIONS:
        st = sk.get(exp["id"], {})
        lvl = st.get("level", 0)
        if lvl > 0:
            assessed += 1
        if lvl >= 3:
            solid_or_above += 1
        rows.append(
            {
                **exp,
                "level": lvl,
                "level_label": LEVEL_LABELS.get(lvl, "Not yet assessed"),
                "trend": st.get("trend", "new"),
                "evidence": st.get("evidence", ""),
                "updated": st.get("updated", ""),
                "history": st.get("history", []),
            }
        )
    tier = ensure_dict.get("mastery_tier") or compute_mastery_tier(ensure_dict)
    return {
        "mastery_tier": tier,
        "tier_info": TIER_DESCRIPTIONS.get(tier, TIER_DESCRIPTIONS[1]),
        "assessed_count": assessed,
        "total_expectations": len(ONTARIO_EXPECTATIONS),
        "solid_count": solid_or_above,
        "expectations": rows,
    }
