# Setting Up Minecraft Java Edition Rewards & Parent Controls (Windows, Mac, ChromeOS & Linux)

With **Gemini Tutor**, your child can earn **Minecraft Java Edition** play time (and/or **[Fists of Doom](https://github.com/wacunn/toronto-fight-game)** play time) by doing active, high-quality writing—never by leaving the app open idle!

Each one-line setup script below automatically installs or updates **Gemini Tutor**, installs **Prism Launcher** (+ **Java 21** where needed), wires a silent login watchdog + shortcut gating so Minecraft cannot be played at `0:00`, and opens **Parent Setup** for your one-time Microsoft login.

---

## Step 1: Run the One-Line Setup for Your OS

### Option A — Windows 11 / 10 (PowerShell)
1. Click **Start**, type `PowerShell`, and press `Enter`.
2. Right-click to paste this line and press `Enter`:
   ```powershell
   irm https://raw.githubusercontent.com/wacunn/gemini-tutor/main/setup_minecraft_windows.ps1 | iex
   ```
   * Installs/updates Gemini Tutor (`$HOME\GeminiTutor`), installs **Prism Launcher** + **Eclipse Temurin Java 21** via `winget`, adds a silent `pythonw.exe` login watchdog in Windows `Startup`, and gates the Desktop shortcut.
   * *(Also auto-detects and gates the Official Microsoft Store / Xbox App Minecraft Launcher & Minecraft Bedrock if installed.)*

### Option B — macOS (Apple Silicon & Intel Macs)
1. Press `⌘ Command` + `Space`, type `Terminal`, and press `Return`.
2. Paste this line and press `Return`:
   ```bash
   curl -fsSL https://raw.githubusercontent.com/wacunn/gemini-tutor/main/setup_minecraft_mac.sh | bash
   ```
   * Installs/updates Gemini Tutor (`~/GeminiTutor`), installs **Prism Launcher.app** (via Homebrew or official GitHub Universal release), and registers a macOS `LaunchAgent` login watchdog (`~/Library/LaunchAgents/com.geminitutor.watchdog.plist`).

### Option C — ChromeOS (Chromebook / Googlebook)
1. Open your Chromebook's **Linux Terminal** *(if Linux isn't turned on yet, see **[SETUP.md → Option C](SETUP.md)** first)*.
2. Paste (`Ctrl` + `Shift` + `V`) and press `Enter`:
   ```bash
   curl -fsSL https://raw.githubusercontent.com/wacunn/gemini-tutor/main/setup_minecraft_chromebook.sh | bash
   ```
   * Works on both **ARM64 (`aarch64`)** and **Intel/AMD (`x86_64`)** Chromebooks: installs `--user` Flatpak Prism Launcher, applies ChromeOS's required `QT_QPA_PLATFORM=xcb` display fix, and wraps the ChromeOS shelf `.desktop` launcher.

### Option D — Linux (Ubuntu, Debian, Fedora, Mint, Arch)
1. Open **Terminal** and paste:
   ```bash
   curl -fsSL https://raw.githubusercontent.com/wacunn/gemini-tutor/main/setup_minecraft_linux.sh | bash
   ```
   * Installs system dependencies via `apt`, `dnf`, or `pacman`, installs Flathub Prism Launcher (`org.prismlauncher.PrismLauncher`), wraps the desktop launcher, and adds an XDG autostart watchdog (`~/.config/autostart/gemini-tutor-watchdog.desktop`).

---

## Step 2: One-Time Parent Microsoft Sign-In (Skip if Already Set Up!)

If you haven't signed into Minecraft on this computer before, Prism Launcher opens automatically at the end of Step 1 in unlocked **Parent Setup** mode:

1. Click **Accounts** (top-right corner) → **Manage Accounts** → **Add Microsoft**, and sign in with the Microsoft account that owns Minecraft Java Edition.
2. Click **Add Instance** (top-left corner), pick your child's preferred Minecraft version (e.g., latest release), and click **OK**.
3. Double-click the new instance once so Minecraft downloads its game files the first time, then close Minecraft and Prism Launcher.

*(Need to add mods, shaders, worlds, or sign in again later? Open Gemini Tutor → **Parent icon** → **Video Game Rewards** → click **🔧 Open Prism Launcher (Parent Setup)** anytime for an unlocked 30-minute maintenance window without spending your child's points!)*

---

## Step 3: Parent Controls & How Earned Time Works (`http://localhost:8787/parent`)

Open Gemini Tutor and click the **Parent icon** (top-right corner) → **Video Game Rewards**:

- **Active Solid Writing Only:** Leaving Gemini Tutor open idle, typing single words, or pushing back earns **0 seconds**. Time counts **only** when your child actively drafts, revises, and locks verified Homework-Standard complete sentences (capital letter, ending punctuation, complete clause, and checked spelling/grammar) or completes Cover-Copy-Compare spelling retrieval.
- **Saved Across Sessions:** By default, every **15 minutes** of active solid writing earns **1 Video Game Point** (never lost between sessions!), and **2 Points (30 minutes of solid writing)** unlocks **15 minutes of game time**.
- **Custom Parent Conversion Ratios:** Adjust **Solid writing per 1 Point (min)**, **Points needed to unlock**, and **Game time earned (min)**, pick which Prism instance launches by default, **+ Grant 15m bonus**, or **Reset bank to 0:00**.
- **Automatic Time-Out & 1-Minute Save Warning:**
  - When game time is earned, a **⛏️ Play Minecraft** button appears right inside Gemini Tutor (and can also be paused mid-session to save remaining minutes for later!).
  - Launching Minecraft directly from the Desktop, Start Menu, or ChromeOS Shelf when banked time is `0:00` automatically notifies your child and opens **Gemini Tutor** instead.
  - With **1 minute left**, a native OS notification + chime warns your child to **Press Esc → Save & Quit to Title**, and at **`0:00`** Gemini Tutor closes Minecraft cleanly.
