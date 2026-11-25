# Setting Up Minecraft (Bedrock & Java) Rewards & Parent Controls (Windows, Mac, ChromeOS & Linux)

With **Gemini Tutor**, your child can earn **Minecraft Bedrock Edition** (*Minecraft for Windows*), **Minecraft Java Edition**, and/or **[Fists of Doom](https://github.com/wacunn/toronto-fight-game)** play time by doing active, high-quality writing—never by leaving the app open idle! All installed games **share the same earned game-time bank**, so your child can spend earned minutes on whichever game or edition they feel like playing.

Each one-line setup script below automatically installs or updates **Gemini Tutor**, wires a silent login watchdog + shortcut gating so Minecraft cannot be played at `0:00`, installs **Prism Launcher** (+ **Java 21** where needed), and on Windows automatically detects & gates **both Minecraft Bedrock and Minecraft Java**.

---

## Step 1: Run the One-Line Setup for Your OS

### Option A — Windows 11 / 10: Minecraft Bedrock &/or Java (PowerShell)
1. *(Optional, for Bedrock Edition)* Install **Minecraft for Windows** from the **Microsoft Store** or **Xbox App** (either before or after running the script below—Gemini Tutor detects it automatically!).
2. Click **Start**, type `PowerShell`, and press `Enter`.
3. Right-click to paste this line and press `Enter`:
   ```powershell
   irm https://raw.githubusercontent.com/wacunn/gemini-tutor/main/setup_minecraft_windows.ps1 | iex
   ```
   * Installs/updates Gemini Tutor (`$HOME\GeminiTutor`), links **Minecraft Bedrock** (`Minecraft for Windows`), installs **Prism Launcher** + **Eclipse Temurin Java 21** via `winget`, adds a silent `pythonw.exe` login watchdog in Windows `Startup`, and creates gated Desktop shortcuts for Bedrock & Java.
   * *(Want **Bedrock only** without installing Java? Run `$env:TUTOR_BEDROCK_ONLY="1"; irm https://raw.githubusercontent.com/wacunn/gemini-tutor/main/setup_minecraft_windows.ps1 | iex`.)*

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

## Step 3: Parent Controls, Parent Override & How Earned Time Works (`http://localhost:8787/parent`)

Open Gemini Tutor and click the **Parent icon** (top-right corner) → **Video Game Rewards**:

- **Active Solid Writing Only:** Leaving Gemini Tutor open idle, typing single words, or pushing back earns **0 seconds**. Time counts **only** when your child actively drafts, revises, and locks verified Homework-Standard complete sentences (capital letter, ending punctuation, complete clause, and checked spelling/grammar) or completes Cover-Copy-Compare spelling retrieval.
- **ADHD-Friendly `1:2` Default (`1 min solid work = 2 min gaming`, Saved Across Sessions):** By default, **15 minutes** of active solid writing earns **1 Video Game Point** (saved across sessions!) and immediately unlocks **30 minutes of game time**—usable in **Minecraft Bedrock**, **Minecraft Java**, or **Fists of Doom**.
- **Parent Override (1-Click Free Play Unlock):** Letting your child play with friends or enjoy weekend free play? Click **🔓 Unlock 30m**, **🔓 Unlock 1 hr**, **🔓 Rest of Today**, or **🔓 Until Turned Off** (and **🔒 End Override Now** anytime) so they can play Bedrock, Java, or Fists of Doom freely without draining banked points.
- **Custom Parent Conversion Ratios & Per-Edition Toggles:** Adjust **Solid writing per 1 Point (min)**, **Points needed to unlock**, and **Game time earned (min)**, gate **Minecraft Bedrock** and **Minecraft Java** independently, pick which Prism instance launches by default, **+ Grant 15m / 30m bonus**, or **Reset bank to 0:00**.
- **Automatic Time-Out & 1-Minute Save Warning:**
  - When game time is earned (or Parent Override is active), **🪨 Minecraft Bedrock** and **☕ Minecraft Java** buttons appear right inside Gemini Tutor (and can be paused mid-session to save remaining minutes for later!).
  - Launching Minecraft Bedrock or Java directly from the Desktop, Start Menu, or ChromeOS Shelf when banked time is `0:00` automatically notifies your child and opens **Gemini Tutor** instead.
  - With **1 minute left**, a native OS notification + chime warns your child to **Press Esc → Save & Quit**, and at **`0:00`** Gemini Tutor closes Minecraft cleanly.
