# Lossless native-state deltas in frame history

The DOS frame timeline supports `storage_mode='full'` (the compatible default)
and opt-in `storage_mode='delta'`. Both modes capture a complete native saved
state and the completed-frame PNG at every recorded point. Delta mode changes
how native payloads are retained in the live cache; it **does not avoid full
native capture, serialization, temporary-file IO or compression** at each frame.
Encoding and reconstruction add CPU work. Retained-memory savings and recording
speed are separate measurements, and either can fail to improve.

```python
debug.timeline_start(storage_mode='delta', keyframe_interval=8,
                     max_frames=120, max_bytes=64 * 1024**2,
                     max_state_bytes=8 * 1024**2, max_image_bytes=2 * 1024**2)
debug.timeline_advance(frames=8, inputs=[
    {'frame': 0, 'edges': [{'key': 'right', 'pressed': True}]},
    {'frame': 2, 'edges': [{'key': 'right', 'pressed': False}]},
])
debug.timeline_rewind(frames=3)
stone = debug.timeline_pin('selected-anchor.sav')
```

The same options pass through JSON `debug-timeline-start` and declarative script
`timeline-start`. Literal malformed options are rejected before earlier script
steps execute. `keyframe_interval` must be an integer from 1 through 128, with
default 8; an interval of 1 stores only full payloads. The interval bounds every
dependency chain to at most `keyframe_interval - 1` deltas. Full fallback and
eviction may introduce additional keyframes.

## What the delta preserves

The codec operates on the **entire opaque native serialized payload**, including
the device/hidden-state information that this backend's native state format
already covers. A full keyframe starts a chain. Later points store a bounded
zlib-compressed XOR against the preceding native payload, with explicit lengths
for growth/shrinkage. Each descriptor binds the base point, base/result lengths
and SHA-256 hashes, payload hash, codec version and dependency depth. A separate
descriptor hash guards those fields. A delta is retained only if its payload
plus complete descriptor is smaller than the original native payload;
otherwise that point becomes a full keyframe.

Before native restoration or durable pinning, the timeline checks the bounded
chain, all relevant checkpoint/image envelopes and every decoded native hash.
The materialized bytes match the recorded native payload exactly. Pinning emits
an ordinary full **Anchor Stone** compatible with existing save/load formats;
the live delta representation is not a new portable state format. Full payloads
are not secretly retained in delta points. PNGs and native checkpoint metadata
are still retained in full.

This is separate from [selected CPU/RAM deltas](CPU_RAM_DELTAS.md), whose partial
state cannot establish complete native restoration. The serialized-state codec
does not expand backend support, make host files roll back, or establish any
greater whole-machine coverage than the existing native save-state mechanism.
Native states are compressed ZIP containers: small guest changes can shift many
serialized bytes, so compact CPU/RAM changes need not produce compact native
payload deltas.

## Eviction, branching and failure

Eviction promotes a dependent successor to a verified full keyframe before
discarding its base. Following descriptors receive new retained-chain depths
without changing their native bytes, original context envelopes or point IDs.
Speculative reservation uses replacement point objects, so a refused preflight
retains the prior branch and future unchanged. Branching removes abandoned
future points and encodes the new future from its selected retained base.

Corrupt or missing bases, mismatched descriptors, hashes, oversized lengths,
excessive chains, malformed compression, trailing compressed data and excessive
decompression output are refused before a cached state can mutate the guest.
The selected dependency chain is also checked before recorded forward work.
An uncertain failure after input/frame execution still closes the owned session
through the existing guard. Codec work checks the shared operation deadline
before and after encode/decode phases.

The existing [RNG preservation policy](FRAME_INPUT_TIMELINE.md#restoring-or-preserving-rng)
is unchanged. It reads the declared current bytes, restores the exact native
point, overlays and verifies only those bytes, and preserves mixed-state
provenance. Without explicit partial-resume permission that state is frozen.
Delta encoding cannot clear the freeze or mark a derived mixed point safe.
Returning to a complete trusted point or Anchor follows the existing recovery
path. Held keyboard ownership, released-mouse requirements, dirty-input
cancellation, mounted-file identity and backend admission guards remain in force.

## Accounting and benchmarks

`timeline_status()` exposes:

| Field | Meaning |
| --- | --- |
| `storage_mode`, `keyframe_interval` | Selected retention mode and chain bound |
| `full_state_points`, `delta_state_points` | Currently retained full/delta point counts |
| `retained_encoded_state_payload_bytes`, `state_payload_bytes` | Actual retained full and compressed-delta payload bytes, excluding descriptors |
| `retained_delta_descriptor_bytes` | Explicit retained delta descriptor bytes |
| `reconstructed_state_payload_bytes` | Sum of the complete native payload sizes represented by those points |
| `state_bytes_used` | Retained encoded payloads, descriptors and native metadata |
| `image_payload_bytes`, `image_bytes_used` | Full PNG payload and image-metadata accounting |
| `bytes_used` | State, image and input-journal logical retained bytes |
| `raw_checkpoint_limit_bytes` | Independent complete-checkpoint admission bound |
| `codec_transient_bound_bytes` | Conservative codec workspace bound including overlapping current capture/reconstruction and metadata: six maximum raw payloads plus 8 MiB and four 64 KiB blocks; zero when full mode uses no delta codec |
| `codec_stats` | Cumulative encode/materialization counts, encode time, materialization/verification/decode time, and individual delta decode count |

Each point also reports `checkpoint_sha256`, raw `checkpoint_size`,
`image_sha256`, `encoded_state_size`, `storage_kind` and `delta_depth`.
`captures_used` still counts **full native captures**, including the initial
point. `codec_stats` fields are `encode_count`, `encode_elapsed_ns`,
`materialize_count`, `decode_elapsed_ns` and `delta_decode_count`. Materialization
time includes chain/hash validation, including full points; it is not solely
decompression time. Preflight, promotion and pinning can also materialize points,
so benchmark per-operation differences around declared phases rather than
assuming one decode per rewind.

The cache's logical byte budget excludes transient codec workspace, native
emulator/serialization memory and Python allocator overhead. Raw capture and
decoded-PNG limits remain independent; these accounting fields are not a total
process-memory guarantee or filesystem-allocation measurement.

Compare full and delta modes using the same backend, prepared Anchor, input plan,
frame count and observed CPU/RAM/PNG projection. Verify each pinned payload
against its own cached native hash. Independent native captures can contain
different ZIP timestamps, so their container hashes need not match across arms.
Report full-capture counts, encode/decode work, retained encoded bytes, temporary
workspace limits, whole recording latency and rewind latency separately. Existing
JPC-RR versus DOSBox scene, input-spacing, observer and frame-boundary differences
remain material; this storage option does not normalize those tasks.

Native states, deltas, databases and raw runtime receipts remain private and
outside Git. The live history ends with its owning session; restart preserves
pinned full Anchor Stones and exported stored images, not the live delta chain.
