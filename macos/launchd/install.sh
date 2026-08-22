#!/usr/bin/env bash
# Install per-user launchd agents for the Docker backend and menu-bar app.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LAUNCHD_DIR="$HOME/Library/LaunchAgents"
BACKEND_LABEL="local.job-hunter.backend"
MENUBAR_LABEL="local.job-hunter.menubar"
BACKEND_PLIST="$LAUNCHD_DIR/$BACKEND_LABEL.plist"
MENUBAR_PLIST="$LAUNCHD_DIR/$MENUBAR_LABEL.plist"
GUI_DOMAIN="gui/$(id -u)"
START_BACKEND="$ROOT/macos/launchd/start-backend.sh"
APP_EXEC="/Applications/JobHunterBar.app/Contents/MacOS/JobHunterBar"

usage() {
  echo "Usage: $0 [--uninstall]"
  echo "  Installs LaunchAgents that start Docker Compose backend and JobHunterBar at login."
  echo "  --uninstall  Unload and remove the LaunchAgents."
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

mkdir -p "$LAUNCHD_DIR" "$ROOT/logs"

unload_if_loaded() {
  local label="$1"
  local plist="$2"
  launchctl bootout "$GUI_DOMAIN" "$plist" >/dev/null 2>&1 || true
  launchctl remove "$label" >/dev/null 2>&1 || true
}

if [[ "${1:-}" == "--uninstall" ]]; then
  unload_if_loaded "$BACKEND_LABEL" "$BACKEND_PLIST"
  unload_if_loaded "$MENUBAR_LABEL" "$MENUBAR_PLIST"
  rm -f "$BACKEND_PLIST" "$MENUBAR_PLIST"
  echo "Removed Job Hunter LaunchAgents."
  exit 0
elif [[ $# -gt 0 ]]; then
  usage >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker not found. Install Docker Desktop first." >&2
  exit 1
fi

if [[ ! -x "$APP_EXEC" ]]; then
  echo "JobHunterBar.app is not installed at /Applications." >&2
  echo "Run: ./macos/JobHunterBar/install.sh" >&2
  exit 1
fi

chmod +x "$START_BACKEND"

cat > "$BACKEND_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$BACKEND_LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$START_BACKEND</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>StartInterval</key>
  <integer>300</integer>
  <key>StandardOutPath</key>
  <string>$ROOT/logs/launchd-backend.out.log</string>
  <key>StandardErrorPath</key>
  <string>$ROOT/logs/launchd-backend.err.log</string>
</dict>
</plist>
EOF

cat > "$MENUBAR_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$MENUBAR_LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$APP_EXEC</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$ROOT/logs/launchd-menubar.out.log</string>
  <key>StandardErrorPath</key>
  <string>$ROOT/logs/launchd-menubar.err.log</string>
</dict>
</plist>
EOF

unload_if_loaded "$BACKEND_LABEL" "$BACKEND_PLIST"
unload_if_loaded "$MENUBAR_LABEL" "$MENUBAR_PLIST"
launchctl bootstrap "$GUI_DOMAIN" "$BACKEND_PLIST"
launchctl bootstrap "$GUI_DOMAIN" "$MENUBAR_PLIST"
launchctl kickstart -k "$GUI_DOMAIN/$BACKEND_LABEL"
launchctl kickstart -k "$GUI_DOMAIN/$MENUBAR_LABEL"

echo "Installed Job Hunter LaunchAgents."
echo "Backend: launchctl print $GUI_DOMAIN/$BACKEND_LABEL"
echo "Menu bar: launchctl print $GUI_DOMAIN/$MENUBAR_LABEL"
