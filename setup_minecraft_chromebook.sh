#!/usr/bin/env bash
# Automatic Chromebook (Crostini Linux) Setup for Minecraft + Gemini Tutor Time-Gating.
#   curl -fsSL https://raw.githubusercontent.com/wacunn/gemini-tutor/main/setup_minecraft_chromebook.sh | bash
#
# Safe to run on both ARM64 (aarch64) and Intel/AMD (x86_64) Chromebooks:
# 1. Installs system packages (`flatpak`, `gnome-keyring`, `libopengl0`, `libsecret-1-0`, `libnotify-bin`)
# 2. Installs Prism Launcher (`org.prismlauncher.PrismLauncher`) as a `--user` Flatpak
# 3. Applies `QT_QPA_PLATFORM=xcb` override (prevents Crostini Wayland/Sommelier crashes)
# 4. Ensures Gemini Tutor is installed in ~/GeminiTutor
# 5. Wires ChromeOS shelf icon gating + Gemini Tutor's earned-writing-time watchdog

set -euo pipefail

REPO="${TUTOR_REPO:-wacunn/gemini-tutor}"
DIR="${TUTOR_DIR:-$HOME/GeminiTutor}"
PRISM_ID="org.prismlauncher.PrismLauncher"
say() { printf "\n\033[1;36m%s\033[0m\n" "$*"; }

say "Setting up Minecraft (Prism Launcher) + Gemini Tutor Rewards on Chromebook ($(uname -m))…"

if ! command -v apt-get >/dev/null 2>&1; then
  echo "This automatic setup script is designed for Chromebook Linux (Debian / Crostini)."
  exit 1
fi

# 1) Install system dependencies required for Flatpak, OpenGL, Microsoft account keyring & desktop notifications
say "Step 1 of 5: Installing Chromebook Linux packages (flatpak, gnome-keyring, libopengl0)…"
sudo apt-get update -y
sudo apt-get install -y flatpak gnome-keyring libopengl0 libsecret-1-0 libnotify-bin curl python3

# 2) Configure user-scoped Flathub & install Prism Launcher (Crostini requires --user Flatpak)
say "Step 2 of 5: Installing Prism Launcher (--user Flatpak, works on both ARM64 & Intel Chromebooks)…"
flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
if ! flatpak info --user "$PRISM_ID" >/dev/null 2>&1; then
  flatpak install --user -y flathub "$PRISM_ID"
else
  echo "Prism Launcher Flatpak already installed."
fi

# 3) Apply permanent XWayland override (native Wayland disconnects Sommelier in Crostini)
say "Step 3 of 5: Applying ChromeOS XWayland display fix (QT_QPA_PLATFORM=xcb)…"
flatpak --user override --env=QT_QPA_PLATFORM=xcb "$PRISM_ID"

# 4) Ensure Gemini Tutor is installed & updated to the latest version (keeps data/ and .env)
say "Step 4 of 5: Ensuring Gemini Tutor is installed & up to date in $DIR…"
if [[ -z "${TUTOR_SKIP_UPDATE:-}" ]]; then
  TUTOR_NO_LAUNCH=1 bash -c "$(curl -fsSL "https://raw.githubusercontent.com/$REPO/main/install.sh")"
fi
chmod +x "$DIR/start.sh" "$DIR/bin/prism-gated-launch.sh" 2>/dev/null || true

# 5) Configure ChromeOS App Drawer / Shelf gating & enable Minecraft rewards in learner.json
say "Step 5 of 5: Linking ChromeOS Shelf icon & Gemini Tutor earned-time gating…"
EXPORT_DESKTOP="$HOME/.local/share/flatpak/exports/share/applications/$PRISM_ID.desktop"
LOCAL_DESKTOP="$HOME/.local/share/applications/$PRISM_ID.desktop"
WRAPPER="$DIR/bin/prism-gated-launch.sh"

mkdir -p "$HOME/.local/share/applications" "$DIR/data"
if [[ -f "$EXPORT_DESKTOP" && -f "$WRAPPER" ]]; then
  sed "s|^Exec=.*$|Exec=\"$WRAPPER\" %U|" "$EXPORT_DESKTOP" > "$LOCAL_DESKTOP"
  sed -i "s|^Exec=.*$|Exec=\"$WRAPPER\" %U|" "$EXPORT_DESKTOP" 2>/dev/null || true
fi

python3 - "$DIR/data/learner.json" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
rec = {}
if p.exists():
    try:
        rec = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        rec = {}
arc = rec.setdefault("arcade", {})
arc.setdefault("enabled", True)
arc.setdefault("minutes_per_point", 15)
arc.setdefault("points_to_unlock", 2)
arc.setdefault("reward_game_minutes", 15)
arc["gate_minecraft"] = True
p.write_text(json.dumps(rec, indent=2), encoding="utf-8")
PY

# Start Gemini Tutor background server silently so the watchdog & Parent page are live
TUTOR_NO_OPEN=1 "$DIR/start.sh" || true

# Check if the parent still needs to log into Microsoft & add a Minecraft instance
INST_DIR="$HOME/.var/app/$PRISM_ID/data/PrismLauncher/instances"
HAS_INSTANCE=0
if [[ -d "$INST_DIR" ]]; then
  for cfg in "$INST_DIR"/*/instance.cfg; do
    if [[ -f "$cfg" ]]; then
      HAS_INSTANCE=1
      break
    fi
  done
fi

if [[ "$HAS_INSTANCE" -eq 1 ]]; then
  say "Done! Existing Minecraft instance detected and linked to Gemini Tutor."
  echo "  • Writing reward settings: http://localhost:8787/parent"
  echo "  • Students earn points from active, verified writing and click 'Play Minecraft' inside Gemini Tutor!"
else
  say "Almost done — One-Time Parent Login Inside Prism Launcher:"
  echo "  1. In the Prism Launcher window opening now, click 'Accounts' (top-right) → 'Add Microsoft' and sign in."
  echo "  2. Click 'Add Instance' (top-left) → select a Minecraft version (e.g. latest release) → click 'OK'."
  echo "  3. Launch the instance once to let Minecraft finish its first-time download, then close it."
  echo "  After that, Minecraft is automatically gated by earned writing time in Gemini Tutor!"
  if [[ -z "${TUTOR_NO_LAUNCH:-}" ]]; then
    curl -fsS -X POST "http://127.0.0.1:8787/api/arcade/minecraft-parent-setup" >/dev/null 2>&1 || \
      QT_QPA_PLATFORM=xcb nohup flatpak run "$PRISM_ID" >/dev/null 2>&1 &
  fi
fi
