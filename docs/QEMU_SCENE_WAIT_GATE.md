# Finite native scene-wait gate

The explicit scene-2 runtime-memory `scene_wait` gate passed on 2026-11-20 at
the source/runtime tuple recorded below. Its source is
`tests/test_qemu_scene_wait_native.py`. This authored DOS result leaves scene-1
parity and DOSBox retirement unqualified.

## Recorded native execution: 2026-11-20

Separately admitted attempt 06 passed **all ten cases, with zero failures,
errors or skips**, using eleven owned VM lifetimes and retaining all 22 native
logs. The outer phase recorded success in 11.512 seconds. All owners were
reaped, the worker process group was gone, and cleanup had no unresolved
descendants. Postflight verified 11,270 input files and six trees unchanged,
covering the exact source/tests, Python closure, private native dependencies,
combined QEMU prefix/firmware and selected host/media inputs.

| Tested identity | Commit or SHA-256 |
| --- | --- |
| Source and test commit | `c1e5e208b117366e8b5c7d487acfd91b2ec98760` |
| Combined QEMU executable | `b82342e48ab014d6a0526675492d9b0bbfe6844d8eb8848570e93b961bbc589c` |
| Matching qemu-img | `e32f68642711fc2e6de17e4e4f46d026356bdc5dc9fbc3a0fd71475bcaa72dbc` |
| Full FreeDOS input image | `552f7cbb0625960c050a3e682a4d2121cc2ffdfa9dc9d592ccd49edf179333dc` |
| Accepted `phase-result.json` | `0cc58fd5216fd0c8ef005eee2c712d44246092011924333862aafc3d94837390` |

The retained private evidence set is
`scene-wait-evidence-20261120/native-attempt-06`; its phase receipt binds the
admission, per-case owners/results, logs, test selection and postflight. Raw
disks, checkpoints, FDBs and output objects remain outside the repository.
The final host selection at the same source passed 85 cases without skips:
80 scene-wait cases and five existing input/passive-scene checks. Earlier
547-case and 86-case selections are separate, overlapping receipts.

The three successful public routes each observed the authored IRQ1 make/break
state after one 107 ms interval. The initial match used no interval. The false
predicate exhausted its observed 20 ms budget in four intervals; this selected
result does not promise arbitrary exact native cutoffs. The first breakpoint
and watchpoint stopped before another predicate read. Full restore required a
new RAM witness, and real DOS exit/TSR returned code 37 with their terminal
evidence preserved. These are results for the declared authored DOS scene-2
RAM predicates, not whole-game, frame, mouse/action or migration qualification.

### Preserved earlier attempts

Every earlier attempt stopped at its first failure and remains separate from
the accepted attempt. None counts as a completed native gate pass.

| Attempt | Observed failure and correction |
| --- | --- |
| 01 | No VM launched. The controller incorrectly required the full 15,000 ms constructor timeout after disk preparation had already consumed part of the startup deadline; admission now checks the positive remaining allowance. |
| 02 | One VM failed to reach DOS READY; no scene wait ran. The selected minimal image lacked the configured `FREEDOS/BIN/COMMAND.COM`. The next admission used the preserved full FreeDOS image identified above. |
| 03 | The Python wait case passed, then controller reconciliation missed the keyboard-press call because it patched the mixin after `MachineContext` had captured its guarded method. The observer target was corrected. |
| 04 | The Python case passed and the JSON wait/export completed; the JSON oracle incorrectly compared canonical integer addresses with the existing public hexadecimal presentation. A test-only correction preserved full canonical/storage equality and checked the full public projection. |
| 05 | Python, JSON and script cases passed. The initial-match check then incorrectly required a cached schedule receipt to remain identical after legitimate observation-timestamp/sequence refresh. The scoped test correction retains all ownership, native receipt, process and guest-clock invariants. Its later assertions had not run in this failed attempt. |

## Cases and maximum owner count

Run only the ten selected cases in this file, with `-x` to stop the campaign
after its first failure. Each case starts one fresh DOS process fixture. Only
the restore case creates a second native owner. The complete selection admits
**at most eleven owned VM lifetimes**; no automatic retry or unrelated campaign
is part of this gate.

| Test suffix in `tests/test_qemu_scene_wait_native.py` | Maximum VM lifetimes | Required observable |
| --- | ---: | --- |
| `test_native_scene_wait_public_routes[python]` | 1 | Initially false predicate becomes true from actual IRQ1 make/break; measured time and stored result |
| `test_native_scene_wait_public_routes[json]` | 1 | Complete public address projection of the canonical result; output artifact export does not execute another interval |
| `test_native_scene_wait_public_routes[script]` | 1 | Saved `scene-wait` followed by assertion; exact retained result |
| `test_native_initial_match_preserves_fixed_arm_and_invalid_script` | 1 | Invalid literal refuses before a prior RAM edit; immediate match leaves a fixed arm completely pending |
| `test_native_false_scene_wait_measures_budget_timeout` | 1 | False observed RAM predicate exhausts 20 ms virtual budget; no additional interval and truthful overshoot |
| `test_native_scene_wait_keeps_first_native_stop[breakpoint]` | 1 | IRQ1 fence stops after make; the first stop wins over a now-true predicate |
| `test_native_scene_wait_keeps_first_native_stop[watchpoint]` | 1 | Held-byte store stops after make; no post-stop poll, continuation or release |
| `test_native_restore_requires_new_scene_wait_witness` | 2 | Original owner closes; restored scene refuses old RAM witness; explicit rebind enables an immediate match |
| `test_native_scene_wait_records_dos_return[guest_exit]` | 1 | Genuine DOS exit advances the capture epoch; JSON retains exact terminal evidence and performs no post-stop poll |
| `test_native_scene_wait_records_dos_return[guest_tsr]` | 1 | Genuine DOS TSR return advances the capture epoch; saved-script failure retains exact evidence and prevents its next step |

The first eight cases use the existing `movement_guest` authored COM in
`tests/support/observed_movement_fixture.py`, launched through
`tests/test_qemu_scenes_native.py`. It executes real DOS, installs IRQ1 and
records make/break bytes in guest RAM. Neither a raw boot fixture nor host test
peers qualify this lane. The input-ledger scene uses its own recognition group;
an edge occurrence and a released key are independent facts. Stop cases use
the same native source bytes and check the make counter separately only after
asserting that the wait performed no post-stop read.

The successful JSON case captures the canonical Python return once, checks
the complete exported result against its public address projection, and
explicitly verifies hexadecimal allocation bounds and driver header addresses.
Stored and reopened observations must exactly equal the canonical result.
Exported bytes retain their own size/hash checks, and export must not execute
or observe another wait. Error-envelope and saved-script receipts retain their
canonical address types; the two terminal cases keep exact result comparisons.

The final two cases use existing `com_exit(37)` and
`resident_com(exit_code=37)` bytes from `tests/support/dos_process_fixture.py`,
saved as `SCNEXIT.COM` and `SCNTSR.COM` respectively. Their initially false
scene compares an explicitly witnessed physical RAM byte at the stopped COM
entry (`90`) to `FF`. Real DOS then reports normal exit or resident return via
the existing process helper. They start at original entry, so they need no
additional ready-breakpoint run. Layer-active close remains focused host
coverage; it is not an extra native case.

## Exact launch tuple and required inputs

Use the ready project Python closure with this worktree on `PYTHONPATH` (or the
repository pytest configuration). Pin its interpreter and package identities,
the exact tested source commit and the generated COM hash. Before starting,
record hashes for the privately prepared QEMU binary, firmware, boot image,
mcopy, NASM and qemu-img. Do not substitute a producer with different native
extensions or reuse a checkpoint from a different QEMU binary.

| Variable | Required input |
| --- | --- |
| `FDISBULL_QEMU_CLOCK` | Fresh combined QEMU executable with native virtual clock, scheduled input, keyboard press and owned-machine checkpoint support |
| `FDISBULL_QEMU_DOS_BOOT_IMAGE` | Preserved full FreeDOS boot image containing `FREEDOS/BIN/COMMAND.COM`; fixture edits only a private copy |
| `FDISBULL_QEMU_DOS_MCOPY` | mcopy executable invocation; preserve its multicall name rather than resolving it to an mtools binary name |
| `NASM` | Pinned assembler for the authored fixture |
| `FDISBULL_QEMU_CLOCK_FIRMWARE` | Matching QEMU firmware directory; `FDISBULL_QEMU_DOS_FIRMWARE` is the existing fallback selector |
| `FDISBULL_QEMU_IMG` | Matching qemu-img checkpoint tool |
| `FDISBULL_REQUIRE_QEMU_CLOCK` | `1`, making missing native prerequisites fail |
| `FDISBULL_REQUIRE_QEMU_DOS_OS` | `1`, making missing DOS/checkpoint prerequisites fail |
| `FDISBULL_TARGET_STORE` | Private per-gate source/object store outside Git |
| `FDISBULL_OUTPUT_ARTIFACT_DIR` | Private per-gate output store outside Git |

The unchanged launch helper selects `backend="qemu-dos"`,
`qemu_transport="pipe"`, `qemu_clock="virtual"`,
`dos_startup_batch="FDAUTO.BAT"`, `boot_timeout_ms=15000`, the matching firmware
and checkpoint tool. The prepared baseline uses the existing FreeDOS boot-key
window suppression; DOS kernel/shell and the process loader still execute.
No caller game or BBS package is needed.

## Time, storage and failure bounds

Each initial launch has a 15-second DOS startup budget, including disk
preparation. The QEMU constructor receives only the positive remaining
allowance, at most 15,000 ms. The first eight cases
also use one 10-second setup run to the fixture's ready breakpoint. After setup, the test installs one
inherited 30-second body deadline; the restore case uses 60 seconds shared
across its original and replacement owners. Every scene wait independently
intersects a 5-second host budget. The saved-script route also has a 7-second
outer bound (also used by the TSR script). Restore explicitly requests at most 30 seconds. These limits do
not add together to renew any inner operation's inherited deadline.

Successful and stop cases request at most 500 ms guest time with 25 ms slices;
the owned fixed press is 80 ms hold/80 ms gap and the wait uses its existing
full-plan first interval. The false-predicate case requests 20 ms total with
5 ms slices and permits at most four intervals. Elapsed virtual nanoseconds
must equal the observed final-minus-initial clocks; native timer overshoot is
retained, rather than rounded away or declared an exact requested duration.
Immediate, stale-witness and rebound waits request no actual execution.
The initial-match case compares the complete public and internal input state,
process, native arm and stopped guest clock, with GDB execution forbidden.
Only the revalidated schedule receipt's `clock.host_monotonic_ns` and
`clock.sequence` may refresh: both remain integers and monotonic, and the
sequence must advance. The invalid-script refusal still requires exact input
state equality because it must fail before that observation. Passive
`scene_check`/`scene_assert` tests retain their existing exact-state assertions.

The gate owner must also apply an independently admitted whole-controller wall
deadline, process/descendant ownership and storage/log caps. The per-operation
deadlines above do not bound all file copying, assembly or cleanup by themselves.
Preflight free space before the private boot copies and the one full checkpoint.
Keep the baseline, per-case disks/FDBs, object store, logs, exported JSON and
checkpoint outside Git. Preserve failed output; do not silently retry to obtain
a green receipt. The owner count remains bounded even if a restore fails partway.

## Invocation and qualification

After independently reviewing the exact source and admitting its runtime tuple,
the native owner can invoke:

```sh
python -m pytest -q -x tests/test_qemu_scene_wait_native.py \
  --basetemp=/private/scene-wait-gate/pytest \
  --junitxml=/private/scene-wait-gate/results.xml
```

Use the gate's real private directory and interpreter, and preserve command,
environment identities, output/exit status and owned-process cleanup receipts.
Expected collection is ten cases. A skip, timeout, missing output or
unreaped/extra owner is incomplete qualification. A passing authored lane
establishes only these scene-2 wait behaviors on that tuple. Legacy frame
identity, absolute mouse authority, scene-1, actions/navigation and broad DOSBox
retirement remain separate open obligations.
