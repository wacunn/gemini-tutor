#!/usr/bin/env bash
# Automatic Desktop Linux (Ubuntu, Debian, Fedora, Mint, Arch) Setup for Minecraft Java + Gemini Tutor Time-Gating.
#   curl -fsSL https://raw.githubusercontent.com/wacunn/gemini-tutor/main/setup_minecraft_linux.sh | bash
set -euo pipefail
REPO="${TUTOR_REPO:-wacunn/gemini-tutor}"
exec bash -c "$(curl -fsSL "https://raw.githubusercontent.com/$REPO/main/setup_minecraft_chromebook.sh")"
