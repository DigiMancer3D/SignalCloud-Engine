#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$APPS"
DESKTOP="$APPS/almond-signal-live-tape.desktop"
cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=Almond Signal: Live Tape
Comment=Choose the game or engine-native SignalCloud stress test
Exec="$ROOT/scripts/launch_control_panel.sh"
Path=$ROOT
Terminal=false
Categories=Game;Development;
StartupNotify=true
EOF
chmod 644 "$DESKTOP"
echo "Installed session launcher: $DESKTOP"
