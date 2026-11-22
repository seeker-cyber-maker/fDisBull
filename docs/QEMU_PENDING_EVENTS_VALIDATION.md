# Pending-event cut qualification — 2026-11-22

The bounded pending-event host selection and the corrected Linux native
witnesses passed. The native witness delivered one real retained RTC event,
preserved held and released-but-attached keyboard owners across public reads,
and completed genuine asynchronous DOS exit and TSR observations. This is local
qualification of the declared cases, not a whole-product or hosted-CI result.

## Exact identities

| Item | Identity |
| --- | --- |
| Native host checkout | `5c9c09b2aa70a42c298e41d08868f2c605710b2b` |
| Corrected QEMU executable SHA-256 | `95b3276fd9e38001b42b95b730e1641fe3c54799a3b1235a4e063c6f283d3c32` |
| Runtime JSON SHA-256 | `6549a7486f31ace53a3e2f606d6a0180424659cd911d036309426885d961e9b7` |
| Behavioral worker SHA-256 | `3e70f5e5b435922de1d55578b66b1dd8558c1f80cdb7fb7f3aba91816ced2fb2` |
| FIFO monitor worker SHA-256 | `51328bfd0d26e550bee0c1538ecbbcdb7a0a384787b0927c3488201bfb47062b` |
| Corrected six-file native patch SHA-256 | `21456f65382c20ef9c63bc74b115cc7fa415df77dd9856a242b7e162cb18f2b6` |
| WNOWAIT supervisor SHA-256 | `d4f6162f00578489843006523af89deb99ce45259839f247c9cba37387e76cf0` |

The native checkout composes pending events, checkpoint and keybatch work.
The separate host-test receipt applies to the pending slice's unchanged
source map, SHA-256
`583a9c76a1f8668089ef26eb67f05054b02415d974989d5d9b53a4e4af0605f9`,
and integration patch
`d8d0d1d9cd1d112e9bd706e0b7d34106d6b584e866a67d535c9e3bd3475d042b`.
Those host results must not be relabeled as an exact-commit test of the later
composed checkout.

## Host results

The three new modules selected **131 tests: 131 passed, zero failures, errors
or skips**. Coverage includes strict packet and ID framing, whole-list validation
before delivery, multi-event callback order and identity, byte/count/deadline
limits, revision invalidation, captured-owner cleanup, all four frame reads,
held-key compatibility, and genuine helper-proof logic at authored transport
boundaries for DOS status transitions.

The adjacent selection collected 525 tests: **524 passed and one skipped**.
The sole skip is the explicit optional `rgba-zstd` codec case because
`zstandard` was not installed. Collection lists, JUnit, complete output, the
immutable source map and earlier failed host iterations are preserved. These
host tests did not execute a native emulator.

## Preserved native failure and monitor correction

The first composed checkpoint witness failed at its first public `status()`
cut on QEMU `31841bb1ef356c5935fda5abb816b8ed5deef9d5223c6f218da23afc28f1d0ae`:
`Pending-event monitor lifetime or setup is ineligible`. No checkpoint case
had run, and the original native owner was reaped.

The original predicate counted QEMU's private GDB-backed HMP monitor as an
extra external monitor. The one-file correction permits only the sole original
QMP plus at most one noninteractive HMP whose exact QOM type is `chardev-gdb`
and whose class is internal. External monitor, active-dispatch, lifetime and
native stopped-state checks remain. The other five native afterimages are
unchanged; all six identities are retained in the source manifest.

The first four monitor-only attempts used Unix sockets and failed before the
QMP greeting with `Operation not permitted` while creating the GDB socket.
They are preserved as **environmental setup failures**, not predicate results.
After the explicit FIFO transport correction, the following four cases each
passed once on the corrected binary, using production TCG and one vCPU:

| Case | Observed result |
| --- | --- |
| Standard stdio QMP + GDB FIFO | Exact empty `prelaunch` cut; immediate repeat retains the same UUID and epoch |
| Additional QMP FIFO | Exact typed monitor setup/lifetime refusal |
| External HMP FIFO | Exact typed monitor setup/lifetime refusal |
| Externally requested `gdb` chardev | Startup rejects the internal driver name |

These monitor cases used `-S`, no guest disk, no continue and no input.
Every original child and supervisor leader was reaped; each supervisor reported
`group_gone=true`, no timeout and no cleanup error.

## Real native behavior

All three cases passed on their first attempts, sequentially, with fresh private
guests. The behavioral worker and its runtime recheck delta received independent
source review before execution.

| Case | Observed result | Worker / supervisor seconds |
| --- | --- | --- |
| RTC, held keys and public reads | One retained `RTC_CHANGE`, empty repeat, both key-owner states and all public read boundaries passed | 5.629 / 5.920 |
| DOS normal exit | `guest_exit`, `exited`, result byte 42, final cut/revision and stable status repeat | 3.124 / 3.390 |
| DOS TSR | `guest_tsr`, `resident`, result byte 43, retained handler bytes, final cut/revision and stable status repeat | 3.090 / 3.289 |

The authored mode-13h program writes the existing RTC seconds value three times
and stops at an exact label. The actual native cut returned a singleton
`RTC_CHANGE` in `debug` state. Its original callback received that exact event
object and incremented the original cooperative revision once. The immediate
repeat was empty with the same monitor UUID, epoch and native state. This proves
delivery identity and order for **that singleton batch**; multi-event ordering
is a separate host-test result. RTC coalescing does not preserve a complete
event history.

With Shift held, and again after release with the same native owner still
attached, public status, probe, RGBA, RPC screenshot and artifact capture each
took exactly one cut before exactly one read admission. Complete native keyboard
proofs, CPU registers and virtual nanoseconds were unchanged across each read.
No read dispatched QMP continue/stop/input or GDB execution. The four frame
routes preserved one retained source identity within each phase, with matching
sparse samples and decoded PNG/indexed pixels. Three explicit source-frame
advances between phases allowed the BIOS to drain the make before release;
the reads themselves did not advance the guest.

The two DOS cases used actual EXEC-helper memory, UART and nonce verification.
Each completed during the status call inside the one public asynchronous
resume; no later polling iteration was needed. The capture epoch changed,
the final stopped cut and original-owner revision were published, and the same
QEMU process remained usable until explicit cleanup. TSR handler bytes were
also read from the real resident allocation.

All three original QEMU processes exited with return code zero. All supervisors
reported a reaped leader, absent process group, no timeout and no cleanup error.
The source map, original and prepared boot inputs and authored program identities
remained unchanged. QEMU, qemu-img, mcopy, NASM, boot image, firmware inventory
and runtime manifest were compared to their initial pins after each run.

## Evidence and limits

The companion `pending-events-verification-20261122.zip` contains only text:
the exact full JSON results, supervision and launch receipts, complete logs,
host selections and failed iterations, baseline native failure, socket setup
failures, source drivers, review delta, native source manifests and patches.
`EVIDENCE_MANIFEST.json` records every member's original path, size and SHA-256.
No guest disk, project database, object store, emulator state, native ELF,
firmware bytes or rendered guest image is included. Original full receipts
remain unchanged outside the archive.

The native **64-all-state iteration bound, overflow refusal and allocation
failure atomicity were not exercised**. Neither were native reconnect/OOB/pretty
QMP, running cuts, a late bare-event injection, malformed native wire, callback
mutation, bad DOS nonce or closed-layer DOS return. Their host tests or source
review must remain separately labeled. The empty repeat does not establish an
event-free future stream. Held-key proof stability does not establish typematic
behavior or application input consumption. Source raster and CPU state remain
non-atomic, with no application drawing-completion or legacy phase equivalence
claim. No macOS, hosted CI or release qualification is established here.
