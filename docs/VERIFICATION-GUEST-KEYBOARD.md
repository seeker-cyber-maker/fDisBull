# Guest keyboard verification, 2026-10-26

Both complete DOSBox patches add controller-level input using the pinned
`029bd65c5dcc7cdc7f2e14e35278620d9707d969` baseline. Clean baseline exports replayed
the patches and matched every resulting manifest entry: 28 stable files and
29 layers files. The earlier backend binary receipts in each manifest are
explicitly historical; they do not qualify the new keyboard source.

The fresh layers build on **macOS ARM64, Python 3.13.14** passed **312 selected
native checks, zero failures and zero skips**. These include debugger execution,
breakpoints/watches, layers/hooks/experiments, bounded waits, native states,
screenshots/grids, temporal code, DOS knowledge and keyboard input. The
[acceptance receipt](evidence/0.16.0-keyboard/acceptance.json),
[test log](evidence/0.16.0-keyboard/native-full.log) and
[XML](evidence/0.16.0-keyboard/native-full.xml) preserve that scope and identity.

The authored keyboard target consumes the real BIOS INT 16h service. Checks
read back ASCII/scan-code pairs for uppercase/lowercase, digits, spaces, shifted
punctuation, Backspace, Enter, a Shift chord, an arrow and F1. They also exercise
saved scripts, pending-input rejection at Python and direct native state-save
boundaries, atomic invalid-text rejection, cancellation on restore and input
after restore. The initial saved-script check failed because `keyboard.press`
did not exist; it passed after implementation.

A final strengthened keyboard check ran **14 tests with no skips** and restores
while an adapter-owned Shift key is actually held, then proves that subsequent
guest input is correct. Its [log](evidence/0.16.0-keyboard-held/native-keyboard-held.log)
and [XML](evidence/0.16.0-keyboard-held/native-keyboard-held.xml) are separate from
the earlier sealed 312-check receipt.

The full host suite was also attempted: **1,050 passed, 62 skipped, two failed
and 23 setup errors** in that pre-final test snapshot. The failures/errors build
GNU/Linux ELF fixtures with Apple compiler/linker tools. This is not a green
full Mac suite. Final-commit ordinary Linux CI and both native Linux backend
profiles remain the release gate; layers acceptance selects Python **3.13.5**.

The [DinoPark driver](../examples/dinopark/verify_keyboard.py) ran on a fresh
private copy, using the real new-game/bank/menu/save-name screens. It typed
`FD16TEST`, pressed Backspace, and typed `1`. Readback found `FD16TES1` at runtime
linear `0x00046CDC`, a dialog heap buffer outside the original mapped EXE. The
driver scans bounded conventional RAM and retains only matching addresses and
the expected short text, not RAM payloads. The
[typed screenshot](evidence/0.16.0-keyboard/dinopark/typed-name.png) visibly
matches. A fresh emulator restored a newly saved native checkpoint and retained
the name in memory and the
[restored screenshot](evidence/0.16.0-keyboard/dinopark/restored-typed-name.png).
A [32-instruction trace](evidence/0.16.0-keyboard/dinopark/name-dialog-trace.json),
saved route and auditable step results accompany the
[game receipt](evidence/0.16.0-keyboard/dinopark/receipt.json).

Navigation was calibrated using actual frames; incomplete attempts failed the
explicit text-readback assertion. The accepted route is a finite replay, not a
general readiness detector or deterministic replay claim. All 192 original game
files and all 192 private copied files remained unchanged; owned emulator
processes were reaped. The driver does not confirm a game save and does not
qualify a durable leaderboard entry. The exact acceptance document referenced
in DinoPark Chat could not be recovered through the chat reader: its newest
messages were unresolved content references. These checks are independently
declared acceptance, not a claim that the unavailable document passed.

Only source, screenshots, short instruction traces, test logs and JSON/XML
receipts enter Git. Game files, checkpoint bytes and project databases remain
private. The [evidence manifest](evidence/0.16.0-keyboard/SHA256SUMS.json) binds the
sealed receipts. [Keyboard API and limits](GUEST_KEYBOARD.md) document queued
delivery, guest-time timing and keyboard-layout assumptions.

A separate [delivered 0.16.0 leaderboard replay](VERIFICATION-DINOPARK-LEADERBOARD.md)
now qualifies the durable-entry boundary: type `DeepSeek016`, release the game's
modal text editor with Ctrl+O, click OK, and read the completed score table through
the original game in a fresh emulator and separate project. The accepted Mac run
recorded rank 7 at $9,608. This follow-up does not alter the earlier sealed
save-name evidence or extend the gameplay result to Linux.
