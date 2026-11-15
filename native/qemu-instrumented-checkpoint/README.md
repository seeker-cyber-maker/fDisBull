# Native instrumented process checkpoint

This native QEMU extension is intended to sit on the existing 13-patch
`checkpoint-status-runtime/qemu-10.0.13` source stack. The extension adds a
bounded sidecar for fDisBull's process-local clock, audio, display and VGA
retrace instrumentation. QEMU's internal snapshot remains responsible for
guest CPU, RAM and device state. The sidecar is versioned as
`fdisbull-instrumented-qemu-state-1`; it is not a replacement for the VM
snapshot.

The source manifest and patch should pin the 13-patch prerequisite stack, this
extension, and the hashes of every changed source member. Keep the QEMU source,
build products, emulator binary and private runtime inputs outside this
checkout. Preserve the upstream QEMU license and notices when distributing the
authored patch or source archive.

## QMP operations

The local host checkpoint adapter uses five private QMP commands:

| Command | Purpose |
| --- | --- |
| `x-fdisbull-instrumented-checkpoint-export` | Validate eligibility and return a bounded serialized sidecar, its SHA-256 and a one-use save token. |
| `x-fdisbull-instrumented-snapshot-save` | Start a scoped internal snapshot save for the authorized token. The wrapper only admits the fixed `disk0` VM-state/device selection. |
| `x-fdisbull-instrumented-snapshot-load` | Start the matching scoped internal snapshot load and guard the stopped restore sequence. |
| `x-fdisbull-instrumented-checkpoint-import` | Import the sidecar after snapshot load, bind restored observers to a fresh native epoch, and return the new ownership receipt. |
| `x-fdisbull-instrumented-checkpoint-status` | Report the current native ownership receipt for host verification. |

The save authorization is single-use and bound to the exported state. Save
eligibility is checked again immediately before the native snapshot operation.
The load wrapper keeps the machine stopped while guest state is restored and
the sidecar is imported. The host adapter compares the re-exported state to the
saved sidecar after restore, allowing only the intentionally fresh owner
identities and stopped-state class to differ.

## Eligibility and migration behavior

Checkpoint operations require a stopped, single-vCPU TCG machine and a
quiescent supported instrumentation profile. The host must release scheduled
input and stop host clock synchronization before capture. A native input
schedule or pending/armed clock budget is not serialized as a new owner; it
must be resolved before checkpointing. Host synchronization state and native
input ownership are not restored by this sidecar.

Ordinary QEMU migration blockers remain in place. The scoped save path may
temporarily allow only the exact blockers owned by the fDisBull clock, audio,
display and retrace extensions, and only for the authorized local snapshot
save. It does not globally bypass migration blockers or ignore unknown device
blockers. Generic migration remains blocked for unsupported state.

Audio state includes the bounded captured PCM prefix, PC-speaker oscillator
state, the supported mixer/backend queue contents, and the native audio timer
deadline needed to rearm the speaker after PIT state has loaded. The export
and save paths call a read-only audio eligibility gate. It admits virtual-only
operation without configured audio; otherwise it requires the supported
fdisbull-pc, 32 kHz mono graph and serializes its bounded queue state. It
refuses unsupported graphs, extra voices, resampling states and backend
buffers that cannot be represented safely. The gate does not flush audio,
advance the guest or manufacture a checkpoint boundary.

## Scope limits

The sidecar is a process-local instrumentation continuation mechanism for the
listed observers. It does not serialize host clock synchronization, pending
input schedules, arbitrary QEMU host state or all possible audio backend
graphs. A successful restore creates a new observer ownership epoch and fresh
tokens. The owning DOS process envelope verifies process identity separately.
The observer sidecar establishes no
general DOSBox parity, game compatibility, full audio waveform equivalence,
or broad checkpoint portability claim. Unsupported profiles or unrepresented
state must remain blocked or be rejected before save/import.
