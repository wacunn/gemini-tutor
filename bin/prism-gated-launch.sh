#!/usr/bin/env bash
# ChromeOS Shelf / App Drawer Gating Wrapper for Prism Launcher (Minecraft).
# Intercepts direct shelf launches:
# - If earned game time is available in Gemini Tutor (or parent disabled gating), starts the
#   Gemini Tutor background time-watchdog silently and launches Prism Launcher under XWayland (xcb).
# - If earned game time is 0:00, notifies the student and opens Gemini Tutor instead.

set -euo pipefail

TUTOR_DIR="${TUTOR_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
LEARNER_JSON="$TUTOR_DIR/data/learner.json"
PRISM_ID="org.prismlauncher.PrismLauncher"
INST_DIR="$HOME/.var/app/$PRISM_ID/data/PrismLauncher/instances"

export QT_QPA_PLATFORM=xcb

if [[ "${1:-}" == "--parent-setup" ]]; then
  shift
  exec flatpak run "$PRISM_ID" "$@"
fi

# Allow initial first-time parent login/instance creation if zero instances exist yet
HAS_INSTANCE=0
if [[ -d "$INST_DIR" ]]; then
  for cfg in "$INST_DIR"/*/instance.cfg; do
    if [[ -f "$cfg" ]]; then
      HAS_INSTANCE=1
      break
    fi
  done
fi

ALLOW=1
if [[ "$HAS_INSTANCE" -eq 1 && -f "$LEARNER_JSON" ]]; then
  ALLOW="$(python3 - "$LEARNER_JSON" <<'PY'
import json, sys
try:
    rec = json.load(open(sys.argv[1], encoding="utf-8"))
    arc = rec.get("arcade") or {}
    enabled = bool(arc.get("enabled", True))
    gate = bool(arc.get("gate_minecraft", True))
    avail = float(arc.get("game_seconds_available") or 0.0)
    print("0" if (enabled and gate and avail < 1.0) else "1")
except Exception:
    print("1")
PY
)"
fi

if [[ "$ALLOW" == "0" ]]; then
  if command -v notify-send >/dev/null 2>&1; then
    notify-send -u normal "⛏️ Earn Minecraft Time in Gemini Tutor!" "You have 0:00 of game time banked. Opening Gemini Tutor so you can earn points!" || true
  fi
  exec "$TUTOR_DIR/start.sh"
fi

# Ensure Gemini Tutor's background watchdog is running so banked minutes count down accurately
if [[ -x "$TUTOR_DIR/start.sh" ]]; then
  TUTOR_NO_OPEN=1 "$TUTOR_DIR/start.sh" >/dev/null 2>&1 || true
fi

exec flatpak run "$PRISM_ID" "$@"
