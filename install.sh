#!/bin/bash
# Installs Screen Reader as a persistent, login-launched menu-bar app:
#   1. builds a real app bundle  ~/Applications/ScreenReader.app
#   2. registers a LaunchAgent so it starts automatically at login
#   3. launches it now
# Run again any time — it's idempotent and refreshes everything.
set -e
cd "$(dirname "$0")"
PROJ="$(pwd)"
APP="$HOME/Applications/ScreenReader.app"
PLIST="$HOME/Library/LaunchAgents/com.local.screenreader.plist"

# --- venv (first run only) ---
if [ ! -d .venv ]; then
  echo "Creating virtualenv and installing dependencies…"
  python3 -m venv .venv
  ./.venv/bin/pip install --upgrade pip >/dev/null
  ./.venv/bin/pip install -r requirements.txt
fi

# --- app bundle ---
echo "Building $APP …"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

# app icon (regenerate the .icns from assets/logo.png if the tools exist)
if [ -f assets/logo.png ] && command -v iconutil >/dev/null; then
  ICONSET="$(mktemp -d)/AppIcon.iconset"; mkdir -p "$ICONSET"
  # Trim the transparent padding and scale to the proportion macOS icons use,
  # otherwise the artwork renders noticeably smaller than every neighbouring
  # icon in the Dock. Falls back to the raw logo if Pillow is unavailable.
  ICON_SRC="$(mktemp -d)/icon_src.png"
  if ! ./.venv/bin/python assets/make_icon.py assets/logo.png "$ICON_SRC" >/dev/null 2>&1; then
    ICON_SRC=assets/logo.png
  fi
  for s in 16 32 128 256 512; do
    sips -z $s $s "$ICON_SRC" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
    sips -z $((s*2)) $((s*2)) "$ICON_SRC" \
         --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
  done
  iconutil -c icns "$ICONSET" -o assets/AppIcon.icns
fi
[ -f assets/AppIcon.icns ] && cp assets/AppIcon.icns "$APP/Contents/Resources/AppIcon.icns"

cat > "$APP/Contents/Info.plist" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>            <string>ScreenReader</string>
    <key>CFBundleDisplayName</key>     <string>Screen Reader</string>
    <key>CFBundleIdentifier</key>      <string>com.local.screenreader</string>
    <key>CFBundleExecutable</key>      <string>ScreenReader</string>
    <key>CFBundleIconFile</key>        <string>AppIcon</string>
    <key>CFBundlePackageType</key>     <string>APPL</string>
    <key>CFBundleShortVersionString</key> <string>1.0</string>
    <key>LSUIElement</key>             <true/>
    <key>NSHighResolutionCapable</key> <true/>
</dict>
</plist>
PLIST_EOF

cat > "$APP/Contents/MacOS/ScreenReader" <<LAUNCH_EOF
#!/bin/bash
mkdir -p "\$HOME/Library/Logs"
LOG="\$HOME/Library/Logs/ScreenReader.log"

# On Apple Silicon, LaunchServices starts this universal Python under Rosetta,
# and the x86_64 slice cannot load the arm64 ctranslate2 that Argos Translate
# needs, which silently disables translation. Pin the native architecture.
if [ "\$(sysctl -n hw.optional.arm64 2>/dev/null)" = "1" ]; then
    exec /usr/bin/arch -arm64 "$PROJ/.venv/bin/python" "$PROJ/screenreader.py" >> "\$LOG" 2>&1
fi
exec "$PROJ/.venv/bin/python" "$PROJ/screenreader.py" >> "\$LOG" 2>&1
LAUNCH_EOF
chmod +x "$APP/Contents/MacOS/ScreenReader"

# --- launch agent: start at every login ---
echo "Registering LaunchAgent…"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<AGENT_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>   <string>com.local.screenreader</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/open</string>
        <string>-a</string>
        <string>$APP</string>
    </array>
    <key>RunAtLoad</key> <true/>
</dict>
</plist>
AGENT_EOF
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

# --- restart the app cleanly ---
pkill -f "screenreader.py" 2>/dev/null || true
sleep 1
open -a "$APP"

echo
echo "✅ Installed. Screen Reader now starts automatically at login."
echo
echo "⚠️  One-time step: grant permissions to the NEW app in"
echo "   System Settings → Privacy & Security:"
echo "     • Screen Recording  → enable “ScreenReader”"
echo "     • Accessibility     → enable “ScreenReader”"
echo "     • Input Monitoring  → enable “ScreenReader” (if listed)"
echo "   (permissions previously granted to Terminal don't carry over)"
echo "   Then quit (👁 → Quit) and reopen it once: open -a \"$APP\""
