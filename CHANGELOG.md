# Changelog

## 0.5.0
- **Full Grade 3–4 Language Replacement Engine (Strands B, C, and D):**
  - **Enforced Multi-Genre Studios (`tutor/controller.py`, `tutor/research_packs.py`):**
    - **Narrative Graphic Novel (`epic_graphic_novel`):** Enforces causal connectors on Story Spine Act II (*But / When / Because*) and Act III (*So / Therefore / Finally*), enforces Mastery Tier 2–4 upgrades (*Power-Up Pass* for causal clauses, direct speech bubbles, and vivid-verb revision), and verifies Ontario `B3.3` dialogue quotation marks, capitals, and inside-quote punctuation.
    - **3-Source Reading-to-Write Research Codex (`epic_codex`):** Covers Ontario Strand C Comprehension (`C1–C3`) + `D1.3` Multi-Source Research + `D2.1` Expository Writing. Presents 3 factual mini-sources (or generates a custom 3-source dossier on any student-chosen topic via `gemini-4-hydrogen`), checks causal inference, scaffolds a 3-sentence Topic → Mechanism → Impact paragraph, and renders wide 2-entry-per-page Encyclopedia PDF spreads (`tutor/pdf_book.py`).
    - **4-Page Persuasive Pitch Book (`medium_pitch`):** Implements SRSD `POW+TREE` (*Topic/Claim → Reason with `because/since` → Counter-Argument with `although/even though` → Final Deal*) exported as an illustrated PDF Case File.
  - **Leitner Spaced Spelling & Systematic Ontario Morphology (`tutor/spelling_srs.py`):** 5-box Leitner spaced-retrieval deck (`18h → 3d → 7d → 14d → 30d`) persisted in `learner.json` + 8-unit systematic Ontario Continuum progression (`1-1-1` doubling, drop silent-`e`, `-tch/-dge`, `y→i`, prefixes, bound roots) guaranteed in every session even when the child avoids hard words during drafting.
  - **Voice-to-Draft Dictation & Edit (`ORAL_DRAFT`):** Externalizes spoken drafts into the editable composer (`prefill`) for low-energy ADHD days while gating rendering until the student checks capitals, connectors, and punctuation (MacArthur speech-to-text + post-dictation editing).
  - **18-Expectation Longitudinal Ontario Report Card:** Expanded `tutor/curriculum_tracker.py` and `/parent` to track all 18 expectations across Strands B2, B3, C1–C3, and D1–D3 alongside the live Spaced Spelling Deck.

## 0.4.0
- Added **Multi-Week Persistent Book Projects** (`tutor/projects.py`) across time scales:
  - **Full Graphic Novel / Comic Book (up to 100+ panels):** Maps causal *Beginning → Middle ('But/When') → End ('So/Finally')* Story Spine first, then zooms in chapter-by-chapter with consistent character art, speech bubbles, and auto-saves across sessions.
  - **Illustrated Monster & Invention Codex:** Multi-session expository field guide teaching paragraph structure.
  - **4-Page Persuasive Pitch Book** + **Quick 10-Minute Sprints** (3-Panel Strip, Live Mini-Game).
- Added **Publication-Quality PDF Book Exporter** (`tutor/pdf_book.py`, `/api/project/{id}/pdf`) generating cover pages, Story Spine architecture pages, chapter spreads, rendered speech bubbles, and captions at any draft or final stage.
- Added **14-Expectation Ontario Grade 3–4 Language Curriculum Report Card & Mastery Escalator (Tiers 1–5)** (`tutor/curriculum_tracker.py`, Parent page) tracking longitudinal mastery across Strands B3, B2, and D and escalating tutor expectations automatically as skills solidify.

## 0.3.2
- Deterministic immediate panel/scene rendering as soon as each complete punctuated sentence is verified, WebSocket auto-reconnect, and one-click **Clear test sessions**.

## 0.3.1
- Generalized learner setup context and added editable profile fields on the Parent page, Windows PowerShell installer (`install.ps1`), and automatic update banner.
