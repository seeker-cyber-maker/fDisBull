# Source popup hotfix, running-park shutdown and PID 63534 — November 3, 2026

This follow-up promotes the installed headless closing-popup hotfix into !72's
source, qualifies that source client against an operating original DinoPark,
and investigates the concurrent SIGABRT preserved by the
[installed entry/title test](VERIFICATION-DINOPARK-INSTALLED-SHUTDOWN-2026-11-03.md).
No package, installation or native rebuild is part of this contribution.

The subsequent [November 4 follow-up](VERIFICATION-SHUTDOWN-RECEIPTS-2026-11-04.md)
captures the literal cleanup exception in an owned TFTD reproduction and
implements truthful persistent shutdown receipts. The dated unknowns below
describe the earlier static/historical investigation; the first corruption
writer and historical PID's exact memory remain unresolved.

## Source change and regression

`DOSBoxRPC` now supplies `-set "dosbox quit warning=false"` in its headless
launch profile. The native `CheckQuit()` code returns immediately for this
setting rather than opening the host quit-warning dialog. Existing SDL dummy
audio, mixer mute and MIDI disable settings remain in that same profile.
The explicit visible-window profile retains its existing quit-warning behavior.

The two-line production addition is byte-identical to the installed hotfix.
Source and installed `dosbox_rpc.py` both hash to
`b6112a55b710ca10de454f499e1c74a8dd6d684d9a71ddc8c36f31bd83f8c17e`.
No installed file was changed by this task.

The existing launch-contract test now requires the headless `-set` pair exactly
once; its visible-window companion checks that the headless override is absent.
Before the production edit, the new headless assertion failed while the window
test passed. After the edit, the complete `tests/test_dosbox_window.py` module
passes **30 tests, with two optional native/window tests skipped**, in 1.75 s.
This mock-transport module verifies arguments and compatibility, not GUI pixels.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:player \
  python -m pytest -q -p no:cacheprovider tests/test_dosbox_window.py
```

## Luna's source-client running-park test

Luna (`gpt-6-luna`) loaded the source package and RPC module from the absolute
worktree `src` path, with bytecode writes disabled. The source reports version
`0.30.0`; this is deliberately distinct from the installed `0.31.1` client used
by the earlier entry/title test. The native executable was the installed macOS
ARM64 backend, SHA-256
`bcf318de2a22d49d1b28888a312e12b774cf1f041fdd8862fc4ab3335ea59b60`.

Each fresh process used the original OLD GAME dialog and existing disk save,
then reached the park through Office and Street. The save SHA-256 is
`7d4cc0dcdb1689540fbfbb0f4834a927a8b75efc1ddf565db9c2e65c6254fd3d`.
All **20 saved memory ranges** and the loaded snapshot matched the qualified
save manifest before navigation. No native state restore, game-memory write,
purchase, new save, guest-code patch or teleport was used.

Native sparse pixel predicates uniquely recognized the expected views and
excluded known notices. The paused pixel/memory observations retained registers
and guest ticks. After reaching the park, an explicit 1,000 ms guest advance
produced these observations in all four qualified cycles:

- Day-of-month counter **13 → 14**.
- Small-feeder food **19 → 18**.
- One guide and one species-4 Coelophysis retained in pen 10.
- Loan **5,000** retained; cash/working cash changed as the original game ran.

This establishes bounded operating progression. Cash differed between fresh
runs, so the batch does not claim trajectory equivalence. A distinct recovered
open/closed flag remains outside this interface's qualification.

| Shutdown from the observed running park | Fresh cycles | Result |
| --- | ---: | --- |
| `session.stop` → `execution.wait` → `rpc.close()` | 2 | Exit 0, reaped, no kill fallback |
| Direct `rpc.close()` | 2 | Exit 0, reaped, no kill fallback |

Actual spawn arguments and selected environment verified quit-warning
suppression and SDL/mixer/MIDI mute in every cycle. All four processes were
reaped and their transient control directories removed. Transport-close time
was **9.250–19.440 ms**, median **19.252 ms**; these figures exclude startup,
navigation and guest-stop RPC time. No matching crash report appeared during
the batch or the parent's delayed readback.

The full existing game inventory, native save, source/native identities and
measured scripts remained unchanged. CUA's independent post-batch running-app
inventory at **01:31:59.401 UTC** found no matching DOSBox-X or crash-report GUI
owner. No closing popup was observed or dismissed. This is bounded observation,
not continuous desktop video or visible-window acceptance.

### Preserved initial harness failure

There were **five launches total**: four qualified running-park passes and an
initial attempt that reached the loaded Office but failed before qualifying
the park. That private harness used `hex()` for a linear `memory.read` offset;
the native API correctly requires the fixed-width `0xNNNNNNNN` representation.
The production memory reader already uses the required format.

The original failed report/script remain unchanged. A separate correction
receipt records the private serialization fix, followed by four fresh cycles.
The initial process also exited zero and was reaped, but is excluded from the
running-park acceptance count. No uncertain original action was replayed in
its former guest.

## PID 63534: identified source session

The earlier concurrent crash is now attributed directly to the **Terror from
the Deep `cold_new` experiment**, target `TERROR.COM`, rather than a DinoPark
test. Its private project's `debug_runs` metadata explicitly records PID 63534,
client version `0.30.0`, headless mode and the installed backend hash above.
Its run is `09dd85428387409abf12c8faec1763fc`.

The stored launch time, **00:48:03.726 UTC**, agrees with the crash report's
process launch at **19:48:03.417 local time**. The canonical close event at
**01:14:49.654 UTC** records:

```json
{"state":"interrupted","error":"Emulator closed the RPC channel","process_reaped":true}
```

The matching IPS records SIGABRT at **20:14:49.732 local time**. The experiment's
higher-level metrics say `closed`; the canonical receipt shows why that label
must not be treated as successful guest shutdown. Reaping only establishes
that the host process ended. The experiment's actual launch arguments and
loaded host-module hash were not retained in the inspected session metadata,
so activation of the popup override in that older run remains unknown.

## Native abort mechanism and remaining uncertainty

The IPS image UUID, `f51c0fac-8720-31ed-ad46-254a1fa62f46`, matches the actual
installed Mach-O. Offline `nm`, `otool` and LLVM unwind inspection place the
failure in the shell destructor's exception-termination path:

`DOS_Shell::~DOS_Shell()` → `__clang_call_terminate` → `std::terminate` → `abort`.

The saved destructor return PC is unslid `0x10020e0b8`, immediately after the
terminate call at `0x10020e0b4`. Its LSDA at file offset `0x93f720` maps that
landing pad to cleanup calls in `[0x10020df60, 0x10020dfa4)`, covering
`DOS_FreeProcessMemory`, PSP selection and `DOS_PSP::CloseFiles`. This narrows
the failure to an exception escaping memory/file cleanup in a destructor that
terminates on an exception. The recorded stack is not a quit-warning UI stack.

The actual binary's `DOS_Mem_E_Exit` logs a fatal DOS-memory error and throws
`int(7)`; its memory-free cold branches include a corrupt-MCB error. That is a
concrete candidate mechanism for this cleanup failure. The retained IPS/FDB
records do not identify the exact thrown value, invalid memory block, file
state or earlier writer. **Corrupt MCB state is a hypothesis, not a confirmed
root cause.** No new TFTD reproduction or native attach was performed.

The next native investigation should stop on the cleanup throw before stack
unwinding, retain the native error/log tail and inspect the affected PSP/MCB or
file state. A native repair should make destructor cleanup non-throwing while
retaining an explicit cleanup failure; suppressing the popup is not evidence
that this separate native failure is fixed. Host shutdown reporting should
also distinguish an interrupted guest stop, actual process return code, signal
termination and reaping. These are recommendations, not additional production
changes in this contribution.

## Evidence and limits

Private source-running-park evidence is under
`/Volumes/CACHE/fDisBull-scene-indexed-20261103/running-park-source-hotfix-small/`.
The corrected report SHA-256 is
`15700a9c15e37396252d32f08f36e1e13009b113e71001f4b7d55c67df016006`;
the measured corrected script is
`2162966becc65df58609c54147e01520f89546d95516a1aab0e9154c8683c3c6`.
The final aggregate, including parent observations, hashes to
`6eee253e4cc99d54a42e163a9144eded5cccdba63511d1031282b1b700540098`.
`PARENT-VERIFICATION.json` independently checks the raw reports, four native
progressions, process cleanup and final source/game/save hashes.

The retained crash SHA-256 is
`4c703143ac7dacef459acadc2498b02345d5315591c3e3c8d9ecd7d59110a492`.
Derived investigation metadata is in the sibling
`pid63534-investigation-small/FINDINGS.json`; the original crash report and
TFTD project/object store remain private and unchanged.

Bulk capture admission was refused because CACHE was below the 20 GB reserve.
The native verification and offline investigation used only the explicit
read-only diagnostic exemption and small transient controls/reports: no new
FDB, image capture, game copy, runtime image, build, package or installation.
Only authored source/tests and sanitized findings enter Git. The earlier
437-test screenshot/scene result retains its prior source scope; this change
adds the 30-test launch check and four source-backed running-park cycles.
No complete-playthrough, visible-window or all-native-crashes claim is made.
