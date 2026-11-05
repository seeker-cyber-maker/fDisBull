# Direct indexed PNG in DinoPark scene checks — November 3, 2026

DinoPark's pixel-only scene observations now prefer native indexed PNG through
`debug.frame_rgba(encoding="png-indexed")`. They decode the native PNG once and
consume RGB pixels directly, avoiding PNG re-encoding, screenshot export and
capture-artifact persistence. This applies the measured result of the
[direct-consumer experiment](VERIFICATION-DINOPARK-DIRECT-RGBA-2026-11-03.md)
to production scene checks rather than only a standalone codec benchmark.

## Selected observations and evidence contract

The shared `dinopark_scenes.observe_frame()` helper now serves six pixel-only
sites: park status/notice recognition, view disambiguation, inventory digit
reading, the current General Store tab guard, Z's parking-notice read and Z's
modal read. Existing recognition samples, tolerances, exclusions, balance
checks and scene assertions are unchanged. Generic manifest checks already use
native sparse pixel probes and retain that path.

The helper returns the existing RGB image shape plus a JSON-safe descriptor
marked `capture: direct` and `persistent: false`. Its SHA-256 identifies raw
RGBA bytes, while transport metadata identifies the native compressed payload.
It contains neither pixel bytes nor an artifact ID. It cannot serve as a
durable screenshot reference in a scene manifest.

Scene publication, recovery qualification, native saves and action evidence
continue to use explicit durable PNG captures. The scene event journal also
continues to record semantic observations; removing capture persistence does
not suppress that journal. New checks do not invoke screenshot hooks.

Encoding selection happens before dispatch. Backends advertising indexed PNG
use it; older backends can use the direct ordinary-PNG consumer. An adapter
without `frame_rgba` retains the explicit legacy capture with hooks disabled.
A dispatched direct-read error propagates as an unknown observation, without
retrying another encoding, replaying an input or advancing the guest. The helper
requires the qualified 320×200 image. A caller's existing explicit bounded
wait policy remains separate from this read-only helper.

## Luna's original-game comparison

Luna (`gpt-6-luna`) ran one fresh, muted original DinoPark guest through ordinary
Office → Bank → Office → Street navigation and then the harness `quit` command.
No borrowing, repayment, purchase, save, restore or replay command was sent.
Harness quit closes the debugger; it does not claim a natural game ending.
Historical recovery guests were not resumed and their old probes are not
represented as current bindings.

For Office, Bank and Street, Luna measured the actual production
`TextScene.observe_one_of()` with `wait_slices=0`, including expected/observed
balance reads and the same semantic event journaling. The baseline substituted
only the capture layer with `take_frame(..., hooks=False)` in the same current
source and backend. Each scene used three warmups and 30 measured pairs with
shuffled order: **180 timed complete checks**, half per capture path.

All three cases selected the expected scene uniquely, with the other two views
negative. Full RGB buffers matched the durable original-game PNG exactly.
Every authored and runtime predicate agreed across both paths and native RGB
probes: 53 authored predicates, 44 runtime predicates and 1,712 distinct sample
coordinates per scene. These predicate counts do not describe the unresolved
binary-entry investigation. Registers, balances, frame ID, mode and captured
guest ticks stayed identical during each paused comparison. Guards disallowed
execution, input and restore RPCs during measurement; navigation occurred
outside those phases.

The optimized checks used one native PNG decode each, zero image-save,
export, screenshot-hook, event/artifact-persistence or SQLite-write attempts,
and unchanged database counters. Each complete view check still emitted its
one expected semantic journal event. The actual spawn used SDL dummy audio,
`mixer nosound=true` and `midi mididevice=none`. Original and disposable game
inventories were unchanged.

The first benchmark's final checker falsely marked shutdown failed: its raw
SQLite query parsed the external-object reference as though it were the close
receipt itself. The report is preserved unchanged, including that failure.
Read-only resolution through `TargetStore.get()` verifies `process_reaped: true`,
and the owned process separately reports exit code zero. The benchmark's only
post-measurement code correction resolves that stored reference before checking
shutdown. No timing/scene code changed and no guest or action was rerun to repair
the receipt. The separate parent verification records this adjudication.

## Measured latency

All values are wall-clock milliseconds, median (p95), on the sampled macOS
ARM64 backend. Each cell has 30 measurements. Complete checks include balance
readback, recognition and the existing fsynced journal. Instrumentation was
enabled and its overhead was not subtracted.

| Paused scene | Legacy complete check | Direct indexed complete check | Median reduction |
| --- | ---: | ---: | ---: |
| Office | 12.421 (14.750) | 10.919 (12.027) | 12.1% |
| Bank | 12.022 (16.211) | 10.078 (11.988) | 16.2% |
| Street | 11.949 (13.443) | 9.428 (10.861) | 21.1% |

| Paused scene | Legacy capture portion | Direct indexed capture portion | Median reduction |
| --- | ---: | ---: | ---: |
| Office | 5.782 (7.212) | 3.499 (3.994) | 39.5% |
| Bank | 5.056 (7.105) | 3.075 (4.419) | 39.2% |
| Street | 4.863 (6.404) | 2.827 (3.308) | 41.9% |

The comparison removes capture persistence as well as redundant image work; it
does not isolate indexed encoding alone. It qualifies these three paused views,
not a whole-playthrough speedup. No modal, inventory-digit, running-park status
or General Store branch was newly exercised in this original-game route; their
wiring is covered by the affected regression suite.

## Regression and source identity

The affected suite passes **437 tests in 33.67 seconds** with the actual native
backend. It covers codec validation, debugger capture contracts, sparse scenes,
hooks, timeline, native ZIP streams and all DinoPark tests. New observer tests
cover encoding selection, legacy compatibility, exact RGB/frame metadata,
unknown readback without fallback, unsupported dimensions, wrong/ambiguous
views and retained scene/state checks. A real authored native fixture confirms
full RGB equality, unchanged registers and zero capture database changes, and
rejects the ephemeral descriptor as a manifest's durable reference. Native CI
test lists include the new module without changing pipeline triggers.

No native rebuild was required. The benchmark used backend SHA-256
`c88248913d582f95ddf1f4ca8aea1ef977f1029c5cb1bf6538cb8fbc4fdd7734`
and complete layers-patch SHA-256
`78c6dde366d10194135360ef7a1b54e5c56b24f723244b1cb511870948fcb754`.
Original `DINOPARK.EXE` remains
`2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c`.

The frozen production scene module SHA-256 is
`1b79816a620dba9c3cf38840d312695457e4459b9beb822e9278d150d5e6e7a3`;
the Z bridge is
`d5b450b8879b7fcacb8b027f85810274dd5bc301b7f4f3e87a7c5b7f679a5d4e`.
Imported original class and predicate identities remain separately recorded;
the adapted class/helper identities are updated in the provenance manifest.

All 384 recorded script/client/profile hashes were unchanged across the native
run. The coordinating agent independently confirmed the final 383 client/profile
files still match; the benchmark's final-receipt-only correction is recorded
separately. The measured script is retained privately at SHA-256
`790f6c40eb5b27d81797f92918dd3e60709de77cd77ff5b9601baba0722a5b92`;
the corrected script is
`efac016d11922bc0172830a0ff7ac34fc44b8754610603465cf7342fda53af9d`.
The preserved original benchmark JSON SHA-256 is
`d93ab2910acd5960950d0e04d3c4a6a133a09fc8f601f5e627df0bfd531a00b8`.

Reproduce only with authorized original inputs and a new private external
directory after storage admission:

```sh
PYTHONPATH=src:player python scripts/benchmark_dinopark_scene_checks.py \
  --backend /private/build/src/dosbox-x \
  --game-dir /private/original-dinopark \
  --work-dir /private/new-scene-check-trial --iterations 30
```

Private evidence remains under
`/Volumes/CACHE/fDisBull-scene-indexed-20261103/`: the original benchmark,
session receipt, target objects, game copy, FDB, source freeze and test logs.
`PARENT-VERIFICATION.json` independently records the unchanged measured source,
side-effect guards and read-only shutdown-receipt resolution.
Only authored source, tests and sanitized methodology are included in !72.
The 97-entry/13-asset research inventory and purchase-presentation investigation
are unchanged. Other platforms, resolutions and whole-game behavior remain
unqualified. No package, release, installation or merge was performed.
