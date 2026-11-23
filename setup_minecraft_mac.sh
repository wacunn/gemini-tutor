#!/usr/bin/env bash
# Automatic macOS Setup for Minecraft Java Edition + Gemini Tutor Earned-Time Gating.
#   curl -fsSL https://raw.githubusercontent.com/wacunn/gemini-tutor/main/setup_minecraft_mac.sh | bash
#
# Safe to run on both Apple Silicon (M1/M2/M3/M4) and Intel Macs:
# 1. Installs or updates Gemini Tutor in ~/GeminiTutor (preserving data/ and .env)
# 2. Installs Prism Launcher.app (via Homebrew if present, or official GitHub Universal release) + Temurin Java 21
# 3. Enables Minecraft earned-writing-time gating in data/learner.json
# 4. Registers a silent macOS LaunchAgent watchdog (`launch.py --no-open`) so time limits work from login
# 5. Opens Prism Launcher in unlocked Parent Setup mode if first-time Microsoft sign-in is needed

set -euo pipefail

REPO="${TUTOR_REPO:-wacunn/gemini-tutor}"
DIR="${TUTOR_DIR:-$HOME/GeminiTutor}"
PORT="${PORT:-8787}"
say() { printf "\n\033[1;36m%s\033[0m\n" "$*"; }

if [[ "$(uname)" != "Darwin" ]]; then
  echo "This script is for macOS. On Chromebook/Linux use setup_minecraft_chromebook.sh or setup_minecraft_linux.sh."
  exit 1
fi

say "Setting up Minecraft Java Edition + Gemini Tutor Earned-Time Gating on macOS ($(uname -m))…"

# 1) Ensure Gemini Tutor is installed & updated
say "Step 1 of 4: Ensuring Gemini Tutor is installed & up to date in $DIR…"
if [[ -z "${TUTOR_SKIP_UPDATE:-}" ]]; then
  TUTOR_NO_LAUNCH=1 bash -c "$(curl -fsSL "https://raw.githubusercontent.com/$REPO/main/install.sh")"
fi

VENV_PY="$DIR/.venv/bin/python"

# 2) Install Prism Launcher.app (+ Java 21 via brew if available) if not already installed
say "Step 2 of 4: Checking Minecraft (Prism Launcher)…"
PRISM_APP=""
if [[ -d "/Applications/Prism Launcher.app" ]]; then
  PRISM_APP="/Applications/Prism Launcher.app"
elif [[ -d "$HOME/Applications/Prism Launcher.app" ]]; then
  PRISM_APP="$HOME/Applications/Prism Launcher.app"
fi

if [[ -z "$PRISM_APP" && -z "${TUTOR_SKIP_PRISM_INSTALL:-}" ]]; then
  if command -v brew >/dev/null 2>&1; then
    say "Installing Prism Launcher & Temurin Java 21 via Homebrew…"
    brew install --cask prismlauncher || true
    brew install --cask temurin@21 || true
  fi
  if [[ -d "/Applications/Prism Launcher.app" ]]; then
    PRISM_APP="/Applications/Prism Launcher.app"
  elif [[ -d "$HOME/Applications/Prism Launcher.app" ]]; then
    PRISM_APP="$HOME/Applications/Prism Launcher.app"
  fi
fi

if [[ -z "$PRISM_APP" && -z "${TUTOR_SKIP_PRISM_INSTALL:-}" ]]; then
  say "Downloading latest official Prism Launcher Universal macOS app from GitHub…"
  DL_URL="$("$VENV_PY" - <<'PY'
import json, urllib.request
req = urllib.request.Request(
    "https://api.github.com/repos/PrismLauncher/PrismLauncher/releases/latest",
    headers={"User-Agent": "gemini-tutor-setup"},
)
with urllib.request.urlopen(req, timeout=20) as r:
    rel = json.loads(r.read().decode("utf-8"))
for a in rel.get("assets", []):
    n = a.get("name", "")
    if "macOS" in n and n.endswith(".zip") and "Legacy" not in n:
        print(a["browser_download_url"])
        break
PY
)"
  if [[ -n "$DL_URL" ]]; then
    TMP_ZIP="$(mktemp -d)/PrismLauncher.zip"
    curl -fL "$DL_URL" -o "$TMP_ZIP"
    DEST_APPS="/Applications"
    [[ -w "/Applications" ]] || { mkdir -p "$HOME/Applications"; DEST_APPS="$HOME/Applications"; }
    ditto -x -k "$TMP_ZIP" "$DEST_APPS"
    xattr -dr com.apple.quarantine "$DEST_APPS/Prism Launcher.app" 2>/dev/null || true
    rm -f "$TMP_ZIP"
    PRISM_APP="$DEST_APPS/Prism Launcher.app"
  fi
fi

# 3) Enable Minecraft gating + macOS LaunchAgent watchdog
say "Step 3 of 4: Linking macOS login watchdog & earned-time rules…"
CFG_JSON="$("$VENV_PY" - "$DIR" <<'PY'
import json, sys
sys.path.insert(0, sys.argv[1])
from tutor import arcade
from tutor.record import load_learner, save_learner

rec = load_learner()
arc = arcade.ensure_arcade(rec)
arc["enabled"] = True
arc["gate_minecraft"] = True
save_learner(rec)
arcade.sync_minecraft_desktop_gate(True)
inst = arcade.list_minecraft_instances()
print(json.dumps({
    "flavor": arcade.minecraft_flavor(),
    "instances": len(inst.get("instances") or []),
}))
PY
)"

# 4) Start Gemini Tutor background server & check first-time Microsoft login
say "Step 4 of 4: Starting Gemini Tutor background supervisor…"
TUTOR_NO_OPEN=1 "$DIR/start.sh" || true

HAS_INST="$("$VENV_PY" -c "import json,sys; d=json.loads(sys.argv[1]); print(1 if d.get('instances',0)>0 else 0)" "$CFG_JSON")"
FLAVOR="$("$VENV_PY" -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('flavor',''))" "$CFG_JSON")"

if [[ "$FLAVOR" == "prism" && "$HAS_INST" == "0" ]]; then
  say "Almost done — One-Time Parent Sign-In Inside Prism Launcher:"
  echo "  1. In the Prism Launcher window opening now, click 'Accounts' (top-right) -> 'Manage Accounts' -> 'Add Microsoft' and sign in."
  echo "  2. Click 'Add Instance' (top-left) -> select a Minecraft version (e.g. latest release) -> click 'OK'."
  echo "  3. Launch the instance once so Minecraft finishes its first-time download, then close it."
  echo "  After that, Minecraft is automatically gated by earned solid writing time in Gemini Tutor!"
  echo "  • Parent controls: http://localhost:$PORT/parent"
  if [[ -z "${TUTOR_NO_LAUNCH:-}" ]]; then
    curl -fsS -X POST "http://127.0.0.1:$PORT/api/arcade/minecraft-parent-setup" >/dev/null 2>&1 || \
      open -a "$PRISM_APP" || true
  fi
else
  say "Done! Minecraft is linked and time-gated by Gemini Tutor."
  echo "  • Parent reward rules & bonus minutes: http://localhost:$PORT/parent"
  [[ -n "${TUTOR_NO_LAUNCH:-}" ]] || "$DIR/start.sh"
fi
