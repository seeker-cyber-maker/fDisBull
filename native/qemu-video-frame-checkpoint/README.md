# Instrumented source-raster checkpoints

This is a newly authored reconstruction of the source checkpoint feature over
the authenticated QEMU 10.0.13 Build03 source preimages. It is not a recovered
copy of the lost checkpoint patch. The manifest binds all six native input and
output files. Historical test reports and native producers do not qualify this
new source.

The patch adds private instrumented format
`fdisbull-instrumented-qemu-state-3`. Formats 1 and 2 retain their existing
import semantics and receipt format. Compatibility with an unknown sidecar
produced by the lost format-3 implementation is unqualified; strict field
validation rejects records that do not match this reconstructed schema.

## Retained source state

Format 3 always carries a `video-frame` record, including canonical idle when
the source observer was never started. A non-idle record carries its selected
primary VGA path, saved logical stream/frame counters and state. Observing and
stopped records also carry the exact configuration/timing generations, line and
frame periods, and DAC interpretation.

The native model remains the existing bounded 320 × 200 chain-4 source model.
Each row occupies 960 RGB888 bytes. The record keeps two independent images:

- `partial-rgb-base64` contains exactly the valid prefix, zero through 199
  rows. `partial-rows` contains exactly those ordered row receipts, and
  `partial-sha256` hashes only those bytes. Allocated but unsampled buffer bytes
  and stale timing-array entries are never exported.
- `rgb-base64` contains exactly 192,000 bytes when `info.frame` identifies a
  completed raster. Its hash and 200 row receipts belong to that retained image.
  The pending prefix cannot be presented as a completed image.

Stopped streams retain their completed image but have no partial progress or
pending timer. Every completed row and the completion timestamp must precede
or equal the recorded stream stop, even when the encompassing checkpoint was
captured later. Invalidated streams retain only their token/path/start/reason
and logical counters; their descriptor, progress and image fields are canonical
empty values. Idle has no source identity, counters, pixels or timer.

All source hashes, canonical Base64 lengths, integer domains, exact field sets,
row order and descriptor relationships are checked before native adoption.
Native import additionally checks the actual restored device and freshly
derived source descriptor. Existing clock, renderer, retrace, input, keyboard,
audio, migration and source-fence admission remain in place. The complete
instrumented sidecar retains its existing 48 MiB limit.

## Timer phase and save behavior

For physical line period H and pending raster phase boundary B, intended row r
is `D = B + floor(H/4) + 2*r*H`. H is at least 4, the frame period P is at least
400H, and P is a whole number of lines. The existing checked native arithmetic
is reused. A sampled row satisfies `D <= actual < D+H` and precedes the saved
stopped time.

`info.next-deadline-ns` remains the original intended row deadline.
`timer-expire-ns` separately stores the actual armed timer expiry A. Start and
ordinary callbacks arm A=D. A callback blocked by a real stop defers to T+1
without changing D. A later timer-disabled step can advance the stopped clock
N while leaving that earlier expiry armed. The admitted relation is therefore
`A == D` or `A > D and A-1 <= N`, with signed nonnegative times and a genuinely
pending observing timer. This subtraction form avoids overflowing N+1. The
exact A is retained and compared; import does not clamp it, rebase it, dispatch
a callback, or sample replacement rows.

After save authorization has verified the complete exported sidecar, the owned
save temporarily removes the source timer from the queue. Save completion
rearms its original expiry on either success or failure if the same source is
still observing. It does not resurrect an invalidated stream. This temporary
transaction state is private and is never accepted from a sidecar.

## Restore ownership and host readback

The snapshot retains guest CPU/RAM/device state. This sidecar restores the
native observer's logical state under a fresh native epoch and a new source
token. A copied live frame receipt uses that fresh epoch; the archived record
and any historical source-fence receipt remain unchanged. All bounded parsing,
pixel validation, source admission and allocation precede source adoption.
Source adoption is last in the native owner-restoration sequence, and a native
success receipt is published only after it completes.

The host removes startup source token/metadata/probe/RGB caches before import.
It checks the import receipt, independently queries checkpoint status, verifies
the clock/key/renderer/retrace owners through existing helpers, and separately
queries each non-idle source owner. It then obtains a complete checkpoint export
and compares all logical data after removing only the explicitly remapped
native epochs and ownership tokens. Pixels, hashes, row times, generations,
device identity, source state and both deadlines remain exact comparisons.
Only then is the new source token/metadata adopted; old probe or RGB caches are
never reused. The destination keeps its fresh host session revision and mode
lifetime.

Canonical idle also works with an instrumented profile whose precise source
VGA is disabled. The public source-query guard continues to require precise
VGA, so idle restore uses import/status plus the exact complete sidecar readback
without issuing that query or adopting any source token/cache.

For a legacy format-1/2 import, the native source becomes canonical idle.
An upgraded format-3 readback can be projected to a saved legacy comparison
only after strict validation proves that neutral source state. A format-1
comparison can omit an added key proof only when its owner is inactive, has no
held/foreign keys, and has zero ownership generation, accepted edges and
modifier state. Legitimate nonempty guest FIFO/controller bytes are retained;
an empty owner does not require an empty guest device. The archived record and
legacy receipt shape are not rewritten.

Failures in the new source/receipt/readback route close and quarantine the
uncertain destination, clear source caches again after cleanup, and preserve
the caught original error and attached result even if cleanup raises. Existing
clock/display validators retain their prior internal cleanup ordering; this
patch does not claim to repair that separate behavior.

## Source and verification boundaries

Apply this patch only to the exact six manifest preimages after the existing
instrumented checkpoint, frame-history, frame-key, audio checkpoint, source
video and source-fence chain. It is not a patch for pristine upstream QEMU.
No guest fixture, checkpoint state, binary, runtime package or recovered private
delivery is included here.

The authored host cases live in:

- `tests/test_qemu_video_checkpoint.py`: strict bounded records, independent
  images, stop-time boundaries, normal/due/deferred/retained timer phases,
  fresh receipt/query/export ownership, valid-to-valid timer mutation refusal,
  source-cache cleanup, host lifetime and off-profile idle behavior.
- `tests/test_qemu_frame_key_checkpoint.py`: format presence matrix, full idle
  key proof, legacy neutral upgrade and preserved guest FIFO state.
- `tests/test_qemu_checkpoint_controls_failures.py`: original error/result
  retention and no source adoption after uncertain restoration or cleanup.

These cases use authored host records and QMP peers. Their expected pixels and
times are declared independently from the validator, but they do not execute
QEMU or prove native continuation. The peer deliberately stubs the existing
precise-retrace admission helper and does not model a complete native audio or
off-profile retrace schema.

The host validator and restore integration have been independently reviewed.
All ten original candidate02 repository afterimages were byte-identical on
takeover. The only host correction was to the tracking test fixture: preserve
the production VM-derived read-only session identity instead of assigning the
plain fixture's identity to it. Production behavior and test assertions were
unchanged by that correction.

The selected host suite has 590 passing cases: 465 retained candidate02 results
and 125 fresh results after the fixture correction. The fresh partitions passed
96 and 29 cases with exact expected identities, no failures, errors or skips,
and unchanged host source hashes before and after execution. They used the
restored Python 3.13 runtime whose original dependency maps were verified.
The earlier fixture failure and a separate temporary-storage setup failure
remain preserved; the 590-case total combines retained and fresh evidence.

The subsequent [2026-11-22 continuation](../../docs/QEMU_CONTINUATION_2026_11_22.md)
records exact composition, QAPI processing, compilation and native execution.
Its sampled-frame trajectory has independent completed/prefix pixels, a real
retained-past expiry, successful and failed save preservation, fresh hot and
separate-process cold restore ownership, and matching future row completion.
Fresh-owner native idle format 3 and neutral schema projections of formats 2/1
also passed the unchanged host validator. These projections are not historical
producer archives. The detailed continuation record separates each qualified
result from preserved harness failures and remaining native combinations.
The earlier host peers alone do not qualify those behaviors.

The complete acceptance gate also needs stopped-time refusal, metadata-only
invalidation, idle off-profile and legacy-format combinations, while retaining
renderer/migration exclusions. Only the separately recorded native cases count
toward that gate; compilation cannot establish whole-game parity.
