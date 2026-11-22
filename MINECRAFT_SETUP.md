# Setting Up Minecraft Rewards (Windows 11/10 & Chromebook)

With **Gemini Tutor**, your child can earn **Minecraft** play time (and/or **Fists of Doom** play time) by doing active, high-quality writing—not just leaving the app open!

---

## Option A — Windows 11 / 10 PC (e.g., Lenovo Yoga 7i 2-in-1)

1. Open **PowerShell**: click **Start**, type `PowerShell`, and press `Enter`.
2. Copy this line, right-click inside PowerShell to paste it, and press `Enter`:

   ```powershell
   irm https://raw.githubusercontent.com/wacunn/gemini-tutor/main/setup_minecraft_windows.ps1 | iex
   ```

3. Wait 1–2 minutes while it automatically:
   - Installs or updates **Gemini Tutor** (`$HOME\GeminiTutor`, keeping your child's data & API key)
   - Installs **Prism Launcher** + **Java 21** via `winget` *(and also auto-detects the Official Microsoft Store Minecraft Launcher & Minecraft Bedrock if installed)*
   - Adds a silent **Windows Startup Watchdog** (`pythonw.exe`) + gated Desktop shortcut so earned-time limits are enforced automatically from Windows login

---

## Option B — Chromebook (Linux / Crostini)

1. Open your Chromebook's **Linux Terminal** *(if Linux isn't turned on yet, see **SETUP.md → Option C** first)*.
2. Copy this line, paste it into Terminal (`Ctrl` + `Shift` + `V`), and press `Enter`:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/wacunn/gemini-tutor/main/setup_minecraft_chromebook.sh | bash
   ```

3. Wait a couple of minutes while it installs Prism Launcher (`--user` Flatpak), applies the ChromeOS display fix (`QT_QPA_PLATFORM=xcb`), and links the ChromeOS shelf icon to Gemini Tutor.

---

## One-Time Microsoft Sign-In (Skip if Minecraft Is Already Set Up!)

If you haven't signed into Minecraft on this computer before, Prism Launcher opens automatically at the end of setup:

1. Click **Accounts** (top-right corner) → **Manage Accounts** → **Add Microsoft**, and sign in with the Microsoft account that owns Minecraft.
2. Click **Add Instance** (top-left corner), pick your child's preferred Minecraft version, and click **OK**.
3. Double-click the new instance once so Minecraft downloads its files the first time, then close Minecraft and Prism Launcher.

*(Need to add mods, worlds, or sign in again later? Open Gemini Tutor → **Parent icon** → **Video Game Rewards** → click **Open Prism Launcher (Parent Setup)** anytime without spending your child's points!)*

---

## How Earning & Playing Minecraft Works

- **Active Solid Writing Only:** Leaving Gemini Tutor open idle, typing single words, or pushing back earns **0 seconds**. Time counts **only** when your child actively drafts, revises, and locks verified complete sentences (capital letter, ending punctuation, complete clause, and checked spelling/grammar).
- **Saved Across Sessions:** By default, every **15 minutes** of active solid writing earns **1 Video Game Point** (never lost between sessions), and **2 Points (30 minutes of solid writing)** unlocks **15 minutes of game time**.
- **Customizable by Parents:** On the **Parent page** (`http://localhost:8787/parent`), under **Video Game Rewards**, you can change the writing-to-game-time ratio (e.g., 30 min writing → 15 min game, 30 min → 20 min, 45 min → 15 min), grant bonus minutes, or reset the bank.
- **Automatic Time-Out & 1-Minute Save Warning:**
  - When game time is earned, a **⛏️ Play Minecraft** button appears right inside Gemini Tutor.
  - Launching Minecraft from the Desktop / Start Menu / Shelf when banked time is `0:00` automatically notifies your child and opens **Gemini Tutor** instead.
  - With **1 minute left**, a native Windows 11 Toast notification + chime (or ChromeOS alert) warns your child to **Save & Quit to Title**, and at **0:00** Gemini Tutor closes Minecraft cleanly.
