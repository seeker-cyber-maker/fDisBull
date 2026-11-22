# Pending stopped monitor event extension

`qemu-10.0.13-fdisbull-pending-events-v1.patch` adds the private no-argument
`x-fdisbull-take-pending-events` command on the recovered QEMU 10.0.13 Build03
source. It changes six existing paths; `source-manifest.json` records the exact
before/after lengths and hashes. Apply with `-p1` only after confirming those
preimages. Compose other native source layers against their declared inputs.

Patch SHA-256:
`21456f65382c20ef9c63bc74b115cc7fa415df77dd9856a242b7e162cb18f2b6`.

The patch is a new source reconstruction. Its original source-only manifest is
separate from the later [native qualification](../../docs/QEMU_PENDING_EVENTS_VALIDATION.md):
the corrected producer compiled and passed four monitor controls plus three
real RTC/frame/status/DOS-return cases. Held and released-but-attached durable
keys were exercised. The 64-total-state boundary including null entries,
permanent overflow refusal without consumption, allocation failure and wider
armed/retired-armed combinations still require separate native probes.

The command validates the full selected list and allocates result references
before consuming retained dictionaries. It adds no input mutation or guest
execution. Held keys alone are compatible with eligibility. The matching
response is a finite batch boundary and cannot establish a quiet stream,
complete event history or causation order.

See [the host contract](../../docs/QEMU_PENDING_EVENTS.md) for exact schema,
wire and event bounds, callback identity rules, frame admission, status and
verified DOS return sequencing, and the limits of authored host tests.

The monitor layout permits the sole original stdio QMP frontend plus the
noninteractive HMP frontend that the system GDB stub always creates internally.
The exact `chardev-gdb` type and its internal class flag are both required;
externally addressable HMP and second-QMP frontends remain ineligible. Active
GDB/HMP command gates are unchanged. The original source-only patch
`d653f67bcbd03eb5b05d10dd07fbb7bb9c63ee0f886904ee7a0363f89c3bc0a5`
incorrectly treated this ordinary internal GDB frontend as an extra monitor.
