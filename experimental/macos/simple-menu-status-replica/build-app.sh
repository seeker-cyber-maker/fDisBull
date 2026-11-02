#!/bin/sh
set -eu
cd "$(dirname "$0")"
swift build -c release
BIN=$(swift build -c release --show-bin-path)
APP="$PWD/build/Simple Menu Status Replica.app"
mkdir -p "$APP/Contents/MacOS"
cp "$BIN/StatusReplica" "$APP/Contents/MacOS/StatusReplica"
mkdir -p "$APP/Contents/Resources/ja.lproj"
cp "Sources/StatusReplica/Resources/ja.lproj/Localizable.strings" "$APP/Contents/Resources/ja.lproj/Localizable.strings"
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>StatusReplica</string>
<key>CFBundleIdentifier</key><string>local.codex.simple-menu-status-replica</string>
<key>CFBundleName</key><string>Simple Menu Status Replica</string>
<key>CFBundleDevelopmentRegion</key><string>en</string>
<key>CFBundleLocalizations</key><array><string>en</string><string>ja</string></array>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>0.1</string>
<key>LSMinimumSystemVersion</key><string>12.0</string>
<key>LSUIElement</key><true/>
</dict></plist>
PLIST
printf 'Built %s\n' "$APP"
