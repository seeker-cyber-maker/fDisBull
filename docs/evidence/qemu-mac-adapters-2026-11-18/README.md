# Installed Mac scene and screenshot-hook witnesses

Three authored native cases passed on macOS with the privately installed wheel
from source `43bd549`. All 723 core payload files matched source, wheel and
installed prefix. The 99 pinned dependencies, test files and installed payload
remained unchanged. The finite supervisor and native test runner both returned
zero, with no skipped tests or remaining owned processes.

The two scene cases exercise actual IRQ1 make/break state and replacement-owner
checkpoint restoration. Passive observations preserve the stopped CPU, virtual
clock and caller input; restoration requires a fresh runtime-memory witness.
The screenshot-hook case verifies exact layer suspension/restoration, passive
capture and first-failure cleanup without guest execution or input release.

`verification.json` records the exact source, native Mach-O image, package,
controller and private-receipt identities. Private work directories, disks,
databases and captures are not included.

These are platform witnesses for the existing bounded adapters. Frame-backed
scenes, fresh-frame screenshot hooks, actions and workflows remain open. No
migration surface, campaign, default, release or shared activation is promoted.
