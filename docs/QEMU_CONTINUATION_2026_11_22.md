# QEMU continuation: 22 November 2026

This continuation reconstructs the three pending implementation slices after
the recovered frame-admission parent `af97dfa1105748098f354e4979df688d997c07d1`.
The lost historical implementation commits are not claimed recovered. Source,
build and qualification records identify the new implementations separately.
The parity ledger remains open: 143 surfaces, 18 workgroups and seven campaigns.

## Implementation

| Commit | Resulting behavior |
|---|---|
| `d117756baee5cffcbb2e8941f1baf4bffec253d7` | Instrumented format 3 retains independent completed and partial source pixels, exact row timing and actual timer expiry, with fresh ownership and full host readback on restore. |
| `f6654499491c3f01b1b3990936190539210f06de` | Native keyboard batches are planned against actual bounded device state; accepted receipts describe the real enqueue, while verified refusals preserve the accepted prefix and cleanup uses the captured owner. |
| `5e1f58df423c4f0b80d0abe338eae5c31a2d8bd6` | One finite pending-QMP-event batch is reconciled before supported stopped frame/status observations and after verified asynchronous DOS return. |
| `db3ac85d1e9ea76a7ff8f04d7e3af56c6335eb59` | The monitor predicate admits QEMU's private GDB HMP frontend while preserving external-HMP, second-QMP and internal-chardev substitution refusals. |
| `5c9c09b2aa70a42c298e41d08868f2c605710b2b` | The native capacity regression selects expectations from the advertised complete batch protocol and probes later ownership errors with an unheld key. |

## Restored inputs and compiled producers

The runtime, complete native baseline source, configured build, bootstrap and
installed prefix were restored before new execution. The full native baseline
map matched 86,043 entries, including 79,611 regular files totaling 710,577,925
bytes. Its map SHA-256 is
`990b6dc80d91c000911933852385ee9ecdfe234855bd4796fcd730e5581ff999`.
The three new native layers composed against 16 disjoint, exact preimages.

| Producer | QEMU executable SHA-256 | Native evidence binding |
|---|---|---|
| Initial composed producer | `31841bb1ef356c5935fda5abb816b8ed5deef9d5223c6f218da23afc28f1d0ae` | Full keyboard queue/refusal/checkpoint witness; checkpoint attempt 01 exposed the monitor predicate defect. |
| Corrected monitor producer | `95b3276fd9e38001b42b95b730e1641fe3c54799a3b1235a4e063c6f283d3c32` | Native capacity case, four monitor controls, three pending-event behavioral cases and sampled-frame checkpoint continuation. |

The first build completed in 163.871 seconds. The one-file monitor correction
rebuilt its object and linked in 4.839 seconds. The common checkpoint tool hash
is `296e707a098d232681969782ce2912f163201c32a2131518fdd4f6ee0658c82e`.
No host-only or documentation change was treated as a reason to rebuild QEMU.

## Host qualification

The exact integrated selection on `5e1f58d` collected 1,315 cases: **1,314
passed, zero failed or errored, and one optional `rgba-zstd` case skipped**.
The formerly skipped case subsequently passed alone with zero skips using an
audited, isolated `zstandard` 0.23.0 wheel. This is one integrated selection plus
one separate dependency-qualified result, not a second combined 1,315-pass run.
The shared runtime and source stayed unchanged.

Earlier slice-specific evidence remains separate: checkpoint has 465 retained
and 125 fresh passing host cases; keybatch has 200 fresh passes; pending events
has 131 focused and 524 compatibility passes with the original optional skip.
These overlapping counts are not added to the integrated total.

## Native keyboard and pending-event results

The [keyboard qualification](QEMU_FRAME_KEY_BATCH_GATE.md) records the exact
Ctrl/Alt/A/Up make and reverse-release IRQ bytes, a queued checkpoint restored
without make reinjection, busy and stale-plan refusals, and the separate updated
capacity test. The full keyboard witness remains bound to the first producer.

The corrected producer passed four monitor controls: normal QMP plus GDB,
second-QMP refusal, external-HMP refusal and rejection of an externally requested
internal GDB chardev. The last case intentionally exits at startup with code 1.
An earlier Unix-socket setup failure is retained separately; the qualified
controls use the production FIFO transport.

Three additional first-attempt native cases passed. An authored RTC stimulus
produced a real retained `RTC_CHANGE`, delivered the actual returned object,
and left an immediate same-lifetime repeat empty. Held and released-but-attached
keys allowed public status, probe, RGBA, RPC screenshot and artifact reads;
each operation completed its cut before admission and preserved the complete
key proof, CPU registers and virtual time. Two authored DOS programs exercised
verified asynchronous normal exit (42) and resident return (43), final revision
publication and stable empty repeats. Every owned process was reaped and all
runtime/manifest rechecks passed.

## Sampled-frame checkpoint continuation

The corrected producer reached a real retained-past timer after one observed
NOTIMER step. The sampled prefix had 64 rows and 61,440 bytes, distinct from the
192,000-byte retained completed raster. Intended next-row time was
1,455,862,125 ns; actual armed expiry was 1,455,862,178 ns; stopped time was
1,455,862,305 ns. Successful save and an actual duplicate-tag failed save
preserved the complete native state and exact expiry.

Hot public restore gave a fresh token and epoch while preserving all logical
source fields. Both the original and restored trajectory completed all 200
rows with identical pixels and completion time. Attempt 03 then stopped in an
in-place legacy harness control, before its cold continuation. The public load
path creates a fresh VM; reusing an already-initialized scheduled-input owner
across raw snapshot reset violates that lifecycle. This is a harness failure,
not evidence that the public replacement path failed.

A separate cold continuation then passed against the retained attempt-03
artifact without repeating the hot/save trajectory. It reconstructed expected
row timing from the authored guest's saved port-read buffer and an independently
journaled clock observation. Two fresh QEMU owners exercised the public load
path in a separate Python process. The exact logical source, both images and
the past armed expiry survived, and the continued raster matched the original
and hot result: 200 rows, completion at 1,464,421,153 ns, pixel SHA-256
`f8553232667b500acea4c92eeb1ccc4f1c2b56cf764f8809cb685d7d82cc1518`.
Both owners exited normally; source, runtime and retained original inputs were
unchanged. The receipt SHA-256 is
`9b21bab56707d4d35d82b89e3d91142771188b96222be2c00e478af8276f4f96`.
An earlier cold setup attempt refused a cloned target-store directory with
incorrect permissions before checkpoint load. The corrected fixture creates
that private directory with the required mode 0700; production guards are unchanged.

The earlier two-step construction also contained a test assumption error:
QEMU can run an overdue timer when a second resume re-enables the clock before
NOTIMER masking. Attempt 03 retained the exact successful single-step values;
no timer field was injected or production behavior relaxed to satisfy a test.

The final fresh-owner control passed on its first attempt. One new authored
idle origin supplied a genuine format-3 export and scoped snapshot; three
independent destinations then loaded and imported format 3, a neutral format-2
projection and a neutral format-1 projection. The unchanged host validator
accepted all three. Each destination loaded before import and before its first
input query, rebound the native epoch to 2, preserved idle source/time/icount,
adopted no source token or window, and executed no guest instructions. All four
sequential QEMU owners exited normally; source, runtime and retained inputs
were unchanged. The sanitized receipt SHA-256 is
`523760f421d861576eb5676847a7ebcfffdcd456ee94137d57bec472b3603bbc`.
Formats 2 and 1 are explicit neutral schema projections of a current native
idle export. They do not establish restoration of an archive from an older
producer or broad public legacy-artifact compatibility.

## Remaining qualification

No whole-game or cross-backend parity promotion follows from these bounded
results. Native typematic and wider scan-code profiles, pending-event all-state
overflow and allocation-failure atomicity, broader checkpoint source states and
off-profile combinations, source-backed timelines, and game-level integration
remain separate work. Existing dynamic source phase differences against
DOSBox-X remain explicit. DOSBox-X stays the default/fallback; no merge,
release, installation or default-backend change is part of this continuation.
