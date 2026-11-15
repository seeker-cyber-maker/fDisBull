# Bounded owned-machine recovery for ordinary protected DOS

Original Doom now has a local public path through fresh E1M1 gameplay,
movement, machine capture, intervening movement, exact hot recovery, recovery
in a separate Python process, and a later normal DOS exit from that same
checkpoint. This uses `-nosound -nomouse`, without LE binding, IRQ-mask changes,
direct guest-code/RAM/register edits or an injected initial prepared state.
**DOSBox-X remains default and retained. Full 1:1 replacement parity is open.**

The [sanitized receipt](verification.json) binds the exact runtime, wheel,
checks and private raw receipts. Original game files, images, VM states and
FDB/object-store data remain private.

## Delivered contract

The explicit [owned-machine API](../../DOS_OWNED_MACHINE_CHECKPOINTS.md) adds
`save_machine_state` / `load_machine_state`, live JSON and saved-script routes,
and offline inspection. Its separate `machine-state` kind and
`fdisbull-qemu-owned-machine-qcow2-v1` archive do not enter `PROCESS_FORMATS`.
Ordinary `save_state`, histories, trials and source-bound anchors retain their
stronger allocation/source checks.

Restore verifies a fresh owned machine, the complete private writable disk,
CPU/address state, architectural RAM witnesses, helper channel and supported
native sidecars before replacing the owner. It retires the original MZ live
ranges, LE handle and runtime tracker, advances epochs and reports
`source_binding_restored=False`. A later TSR return cannot revive those ranges.
Supported explicit native layers and linear hooks survive; source/task-private
controls and active provenance/scheduler owners refuse in this mode. Their
existing source-bound paths remain separate.

Full recovery completion now holds the stable machine lock through verification
and undo completion. Private invocation-bound attestation prevents a Boolean,
copied result, stale owner, expired deadline or queued caller from thawing a
partial undo. Cleanup failures preserve the primary snapshot/control/hook/layer/
instrumentation diagnosis and quarantine an uncertain owner.

## Actual Doom observations

- Strict source `save_state` still refuses with
  `DOS process allocation ownership changed`. CPU, cached process, PID and
  source-state count remain unchanged. No ownership comparison is weakened.
- The new machine artifact is **29,271,726 bytes**, SHA-256
  `7975550c822161f2a7c8e6fd75df073dc149552b28b5316214424b52d1dfd079`.
- Physical forward movement after capture changes both the observed CPU
  endpoint and screen. Hot restore reproduces the saved CPU and exact PNG,
  installs a fresh owner/epoch and reaps the prior owner.
- After closing the original Project/session, a **separate Python process**
  reopens the project, launches a fresh entry owner and restores that artifact.
  CPU and screen match exactly; a subsequent 100 ms virtual advance succeeds.
- A separate bounded continuation restores the same archive, follows inspected
  Escape/Q/Enter/Y input, then supplies an additional Enter with a budget of up
  to one second while shutdown is still active. The nonce-bound parent callback reports
  **`guest_exit`, normal DOS code 0**, no resident allocations and retired
  source ranges. The final operation stops after 51,760,000 ns: its keydown
  callback dispatches and its release is cancelled at guest stop. No complete
  final key cycle, guest consumption or exclusive causal role is inferred.
- All owned guests close/reap, no owned processes remain, and original inputs,
  copied native runtime and frozen Python prefix remain unchanged.

The exit continuation retains process-handle and group-emptiness checks, but
does not retain its concrete PIDs/PGID. The earlier recovery/cold receipts do;
their identities are not substituted for the exit job. Return classification
is retained through the verified helper path and derived controller receipt;
the raw TERMINATED packet is not retained.

The successful recovery trial's input window ended after selecting Quit; it
does not claim an exit. The separate continuation supplies the actual exit
evidence. These are bounded composed gates, not a whole-game completion or
source-lifetime proof.

## Qualification and retained failures

Runtime commit: `01d5c891c988916e964b049750211c5c32120a1f`.
Tool-only wheel SHA-256:
`d6b5226a3f0a81cf13baf109644b036fb00fe478d7d400bb3e3e069ab54b544c`.
All **711 runtime payload files** match committed source, wheel and private
installation. The existing native QEMU and firmware are reused.

**397 host cases and 26 native cases pass, zero skips.** Three new native
cases prove real AH=4Ah allocation shrink, open-handle AA-to-BB disk rollback,
CPU/RAM changes, physical/linear fetch and RAM layers, linear hooks, hot and
reopened-project recovery, exit/TSR source retirement and return to an original
strong source checkpoint. The instrumented case restores nonconstant speaker
PCM, display pixels, clock/icount, retrace and held-key FIFO ownership under
fresh tokens; BIOS consumption and release are observed after restoration.
The other 23 native cases preserve the existing history/trial/selected-undo/
frame/task-private-layer/hook/RNG/checkpoint/IRQ and ordinary file/workload gates.
Counts describe verification, not completion percentages.

An independent fresh Python host opens a verified copy of the closed project
and object store, validates the new format and exports the archive plus 14
stored images exactly. Three public JSON replies additionally validate state
inspection and two exact exports. No guest starts, the canonical Project is
not opened by the reader, and the canonical database and 479 object files stay
unchanged. Receipt hashes are included in the sanitized verification JSON.

Failed trials remain retained. The first instrumented fixture attempted a key
release while its interrupt-disabled guest could not drain the make code; an
authored STI/BIOS-consumption variant corrected that test. An earlier Doom trial
ended at its operator input limit. A later real capture exposed a publication
bug: the new artifact kind inherited the generic 16 MiB ceiling. It now shares
the existing state limit of 128 MiB, with real boundary/readback tests; other
kinds retain 16 MiB and the project aggregate remains 256 MiB.

Protected LE source-bound checkpoint/history continuity, broader audio/mouse/
device/media/timing compatibility, portable delivery and the older strict
DOSBox-X ATTT cold-reference display gap remain open. DESQview completion stays
deferred unless it blocks ordinary DOS. No CI, native rebuild, release, merge,
default switch or shared activation was performed.
