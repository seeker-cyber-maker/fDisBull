# Finite native scene-wait gate

This is a prepared acceptance plan for the explicit scene-2 runtime-memory
`scene_wait` contract. Its source is `tests/test_qemu_scene_wait_native.py`.
It does not record a native pass, qualify scene-1 behavior or authorize DOSBox
retirement. Record actual results against the exact source/runtime tuple.

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
| `FDISBULL_QEMU_DOS_BOOT_IMAGE` | Preserved caller-owned FreeDOS boot image; fixture edits only a private copy |
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

Each initial launch has a 15-second DOS startup budget. The first eight cases
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
