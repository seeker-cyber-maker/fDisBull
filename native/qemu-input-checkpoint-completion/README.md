# Completed native input and instrumented checkpoints

This incremental QEMU 10.0.13 patch fixes a narrow N24 checkpoint-admission
failure. A completed physical keyboard press retains its descriptor so its
timed make/break receipt remains inspectable. N24 mistook that descriptor for
pending work and refused an instrumented checkpoint after all edges had been
dispatched. It made the same mistake in the input-owned migration-blocker
exception. Press/type/click and retrace/motion descriptors are retained metadata,
while the owned batches, next-step queues and timer are the pending work.

The new predicate admits retained metadata only when input state is
`DISPATCHED`, both terminal and dispatch markers are present, and all actual
pending queues/batches/timer are empty. Press/type/click descriptors additionally
require `dispatched_count == event_count`. It continues to reject invalidation,
`ARMED`, `FAILED`, and retained incomplete `CANCELLED` descriptors. Descriptor-free
legacy quiescent cases remain admitted. The same predicate guards checkpoint
safety and bypass of **only the exact input-owned blocker** during an instrumented
checkpoint; ordinary migration is not enabled.

The patch does not change event dispatch, delete the completed receipt, replay
input, synthesize releases, or claim the guest consumed the input. The selected
PS/2 handlers were called synchronously; any guest-visible device queue state
remains ordinary serialized machine state. Host lease/pending-input admission
and the separate clock/audio/display/frame guards remain in force.

## Parent and candidate boundary

Apply this patch only over the exact source chain in the adjacent
`source-manifest.json`, ending at
[`native/qemu-dos-save-stop`](../qemu-dos-save-stop/source-manifest.json). Dry-run
and check the declared before-file hash before applying it to a new candidate.
Only `system/fdisbull-input.c` changes. QMP input API 1 and VMState layouts are
unchanged. The resulting executable still has a new binary identity: no
cross-binary checkpoint compatibility is claimed, and accepted N24 remains
retained for its existing checkpoints.

The local candidate was produced by copying the existing N24 object/generated
build inputs into a private CACHE directory, compiling just the candidate C
file, replaying the recorded target linker command, then replaying the macOS
resource wrapper command. It used the accepted source headers and resource as
read-only inputs. It ran no configure, generators, default Ninja build, CHIP-8
build or DOSBox-X build. Exact commands, relocation adaptations, logs, durations,
source/object/binary before/after hashes and the frozen output are recorded in
the private build receipt referenced by the manifest.

The one-object compile/link/wrap commands completed locally on macOS arm64;
their elapsed time is a bounded incremental-build observation, not a clean-build
benchmark or guest-performance claim. All recorded accepted N24 inputs remain
byte-identical.

The separate root-owned native check now demonstrates an original ATTT round:
four physical moves, a full mid-round save, reversible assisted RAM-layer edit,
owner/FDB close and reopen, cold restore, two repeated winning outcomes from
the same checkpoint, native winning-screen PNG export, a new round and actual
DOS exit code 0. Armed input still refuses both public and native checkpoint
export. Existing audio/display migration blockers and COM/MZ virtual mid-program
restore checks also pass. The private workflow receipt and five-case XML are
named in the manifest. Completed keyboard input is the exercised path; other
retained descriptor kinds and broad game/timing compatibility are not newly
qualified by this result.

No CI, release, installation or backend-default change is part of this package.
DOSBox-X remains the default and retained fallback.
