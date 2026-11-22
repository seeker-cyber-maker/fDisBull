# Pending stopped monitor event extension

`qemu-10.0.13-fdisbull-pending-events-v1.patch` adds the private no-argument
`x-fdisbull-take-pending-events` command on the recovered QEMU 10.0.13 Build03
source. It changes six existing paths; `source-manifest.json` records the exact
before/after lengths and hashes. Apply with `-p1` only after confirming those
preimages. Compose other native source layers against their declared inputs.

Patch SHA-256:
`d653f67bcbd03eb5b05d10dd07fbb7bb9c63ee0f886904ee7a0363f89c3bc0a5`.

The patch is a new source reconstruction, not a recovered historical binary
or acceptance receipt. Its manifest records no QAPI generation, compilation,
or native execution. Fresh build and finite native behavioral probes remain
separate obligations. In particular, validate 64 total throttle states
including null entries, permanent overflow refusal without consumption,
held and released-but-attached durable keys, timers and coalescing, original
monitor lifetime, and unchanged armed/retired-armed stopped-control refusal.

The command validates the full selected list and allocates result references
before consuming retained dictionaries. It adds no input mutation or guest
execution. Held keys alone are compatible with eligibility. The matching
response is a finite batch boundary and cannot establish a quiet stream,
complete event history or causation order.

See [the host contract](../../docs/QEMU_PENDING_EVENTS.md) for exact schema,
wire and event bounds, callback identity rules, frame admission, status and
verified DOS return sequencing, and the limits of authored host tests.
