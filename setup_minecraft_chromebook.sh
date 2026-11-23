#!/usr/bin/env bash
# Automatic Chromebook (Crostini) & Desktop Linux Setup for Minecraft Java + Gemini Tutor Time-Gating.
#   curl -fsSL https://raw.githubusercontent.com/wacunn/gemini-tutor/main/setup_minecraft_chromebook.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/wacunn/gemini-tutor/main/setup_minecraft_linux.sh | bash
#
# Safe to run on ChromeOS (ARM64 & Intel/AMD) as well as Ubuntu, Debian, Linux Mint, Fedora, and Arch:
# 1. Installs system packages (`flatpak`, `gnome-keyring`, OpenGL, `libnotify`) via apt / dnf / pacman
# 2. Installs Prism Launcher (`org.prismlauncher.PrismLauncher`) as a `--user` Flatpak
# 3. Applies `QT_QPA_PLATFORM=xcb` override when running inside ChromeOS Crostini
# 4. Ensures Gemini Tutor is installed in ~/GeminiTutor
# 5. Wires app-launcher icon gating + autostart login watchdog + Gemini Tutor's earned-writing-time bank

set -euo pipefail

REPO="${TUTOR_REPO:-wacunn/gemini-tutor}"
DIR="${TUTOR_DIR:-$HOME/GeminiTutor}"
PRISM_ID="org.prismlauncher.PrismLauncher"
IS_CROSTINI=0
[[ -e "/dev/.cros_milestone" ]] && IS_CROSTINI=1
say() { printf "\n\033[1;36m%s\033[0m\n" "$*"; }

say "Setting up Minecraft Java (Prism Launcher) + Gemini Tutor Rewards ($(uname -s) $(uname -m))…"

# 1) Install system dependencies required for Flatpak, OpenGL, Microsoft account keyring & desktop notifications
say "Step 1 of 5: Installing Linux packages (flatpak, keyring, notifications)…"
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -y
  sudo apt-get install -y flatpak gnome-keyring libopengl0 libsecret-1-0 libnotify-bin curl python3
elif command -v dnf >/dev/null 2>&1; then
  sudo dnf install -y flatpak gnome-keyring libsecret libnotify curl python3
elif command -v pacman >/dev/null 2>&1; then
  sudo pacman -Sy --noconfirm --needed flatpak gnome-keyring libsecret libnotify curl python
elif ! command -v flatpak >/dev/null 2>&1; then
  echo "Please install 'flatpak' and 'curl' using your Linux package manager, then re-run this script."
  exit 1
fi

# 2) Configure user-scoped Flathub & install Prism Launcher (works on both ARM64 & x86_64)
say "Step 2 of 5: Installing Prism Launcher (--user Flatpak)…"
flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
if ! flatpak info --user "$PRISM_ID" >/dev/null 2>&1; then
  flatpak install --user -y flathub "$PRISM_ID"
else
  echo "Prism Launcher Flatpak already installed."
fi

# 3) Apply permanent XWayland override on ChromeOS Crostini (native Wayland disconnects Sommelier)
if [[ "$IS_CROSTINI" -eq 1 ]]; then
  say "Step 3 of 5: Applying ChromeOS XWayland display fix (QT_QPA_PLATFORM=xcb)…"
  flatpak --user override --env=QT_QPA_PLATFORM=xcb "$PRISM_ID"
else
  say "Step 3 of 5: Desktop Linux display ready."
fi

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

"$DIR/.venv/bin/python" - "$DIR" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from tutor import arcade
from tutor.record import load_learner, save_learner

rec = load_learner()
arc = arcade.ensure_arcade(rec)
arc["enabled"] = True
arc["gate_minecraft"] = True
save_learner(rec)
arcade.sync_minecraft_desktop_gate(True)
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
