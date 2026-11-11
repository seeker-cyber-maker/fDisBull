# Native stopped frame-key ownership

This patch adds an opt-in QMP owner for bounded PS/2 key make/break edges on a
stopped x86 TCG machine. The owner records which QCodes it holds, applies an
atomic generation-checked edge batch to the selected PS/2 keyboard, and exposes
the PS/2 FIFO and i8042 state needed to verify checkpoint continuity.

## QMP flow

1. Query `x-fdisbull-query-frame-keys`. The query is observational and does not
   initialize ownership. It requires the supported stopped virtual-clock
   profile and reports the selected keyboard/controller proof.
2. Apply the first edge batch with a fresh token and the generation just queried
   (zero in a fresh process, possibly nonzero after detach) using `x-fdisbull-apply-frame-key-edges`. Later batches use the returned
   token and generation. All edge validation, handler identity checks, and
   conservative FIFO-capacity checks happen before dispatch. The first batch
   publishes the owner only after the exact captured keyboard handler accepts
   the callbacks. Stopped dispatch calls that revalidated handler directly;
   QEMU's ordinary send wrapper intentionally drops events while paused.
3. Query again to verify the held set and device state. A foreign keyboard
   event while ownership is active invalidates the owner. Do not continue after
   an invalid receipt.
4. Export and restore through the instrumented checkpoint API. State format 2
   records the held QCodes and a canonical device/FIFO/controller proof. Restore
   checks the VMState-restored PS/2/i8042 state and adopts a fresh owner token
   for the new clock epoch. It does not send the key edges again.
5. Use `x-fdisbull-detach-frame-keys` only after every owned key is released.
   Detach uses the current token and generation, advances the generation, and
   leaves the accepted-edge counter intact. Ordinary physical input can resume
   after a successful empty-owner detach.

The commands are:

- `x-fdisbull-query-frame-keys`
- `x-fdisbull-apply-frame-key-edges {token, expected-generation, edges}`
- `x-fdisbull-detach-frame-keys {token, expected-generation}`

`FdisbullFrameKeysInfo` reports active/valid state, epoch, generation, sorted
owned and foreign held sets, edge count/capacity, selected device identity,
modifier and scan configuration, FIFO cursors/count/hash, controller state,
and throttle deadline. `fifo-sha256` hashes explicit serialized values rather
than C structure padding. The checkpoint sidecar includes this proof and the
held set, while the native VMState carries the actual keyboard/controller
state.

## Bounds and limits

- One stopped virtual-clock TCG vCPU. The native dispatch helper admits
  `PRELAUNCH`, `PAUSED`, and `DEBUG`; it never dispatches while running.
- Exactly one realized PS/2 keyboard handler attached to ISA i8042.
- At most 32 edges in one batch, at most 64 held keys, and no more edges than
  the conservatively available PS/2 FIFO capacity: two edges when the FIFO and
  i8042 output are quiescent, zero otherwise.
- Explicit key transitions only. Typematic repeat is unsupported and the
  receipt reports `repeat-supported: false`.
- Scheduled/failed input plans cannot overlap the owner. External keyboard
  events invalidate an active owner. Generic migration is blocked while keys
  are owned; use the instrumented checkpoint path.
- New exports use checkpoint format 2. Format 1 remains accepted under its
  legacy constraints; cross-binary restore is not qualified by this patch.
- This does not qualify host keyboard leases, arbitrary input backends,
  DOSBox-X behavior, non-x86 targets, or full input-device parity.

## Build

The patch is incremental over the N20 renderer-history runtime. The source
manifest records the prerequisite patch, all changed-file hashes, exact build
profile, and candidate binary hash. Rebuild only in an isolated QEMU source and
build directory; do not edit the sealed N20 source.

From the `frame-keys-runtime` directory, the configured x86_64-softmmu TCG
build used:

```sh
TMPDIR=<frame-keys-runtime/tmp-n21> \
  /Users/tiga/miniconda/bin/ninja -C build-n21 -j4 qemu-system-x86_64
```

The configure invocation and final binary identity are in
`source-manifest.json`.

## Qualification status

The patch author did not run guests or CI. Root-owned native checks have
verified the BIOS path, stopped key dispatch, held-key checkpoint restore and
release, schedule/branch behavior, native generation/capacity guards, Python, JSON
and script routes, private IRQ checkpointing, and legacy detach behavior.
The corrected root-owned native suite passed all 14 cases in
`R/frame-keys-native-corrected.xml` (24.88 seconds). This is bounded local
evidence, not hosted CI or cross-platform qualification.
