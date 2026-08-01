#!/usr/bin/env bash
# Build JobHunterBar and install it under /Applications so it runs without Xcode.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$ROOT/JobHunterBar.xcodeproj"
SCHEME="JobHunterBar"
BUILD_DIR="$ROOT/.build"
APP_NAME="JobHunterBar.app"
DEST="/Applications/$APP_NAME"
ADD_LOGIN=0

for arg in "$@"; do
  case "$arg" in
    --login) ADD_LOGIN=1 ;;
    -h|--help)
      echo "Usage: $0 [--login]"
      echo "  Builds a Release .app, copies it to /Applications, and launches it."
      echo "  --login  Also register as a Login Item (opens at login)."
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 1
      ;;
  esac
done

if ! command -v xcodebuild >/dev/null 2>&1; then
  echo "xcodebuild not found. Install Xcode from the App Store, then re-run." >&2
  exit 1
fi

echo "Building Release..."
rm -rf "$BUILD_DIR"
xcodebuild \
  -project "$PROJECT" \
  -scheme "$SCHEME" \
  -configuration Release \
  -derivedDataPath "$BUILD_DIR" \
  CODE_SIGN_IDENTITY="-" \
  CODE_SIGNING_REQUIRED=NO \
  CODE_SIGNING_ALLOWED=YES \
  build

BUILT_APP="$(find "$BUILD_DIR/Build/Products/Release" -maxdepth 1 -name "$APP_NAME" -print -quit)"
if [[ -z "$BUILT_APP" || ! -d "$BUILT_APP" ]]; then
  echo "Build succeeded but $APP_NAME was not found under $BUILD_DIR" >&2
  exit 1
fi

echo "Installing to ${DEST}..."
# Quit a running copy so the replace sticks.
osascript -e 'tell application "JobHunterBar" to quit' >/dev/null 2>&1 || true
sleep 0.5
rm -rf "$DEST"
cp -R "$BUILT_APP" "$DEST"

echo "Launching..."
open "$DEST"

if [[ "$ADD_LOGIN" -eq 1 ]]; then
  echo "Registering Login Item..."
  # macOS 13+: SMAppService via osascript isn't trivial; use open-at-login via System Events.
  osascript <<'EOF' || true
tell application "System Events"
  if not (exists login item "JobHunterBar") then
    make login item at end with properties {path:"/Applications/JobHunterBar.app", hidden:false}
  end if
end tell
EOF
  echo "Login Item registered (System Settings → General → Login Items to verify)."
fi

echo "Done. JobHunterBar is in the menu bar (no Dock icon)."
echo "Keep the API up with: docker compose up -d"
