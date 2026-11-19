# Observed QEMU executable identity

This contract covers the shared `QemuMachine` owner used by raw-PC, native DOS,
Wine and DOSBox-in-QEMU sessions. The separately implemented CHIP-8 owner is
outside this slice and retains its earlier launcher-based identity.

`runtime_inputs.qemu` keeps the selected launch path, launch-file SHA-256 and
version output. That path remains the relaunch route: wrappers can supply
runtime library and firmware configuration.

`runtime_inputs.qemu_image` records the main native image of the owned QMP
process: format `fdisbull-qemu-executed-image-1`, diagnostic path, byte size,
SHA-256 and QMP numeric version. Compatibility projections retain its SHA-256
and version as a separate top-level component. This measures the main
executable, not its loaded shared libraries.

Startup binds `query-cpus-fast` to the exact Popen owner, matches QMP and launch
versions, and hashes a bounded native image inside the inherited startup
deadline. Linux opens `/proc/PID/exe` itself, so a deleted or replaced pathname
does not substitute different bytes. macOS binds `proc_pidpath` to the mapped
vnode returned by `PROC_PIDREGIONPATHINFO` and the open descriptor's file
identity; missing or inconsistent observations refuse admission. No wrapper
layout, basename or version-only fallback qualifies an image.

The live proof keeps process birth, descriptor and inode/vnode observations
outside portable metadata. Capture and restore recheck this proof; a changed
or unavailable live producer closes and quarantines that owner. A saved
producer mismatch refuses before snapshot import and preserves the healthy
stopped source owner. A fresh destination must match before import. Wine
replacement checks its destination before retiring the old transport or
calling migration restore. States lacking an observed image are explicitly
unqualified legacy states and cannot be restored through these routes.
Cold Wine sessions pass the saved producer expectation to transport admission.
DOSBox-in-QEMU uses the shared locked capture/restore preflight for both durable
states and frame-timeline payloads, and its timeline identity retains the
portable runtime component hashes. Ordinary DOSBox has no new QEMU requirement.

## Forwarding wrappers and cleanup limits

Wrappers must `exec` the QMP process. A QMP CPU observation identifying an
owned descendant is refused. Cleanup first requests QMP quit, then uses the
captured Linux pidfd for bounded TERM/KILL if necessary. Darwin rechecks the
captured birth immediately before targeted PID signaling; unlike Linux pidfd,
that exceptional fallback has a residual PID-reuse race. No process-name or
process-group scan is used. A changed birth forbids signaling.

If QMP connection or CPU-owner observation fails before a descendant can be
identified, cleanup reaps the known Popen owner and attempts private QMP quit
when available. Arbitrary unobserved forwarded descendants remain
**unqualified cleanup**, recorded on the startup error; this slice does not
claim containment of arbitrary forwarding wrappers. Observation or cleanup
failure cannot skip known-owner reap or replace the original admission error.

Host tests exercise real native processes with byte-identical launchers and
different image bytes, deleted-image inode hashing, owner loss, legacy
refusal, fresh-destination refusal, input/control preservation, version and
deadline rejection, mapped-vnode mismatch, and captured-descendant cleanup.
Platform/runtime qualification receipts are separate from implementation.
