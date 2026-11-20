# Gemini Tutor

A local-first, voice + typing + stylus AI writing and spelling tutor built on Gemini, grounded in empirical writing science (SRSD, sentence combining, intrinsic game integration, escape extinction + antecedent scaffolding, and Cover-Copy-Compare morphological spelling) and aligned verbatim with the **Ontario Language Curriculum (2023), Grades 3–4**.

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
