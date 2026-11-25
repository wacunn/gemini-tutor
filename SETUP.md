# Setting Up & Updating Gemini Tutor (Windows, Mac, ChromeOS & Linux)

Takes about **5–10 minutes one time**. No coding or Python knowledge needed—after setup, you just click the **Gemini Tutor** icon, and updates happen with **one button inside the app**.

---

## Step 1: Get a Gemini API Key (One Time)

1. Open **https://aistudio.google.com/app/api-keys** and sign in with your Google account.
2. Click **Create API key**, then click **Copy**.
3. Leave that tab open—you'll paste the key once when the app opens.

---

## Step 2: Install Gemini Tutor on Your Computer

Choose your operating system below:

### Option A — Windows 11 / 10 (PC & 2-in-1 Touch Laptops)

1. Open **PowerShell**: click the **Start** button, type `PowerShell`, and press `Enter`.
2. Copy this line, right-click inside PowerShell to paste it, and press `Enter`:

   ```powershell
   irm https://raw.githubusercontent.com/wacunn/gemini-tutor/main/install.ps1 | iex
   ```

3. Wait about 1–2 minutes until it says **Done!** The tutor will open automatically, and you can close PowerShell.
4. **Every day after this:** double-click **Gemini Tutor** on your **Desktop** (or in the **Start Menu**).

---

### Option B — Mac (Apple Silicon & Intel MacBook / iMac)

1. Open **Terminal**: press `⌘ Command` + `Space`, type `Terminal`, and press `Return`.
2. Copy this line, paste it into Terminal (`⌘ Command` + `V`), and press `Return`:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/wacunn/gemini-tutor/main/install.sh | bash
   ```

3. Wait about 1–2 minutes until it says **Done!** The tutor will open automatically, and you can close Terminal.
4. **Every day after this:** double-click **Gemini Tutor** on your **Desktop** (or in your `Applications` folder).

---

### Option C — ChromeOS (Chromebook / Googlebook)

First, turn on Linux once (takes 3 minutes):

1. Open **Settings** → **About ChromeOS** → **Developers** → **Linux development environment** → click **Turn On / Set up**.
   *(On some Chromebooks: **Settings** → **Advanced** → **Developers**.)*
2. Click **Next** → **Install**. When it finishes, a black **Terminal** window opens automatically.
   *(Note: If your Chromebook is managed by a school district, Linux may be locked—use a personal profile or a Windows/Mac computer.)*

Then install Gemini Tutor:

3. Copy this line, paste it into the Terminal window (`Ctrl` + `Shift` + `V`), and press `Enter`:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/wacunn/gemini-tutor/main/install.sh | bash
   ```

4. Wait about 1–2 minutes until it says **Done!** The tutor will open in native ChromeOS Chrome (preserving full USI stylus pressure/tilt telemetry on touchscreen Chromebooks).
5. **Every day after this:** click the **App Launcher** (circle in the bottom-left corner) → **Linux apps** → **Gemini Tutor**. *(Tip: right-click the icon and select **Pin to shelf**!)*

---

### Option D — Linux (Ubuntu, Debian, Fedora, Mint, Arch)

1. Open **Terminal** (`Ctrl` + `Alt` + `T`).
2. Paste this line and press `Enter` *(if `curl` isn't installed yet: `sudo apt install -y curl` or `sudo dnf install -y curl`)*:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/wacunn/gemini-tutor/main/install.sh | bash
   ```

3. Wait about 1–2 minutes until it says **Done!** Every day after this, launch **Gemini Tutor** from your desktop application menu (or run `~/GeminiTutor/start.sh`).

---

## Step 3: First-Run Screen (30 Seconds)

The first time Gemini Tutor opens, fill in the short parent card:

- **Child's first name** and **Grade**
- **What they call you** (e.g., `Mom` or `Dad`)
- **Voice** (can be changed anytime)
- **Optional notes** (interests, what's hard at school, what to avoid)
- **Gemini API key** (paste from Step 1)

Click **Done**. Everything stays privately on your computer.

---

## Optional Step 4: Add Earned Video Game Rewards & Parent Controls

Gemini Tutor shows **zero** video game UI unless **Fists of Doom**, **Minecraft Bedrock**, and/or **Minecraft Java Edition** is installed locally on the same computer. All installed games **share the same earned game-time bank**.

### 1. Install *Fists of Doom: Toronto* (Local Install)
- **Windows (PowerShell):**
  ```powershell
  irm https://raw.githubusercontent.com/wacunn/toronto-fight-game/main/install.ps1 | iex
  ```
- **Mac, ChromeOS, or Linux (Terminal):**
  ```bash
  curl -fsSL https://raw.githubusercontent.com/wacunn/toronto-fight-game/main/install.sh | bash
  ```

### 2. Install & Time-Gate *Minecraft (Bedrock &/or Java Edition)*
See **[MINECRAFT_SETUP.md](MINECRAFT_SETUP.md)** for full details and Microsoft account sign-in steps, or run the one-line setup for your OS:

- **Windows 11 / 10 — Minecraft Bedrock & Java (PowerShell):**
  ```powershell
  irm https://raw.githubusercontent.com/wacunn/gemini-tutor/main/setup_minecraft_windows.ps1 | iex
  ```
  *(Automatically detects & gates **Minecraft for Windows (Bedrock)** from Microsoft Store / Xbox App AND installs **Prism Launcher + Java 21** so your child can spend earned minutes on **either Bedrock or Java**! For Bedrock-only without installing Java: `$env:TUTOR_BEDROCK_ONLY="1"; irm https://raw.githubusercontent.com/wacunn/gemini-tutor/main/setup_minecraft_windows.ps1 | iex`.)*
- **Mac (Terminal):**
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

### 3. Configure Parent Controls & Parent Override (`http://localhost:8787/parent`)
Click the **Parent icon** (top-right corner of Gemini Tutor) → **Video Game Rewards**:

- **ADHD-Friendly `1:2` Default Ratio:** By default, **1 minute of active, verified solid writing earns 2 minutes of gaming** (`15 min solid writing → 1 Point → 30 min gaming`, with partial minutes always saved across sessions). You can adjust **minutes per point**, **points to unlock**, and **game minutes earned** anytime or click 1-tap presets.
- **Parent Override (Free Play Unlock):** Unlock free play for **30m**, **1 hr**, **Rest of Today**, or **Until Turned Off** (plus **End Override Now**) without draining your child's banked points or closing Bedrock/Java/Fists of Doom.
- **Bonus / Reset / Per-Edition Lock Controls:** Grant `+15m` / `+30m` bonus time, reset banked time to `0:00`, lock standalone *Fists of Doom* at `0:00`, or toggle OS-level gating independently for **Minecraft Bedrock** and **Minecraft Java** (silent login watchdog + Desktop/Shelf shortcut wrapper + 1-minute save warning + auto-close at `0:00`).
- **Parent Maintenance Mode:** Click **🔧 Open Bedrock (Parent Setup)** or **🔧 Open Prism Launcher (Parent Setup)** anytime to log into Microsoft, update Minecraft, or install mods without deducting your child's banked time.

---

## How to Update the Software (One Click in the Menu!)

Whenever an update is pushed to GitHub, you do **not** need Terminal or PowerShell:

1. In Gemini Tutor, click the **Parent icon** (person icon in the top-right corner).
2. Scroll to **Software** and click **Check for updates**.
3. If a new version is ready, click **Update now**.
4. Wait ~45 seconds—the app downloads the new code, **keeps all of your child's progress, points, and your API key**, restarts itself, and reloads the page automatically!

---

## Daily Tips & Troubleshooting

- **Headphones with a mic** give the best experience so your child can talk while Gemini talks; without headphones, the app automatically pauses the mic while Gemini speaks so there's no echo.
- **Stylus / 2-in-1 Touchscreen:** Tap the **pen icon** next to the typing box on any Windows 2-in-1 (Windows Ink), touchscreen Chromebook (USI 2.0), or iPad (`http://<computer-ip>:8787`) to handwrite with full pressure sensitivity and palm rejection.
- **If the page ever doesn't open:** Wait 5 seconds and click the **Gemini Tutor** icon again, or re-run the Step 2 install line (it safely updates without erasing your child's data or API key).
- **To close the background server completely:** Parent page → **Software** → **Quit tutor**.
