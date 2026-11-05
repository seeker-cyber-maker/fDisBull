#!/bin/sh
# Native agent interface. Works without AppKit or the original game resources.
set -eu
SHERLOCK_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SHERLOCK_ROOT"
SHERLOCK_CC=${CC:-cc}
mkdir -p bin
"$SHERLOCK_CC" -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror \
    core/*.c state/sherlock_state.c state/sherlock_hint_proof.c \
    cli/sherlock_cli.c cli/main.c -o bin/sherlock-cli
printf 'Built %s\n' "$SHERLOCK_ROOT/bin/sherlock-cli"
