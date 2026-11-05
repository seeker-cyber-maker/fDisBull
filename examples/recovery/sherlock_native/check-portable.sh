#!/bin/sh
# Build and exercise the actual portable game code on macOS or Linux.
set -eu
SHERLOCK_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SHERLOCK_ROOT"
SHERLOCK_CC=${CC:-cc}
SHERLOCK_CHECK="$SHERLOCK_ROOT/build/checks"
SHERLOCK_TABLE=${SHERLOCK_PUZZLE_TABLE:-"$SHERLOCK_ROOT/Resources/sherlock_puzzles.bin"}
mkdir -p "$SHERLOCK_CHECK"

"$SHERLOCK_CC" -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror \
  tests/test_shi.c media/shi.c -o "$SHERLOCK_CHECK/test-shi"
"$SHERLOCK_CHECK/test-shi"
"$SHERLOCK_CC" -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror \
  tests/test_images.c state/sherlock_images.c media/shi.c -o "$SHERLOCK_CHECK/test-images"
"$SHERLOCK_CHECK/test-images"
"$SHERLOCK_CC" -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror \
  tests/test_font.c media/sherlock_font.c -o "$SHERLOCK_CHECK/test-font"
"$SHERLOCK_CHECK/test-font"
"$SHERLOCK_CC" -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror \
  tests/test_explain.c state/sherlock_explain.c -o "$SHERLOCK_CHECK/test-explain"
"$SHERLOCK_CHECK/test-explain"
"$SHERLOCK_CC" -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror \
  tests/test_victory.c state/sherlock_victory.c -o "$SHERLOCK_CHECK/test-victory"
"$SHERLOCK_CHECK/test-victory"
"$SHERLOCK_CC" -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror \
  tests/test_state.c state/sherlock_state.c core/sherlock_logic.c -o "$SHERLOCK_CHECK/test-state"
"$SHERLOCK_CHECK/test-state"
"$SHERLOCK_CC" -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror \
  tests/test_logic.c core/sherlock_logic.c -o "$SHERLOCK_CHECK/test-logic"
"$SHERLOCK_CHECK/test-logic"
./Build-CLI.sh
if [ -f "$SHERLOCK_TABLE" ]; then
  python3 tests/test_cli.py bin/sherlock-cli "$SHERLOCK_TABLE"
else
  python3 tests/test_cli.py bin/sherlock-cli
  printf '%s\n' 'Original numbered-puzzle checks skipped: owner-supplied table is absent.'
  printf '%s\n' 'Authored portable checks passed. AppKit execution must be checked on a Mac.'
  exit 0
fi
"$SHERLOCK_CC" -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror \
  tests/test_integration.c state/sherlock_state.c core/sherlock_core.c core/sherlock_logic.c \
  -o "$SHERLOCK_CHECK/test-integration"
"$SHERLOCK_CHECK/test-integration" "$SHERLOCK_TABLE" 64
"$SHERLOCK_CC" -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror \
  tests/test_corpus.c state/sherlock_state.c core/sherlock_core.c core/sherlock_logic.c \
  -o "$SHERLOCK_CHECK/test-corpus"
"$SHERLOCK_CHECK/test-corpus" "$SHERLOCK_TABLE"
printf '%s\n' 'Portable checks passed. AppKit execution must be checked on a Mac.'
