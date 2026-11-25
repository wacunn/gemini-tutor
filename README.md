# Gemini Tutor

An AI writing, reading, and spelling tutor for elementary-school kids (built around the Grade 3–4 Ontario Language curriculum), powered by Gemini voice, text, handwriting vision, and comic illustration.

Kids learn sentence structure, verb endings, punctuation, and spelling by making real books and games they actually want to show off—without boring worksheets or babyish clipart. Your API key and all of your child's books, notes, and progress stay saved privately on your own computer.

## What Kids Can Make

- **Comic Books & Graphic Novels (Save Anytime · Printable PDF):** Kids plan the kickoff, jump to the big finale, pack the middle with plot twists, and write chapter by chapter with speech bubbles and consistent characters across 6 comic art styles (*Dog Man*-style marker comics, *Wimpy Kid*-style lined-notebook doodles, action manga, heavy-metal zine ink, blocky voxel worlds, and indie adventure comics).
- **How-To Guides & Minecraft Diaries (Printable PDF):** Pure procedural step-by-step guides and illustrated survival journals driven by the student's own ideas.
- **Fact & Invention Codex (Reading + Writing · PDF):** Kids read 3 short real-world science, history, or engineering sources, answer an inference question, and build a 3-sentence illustrated encyclopedia entry.
- **4-Page Persuasive Pitch ('Why We Should…' · PDF):** Guides kids step by step through making a real case (*Claim → Reason → Counter-Argument → Deal*) to print or show a parent.
- **Stylus / 2-in-1 Touchscreen Handwriting Pad:** Primary-lined **Sky, Fence, Grass, and Worm** handwriting sheet with 120–240Hz `PointerEvent` stylus pressure/tilt capture, 360°-tablet palm rejection, and single-letter erase & touch-up.
- **Multiple Saved Books & Parent Sandbox (`/?sandbox=1`):** Open the `☰` menu to switch between saved books or start a new one, or use **Parent Try-It (Sandbox)** to test everything without touching your child's saved work, points, or progress report.

---

## 💻 Installation by Operating System (Windows, Mac, ChromeOS & Linux)

No coding or manual Python setup needed—each one-line installer downloads standalone Python 3.12 (`uv`), creates a Desktop / App Launcher icon, and opens Gemini Tutor automatically. After installing, **updates happen with one click inside the Parent page**.

*(Before starting, grab a free Gemini API key once at **https://aistudio.google.com/app/api-keys** to paste on the first-run screen. Full step-by-step parent walkthrough: **[SETUP.md](SETUP.md)**.)*

### 1. Windows 11 / 10 (PC & 2-in-1 Touch Laptops)
Open **PowerShell** (`Start` → type `PowerShell` → `Enter`) and paste:
```powershell
irm https://raw.githubusercontent.com/wacunn/gemini-tutor/main/install.ps1 | iex
```

### 2. macOS (Apple Silicon & Intel Macs)
Open **Terminal** (`⌘ Command` + `Space` → type `Terminal` → `Return`) and paste:
```bash
curl -fsSL https://raw.githubusercontent.com/wacunn/gemini-tutor/main/install.sh | bash
```

### 3. ChromeOS (Chromebook / Googlebook)
1. One-time Linux turn-on: **Settings → About ChromeOS → Developers → Linux development environment → Turn On**.
2. In the **Linux Terminal** window (`Ctrl` + `Shift` + `V` to paste), run:
```bash
curl -fsSL https://raw.githubusercontent.com/wacunn/gemini-tutor/main/install.sh | bash
```

### 4. Linux (Ubuntu, Debian, Fedora, Mint, Arch)
Open **Terminal** and paste:
```bash
curl -fsSL https://raw.githubusercontent.com/wacunn/gemini-tutor/main/install.sh | bash
```

---

## 🎮 Optional Add-Ons: Earned Video Game Time & Parent Controls

**Important:** Gemini Tutor shows **zero** video game UI, points, or game buttons **unless** you install **[Fists of Doom: Toronto](https://github.com/wacunn/toronto-fight-game)**, **Minecraft Bedrock Edition** (*Minecraft for Windows*), and/or **Minecraft Java Edition** locally on the same computer. When multiple games are installed, they **share the same earned game-time bank** so your child can choose whichever one they want to play!

### Option A — Add *Fists of Doom: Toronto* (Local Install + In-Tutor Arcade)
Kids earn play time through verified writing and launch *Fists of Doom* right inside Gemini Tutor (with a live countdown and auto-close at `0:00`):

- **Windows (PowerShell):**
  ```powershell
  irm https://raw.githubusercontent.com/wacunn/toronto-fight-game/main/install.ps1 | iex
  ```
- **Mac, ChromeOS, or Linux (Terminal):**
  ```bash
  curl -fsSL https://raw.githubusercontent.com/wacunn/toronto-fight-game/main/install.sh | bash
  ```

### Option B — Add *Minecraft Bedrock &/or Java Edition* (Auto-Setup + OS Time-Gating)
Each one-line script wires OS shortcuts & a silent login watchdog to Gemini Tutor's earned-time bank, installs **Prism Launcher + Java 21** for Java Edition, and (on Windows) automatically detects & gates **Minecraft Bedrock (`Minecraft for Windows` from Microsoft Store / Xbox App)** alongside **Minecraft Java** (full details in **[MINECRAFT_SETUP.md](MINECRAFT_SETUP.md)**):

- **Windows 11 / 10 — Bedrock & Java (PowerShell):**
  ```powershell
  irm https://raw.githubusercontent.com/wacunn/gemini-tutor/main/setup_minecraft_windows.ps1 | iex
  ```
  *(Supports **both** Minecraft Bedrock from Microsoft Store / Xbox App and Minecraft Java via Prism / Official Launcher! If you only want Bedrock without installing Java, run `$env:TUTOR_BEDROCK_ONLY="1"; irm https://raw.githubusercontent.com/wacunn/gemini-tutor/main/setup_minecraft_windows.ps1 | iex`.)*
- **macOS (Terminal):**
  ```bash
  curl -fsSL https://raw.githubusercontent.com/wacunn/gemini-tutor/main/setup_minecraft_mac.sh | bash
  ```
- **ChromeOS / Chromebook (Linux Terminal):**
  ```bash
  curl -fsSL https://raw.githubusercontent.com/wacunn/gemini-tutor/main/setup_minecraft_chromebook.sh | bash
  ```
- **Linux — Ubuntu, Debian, Fedora, Mint, Arch (Terminal):**
  ```bash
  curl -fsSL https://raw.githubusercontent.com/wacunn/gemini-tutor/main/setup_minecraft_linux.sh | bash
  ```

### 👨‍👩‍👦 Parent Controls & Parent Override (`http://localhost:8787/parent`)
Click the **Parent icon** (person icon in the top-right corner of Gemini Tutor) and scroll to **Video Game Rewards**:

- **Active Solid Writing Only (Never Idle Open-App Time):** Leaving the app open, typing `"idk"`, fragments, or off-task chat earns **0 seconds**. Each turn caps active thinking/writing time (`<= 75s`) and commits credit **only** when a Homework-Standard complete sentence (starting capital, ending punctuation, complete clause, clean spelling/grammar) or Cover-Copy-Compare spelling retrieval succeeds.
- **ADHD-Friendly `1:2` Default (`1 min solid work = 2 min gaming`, Saved Across Sessions):** Because getting **15 minutes** of genuine, verified solid writing often takes ~25–30 minutes at the desk, the default rule rewards **15 minutes of solid writing = 1 Point = 30 minutes of game time** (and partial minutes are always saved across sessions so shorter sittings never lose progress!).
- **Parent Override (1-Click Free Play Unlock):** Need to let your child play Bedrock with friends or enjoy weekend free play without spending banked points? Click **🔓 Unlock 30m**, **🔓 Unlock 1 hr**, **🔓 Rest of Today**, or **🔓 Until Turned Off** (plus **🔒 End Override Now** anytime).
- **Customizable Conversion Rules & Independent Edition Gates:** Parents can set any custom **minutes per point**, **points to unlock**, and **game minutes earned** (or pick 1-click presets), gate **Minecraft Bedrock** and **Minecraft Java** independently, **+ Grant 15m / 30m bonus time**, or **reset the bank to `0:00`**.
- **Automatic Enforcement & 1-Minute Save Warning:**
  - Launching Minecraft (Bedrock or Java) from the Desktop / Start Menu / ChromeOS Shelf when banked time is `0:00` notifies your child and opens **Gemini Tutor** instead; standalone *Fists of Doom* can also be locked at `0:00`.
  - With **1 minute left**, a native OS notification + chime warns your child to **Save & Quit**, and at **`0:00`** the game closes automatically.
  - Need to sign in, update Minecraft, or add mods/worlds without using banked time? Click **🔧 Open Bedrock (Parent Setup)** or **🔧 Open Prism Launcher (Parent Setup)** on `/parent`.

---

## 🔄 One-Click Updates Inside the App
No command line needed after installing: click the **Parent icon** (top right) → **Software** → **Check for updates** → **Update now**. Your API key and all saved books, points, and progress stay untouched.

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
./start.sh          # Mac / ChromeOS / Linux -> http://localhost:8787
start.cmd           # Windows PC -> http://localhost:8787
```

`.env` and `data/` are gitignored and never leave your machine.
