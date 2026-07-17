#!/bin/bash
# Removes the login autostart and the app bundle (keeps this project folder).
PLIST="$HOME/Library/LaunchAgents/com.local.screenreader.plist"
launchctl unload "$PLIST" 2>/dev/null || true
rm -f "$PLIST"
pkill -f "screenreader.py" 2>/dev/null || true
rm -rf "$HOME/Applications/ScreenReader.app"
echo "✅ Uninstalled (project folder kept; run ./install.sh to reinstall)."
