# Setting Up Minecraft Rewards on a Chromebook (Gemini Tutor)

With **Gemini Tutor**, your child can earn **Minecraft** play time (and/or **Fists of Doom** play time) by doing active, high-quality writing—not just leaving the app open!

Because many Chromebooks use **ARM64 (`aarch64`)** processors where Mojang's standard Linux `.deb` installer does not work, our automatic Chromebook script sets up **Prism Launcher** (with ChromeOS's required `XWayland` display fix) and links it directly to Gemini Tutor's time bank.

---

## One-Line Chromebook Setup (For Parents)

1. Open your Chromebook's **Linux Terminal** *(if Linux isn't turned on yet, see **SETUP.md → Option C** first)*.
2. Copy this line, paste it into Terminal (`Ctrl` + `Shift` + `V`), and press `Enter`:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/wacunn/gemini-tutor/main/setup_minecraft_chromebook.sh | bash
   ```

3. Wait a couple of minutes while it installs Prism Launcher, applies the ChromeOS display fix (`QT_QPA_PLATFORM=xcb`), and links the ChromeOS shelf icon to Gemini Tutor.

### One-Time Microsoft Sign-In (Skip if Minecraft Is Already Set Up!)

If you haven't signed into Minecraft on this Chromebook before, Prism Launcher will open automatically at the end of the script:

1. Click **Accounts** (top-right corner) → **Manage Accounts** → **Add Microsoft**, and sign in with the Microsoft account that owns Minecraft Java Edition.
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
  - Clicking the Prism Launcher icon on the ChromeOS shelf when banked time is `0:00` automatically opens **Gemini Tutor** instead of Minecraft.
  - With **1 minute left**, a ChromeOS alert pops up telling your child to **Save & Quit to Title**, and at **0:00** Gemini Tutor closes Minecraft cleanly (`flatpak kill org.prismlauncher.PrismLauncher`).
