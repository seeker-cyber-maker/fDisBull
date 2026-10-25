# Initial remote-endpoint verification — 2026-10-25

This is unreleased source work after `48fd05b` / the published 0.13.0 release.
It has not been committed, pushed, tagged or published. The frozen 0.13.0
packages and existing DeepSeek deliveries were not replaced.

This document freezes the initial endpoint milestone. Later bounded-trace
performance work has [separate measurements and evidence](IDA_TRACE_PERFORMANCE.md); the initial receipts
below are preserved and do not qualify later changes by themselves.

## Accepted real sessions

The combined DOS/endpoint regression run passed **56 tests**, with **one
unconfigured PE-native test skipped**. It includes the existing DOS debugger,
layer and screenshot-grid tests, the binary wire tests, and four new native DOS
endpoint cases. The separate configured PE gate passed **two tests**: one input
preflight test and one real Wine/QEMU integration test, without a native skip.
These are local tests, not GitHub CI.

Two additional native endpoint cases passed for binary-wire **read** and
**read/write** watches on the high byte of a word access. Together with the
write-watch case in the combined run, all three data access modes were
exercised through the new endpoint itself.

Reports and selected PNG/JSON evidence are under
[`experimental/remote-debugger/evidence/2026-10-25/`](../experimental/remote-debugger/evidence/2026-10-25/).

### Actual IDA Windows server

The real user-supplied server was IDA Windows 64-bit remote debug server
**9.4.31**, SHA-256
`d11a634a17ab658cf4533396bd8a4bac5e594ab23d57464719d55eb63b06b0bf`.
It ran under Wine 9.0 in an offline Linux 6.1.0-50 QEMU guest on the Mac ARM64
host, using the existing QEMU 11.1.2 delivery. No IDA GUI, IDA database, plugin
or IDA license file was uploaded to the guest. The target was the authored
`tests/wine_gui_fixture.c` program, compiled privately; its EXE is not evidence
or a package member.

The final integration test exercised:

- Observed main-module relocation, the verified PE entry stop and a breakpoint
  placed from a stored disassembly address.
- IDA page execution breakpoints, with unchanged guest instruction bytes.
- Original counter **7**, checked edit to **41**, a full-width RAX edit/readback
  to `0x123456789abcdef0`, and restoration of the original RAX value.
- A real complete four-instruction trace: `push rbp`, `mov rbp,rsp`, `nop`,
  `nop`, with pre-instruction registers and observed instruction bytes.
- Native client-window screenshots and an 8px marked click frame. The actual
  click increments the edited counter from **41 to 42** and hits the breakpoint
  again. The saved final screenshot visibly reads `Counter = 42`.
- A RAM layer changing the paused counter **42 → 43**, then disabling it and
  observing **42** again.
- A bounded run ending in a stopped timeout; complete process cleanup.
- Reopened-project PNG/trace exports, preservation of original disassembly and
  artifact isolation from a new static patch version.

The configured test completed in **204.40s**. This qualifies a finite authored
GUI fixture. It does not establish arbitrary Windows game compatibility,
unlimited threading behavior, or all features in the IDA user interface.

### DOS endpoint and DinoPark

The DOS endpoint tests run against the actual patched heavy-debug DOSBox layers
build on native macOS ARM64. The same interface-31 client proved:

- Execution breakpoints without modifying physical code bytes, actual single
  stepping, integer/segment register edits and checked memory write/readback.
- A one-byte write watch on the high byte of a word access, stopping after the
  real write. CPU instruction fetch is not reported as a data read.
- A complete six-instruction trace, native-state save/restore, RAM-layer
  enable/disable, 8px screenshots/click-frame and a stopped timeout.
- An execution-only immediate of **0x2222** reaching AX while an actual guest
  data read of the same instruction's original bytes reaches BX as **0x1111**.
- Disconnect while the CPU is running reaps the owned emulator. Exports remain
  usable after the endpoint and project close; static child versions have no
  inherited runtime artifacts.

The actual DinoPark replay used executable SHA-256
`2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c`.
It skipped **35 guest seconds**, captured the main menu, marked and queued the
New Game click at **(75,160)**, stopped at project address **0x175bc**, recorded
**512 complete game instructions**, and reached the bank loan dialog. It
verified unchanged `b8 03 00` bytes before/after breakpoint placement and
unchanged original game inputs. PNG/trace exports were checked after shutdown.

Replay source:
[`examples/dinopark/verify_remote_endpoint.py`](../examples/dinopark/verify_remote_endpoint.py).
The private copied game and database are in the user-selected debugger-runs
area, outside Git and outside the selected evidence directory. No new
concession-price or parking-commit conclusion is claimed from this replay.

## Development findings and current limits

The first real hardware execution breakpoint was accepted by IDA but never
fired in this Wine/QEMU environment. The adapter therefore requests page
execution breakpoints and verifies that the server actually supplies them.
There is no silent INT3 fallback.

Two client requirements were exposed by actual sessions: the Windows server
needs an explicit exception policy for its internal page-breakpoint
displacement, and accepts `RESMOD_INTO` without a later `RESMOD_NONE` reset.
Genuine target exceptions are returned unhandled for later guest SEH
continuation. Internal page stops are consumed by the debugger. The finite
fixture test covers the accepted trace path; exhaustive SEH and thread-creation
behavior remain unqualified.

PE data watches, execution-only layers, native-state reconnection and guest
register-read filters are **not qualified for this endpoint**. The PE adapter
rejects their unsupported operations. The existing `wine-qemu` backend retains
those qualified PE features except the proposed guest register filters. The
DOS endpoint reuses the existing emulator-level layers and native states;
wire breakpoints must be removed before a state capture/restore.

The direct macOS ordinary run reported **761 passed, 34 skipped, two failed
and 23 errors**. Its ELF fixtures invoke GNU/Linux linker options with Apple's
compiler/linker, and the two executable-format assertions expect ELF from that
compiler. That run is not an all-green macOS-suite claim. Native Mac debugger
acceptance is reported separately above.

The first full emulated Linux ordinary run reported **779 passed, 36 skipped
and ten failed**. All ten failures were in the packaging test's precondition:
its miniature valid archive still contained only the old eight required files.
The checker correctly required the new endpoint sources. The fixture was
updated to all fifteen required entries; the corrected packaging checks and
wire/adapter preflight checks passed **30 tests on macOS** and **30 tests in
Linux** (11.22s for the Linux test phase). This is a targeted rerun after fixing
the archive fixture, not a claim that the full suite was repeated. All ten
previously failing cases passed. The initial failed report remains under the
`linux-initial-` evidence names; the successful rerun is under
`linux-corrected-`. All production Python sources in the full Linux input
snapshot matched the final implementation; subsequent changes were to the
packaging guard/fixture, notices, documentation and added native-watch tests.

## Publication boundary

No commit, push, release tag or GitHub release was requested for this iteration.
Tool packages are built locally for exclusion/resource checks only. All game
files, saved/emulator states, databases, vendor executables, boot images and
license keys stay outside Git and outside the tool archives. The packaged SDK
license notice covers the public reference source; vendor binaries are never
redistributed by this implementation.
