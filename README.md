# Gemini Tutor

An AI writing, reading, and spelling tutor for elementary-school kids (built around the Grade 3–4 Ontario Language curriculum), powered by Gemini voice, text, handwriting vision, and comic illustration.

Kids learn sentence structure, verb endings, punctuation, and spelling by making real books and games they actually want to show off—without boring worksheets or babyish clipart. Your API key and all of your child's books, notes, and progress stay saved privately on your own computer.

## What Kids Can Make

- **Comic Books & Graphic Novels (Save Anytime · Printable PDF):** Kids plan the kickoff, jump to the big finale, pack the middle with as many wild plot twists as they want, and then write chapter by chapter with speech bubbles and consistent characters. Includes 6 comic art styles (*Dog Man*-style marker comics, *Wimpy Kid*-style lined-notebook doodles, action manga, heavy-metal zine ink, blocky voxel worlds, and indie adventure comics).
- **Fact & Invention Codex (Reading + Writing · PDF):** Kids read 3 short real-world science, history, or engineering sources (or ask to research any topic they want), answer an inference question, and build a 3-sentence illustrated encyclopedia entry.
- **4-Page Persuasive Pitch ('Why We Should…' · PDF):** Guides kids step by step through making a real case (*Claim → Reason → Counter-Argument → Deal*) to print or show a parent.
- **Quick 3-Panel Strips, Mini-Games & Primary-Lined Handwriting Pad:** Includes a stylus/touchscreen writing pad with **Sky, Fence, Grass, and Worm** letter lines (plus single-letter erase & touch-up), spoken dictation-to-edit for tired days, and daily spaced spelling practice.
- **Multiple Saved Books & Parent Sandbox (`/?sandbox=1`):** Open the `☰` menu to switch between saved books or start a new one, or use **Parent Try-It (Sandbox)** to test everything without touching your child's saved work or progress report.

## One-Line Install (Mac, Windows PC & Chromebook)

For step-by-step parent instructions, see **[SETUP.md](SETUP.md)**.

- **Mac or Chromebook (Terminal):**
  ```bash
  curl -fsSL https://raw.githubusercontent.com/wacunn/gemini-tutor/main/install.sh | bash
  ```
- **Windows PC (PowerShell):**
  ```powershell
  irm https://raw.githubusercontent.com/wacunn/gemini-tutor/main/install.ps1 | iex
  ```

### One-Click Updates Inside the App
No command line needed after installing: click the **Parent icon** (top right) → **Software** → **Check for updates** → **Update now**. Your API key and all saved books and progress stay untouched.

### Optional Local Video Game Rewards (Fists of Doom & Chromebook Minecraft)
When **[Fists of Doom](https://github.com/wacunn/toronto-fight-game)** and/or **Minecraft (Prism Launcher)** is installed locally on the same computer, students can earn video game points from **active, verified writing** (never idle open-app time, fragments, or avoidance—saved across sessions so progress is never lost) and launch earned game time straight from Gemini Tutor. Parents control the exact conversion ratio on `/parent`. For one-line Chromebook Minecraft setup and shelf gating, see **[MINECRAFT_SETUP.md](MINECRAFT_SETUP.md)**.

## Models Used

| Part | Model | What It Does |
|---|---|---|
| Live voice tutor | `gemini-3.8-live` | Real-time voice conversation and canvas tools |
| Adaptive coach | `gemini-3.5-flash` | Decides each turn whether to draw now or ask for one change, and how much help to give, based on his writing and how he's doing today |
| Sentence, grammar, spelling & handwriting check | `gemini-3.5-flash` | Checks sentence completeness, verb endings (`B3.2`), punctuation, spelling, and primary-line handwriting |
| Story questions & sentence starters | `gemini-3.1-flash-lite` | Fast next question about his story plus tappable starters |
| Progress & session planner | `gemini-4-hydrogen` | Tracks engagement, vets game ideas, and generates custom reading packs |
| Mini-game builder | `gemini-3.8-flash` | Builds playable HTML5 mini-games controlled by complete sentences |
| Comic illustrator | `gemini-3.1-flash-image` | Draws comic panels and covers in the child's chosen art style |
| Post-session review | `gemini-4-carbon` | Summarizes each session and updates `data/learner.json` for the parent page |

## Running Locally from Source

```bash
./start.sh          # Mac / Chromebook / Linux -> http://localhost:8787
start.cmd           # Windows PC -> http://localhost:8787
```

`.env` and `data/` are gitignored and never leave your machine.
