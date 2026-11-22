#!/usr/bin/env bash
# Gemini Tutor installer for Mac and Chromebook (Linux).
#   curl -fsSL https://raw.githubusercontent.com/wacunn/gemini-tutor/main/install.sh | bash
# Safe to run again: it updates the code and keeps your child's data and API key.
set -euo pipefail

REPO="${TUTOR_REPO:-wacunn/gemini-tutor}"
DIR="${TUTOR_DIR:-$HOME/GeminiTutor}"
say() { printf "\n\033[1m%s\033[0m\n" "$*"; }

say "Installing Gemini Tutor into $DIR"

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is missing. On a Chromebook run: sudo apt-get install -y curl"; exit 1
fi

# 1) uv: a small tool that brings its own Python, so nothing else needs installing.
if ! command -v uv >/dev/null 2>&1 && [[ ! -x "$HOME/.local/bin/uv" ]]; then
  say "Step 1 of 4: getting uv (brings its own Python)…"
  curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null
else
  say "Step 1 of 4: uv already installed."
fi
UV="$(command -v uv 2>/dev/null || echo "$HOME/.local/bin/uv")"

# 2) The tutor's code (keeps data/ and .env if this is a reinstall).
say "Step 2 of 4: downloading the tutor…"
mkdir -p "$DIR"
TMP="$(mktemp -d)"
if [[ -n "${TUTOR_SRC:-}" ]]; then
  cp -R "$TUTOR_SRC" "$TMP/src"
else
  curl -fsSL "https://codeload.github.com/$REPO/tar.gz/refs/heads/main" | tar -xz -C "$TMP"
fi
SRC="$(find "$TMP" -mindepth 1 -maxdepth 1 -type d | head -n1)"
(cd "$SRC" && tar -cf - --exclude=./data --exclude=./.env --exclude=./.venv --exclude=./.git .) | (cd "$DIR" && tar -xf -)
rm -rf "$TMP"
chmod +x "$DIR/start.sh" "$DIR/install.sh"
[[ -f "$DIR/setup_minecraft_chromebook.sh" ]] && chmod +x "$DIR/setup_minecraft_chromebook.sh" || true
[[ -f "$DIR/bin/prism-gated-launch.sh" ]] && chmod +x "$DIR/bin/prism-gated-launch.sh" || true

# 3) Python and libraries (one time, about a minute).
say "Step 3 of 4: setting up Python (about a minute the first time)…"
if [[ ! -x "$DIR/.venv/bin/python" ]]; then
  "$UV" venv --python 3.12 "$DIR/.venv" -q
fi
"$UV" pip install --python "$DIR/.venv/bin/python" -q -r "$DIR/requirements.txt"

# 4) An app icon.
say "Step 4 of 4: adding the Gemini Tutor icon…"
if [[ -n "${TUTOR_NO_SHORTCUT:-}" ]]; then
  WHERE="(shortcut skipped)"
elif [[ "$(uname)" == "Darwin" ]]; then
  APP="$HOME/Applications/Gemini Tutor.app"
  rm -rf "$APP"
  mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
  cat > "$APP/Contents/MacOS/GeminiTutor" <<EOF
#!/bin/bash
exec "$DIR/start.sh"
EOF
  chmod +x "$APP/Contents/MacOS/GeminiTutor"
  if command -v sips >/dev/null && command -v iconutil >/dev/null && [[ -f "$DIR/static/icon-512.png" ]]; then
    IS="$(mktemp -d)/AppIcon.iconset"; mkdir -p "$IS"
    for s in 16 32 64 128 256 512; do sips -z $s $s "$DIR/static/icon-512.png" --out "$IS/icon_${s}x${s}.png" >/dev/null; done
    cp "$IS/icon_32x32.png" "$IS/icon_16x16@2x.png"; cp "$IS/icon_64x64.png" "$IS/icon_32x32@2x.png"
    cp "$IS/icon_256x256.png" "$IS/icon_128x128@2x.png"; cp "$IS/icon_512x512.png" "$IS/icon_256x256@2x.png"
    iconutil -c icns "$IS" -o "$APP/Contents/Resources/AppIcon.icns" 2>/dev/null || true
  fi
  cat > "$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Gemini Tutor</string>
  <key>CFBundleDisplayName</key><string>Gemini Tutor</string>
  <key>CFBundleIdentifier</key><string>com.github.geminitutor</string>
  <key>CFBundleExecutable</key><string>GeminiTutor</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSUIElement</key><true/>
</dict></plist>
EOF
  ln -sfn "$APP" "$HOME/Desktop/Gemini Tutor.app" 2>/dev/null || true
  WHERE="on your Desktop and in Applications"
else
  mkdir -p "$HOME/.local/share/applications"
  cat > "$HOME/.local/share/applications/gemini-tutor.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Gemini Tutor
Exec=$DIR/start.sh
Icon=$DIR/static/icon-512.png
Terminal=false
Categories=Education;
EOF
  WHERE="in your app launcher (inside the 'Linux apps' folder)"
fi

say "Done! Opening Gemini Tutor now. Next time, click the Gemini Tutor icon $WHERE."
[[ -n "${TUTOR_NO_LAUNCH:-}" ]] || "$DIR/start.sh"
