# Persisted LE source checkpoints and stopped capture history

The native `qemu-dos` backend now saves a qualified stopped LE source descriptor
joined to an exact full owned-machine checkpoint. Restore re-admits source and
compares saved canonical instruction/location, object placements, GDT and CPU
before atomic completion events or recovery attestation. It issues a new handle
and capture epoch, retains `source_binding_restored=False` and retired MZ ranges,
and reports `le_source_checkpoint_restored=True`. This is a stopped LE relation;
`lifetime_qualified=False` remains explicit. See the
[API contract](../../DOS_LE_SOURCE_CHECKPOINTS.md) and [sanitized receipt](verification.json).

The separate capture-only history provider persists immutable full-checkpoint
DAG revisions, operation intents, exact node references and full machine+companion
charges. External gameplay is an unobserved interval. Cold attachment creates no
live connection or recording lineage: an explicit node restore must earn those
before another capture. Existing MZ histories, frame histories, trials, selected
undo, layers/hooks and IRQ contracts keep their formats and guards.

## Exact local package and checks

Runtime `531d405f01158ad0b064c5b3683f4239065d4fe0` is packaged as a private tool-only
wheel, SHA-256 `b70be8f4feb0bd432ba88d34f571d1b6cfb38946012b662f8f0c97180974b274`.
All 713 runtime members match committed source, wheel and private prefix.

- 613 selected installed host cases pass with zero failures/errors/skips.
- 33 native-suite cases pass: 32 exercise native routes; one is a fixture
  assembly/structure check. Both new standard/virtual LE source checkpoint/history
  cases execute native routes, including hot/cold restore and a retained branch.
- The selection retains prior DOS/CHIP-8 histories, frames, trials, selected undo,
  task-private layers, hooks, RNG, full checkpoints, IRQs and ordinary workloads.

Counts describe verification and do not measure a parity percentage. The lineage
review correction is retained as the separate preceding candidate `3956523d`;
that candidate was packaged but was not used for native acceptance.

## Actual original-Doom A/B qualification

A new private qualification project imports the exact earlier 29,271,726-byte
E1M1 machine archive (SHA-256 `7975550c822161f2a7c8e6fd75df073dc149552b28b5316214424b52d1dfd079`)
and its original workspace/run dependency lineage. Previous projects and all
original bytes are preserved. Initial preparation correctly refused a missing
workspace dependency; retaining its original referenced artifacts resolved that
input issue before any guest launch.

With `-nosound -nomouse`, the test saves an explicit LE checkpoint A and a history
root A, then uses physical Up/Right input with 200 ms virtual-clock intervals to
reach a different CPU state and image B. It records B in the two-node capture
history. Hot explicit-A loading and both A/B history restores reproduce the
saved exposed CPU, canonical source site and exact PNG under new owned processes,
binding IDs and capture epochs. The history charge is 135,644,192 bytes; the
256 MiB project runtime-artifact cap is unchanged.

A separate Python host reopens the closed project. Attachment has no live cursor;
explicit A loading and both history-node restores re-earn proof and reproduce
the same CPU/site/PNG. Six new source traces qualify and query after closure;
companion, linked machine and history exports match exact retained bytes. A trace
contains one stored pre-instruction boundary and one attempted debugger step
interval, with no instruction-retirement claim.

All nine QEMU process handles exit with code zero and both owned groups are
freshly checked empty. Original delivery bytes, the executed EXE/WAD copies,
the native kit, private prefix and previous R4/R5 evidence remain unchanged.
The hot memory supervisor completed with an exit-time group-identity advisory;
process absence uses the independent handle/group receipts, and the subsequent
guarded cold run completed cleanly. Supervisor status/advisory is retained only
as parent-observed tool output, without a separate raw guard receipt. No guard
hold was cleared or bypassed.

## Independent closed-copy public readback

A separate reader verifies a copied, closed database and its actual copied CAS
root, without opening the canonical Project or launching a guest. It checks 24
exact Python exports: three LE companions, three linked machines, two history
manifests, six traces and ten PNGs. Six state inspections, six cold source queries
and 126 loaded module origins/hashes match the exact runtime. A fresh CLI also
returns five successful JSON replies: two LE inspections, two overlapping exact
exports and one source query. Canonical DB and all 574 immutable objects stay
unchanged. Both reader receipt hashes are in the sanitized verification record.
An earlier reader-harness query used the wrong documented parameter name; its
failure and exports are retained separately from the corrected successful run.

## Refusals and remaining gates

Creation/admission/binding/joint-capture receipts prevent mixing individually
valid source and machine states from different captures, even with equal CPU
and capture epoch. Expected-source mismatches and late/publication failures
cannot publish a valid history cursor or clear a partial-undo freeze. Failure on
the second load-completion event rolls both completion events back. Review also
closed the cold-attach recording bypass before admission or intent.

This is capture-only stopped history, with no continuous step/replay, LE frame
history, LE trial or LE selected-undo claim. Task/allocation lifetime, aliased or
active layered source ownership, broader sound/mouse/device/media/timing,
portable delivery and full DOSBox-X parity remain open. DOSBox-X stays default
and retained; DESQview remains deferred unless it blocks ordinary DOS. No CI,
native rebuild, release, merge or shared activation occurred. Commercial game,
state, screen and FDB/CAS bytes remain outside Git and tool packages.

Private controls: `/Volumes/CODEX/Codex_Projects/active/fDisBull-local-studies/QEMU-DOSBox-Parity-20261110/qemu-le-source-history-20261115/`.
Private evidence: `/Volumes/CACHE/fdisbull-ci-builds/qemu-le-source-history-20261115/`.
