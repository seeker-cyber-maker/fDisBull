# Bounded stopped-surface screenshot hooks

QEMU DOS screenshot hooks now support an explicit stopped-surface profile (`require_fresh_frame=false`). Preparation and cleanup plans are validated together before effects. Passive reads, assertions and typed layer transitions share the capture owner, epoch, lock and deadline. Raw `capture_surface` remains a direct passive operation.

The independent host gate passed 37 cases, including three regressions found during review: closed-owner handling, a deadline expiring during final event publication, and preserving a raw capture when later grid derivation fails. The integrated selection passed 273 cases with six explicitly unrun legacy native cases.

One authored native mode-13h COM case passed on exact integrated source. It observed the base RAM value with a layer suspended, captured the stopped surface, and restored the exact layer stack. CPU registers, instruction count, virtual clock and a caller-owned keyboard hold remained unchanged. A failing preparation assertion prevented subsequent preparation and capture while cleanup restored the layer stack. The owner was reaped.

The [verification receipt](verification.json) preserves the native result and a separate post-test exporter failure. Read-only receipt extraction recovered the evidence without a native rerun. Execution hooks, fresh completed-renderer frames and whole migration qualification remain open.
