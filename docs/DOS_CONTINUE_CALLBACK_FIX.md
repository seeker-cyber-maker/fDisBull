# DOSBox callback-safe continuation — 0.19 development

The intermittent counter failure reported during 0.18 qualification had a real
execution defect behind the reproduced symptom. A no-input continuation could
return from the BIOS keyboard routine using an old AX value. The scene system
correctly rejected the resulting counter change; changing its assertion or
lengthening keyboard holds would not correct that execution path.

## Mechanism and decisive reproduction

The agent's `DebuggerAdapter::Continue()` called the debugger's `RUN` command.
That command called `DEBUG_Run(1, false)` before returning to the normal loop,
but discarded the CPU decoder's return value. DOSBox's synthetic `FE 38` BIOS
callback instruction returns a callback identifier to its caller. The normal
emulator loop dispatches that identifier; the discarded pre-step did not.

A private diagnostic ring first reproduced an extra guest counter increment
before the next key-down, with no typematic event or extra BIOS-buffer word.
The deterministic regression then resolved INT 16h through its actual IVT
entry, verified the callback opcode, and stopped exactly before that opcode.
After deleting the breakpoint and continuing without input:

| Backend | Counter without input | Counter after one key |
| --- | ---: | ---: |
| Original 0.18 Mac layers backend | 1 | 2 |
| Corrected Mac layers backend | 0 | 1 |

The permanent authored regression is
`tests/test_keyboard.py::test_real_continue_at_bios_callback_does_not_invent_keyboard_input`.
It also captures/restores a native checkpoint at the callback boundary, then
checks no-input and one-key behavior again. Its ROM breakpoint is test-only
native instrumentation; public static project address guards remain intact.

## Correction

`DEBUG_AgentContinue()` resumes without executing a debugger pre-step. It uses
the existing no-step resume path, activates breakpoints and lets the normal
loop decode and dispatch the next instruction. The first execution-breakpoint
check is skipped once, preserving continuation from the current breakpoint and
future re-hits. The agent adapter calls this helper instead of parsing `RUN`.

Both complete source patches retain their pinned upstream baseline
`029bd65c5dcc7cdc7f2e14e35278620d9707d969`. The changed native source is limited to
`include/debug.h`, `src/debug/debug.cpp` and
`src/agent/debugger/debugger_adapter.cpp`. Each complete patch was reapplied to
fresh baseline preimages and all declared output hashes matched: 28 stable and
29 layers source files.

## Fresh bounded verification

Mac ARM64 / Python 3.13.17 qualification of the combined 0.19 development source:

- **386 passed, no failures/errors/skips** in the full layers/native/package
  selection, including the previously failing relative scene test and the
  forced callback regression.
- **66 passed, no failures/errors/skips** in the stable backend selection.
- A persistent breakpoint on the current instruction stopped on three later
  hits with counter values 0, 1 and 2, preserving ordinary breakpoint behavior.

The original uncorrected backend failed the permanent regression at the actual
no-input counter check. An earlier test draft used an incorrectly padded native
address and was rejected before reaching that check; that setup failure is
retained separately, not counted as evidence of the defect.

The earlier interrupted source qualification, baseline repetition and failed CI
receipts remain unchanged. The forced-boundary proof establishes this concrete
mechanism; it does not independently attribute every historical timeout to it.
Fresh hosted Linux CI remains a release gate. No proprietary game inputs,
native state bytes, compiled test guests or project databases are included in
the source/evidence record.

## Compatibility and remaining scope

The correction applies to agent Continue and bounded execution/trace routes
that use it. Explicit low-level `DEBUG_AgentStep` at emulator callback opcodes
has separate return-handling limitations and is not qualified by this fix.
The high-level Python/saved-script API does not expose that raw step operation.

Native checkpoints still require their recorded backend hash. This fix does not
silently waive that compatibility check, rewrite old archives or update the
published/shared 0.18 installation. Keep the previous version-bound backend for
states requiring its exact identity. The new candidate needs normal release
qualification before replacing the shared installation.
