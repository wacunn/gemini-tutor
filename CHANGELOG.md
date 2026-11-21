# Changelog

## 0.7.1
- **Restored Clean, Uncluttered Gemini App UX (`static/index.html`, `static/style.css`, `static/app.js`, `tutor/controller.py`):**
  - Replaced hero box grids, top-bar buttons, and in-stream instruction boxes with a **Gemini-style slide-out left sidebar (`☰`)** for creating/switching books, strips, games, and toggling Parent Sandbox, leaving the center start screen (`Hi …` + minimal borderless suggestion pills) and chat stream calm and clutter-free.

## 0.7.0
- **Fixed Fresh-Install / `.app` LLM Connection Error (`tutor/config.py`, `tutor/live.py`, `requirements.txt`):**
  - `google-genai` 3.x (installed on fresh `uv` setups via `install.sh` / `install.ps1`) changed `aio.live.connect()`'s default endpoint away from `v1alpha`, causing `HTTP 404` WebSocket rejections (`Reconnecting…`). Added `genai_client(live=True)` forcing `http_options={"api_version": "v1alpha"}` plus native OS Keychain / `truststore` + `certifi` SSL setup, Live model fallbacks, and a one-click **Test Gemini connection** check on `/parent`.
- **Live AI Story & Inquiry Director — Zero Static Worksheet Scripts (`tutor/controller.py`, `tutor/prompt.py`):**
  - Replaced static Spine, Panel, and Persuasive Pitch templates with `ai_direct_next_beat()`, which reads the child's exact characters/plot, reminds them of what they already wrote (zero working-memory tax), and asks curious, story-specific `where / why / how` questions paired with complete-sentence goals.
- **Immediate Visual Rewards & Progress Unlocks Starting on Sentence 1 (`tutor/controller.py`, `tutor/live.py`, `tutor/pdf_book.py`, `static/app.js`):**
  - Every Graphic Novel Story Spine beat now immediately unlocks live artwork on the Book Canvas and in the PDF (**Act I unlocks Cover & Beginning Art**, **Act II unlocks Twist Art**, **Act III unlocks Climax Art**), Codex Step 0 unlocks a **Specimen Blueprint Sketch**, and every beat triggers a progress bar step + subtle WebAudio unlock chime.
- **Filtered `<no speech detected>` Mic Noise (`tutor/live.py`):**
  - Stripped `<no speech detected>` and silence/noise ASR tags from `input_transcription` so room silence never renders phantom bubbles.

## 0.6.0
- **Multi-Book Library & Switcher Across All Studios (`tutor/projects.py`, `tutor/record.py`, `static/app.js`):**
  - Save multiple separate Graphic Novels, 3-Source Fact Codices, 4-Page Persuasive Pitches, Quick 3-Panel Strips, and Live Mini-Games simultaneously—switch between books or start a brand-new one anytime via the **Books / New** shelf or **Save & Switch / New** header button without overwriting earlier work, plus one-click **Rename** and **Delete**.
  - Lazy project persistence prevents empty 0-word `"Untitled"` files from cluttering the shelf if a user browses options before writing.
- **Parent Try-It Sandbox Mode (`/?sandbox=1`):**
  - One-click **Parent Try-It** mode on both the Start Screen and Parent Page lets parents test Graphic Novels, Codices, Pitches, Strips, Mini-Games, and PDF downloads in an isolated ephemeral sandbox with **zero writes** to the child's books, report card, spelling deck, session logs, or learner model.
- **2-Stage Specific Inline Spelling Help (`tutor/controller.py`):**
  - **Attempt 1:** Never says vague `"fix spelling"`—always names the **exact misspelled word** (with phrase context for short words like `"at" in "bought at new"` and an age-appropriate morphological/orthographic clue at early tiers) while keeping the draft pre-filled in the box.
  - **Attempt 2 ("Start All the Help"):** If the word isn't fixed on retry, immediately launches full spelling support on screen—displaying the **Morpheme / Chunk Word Card** (`trap + p + ed`, Cover-Copy-Compare) plus a **Sentence Context Card** highlighting `[meant]`. Typing/writing just the target word from memory automatically splices the corrected spelling into the student's sentence and locks/renders their panel or story beat.

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
