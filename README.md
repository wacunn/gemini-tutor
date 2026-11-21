# Gemini Tutor

A local-first, voice + typing + stylus AI Language, Writing, Reading-to-Write, and Spelling studio built on Gemini, grounded in empirical writing & ADHD science (SRSD `POW+TREE` & Story Blueprints, Saddler & Graham sentence combining, Habgood & Ainsworth intrinsic integration, Dunlap escape extinction + antecedent choice, MacArthur dictation-to-edit, and Leitner spaced Cover-Copy-Compare morphological spelling) and aligned verbatim with **18 expectations across Strands B, C, and D of The Ontario Curriculum, Grades 1–8: Language (2023), Grades 3–4**.

### Multi-Scale Creative & Expository Studios (All Save Across Weeks & Export 150-DPI PDFs)
- **Full Graphic Novel Studio (Up to 100+ Panels):** Maps a verified causal *Beginning → Middle ('But / When / Because') → End ('So / Finally')* Story Spine first, then zooms in chapter-by-chapter with consistent character art, `B3.3`-punctuated speech bubbles, and automatic Mastery Tier 1–5 escalation.
- **3-Source Fact & Invention Codex (Reading Comprehension + Research Synthesis):** Presents 3 real science/engineering/history/acoustics sources (or generates a custom 3-source dossier on any topic the child asks to research), verifies causal inference (`C2.3 / C3.2`), builds a cohesive 3-sentence informational paragraph, and exports wide Encyclopedia PDF spreads.
- **4-Page Persuasive Pitch Book (`POW+TREE`):** Scaffolds *Claim → Evidence (`because/since`) → Counter-Argument (`although/even though`) → Final Deal* into an illustrated PDF Case File.
- **Quick Sprints & Voice-to-Draft Mode:** 3-Panel Strips, live HTML5 sentence-driven mini-games, spoken dictation-into-editable-box (`ORAL_DRAFT`) for low-energy ADHD days, and guaranteed daily Leitner Spaced Word Forge.
- **Multi-Book Shelf & Parent Sandbox (`/?sandbox=1`):** Save and switch among multiple Graphic Novels, Codices, Persuasive Pitches, Strips, and Mini-Games via **Books / New**, or click **Parent Try-It** (`/?sandbox=1`) to test any studio and PDF export without touching your child's books, report card, or profile.

## One-Line Install (Mac, Windows PC & Chromebook)

For full non-technical setup and updating instructions (written for parents), open **[SETUP.md](SETUP.md)**.

- **Mac or Chromebook (Terminal):**
  ```bash
  curl -fsSL https://raw.githubusercontent.com/wacunn/gemini-tutor/main/install.sh | bash
  ```
- **Windows PC (PowerShell):**
  ```powershell
  irm https://raw.githubusercontent.com/wacunn/gemini-tutor/main/install.ps1 | iex
  ```

### One-Click In-App Software Updates
No `git` or command line required after install: click the **Parent icon** (top right) → **Software** → **Check for updates** → **Update now**. The app downloads the latest release from GitHub, keeps `.env` and `data/` untouched, restarts in the background, and reloads automatically.

## Model Architecture

| Component | Model / Engine | Role |
|---|---|---|
| Live voice & canvas tutor | `gemini-3.8-live` | Real-time native audio + tool execution (`comic`, `draw`, `show_card`, `show_word`, `build_activity`) |
| Pedagogical controller & gates | `tutor/controller.py` + `gemini-3.5-flash` | Sub-second state machine (`OPENING` → `BUILDING` → `WORD_STUDY` → `WRAP`), B3.1 rung progression, 2-kernel sentence combining scaffolds, and hard Python tool gates |
| Child modeling, critic & inventor | `gemini-4-hydrogen` | Live engagement/skill tracker, educational critic, per-turn auditor, game spec vetter, and mechanic inventor |
| Live game builder | `gemini-3.8-flash` | Streams custom sandboxed HTML5 mini-games (`window.tutor.send` bridge) |
| Panel & scene illustrator | `gemini-3.1-flash-image` | Single-frame literal illustrations unlocked only by complete sentences |
| Post-session specialist review | `gemini-4-carbon` | Deep post-session multi-specialist review updating `data/learner.json` |

## Local Development

```bash
./start.sh          # Mac / Chromebook / Linux -> http://localhost:8787
start.cmd           # Windows PC -> http://localhost:8787
```

All API keys (`.env`, `chmod 600`) and learner records (`data/`) are gitignored and stay strictly on your local computer.
