# TFTD first MCB overwrite and contained native cleanup

November 4, 2026. This continues the [cleanup-exception investigation](VERIFICATION-SHUTDOWN-RECEIPTS-2026-11-04.md).
Original game inputs, raw memory/code windows, LLDB records, project databases,
native test binaries and complete failure logs remain private. No game binary
or sound driver was patched. No package, release or installation was produced.

## First corrupting write

Two fresh owned LLDB runs watched the first byte of the previously identified
MCB at physical `0x11340`, plus the preceding block's size field. The watches
were armed at original `TERROR.COM` entry, before ordinary startup execution.
The initial setup attempt stopped before guest continuation because this LLDB
does not expose `SBWatchpoint.SetScriptCallbackFunction`; it is preserved as a
failed attempt. The subsequent runs used LLDB's watchpoint callback command.

Both successful traces record seven watched accesses. They show the header
being created with valid type `0x4d`, the preceding live block settling at
segment `0x0f00` with size `0x0233` paragraphs, and then the first invalidating
write changing the next header's type to `0x80`.

The writer is original `UFOEXE/GEOSCAPE.EXE`:

| Observation | Bound value |
| --- | --- |
| Original file SHA-256 | `490f8d271dda18c7ea1e9aff42b235ba62a9965ca9e26141c93a57c675ed6894` |
| Runtime writer | `CS=0x0150`, `EIP=0x0020efd0`, flat code base |
| Instruction | `REP STOSB`, with `AL=0x80` |
| Writer file offset | `0x579d0`; matched surrounding original instructions, load/file delta `0x1b7600` |
| Fill function / caller | `0x20efc1` / call at `0x20e398`, return `0x20e39d` |
| Observed call arguments | destination `0x10000`, length `0x1770` (6,000), value `0x80` |
| Requested fill extent | `[0x10000,0x11770)` |
| Live allocation before next header | data `[0x0f010,0x11340)` |
| First invalid header byte | physical `0x11340`, `0x4d → 0x80` |

This is an observation during the repeated instruction. It does not certify
instruction retirement or the final iteration. The exposed EDI/CX values and
host string-operation locals must not be confused with completed REP state.
The native write stack is `DoString_Normal → CPU_Core_Normal_Run`; the guest
call frame independently supplies the original fill arguments.

The original caller provides the narrower cause: its digital-audio setup sets
a 3,000-byte size, requests three times that size, then advances a candidate
buffer pointer in ten-byte steps while checking it through an `INT 66h`
wrapper. It fills twice the size after that check accepts. In this execution,
the accepted candidate is `0x10000`, and its 6,000-byte fill exceeds the DOS
allocation by `0x430` (1,072) bytes. The saved code and call arguments establish
this path; a complete DIGPAK driver/allocator contract or every possible audio
configuration has not been reconstructed. Host output muting leaves the guest
sound devices and this initialization code active.

The first writer is now identified for the fresh reproduction. Historical PID
63534's exact memory is still unavailable. This is not proof that every TFTD
edition, route, memory layout or sound setting reaches the same overwrite.

## Native fix and receipt boundary

Both complete DOSBox patches now contain two narrowly scoped changes:

1. `DebuggerAdapter::TerminateTarget` catches the known DOS debug-memory
   `int(7)` and returns failure. It performs no subsequent IRET adjustment or
   shell resume after that partially completed memory walk. The server exposes
   a failed stop; the canonical Python certificate remains interrupted.
2. `SHELL_FreeMemoryForExit` contains that same error only for an explicitly
   configured agent session. Shell destruction then skips unsafe process
   metadata traversal and allows final host DOS/file/device disposal. The
   failure is logged as discarding the guest, never repairing it. Other integer
   errors and non-agent behavior retain their existing exception semantics.

The shell destructor previously let the DOS exception escape an implicit
non-throwing boundary, causing native termination. The change contains this
cleanup failure; it does not change original game behavior or repair guest RAM.
The [shutdown certificate](SHUTDOWN_RECEIPTS.md) still distinguishes clean host
exit from successfully completed guest stop. An exit-zero host can correctly
carry `closed=false`, `guest_stop_complete=false`, `status=interrupted`.

## Source and native identities

The writer traces use installed native SHA-256
`bcf318de2a22d49d1b28888a312e12b774cf1f041fdd8862fc4ab3335ea59b60`.
That installation was not changed. Its complete historical patched build tree
was unavailable; retained source trees differ from its installed manifest.

The actual baseline/candidate comparison instead uses the existing complete
layers source for this MR, all declared source files independently checked:

| Edge | SHA-256 |
| --- | --- |
| Retained MR baseline binary | `c88248913d582f95ddf1f4ca8aea1ef977f1029c5cb1bf6538cb8fbc4fdd7734` |
| Private incremental candidate | `3f3d14cde64c93ff8fb6b8ce54ca8290bf97e6c88a4fd5f0819e5140dde6c9ad` |
| Stable complete patch | `8d2ffb7105faafe4a28be7497bd1e860babb74cbda58b180e4d773a6c7b60ef9` |
| Layers complete patch | `07f6d8edbe79412ff11de09a199488023d33e463cac07b76287ff51fed5d1c3b` |

Only shell and debugger-adapter source were rebuilt, their archives regenerated
and the private candidate relinked. Baseline objects/libraries and configuration
are retained provenance; this is not a fresh full native rebuild. The source
overlay matches the candidate layers manifest. Full patch replay against
upstream `029bd65c5dcc7cdc7f2e14e35278620d9707d969` verifies all 38 stable and
39 layers manifest paths. Stable has compiled isolated-guard and replay evidence;
the original-game acceptance below qualifies the layers candidate only.

## Luna's original-game regression and independent readback

All five ordinary acceptance processes were launched without LLDB. Each made
one native stop request. No case needed a forced-kill fallback. Actual spawn
arguments and selected environment confirm dummy SDL audio, mixer output off,
MIDI device none and headless quit-warning suppression.

| Case | PID | Native return | Canonical certificate |
| --- | ---: | ---: | --- |
| Baseline TFTD after bounded 8-second startup | 34967 | `-6`, SIGABRT | interrupted, closed false |
| Candidate TFTD entry | 37049 | `0` | closed true |
| Candidate TFTD after same bounded startup | 37052 | `0` | interrupted, closed false; native stop failed |
| Candidate original DinoPark, existing running-park save | 37054 | `0` | closed true |
| Candidate DinoPark, loss of real terminal stop observation injected | 37072 | `0` | interrupted, closed false |

The faulted candidate's retained log contains both the DOS corrupt-MCB error
and the new shell cleanup/discard diagnostic, without native SIGABRT. Healthy
entry/park cases continue to close successfully. The injected host readback
loss still cannot become a successful guest stop merely because exit is zero.

Luna reopened each actual Project and checked one close event, matching
certificate and run state/end time. Repeated close returned/raised the same
outcome without another RPC/event. Public workspace stop forwarded that same
certificate and released ownership. The native workspace check follows direct
close on the same session; first-call workspace coverage remains in unit tests.

The parent independently read each SQLite event, verified the external object's
size/SHA-256, decoded it and compared the complete certificate. Frozen source
and native identities match; acceptance input/save inventories are unchanged;
all acceptance and trace-owned PIDs are absent. Each acceptance output remained
within its 16 MB diagnostic bound. The user approved a finite CACHE investigation
up to 3 GB, maintaining a 20 GB CACHE reserve while temporarily allowing the
current internal free space. Global storage guards were not changed.

Fresh affected tests:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:player python3 -m pytest -q -p no:cacheprovider \
  tests/test_shutdown_receipts.py tests/test_timeline_interfaces.py \
  tests/test_dosbox_window.py tests/test_dosbox_window_native_contract.py \
  tests/test_dosbox_cleanup_native_contract.py tests/test_dosbox_source_companion.py
115 passed, 2 optional skips in 3.39 s
```

The new isolated C++ checks compile the shipped guard for both profiles and
exercise healthy cleanup, the owned int(7), other integers, missing control and
non-agent configuration. Both profiles initially lacked the guard and failed
the new checks. The real baseline additionally demonstrates the native crash.

## Pending fuzzer integration assessment

The requested pending implementation is [MR !60](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/60),
commit `bc1bcee6d78186236b411a5b5d632a57ae4216da`. Its exact branch was fetched
from GitLab and its `debug_fuzz` / `debug_fuzz_native` implementation inspected.
The existing matching checkout passed both focused test files: **36 passed**.
Those are planner/fake-session contracts on that separate branch, not original
DOS execution or tests of this MR's delivered source.

The feature uses finite declared input variants, fresh owned guests, pinned
inputs and terminal feedback. Those controls are useful for later route
variation and minimizing an input-dependent reproducer. Its native runner
currently admits only `wine-ne` and `wine-qemu`; DOSBox campaigns are explicitly
refused pending whole-mount input binding. The guard was retained. No unsupported
DOS fuzz campaign ran, and the unrelated Windows runtime stack was not merged
into this MR. Targeted first-write watching was sufficient for this deterministic
startup failure. A useful future extension would bind the whole DOS mount and
native/source identities, retain MCB-invariant feedback and native return codes,
and require guest reaping before each fresh variant.

## Claim limits and retained private evidence

This qualifies bounded original startup and prepared-save DinoPark cleanup on
macOS ARM64. It does not establish a full TFTD playthrough, repaired game memory,
historical PID replay, every destructor exception, other operating systems or a
fresh packaged/installed backend. No hosted CI, release or merge is claimed.

Private evidence root: `/Volumes/CACHE/fDisBull-scene-indexed-20261103/tftd-mcb-writer-20261104`.
Its `attempt-02` and `attempt-03` records preserve the writer observations;
`baseline-c882` and `candidate-acceptance` retain the canonical native cases.
`CANDIDATE-FROZEN.json`, `PATCH-REPLAY.json` and `PARENT-VERIFICATION.json` bind
source, native and persisted readback. Full raw evidence remains outside Git.
