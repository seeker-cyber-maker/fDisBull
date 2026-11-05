#!/bin/bash
# Compile the recovered game and its native AppKit host on this Mac, then open
# the resulting application. No DOS emulator or Windows compatibility layer is
# involved in either the build or the application.
set -euo pipefail

SHERLOCK_ROOT="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$SHERLOCK_ROOT"

if [[ "$(uname -s)" != Darwin ]]; then
    echo "This launcher builds the AppKit application on macOS."
    echo "The portable C components can be checked on Linux with ./check-portable.sh."
    exit 1
fi

if ! SHERLOCK_CC="$(xcrun --find clang 2>/dev/null)"; then
    echo "Apple's Command Line Tools are needed for this first source build."
    echo "Run: xcode-select --install"
    echo "After installation completes, open this launcher again."
    read -r -p "Press Return to close. " _unused
    exit 1
fi

SHERLOCK_BUILD="$SHERLOCK_ROOT/build"
SHERLOCK_APP="$SHERLOCK_BUILD/Sherlock Native.app"
SHERLOCK_MACOS="$SHERLOCK_APP/Contents/MacOS"
SHERLOCK_RESOURCES="$SHERLOCK_APP/Contents/Resources"
mkdir -p "$SHERLOCK_BUILD/objects" "$SHERLOCK_MACOS" "$SHERLOCK_RESOURCES"

for SHERLOCK_REQUIRED in Resources/sherlock_puzzles.bin Resources/PatternPresets.bin Resources/Images/SHERLOCK.SHI Resources/Images/ORGINAL.SHI; do
    if [[ ! -f "$SHERLOCK_REQUIRED" ]]; then
        printf 'Missing application resource: %s\n' "$SHERLOCK_REQUIRED"
        echo "Extract the complete source package before building."
        exit 1
    fi
done

# Default to the architecture of the current Mac. The source uses fixed-width
# game state and can also be built for an Intel Mac by running it there.
SHERLOCK_ARCH="$(uname -m)"
SHERLOCK_OBJECTS=()
for SHERLOCK_SOURCE in core/*.c state/*.c media/*.c cli/sherlock_cli.c; do
    [[ -f "$SHERLOCK_SOURCE" ]] || continue
    SHERLOCK_OBJECT="$SHERLOCK_BUILD/objects/${SHERLOCK_SOURCE//\//_}.o"
    "$SHERLOCK_CC" -std=c11 -O2 -Wall -Wextra -arch "$SHERLOCK_ARCH" \
        -mmacosx-version-min=11.0 -Icore -Istate -Imedia -Icli \
        -c "$SHERLOCK_SOURCE" -o "$SHERLOCK_OBJECT"
    SHERLOCK_OBJECTS+=("$SHERLOCK_OBJECT")
done
for SHERLOCK_SOURCE in app/*.m; do
    [[ -f "$SHERLOCK_SOURCE" ]] || continue
    SHERLOCK_OBJECT="$SHERLOCK_BUILD/objects/${SHERLOCK_SOURCE//\//_}.o"
    "$SHERLOCK_CC" -fobjc-arc -O2 -Wall -Wextra -arch "$SHERLOCK_ARCH" \
        -mmacosx-version-min=11.0 -Icore -Istate -Imedia -Icli \
        -c "$SHERLOCK_SOURCE" -o "$SHERLOCK_OBJECT"
    SHERLOCK_OBJECTS+=("$SHERLOCK_OBJECT")
done

"$SHERLOCK_CC" -arch "$SHERLOCK_ARCH" -mmacosx-version-min=11.0 \
    "${SHERLOCK_OBJECTS[@]}" -framework Cocoa -framework CoreGraphics \
    -o "$SHERLOCK_MACOS/SherlockNative"
cp app/Info.plist "$SHERLOCK_APP/Contents/Info.plist"
if [[ -d Resources ]]; then
    cp -R Resources/. "$SHERLOCK_RESOURCES/"
fi
if [[ -f README.md ]]; then
    cp README.md "$SHERLOCK_RESOURCES/BUILD-README.md"
fi

# Ad-hoc signing is local to this build. It is not Developer ID signing or
# Apple notarization, and the result is intended for the owner's local use.
codesign --force --sign - "$SHERLOCK_APP"
printf 'Built %s for %s.\n' "$SHERLOCK_APP" "$SHERLOCK_ARCH"
./Build-CLI.sh
open "$SHERLOCK_APP"
