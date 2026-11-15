# Fresh LE admission after owned QEMU machine restore

This bounded slice adds `load_machine_state(..., rebind_protected_source=True)`.
The loader verifies the owned machine, then performs full fresh LE admission
and stopped-instruction qualification under one controller lock and deadline.
It issues a new binding ID/capture epoch. `source_binding_restored` stays false,
MZ live ranges stay retired, and old source histories/selected anchors stay
invalid. The machine archive format and default machine-only behavior are unchanged.
See the [API contract](../../DOS_OWNED_MACHINE_CHECKPOINTS.md) and
[sanitized receipt](verification.json).

Runtime `b4d74d7b2d67c3a31fc4b3ab406e4e263e5c6bc2` is packaged in a private
tool-only wheel, SHA-256 `276074a81fb5b6101103d920d7f5f293249fd723a3b33942aa0f8bce144b517e`.
All 711 runtime files match committed source, wheel and private installation.
543 selected installed host cases and 31 native cases pass with zero skips.
The native selection retains the earlier 26 preservation cases, the existing
LE fixture checks, and two new standard/virtual hot+cold source-rebind cases.
Counts describe verification, not a parity percentage.

On a verified private copy of the earlier original-Doom E1M1 checkpoint,
fresh LE admission, a new 44,410,703-byte machine capture, intervening source
stepping, exact hot CPU recovery, fresh canonical source traces, separate
Python-host cold recovery and cold query/export all pass. Each trace contains
four qualified boundaries. This is a stopped-source endpoint experiment with
`-nosound -nomouse`; it does not add a new gameplay, sound, mouse or exit claim.
Original executables, WAD and the canonical earlier FDB/CAS remain unchanged.
Concrete owned PIDs/groups are retained privately and all are empty after reaping.

Two failed native candidates remain retained. The first exposed a shared trace
guard that required the retired MZ mapping. The second exposed virtual clock
identity comparisons against launch admission. The fixes keep classic MZ guards
intact, require the exact installed LE handle/owner/epoch before each observation,
and bind restored LE clocks to the epoch-specific load/instrumentation receipt.
Malformed/stale handles, forged receipts, changed immutable facts and deadline
or publication failures are covered by refusals. Historical queries validate
bounded manifests/receipts and source proofs; they do not re-admit a native VM
or claim independent validation of the complete machine payload.

**This does not implement persisted LE source-bound checkpoints/history.**
The newer Doom-chat request explicitly adds that next seam. Reusing a cached
source flag, thawing old MZ histories or clearing the owned-machine marker would
be incorrect. Task/allocation lifetime and alias ownership remain unknown.
DOSBox-X remains default and retained. No CI, native rebuild, release, merge or
shared activation occurred. Game bytes, screens, states and FDB/CAS stay private.

Private controls/index: `/Volumes/CODEX/Codex_Projects/active/fDisBull-local-studies/QEMU-DOSBox-Parity-20261110/qemu-le-rebind-20261115/`.
Private native/game evidence: `/Volumes/CACHE/fdisbull-ci-builds/qemu-le-rebind-20261115/`.
