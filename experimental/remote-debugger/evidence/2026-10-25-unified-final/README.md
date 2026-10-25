# Final shared-controller correction and source acceptance

This receipt follows the sealed `../2026-10-25-unified/` milestone. Earlier
screenshots, traces, runtime metadata and test reports remain unchanged, and
all their recorded checksums were verified before writing this follow-up.

The final review found a race between an outer-machine pause and a queued
request to the guest debugger. The pause check now occurs under the shared
machine lock. A deterministic test demonstrates failure of the previous code
and verifies that current code sends no guest bytes and preserves the VM.

Fresh checks on the final source:

| Gate | Result |
| --- | --- |
| Focused Linux snapshot, exact current release-file hashes | 45 passed, 15 optional native skips |
| Real DOS/QEMU workflow, boot contexts and lock contracts | 16 passed, no skips; 1 previously qualified PE native case deselected |
| Freshly installed final wheel, real boot plus contracts | 50 passed, 10 optional native skips |
| Tool package exclusions and source-byte readback | Passed: 84 wheel, 205 ZIP and 213 sdist entries |

The earlier full ordinary Linux snapshot passed **812 tests with 45 skips**;
the earlier IDA/Wine native gate passed **4**, and the custom Wine native gate
passed **13**, without native skips. The final correction changes one host
transport-lock check and its regression test; no guest resources or Windows
feature engines changed. Exact source deltas and the earlier gates are retained
in `verification.json`, so these are not presented as one fresh full-suite run.

The full DOS native state/layer/watch/grid/input/restart workflow was rerun
after this correction. The actual DinoPark replay, bank screenshot and 512
fetch records remain under `../2026-10-25-unified/dinopark/`. The final requested
DOS fetch record is pending execution; machine/PE trace records confirm steps.

All owned emulator processes exited. Game files, states, databases, vendor
executables/keys and runtime images remain excluded from public source and tool
packages. These are local, uncommitted changes on `main`, with 0.13.0 package
metadata retained for audit builds. No push, tag, hosted CI, release or delivery
was performed. See `docs/UNIFIED_DEBUGGER.md` for usage and explicit limits.
