# Setting Up & Updating Gemini Tutor

Takes about **5–10 minutes one time**. No coding or Python knowledge needed—after setup, you just click the **Gemini Tutor** icon, and updates happen with **one button inside the app**.

---

## Step 1: Get a Gemini API Key (One Time)

1. Open **https://aistudio.google.com/app/api-keys** and sign in with your Google account.
2. Click **Create API key**, then click **Copy**.
3. Leave that tab open—you'll paste the key once when the app opens.

---

## Step 2: Install on Your Computer

Choose your computer type below:

### Option A — Mac (MacBook / iMac)

1. Open **Terminal**: press `⌘ Command` + `Space`, type `Terminal`, and press `Return`.
2. Copy this line, paste it into Terminal (`⌘ Command` + `V`), and press `Return`:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/wacunn/gemini-tutor/main/install.sh | bash
   ```

3. Wait about 1–2 minutes until it says **Done!** The tutor will open automatically, and you can close Terminal.
4. **Every day after this:** double-click **Gemini Tutor** on your **Desktop** (or in your `Applications` folder).

---

### Option B — Windows PC

1. Open **PowerShell**: click the **Start** button, type `PowerShell`, and press `Enter`.
2. Copy this line, right-click inside PowerShell to paste it, and press `Enter`:

   ```powershell
   irm https://raw.githubusercontent.com/wacunn/gemini-tutor/main/install.ps1 | iex
   ```

3. Wait about 1–2 minutes until it says **Done!** The tutor will open automatically, and you can close PowerShell.
4. **Every day after this:** double-click **Gemini Tutor** on your **Desktop** (or in the **Start Menu**).

---

### Option C — Chromebook / Googlebook

First, turn on Linux once (takes 3 minutes):

1. Open **Settings** → **About ChromeOS** → **Developers** → **Linux development environment** → click **Turn On / Set up**.
   *(On some Chromebooks: **Settings** → **Advanced** → **Developers**.)*
2. Click **Next** → **Install**. When it finishes, a black **Terminal** window opens automatically.
   *(Note: If your Chromebook is managed by a school district, Linux may be locked—use a personal profile or a Mac/PC.)*

Then install Gemini Tutor:

3. Copy this line, paste it into the Terminal window (`Ctrl` + `Shift` + `V`), and press `Enter`:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/wacunn/gemini-tutor/main/install.sh | bash
   ```

4. Wait about 1–2 minutes until it says **Done!** The tutor will open in Chrome.
5. **Every day after this:** click the **App Launcher** (circle in the bottom-left corner) → **Linux apps** → **Gemini Tutor**. *(Tip: right-click the icon and select **Pin to shelf** so it stays on the bottom bar!)*

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

## How to Update the Software (One Click in the Menu!)

Whenever an update is pushed to GitHub, you do **not** need Terminal or PowerShell:

1. In Gemini Tutor, click the **Parent icon** (person icon in the top-right corner).
2. Scroll to **Software** and click **Check for updates**.
3. If a new version is ready, click **Update now**.
4. Wait ~45 seconds—the app downloads the new code, **keeps all of your child's progress and your API key**, restarts itself, and reloads the page automatically!

---

## Optional: Earn Video Game Time (Fists of Doom &amp; Minecraft on Windows / Chromebook)

If **Fists of Doom** and/or **Minecraft** is installed locally on the same computer, your child can earn video game points from **active, verified writing** (15 min solid writing = 1 point, saved across sessions; 2 points = 15 min of game time by default, customizable on the **Parent page**):

- **Install Fists of Doom (Windows PowerShell):**
  ```powershell
  irm https://raw.githubusercontent.com/wacunn/toronto-fight-game/main/install.ps1 | iex
  ```
- **Set Up &amp; Time-Gate Minecraft on Windows 11/10 (PowerShell):**
  ```powershell
  irm https://raw.githubusercontent.com/wacunn/gemini-tutor/main/setup_minecraft_windows.ps1 | iex
  ```
- **Install Fists of Doom (Mac / Chromebook):**
  ```bash
  curl -fsSL https://raw.githubusercontent.com/wacunn/toronto-fight-game/main/install.sh | bash
  ```
- **Set Up &amp; Time-Gate Minecraft on a Chromebook (Prism Launcher):**
  See **[MINECRAFT_SETUP.md](MINECRAFT_SETUP.md)**, or run this one line in your Chromebook's Linux Terminal:
  ```bash
  curl -fsSL https://raw.githubusercontent.com/wacunn/gemini-tutor/main/setup_minecraft_chromebook.sh | bash
  ```

*(If neither game is installed on a computer, Gemini Tutor hides all video game UI completely.)*

---

## Daily Tips & Troubleshooting

- **Headphones with a mic** give the best experience so your child can talk while Gemini talks; without headphones, the app automatically pauses the mic while Gemini speaks so there's no echo.
- **Stylus / Touchscreen:** Tap the **pen icon** next to the typing box on any touchscreen Chromebook, Windows 2-in-1, or iPad (`http://<computer-ip>:8787`) to handwrite spelling words or captions.
- **If the page ever doesn't open:** Wait 5 seconds and click the **Gemini Tutor** icon again, or re-run the Step 2 install line (it safely updates without erasing your child's data or API key).
- **To close the background server completely:** Parent page → **Software** → **Quit tutor**.
