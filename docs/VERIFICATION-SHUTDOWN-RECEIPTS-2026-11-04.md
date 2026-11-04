# Native cleanup exception and truthful shutdown receipts — November 4, 2026

Follow-up: [the first corrupting write and native cleanup fix](VERIFICATION-TFTD-MCB-WRITER-2026-11-04.md) identify the original GEOSCAPE fill, contain the owned shell cleanup exception, and compare an actual SIGABRT baseline with a candidate that exits zero while retaining an interrupted guest receipt. The historical evidence below remains unchanged.

This contribution continues the [PID 63534 investigation](VERIFICATION-DINOPARK-SOURCE-SHUTDOWN-2026-11-03.md).
It captures a matching original TFTD cleanup exception before unwind, repairs
the DOS shutdown certificate and tests that certificate against original TFTD
and DinoPark. The native C++ cleanup fault remains present; the host now retains
and reports its failure instead of treating process reaping as success.

## Exact exception in an owned TFTD reproduction

Historical PID 63534 was previously identified directly in the private TFTD
`cold_new` project as target `TERROR.COM`, run
`09dd85428387409abf12c8faec1763fc`. Its native image and teardown stack matched
the installed backend. The old receipt recorded an interrupted stop and RPC
channel loss; it did not retain a thrown value or pre-unwind memory.

Luna (`gpt-6-luna`) launched a new owned original-game process, PID 16816, and
used LLDB callbacks to observe the failure before stack unwinding. The native
executable remained SHA-256
`bcf318de2a22d49d1b28888a312e12b774cf1f041fdd8862fc4ab3335ea59b60`.
The actual observations were:

- `DOS_Mem_E_Exit` received **`Corrupt MCB chain`**.
- `__cxa_throw` carried C++ type **`int`**, value **7**.
- The stack passed through `DOS_FreeProcessMemory` and `DOS_Shell::~DOS_Shell`
  before native termination by SIGABRT, signal 6.
- Shell cleanup selected PSP **`0x0701`**, starting from MCB **`0x0450`**.
  MCB header segment **`0x1134`** was invalid, with type `0x80` and owner/size
  values `0x8080`. The native dump's following data segment is `0x1135`.

The raw stack retains a linker cold-function alias rather than rewriting it
as a source-level caller. Address/unwind evidence establishes the memory-free
cleanup context; an alias name alone does not identify a different path.

This confirms the literal exception and invalid-MCB context in the owned
reproduction. It does not reconstruct historical PID 63534's exact memory,
prove the same invalid block existed then, or identify the first writer.
There is no claim that a rejected mouse request caused the corruption.

The trace used one bounded original startup interval. TFTD's title was not
qualified: absolute mouse input was rejected in protected mode, and no accepted
game input, save, purchase or guest-memory edit followed. The cleanup failure
was observed when ending that owned process. An earlier trace-attachment
attempt ended cleanly before attachment and is preserved separately. No host
security settings or original files were changed.

## Receipt implementation

The [DOS shutdown contract](SHUTDOWN_RECEIPTS.md) now distinguishes guest-stop
completion, terminal session ownership, process reaping, actual return code
and signal termination. `DebugSession.close()` retains a
`fdisbull-shutdown-1` certificate. It returns a copy on success and raises
`DebuggerShutdownError` carrying the certificate for an interrupted outcome.
Existing cleanup exceptions retain their original type and gain the receipt.

The public `debug-stop` route returns the certificate's actual `closed/status`,
then releases terminal ownership. It no longer manufactures `closed: true`
after an interrupted stop. The internal `debug.closed` flag still means the
session may not issue further actions; it is not a success certificate.

Repeated closes return or raise the same retained outcome without another
native request or close event. Transport cleanup retains the final bounded
native-log text before removing the temporary directory. The abnormal TFTD
case now preserves the fatal MCB message in its canonical project event.
Project/server teardown also attempts every owner before surfacing a failure;
an earlier failing session cannot prevent cleanup of later owners.

## Original-game acceptance by Luna

The final source was frozen before this phase. It used the source package
and the pinned installed native backend, not a newly installed tool. Existing
private original-game inputs and the qualified DinoPark native disk save were
reused. No game directory was copied and no screenshot/state capture, analysis
traversal, native rebuild or package was requested. Small diagnostic projects
were created solely to test actual persistent close events.

| Qualified case | Expected and observed certificate | Owned process |
| --- | --- | --- |
| TFTD at executable entry | `closed: true`, `status: closed` | PID 21332, exit 0 |
| TFTD after bounded startup | `closed: false`, `status: interrupted` | PID 21334, return code −6, signal 6 |
| DinoPark after native-save load and observed park operation | `closed: true`, `status: closed` | PID 22714, exit 0 |
| DinoPark after real stop, with injected loss of its observation | `closed: false`, `status: interrupted` | PID 22758, exit 0 |

The startup TFTD case reproduced the actual MCB failure without LLDB. Its new
certificate retained `Corrupt MCB chain` in the native-log diagnostics and
raised `DebuggerShutdownError`. This is a positive test of failure reporting,
not a repaired native shutdown.

For DinoPark, the harness loaded the existing save through the original UI,
qualified Office/Street/Park with native sparse predicates and observed park
resources and explicit progression. In the fault case it first received the
real terminal native stop observation, then injected a host readback error.
There was one stop request. Despite return code zero and successful reaping,
the certificate correctly retained unknown guest-stop completion.

For all four qualified cases:

- Reopening the actual private project found exactly one canonical close event,
  equal to the session certificate, with the expected stored run state/end time.
- Repeated `DebugSession.close()` calls performed no new RPC or event write.
- `DebugWorkspace.invoke('debug-stop', ...)` forwarded that same certificate
  and removed ownership. This native workspace check followed direct close on
  the same session; the unit tests also exercise first-call workspace shutdown.
- Actual arguments/environment verified quit-warning suppression and SDL,
  mixer and MIDI mute. All owned PIDs are absent and transport directories gone.
- Frozen source, measured scripts, native binary and original game/save
  inventories matched their recorded hashes after execution.

There were **five acceptance attempts**: these four qualified cases and an
initial DinoPark attempt aborted by the private harness's conservative 5 MB
evidence guard. Its report, script and diagnostic project remain unchanged and
excluded from acceptance. The observed SQLite/object footprint justified a
separate bounded DinoPark continuation; the passed TFTD cases were not rerun.
The complete cleanup diagnostic packet occupied **11,759,446 bytes**, within
the revised 16 MB bound. This was small read-only target diagnosis, not the
bulk capture/build allocation refused by the storage gate.

The parent's 12:07:20.771 UTC CUA running-app inventory found no matching
DOSBox-X or crash-report GUI owner. No closing dialog was dismissed. This is
a bounded post-test observation, not continuous desktop video.

## Regression and private receipts

Before implementation, all ten initial regression cases failed for the missing
certificate/error/readback semantics. The final affected unit suite passes
**110 tests, with two optional native/window skips**, in 1.79 s:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:player \
  python -m pytest -q -p no:cacheprovider \
  tests/test_shutdown_receipts.py tests/test_timeline_interfaces.py \
  tests/test_dosbox_window.py
```

Coverage includes return-code/signal outcomes, lost stop replies with exit zero,
failure diagnostics surviving temporary cleanup, UTF-8 log bounds, idempotence,
public stop replies, cleanup after earlier owner failures and preserving an
existing context-body exception. The window-profile fixture now supplies an
actual exited stop result instead of an unrelated paused-state result.

Private evidence lives under
`/Volumes/CACHE/fDisBull-scene-indexed-20261103/cleanup-receipts-20261104-small/`:
`TRACE-FINDINGS.json`, raw LLDB records, `SOURCE-FROZEN.json`,
`FINAL-ACCEPTANCE.json`, `PARENT-VERIFICATION.json` and the two acceptance roots.

- Exact-trace findings SHA-256:
  `c8f6c9379f0776d171d3c3f470e999165aa05a3ad8008d453ecf27cfa223111e`.
- Final native acceptance SHA-256:
  `fffe876ffdbec7badebbea091be51202b7202eec61c2aabf853ae2618c074b26`.

Raw game files, projects/object stores, inventories and crash/LLDB bodies stay
outside Git. No TFTD corruption-writer fix, native C++ repair, full-game parity,
other-platform or visible-window qualification is claimed. Earlier screenshot
and park-only test receipts retain their own source scopes. No package,
installation, release, merge or hosted CI execution was performed.

## Project-wide video assessment

The separate [CPU semantics/cost-profile note](research/2026-11-04-cpu-video-udl-uil-udc.md)
records the supplied video's relevant timestamps, primary-source corroboration
and recommendations for UDL/UIL/UDC and Z benchmarking. Full captions remain
private; the note adds no compiler feature or new hardware compatibility claim.
